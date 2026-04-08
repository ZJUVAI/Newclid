import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from newclid.training.grpo_rewards import AuxEvaluationResult


def load_module(path: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, Path(path))
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class StubEvaluator:
    def evaluate(self, completion, fl_problem):
        mapping = {
            "greedy_good": AuxEvaluationResult("aux1", True, True, "solved", None, 1.0),
            "sample_solved": AuxEvaluationResult("aux2", True, True, "solved", None, 1.0),
            "sample_unsolved": AuxEvaluationResult("aux3", True, True, "unsolved", None, 0.25),
            "sample_invalid": AuxEvaluationResult("aux4", True, False, "build_invalid", "build_definition_error", -0.25),
        }
        return mapping[completion]


class TestGRPODataSelection(unittest.TestCase):
    def setUp(self):
        self.analyze_dataset = load_module("scripts/analyze_dataset.py", "analyze_dataset")
        self.build_candidate_pool = load_module("scripts/grpo/build_candidate_pool.py", "build_candidate_pool")
        self.label_difficulty = load_module("scripts/grpo/label_difficulty.py", "label_difficulty")
        self.select_debug_set = load_module("scripts/grpo/select_debug_set.py", "select_debug_set")

    def test_annotation_helpers(self):
        query = "<problem> a : ; b : perp a b b c [001] ; ? eqratio a b c d </problem>"
        output = "<aux> x00 g : coll a b g [002] ; </aux><proof>...</proof>"
        record = {
            "llm_input_renamed": query,
            "llm_output_renamed": output,
            "fl_problem": "a b c d = quadrangle a b c d ? eqratio a b c d",
        }
        annotation = self.analyze_dataset.annotate_record(record, "sample:0")
        self.assertEqual(annotation["sample_id"], "sample:0")
        self.assertTrue(annotation["has_aux"])
        self.assertEqual(annotation["aux_segment_count"], 1)
        self.assertEqual(annotation["aux_points_total"], 1)
        self.assertEqual(annotation["goal_predicate"], "eqratio")
        self.assertIn("ratio_family", annotation["predicate_family_tags"])
        self.assertIn("parallel_perp_family", annotation["predicate_family_tags"])

    def test_annotation_counts_on_real_dataset(self):
        annotations, summary = self.analyze_dataset.annotate_jsonl(
            Path("datasets/test_new_construction/geometry_clauses10_samples10.jsonl")
        )
        self.assertEqual(len(annotations), 110)
        self.assertEqual(summary["aux_rows"], 34)

    def test_candidate_pool_keeps_only_valid_aux_rows(self):
        rows = [
            {
                "sample_id": "a",
                "query": "q",
                "fl_problem": "p",
                "response_aux": "<aux> a </aux>",
                "has_aux": True,
                "aux_segment_count": 1,
                "aux_points_total": 1,
                "goal_predicate": "eqratio",
                "predicate_family_tags": ["ratio_family"],
            },
            {
                "sample_id": "b",
                "query": "q",
                "fl_problem": "p",
                "response_aux": None,
                "has_aux": False,
                "aux_segment_count": 0,
                "aux_points_total": 0,
                "goal_predicate": "perp",
                "predicate_family_tags": ["parallel_perp_family"],
            },
        ]
        pool, summary = self.build_candidate_pool.build_candidate_pool(rows)
        self.assertEqual(len(pool), 1)
        self.assertEqual(pool[0]["response"], "<aux> a </aux>")
        self.assertEqual(summary["dropped_no_aux"], 1)

    def test_aggregate_difficulty_metrics(self):
        sample = {
            "sample_id": "id",
            "query": "query",
            "fl_problem": "problem",
            "response": "<aux> gold </aux>",
        }
        result = self.label_difficulty.aggregate_difficulty_metrics(
            sample=sample,
            greedy_completion="greedy_good",
            sampled_completions=["sample_solved", "sample_unsolved", "sample_invalid", "sample_unsolved"],
            evaluator=StubEvaluator(),
        )
        self.assertTrue(result["greedy_success"])
        self.assertEqual(result["ddar_valid_count"], 3)
        self.assertEqual(result["ddar_solved_count"], 1)
        self.assertEqual(result["format_valid_count"], 4)
        self.assertEqual(result["unique_aux_count"], 3)
        self.assertAlmostEqual(result["duplicate_aux_ratio"], 0.25)
        self.assertFalse(result["all_invalid"])

    def test_select_debug_rows_filters_and_formats_output(self):
        rows = [
            {
                "sample_id": "mastered",
                "query": "q",
                "fl_problem": "p",
                "response": "r",
                "greedy_success": True,
                "pass_at_16": 1.0,
                "all_invalid": False,
                "goal_predicate": "eqratio",
                "predicate_family_tags": ["ratio_family"],
                "aux_segment_count": 1,
                "aux_points_total": 1,
            },
            {
                "sample_id": "dead",
                "query": "q",
                "fl_problem": "p",
                "response": "r",
                "greedy_success": False,
                "pass_at_16": 0.0,
                "all_invalid": True,
                "goal_predicate": "eqangle",
                "predicate_family_tags": ["angle_family"],
                "aux_segment_count": 1,
                "aux_points_total": 1,
            },
            {
                "sample_id": "keep1",
                "query": "q1",
                "fl_problem": "p1",
                "response": "r1",
                "greedy_success": False,
                "pass_at_16": 0.2,
                "all_invalid": False,
                "goal_predicate": "eqratio",
                "predicate_family_tags": ["ratio_family"],
                "aux_segment_count": 2,
                "aux_points_total": 2,
            },
            {
                "sample_id": "keep2",
                "query": "q2",
                "fl_problem": "p2",
                "response": "r2",
                "greedy_success": False,
                "pass_at_16": 0.5,
                "all_invalid": False,
                "goal_predicate": "perp",
                "predicate_family_tags": ["parallel_perp_family"],
                "aux_segment_count": 1,
                "aux_points_total": 1,
            },
        ]
        final_rows, report = self.select_debug_set.select_debug_rows(rows, target_size=2)
        self.assertEqual(len(final_rows), 2)
        self.assertEqual(sorted(final_rows[0].keys()), ["fl_problem", "query", "response"])
        self.assertEqual(report["removed_mastered"], 1)
        self.assertEqual(report["removed_all_invalid"], 1)

    def test_file_round_trip_for_candidate_pool(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            annotations_path = tmp_path / "annotations.jsonl"
            output_path = tmp_path / "candidate_pool.jsonl"
            summary_path = tmp_path / "summary.json"
            rows = [
                {
                    "sample_id": "a",
                    "query": "q",
                    "fl_problem": "p",
                    "response_aux": "<aux> a </aux>",
                    "has_aux": True,
                    "aux_segment_count": 1,
                    "aux_points_total": 1,
                    "goal_predicate": "eqratio",
                    "predicate_family_tags": ["ratio_family"],
                }
            ]
            with annotations_path.open("w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row))
                    handle.write("\n")

            loaded = self.build_candidate_pool.load_jsonl(annotations_path)
            pool, summary = self.build_candidate_pool.build_candidate_pool(loaded)
            self.build_candidate_pool.write_jsonl(output_path, pool)
            self.build_candidate_pool.write_json(summary_path, summary)

            self.assertTrue(output_path.exists())
            self.assertTrue(summary_path.exists())


if __name__ == "__main__":
    unittest.main()
