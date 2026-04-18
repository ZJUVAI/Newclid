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
            "sample_solved": AuxEvaluationResult(
                "aux2", True, True, "solved", None, 1.0
            ),
            "sample_unsolved": AuxEvaluationResult(
                "aux3", True, True, "unsolved", None, 0.25
            ),
            "sample_invalid": AuxEvaluationResult(
                "aux4", True, False, "build_invalid", "build_definition_error", -0.25
            ),
        }
        return mapping[completion]


class TestGRPODataSelection(unittest.TestCase):
    def setUp(self):
        self.analyze_dataset = load_module(
            "scripts/analyze_dataset.py", "analyze_dataset"
        )
        self.analyze_selected_dataset = load_module(
            "scripts/grpo/analyze_selected_dataset.py",
            "analyze_selected_dataset",
        )
        self.build_candidate_pool = load_module(
            "scripts/grpo/build_candidate_pool.py", "build_candidate_pool"
        )
        self.prefilter_candidate_pool = load_module(
            "scripts/grpo/prefilter_candidate_pool.py", "prefilter_candidate_pool"
        )
        self.label_difficulty = load_module(
            "scripts/grpo/label_difficulty.py", "label_difficulty"
        )
        self.select_debug_set = load_module(
            "scripts/grpo/select_debug_set.py", "select_debug_set"
        )

    def test_annotation_helpers(self):
        query = "<problem> a : ; b : perp a b b c [001] ; ? eqratio a b c d </problem>"
        output = "<aux> x00 g : coll a b g [002] ; </aux><proof>...</proof>"
        record = {
            "llm_input_renamed": query,
            "llm_output_renamed": output,
            "fl_problem": "a b c d = quadrangle a b c d ? eqratio a b c d",
            "n_premises": 6,
        }
        annotation = self.analyze_dataset.annotate_record(record, "sample:0")
        self.assertEqual(annotation["sample_id"], "sample:0")
        self.assertTrue(annotation["has_aux"])
        self.assertEqual(annotation["aux_segment_count"], 1)
        self.assertEqual(annotation["aux_points_total"], 1)
        self.assertEqual(annotation["goal_predicate"], "eqratio")
        self.assertIn("ratio_family", annotation["predicate_family_tags"])
        self.assertIn("parallel_perp_family", annotation["predicate_family_tags"])
        self.assertEqual(annotation["n_premises"], 6)
        self.assertEqual(annotation["problem_predicate_count"], 2)
        self.assertEqual(annotation["problem_clause_count"], 1)

    def test_annotation_counts_on_generated_dataset(self):
        rows = [
            {
                "llm_input_renamed": "<problem> a : ; b : perp a b b c [001] ; ? eqratio a b c d </problem>",
                "llm_output_renamed": "<aux> x00 g : coll a b g [002] ; </aux><proof>...</proof>",
                "fl_problem": "a b c d = quadrangle a b c d ? eqratio a b c d",
                "n_premises": 6,
            },
            {
                "llm_input_renamed": "<problem> a : ; b : para a b b c [001] ; ? perp a b c d </problem>",
                "llm_output_renamed": "<proof> no aux here </proof>",
                "fl_problem": "a b c d = quadrangle a b c d ? perp a b c d",
                "n_premises": 4,
            },
            {
                "llm_input_renamed": "<problem> a : ; b : cong a b c d [001] ; ? eqangle a b c d e f g h </problem>",
                "llm_output_renamed": "<aux> x00 e : coll a b e [002] ; f : perp e f a b [003] ; </aux>",
                "fl_problem": "a b c d = quadrangle a b c d ? eqangle a b c d e f g h",
                "n_premises": 5,
            },
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            input_path = Path(tmp_dir) / "annotate.jsonl"
            input_path.write_text(
                "\n".join(json.dumps(row) for row in rows) + "\n",
                encoding="utf-8",
            )
            annotations, summary = self.analyze_dataset.annotate_jsonl(input_path)

        self.assertEqual(len(annotations), 3)
        self.assertEqual(summary["aux_rows"], 2)
        self.assertEqual(
            summary["goal_predicate_distribution"],
            {"eqratio": 1, "perp": 1, "eqangle": 1},
        )

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
                "n_premises": 7,
                "problem_predicate_count": 5,
                "problem_clause_count": 3,
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
        self.assertEqual(pool[0]["n_premises"], 7)
        self.assertEqual(pool[0]["problem_predicate_count"], 5)
        self.assertEqual(pool[0]["problem_clause_count"], 3)
        self.assertEqual(summary["dropped_no_aux"], 1)

    def test_selected_dataset_annotation_helpers(self):
        record = {
            "query": "<problem> a : ; b : perp a b b c [001] ; ? eqratio a b c d </problem>",
            "fl_problem": "a b c d = quadrangle a b c d ? eqratio a b c d",
            "response": "<aux> x00 g : coll a b g [002] ; h : perp g h a b [003] ; </aux>",
        }
        annotation = self.analyze_selected_dataset.annotate_record(record, "selected:0")
        self.assertEqual(annotation["sample_id"], "selected:0")
        self.assertTrue(annotation["has_aux"])
        self.assertEqual(annotation["aux_segment_count"], 2)
        self.assertEqual(annotation["aux_points_total"], 2)
        self.assertEqual(annotation["goal_predicate"], "eqratio")
        self.assertIn("ratio_family", annotation["predicate_family_tags"])
        self.assertIn("parallel_perp_family", annotation["predicate_family_tags"])
        self.assertEqual(annotation["problem_predicate_count"], 2)
        self.assertEqual(annotation["problem_clause_count"], 1)

    def test_selected_dataset_summary_handles_invalid_aux_rows(self):
        rows = [
            {
                "sample_id": "a",
                "query": "<problem> ? eqratio a b c d </problem>",
                "fl_problem": "a b c d = quadrangle a b c d ? eqratio a b c d",
                "response": "<aux> x00 g : coll a b g [002] ; </aux>",
                "has_aux": True,
                "aux_segment_count": 1,
                "aux_points_total": 1,
                "goal_predicate": "eqratio",
                "predicate_family_tags": ["ratio_family"],
                "problem_predicate_count": 1,
                "problem_clause_count": 1,
            },
            {
                "sample_id": "b",
                "query": "<problem> ? perp a b c d </problem>",
                "fl_problem": "a b c d = quadrangle a b c d; e = midpoint e a c ? perp a b c d",
                "response": "<proof> no aux here </proof>",
                "has_aux": False,
                "aux_segment_count": 0,
                "aux_points_total": 0,
                "goal_predicate": "perp",
                "predicate_family_tags": ["parallel_perp_family"],
                "problem_predicate_count": 1,
                "problem_clause_count": 2,
            },
        ]
        summary = self.analyze_selected_dataset.summarize_annotations(rows)
        self.assertEqual(summary["total_rows"], 2)
        self.assertEqual(summary["aux_rows"], 1)
        self.assertEqual(
            summary["goal_predicate_distribution"], {"eqratio": 1, "perp": 1}
        )
        self.assertEqual(summary["aux_segment_count_distribution"], {1: 1})
        self.assertEqual(summary["problem_clause_count_distribution"], {1: 1, 2: 1})

    def test_prefilter_candidate_pool_dedupes_and_prefers_multi_aux(self):
        rows = [
            {
                "sample_id": "a1",
                "query": "dup-query",
                "fl_problem": "p",
                "response": "<aux> a </aux>",
                "goal_predicate": "eqratio",
                "predicate_family_tags": ["ratio_family"],
                "aux_segment_count": 1,
                "aux_points_total": 1,
                "n_premises": 3,
                "problem_predicate_count": 2,
                "problem_clause_count": 3,
            },
            {
                "sample_id": "a2",
                "query": "dup-query",
                "fl_problem": "p",
                "response": "<aux> a2 </aux>",
                "goal_predicate": "eqratio",
                "predicate_family_tags": ["ratio_family"],
                "aux_segment_count": 2,
                "aux_points_total": 2,
                "n_premises": 8,
                "problem_predicate_count": 2,
                "problem_clause_count": 3,
            },
            {
                "sample_id": "b",
                "query": "q-b",
                "fl_problem": "p",
                "response": "<aux> b </aux>",
                "goal_predicate": "eqangle",
                "predicate_family_tags": ["angle_family"],
                "aux_segment_count": 2,
                "aux_points_total": 2,
                "n_premises": 8,
                "problem_predicate_count": 4,
                "problem_clause_count": 6,
            },
            {
                "sample_id": "c",
                "query": "q-c",
                "fl_problem": "p",
                "response": "<aux> c </aux>",
                "goal_predicate": "perp",
                "predicate_family_tags": ["parallel_perp_family"],
                "aux_segment_count": 2,
                "aux_points_total": 2,
                "n_premises": 6,
                "problem_predicate_count": 4,
                "problem_clause_count": 6,
            },
            {
                "sample_id": "d",
                "query": "q-d",
                "fl_problem": "p",
                "response": "<aux> d </aux>",
                "goal_predicate": "cyclic",
                "predicate_family_tags": ["circle_family"],
                "aux_segment_count": 1,
                "aux_points_total": 1,
                "n_premises": 2,
                "problem_predicate_count": 1,
                "problem_clause_count": 2,
            },
        ]
        selected, report = self.prefilter_candidate_pool.prefilter_candidate_pool(
            rows,
            target_size=3,
            seed=7,
        )
        self.assertEqual(len(selected), 3)
        self.assertEqual(len({row["query"] for row in selected}), 3)
        self.assertEqual(report["exact_duplicate_queries_removed"], 1)
        self.assertGreaterEqual(
            sum(
                1
                for row in selected
                if row["aux_segment_count"] >= 2 or row["aux_points_total"] >= 2
            ),
            2,
        )

    def test_prefilter_candidate_pool_is_deterministic(self):
        rows = []
        for idx in range(12):
            rows.append(
                {
                    "sample_id": f"id-{idx}",
                    "query": f"query-{idx}",
                    "fl_problem": "p",
                    "response": f"<aux> {idx} </aux>",
                    "goal_predicate": "eqratio" if idx < 6 else "eqangle",
                    "predicate_family_tags": ["ratio_family"]
                    if idx < 6
                    else ["angle_family"],
                    "aux_segment_count": 2 if idx % 2 == 0 else 1,
                    "aux_points_total": 2 if idx % 2 == 0 else 1,
                    "n_premises": 8 if idx % 3 == 0 else 5,
                    "problem_predicate_count": 4,
                    "problem_clause_count": 6,
                }
            )
        first, first_report = self.prefilter_candidate_pool.prefilter_candidate_pool(
            rows, target_size=6, seed=11
        )
        second, second_report = self.prefilter_candidate_pool.prefilter_candidate_pool(
            rows, target_size=6, seed=11
        )
        self.assertEqual(first, second)
        self.assertEqual(first_report, second_report)

    def test_compute_bucket_quotas_prioritizes_high_premise_rows(self):
        bucket_counts = {
            ("multi_aux", "p8_plus", "angle_family"): 10,
            ("multi_aux", "p5_7", "angle_family"): 10,
            ("multi_aux", "p0_4", "angle_family"): 10,
            ("single_aux", "p8_plus", "ratio_family"): 10,
            ("single_aux", "p5_7", "ratio_family"): 10,
            ("single_aux", "p0_4", "ratio_family"): 10,
        }
        quotas = self.prefilter_candidate_pool.compute_bucket_quotas(
            bucket_counts, target_size=20
        )

        self.assertGreater(
            quotas[("multi_aux", "p8_plus", "angle_family")],
            quotas[("multi_aux", "p5_7", "angle_family")],
        )
        self.assertGreater(
            quotas[("multi_aux", "p5_7", "angle_family")],
            quotas[("multi_aux", "p0_4", "angle_family")],
        )
        self.assertGreater(
            quotas[("single_aux", "p8_plus", "ratio_family")],
            quotas[("single_aux", "p5_7", "ratio_family")],
        )
        self.assertGreater(
            quotas[("single_aux", "p5_7", "ratio_family")],
            quotas[("single_aux", "p0_4", "ratio_family")],
        )

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
            sampled_completions=[
                "sample_solved",
                "sample_unsolved",
                "sample_invalid",
                "sample_unsolved",
            ],
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
        final_rows, report = self.select_debug_set.select_debug_rows(
            rows, target_size=2
        )
        self.assertEqual(len(final_rows), 2)
        self.assertEqual(
            sorted(final_rows[0].keys()), ["fl_problem", "query", "response"]
        )
        self.assertEqual(report["removed_mastered"], 1)
        self.assertEqual(report["removed_all_invalid"], 1)

    def test_select_debug_rows_accepts_pass_at_8(self):
        rows = [
            {
                "sample_id": "mastered",
                "query": "q0",
                "fl_problem": "p0",
                "response": "r0",
                "greedy_success": True,
                "pass_at_8": 1.0,
                "all_invalid": False,
                "goal_predicate": "eqratio",
                "predicate_family_tags": ["ratio_family"],
                "aux_segment_count": 1,
                "aux_points_total": 1,
            },
            {
                "sample_id": "keep1",
                "query": "q1",
                "fl_problem": "p1",
                "response": "r1",
                "greedy_success": False,
                "pass_at_8": 0.25,
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
                "pass_at_8": 0.5,
                "all_invalid": False,
                "goal_predicate": "perp",
                "predicate_family_tags": ["parallel_perp_family"],
                "aux_segment_count": 1,
                "aux_points_total": 1,
            },
        ]
        final_rows, report = self.select_debug_set.select_debug_rows(
            rows, target_size=2
        )
        self.assertEqual(len(final_rows), 2)
        self.assertEqual(report["pass_key"], "pass_at_8")
        self.assertEqual(report["removed_mastered"], 1)

    def test_select_debug_rows_relaxes_into_non_dead_and_caps_mastered(self):
        rows = [
            {
                "sample_id": "s1",
                "query": "q1",
                "fl_problem": "p1",
                "response": "r1",
                "greedy_success": False,
                "pass_at_16": 0.20,
                "all_invalid": False,
                "goal_predicate": "eqratio",
                "predicate_family_tags": ["ratio_family"],
                "aux_segment_count": 2,
                "aux_points_total": 2,
            },
            {
                "sample_id": "s2",
                "query": "q2",
                "fl_problem": "p2",
                "response": "r2",
                "greedy_success": False,
                "pass_at_16": 0.70,
                "all_invalid": False,
                "goal_predicate": "perp",
                "predicate_family_tags": ["parallel_perp_family"],
                "aux_segment_count": 1,
                "aux_points_total": 1,
            },
            {
                "sample_id": "s3",
                "query": "q3",
                "fl_problem": "p3",
                "response": "r3",
                "greedy_success": False,
                "pass_at_16": 0.92,
                "all_invalid": False,
                "goal_predicate": "eqangle",
                "predicate_family_tags": ["angle_family"],
                "aux_segment_count": 1,
                "aux_points_total": 1,
            },
            {
                "sample_id": "m1",
                "query": "q4",
                "fl_problem": "p4",
                "response": "r4",
                "greedy_success": True,
                "pass_at_16": 0.95,
                "all_invalid": False,
                "goal_predicate": "cyclic",
                "predicate_family_tags": ["circle_family"],
                "aux_segment_count": 1,
                "aux_points_total": 1,
            },
            {
                "sample_id": "m2",
                "query": "q5",
                "fl_problem": "p5",
                "response": "r5",
                "greedy_success": True,
                "pass_at_16": 0.99,
                "all_invalid": False,
                "goal_predicate": "eqratio",
                "predicate_family_tags": ["ratio_family"],
                "aux_segment_count": 1,
                "aux_points_total": 1,
            },
        ]

        final_rows, report = self.select_debug_set.select_debug_rows(
            rows, target_size=5, mastered_max_fraction=0.20
        )

        self.assertEqual(len(final_rows), 4)
        self.assertEqual(report["stage_selected_rows"]["preferred"], 1)
        self.assertEqual(report["stage_selected_rows"]["fallback"], 1)
        self.assertEqual(report["stage_selected_rows"]["non_dead"], 1)
        self.assertEqual(report["stage_selected_rows"]["capped_mastered"], 1)
        self.assertEqual(report["selected_mastered_rows"], 1)
        self.assertIn("mastered_cap_reached", report["shortage_reasons"])
        self.assertEqual(report["selected_pass_histogram"]["0.9500"], 1)

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
                    "n_premises": 4,
                    "problem_predicate_count": 2,
                    "problem_clause_count": 3,
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

    def test_file_round_trip_for_selected_dataset_analysis(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "selected.jsonl"
            annotations_path = tmp_path / "annotations.jsonl"
            summary_path = tmp_path / "summary.json"
            rows = [
                {
                    "query": "<problem> ? eqratio a b c d </problem>",
                    "fl_problem": "a b c d = quadrangle a b c d ? eqratio a b c d",
                    "response": "<aux> x00 g : coll a b g [002] ; </aux>",
                },
                {
                    "query": "<problem> ? perp a b c d </problem>",
                    "fl_problem": "a b c d = quadrangle a b c d; e = midpoint e a c ? perp a b c d",
                    "response": "<proof> no aux here </proof>",
                },
            ]
            with input_path.open("w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row))
                    handle.write("\n")

            annotations, summary = self.analyze_selected_dataset.analyze_jsonl(
                input_path
            )
            self.analyze_selected_dataset.write_jsonl(annotations_path, annotations)
            self.analyze_selected_dataset.write_json(summary_path, summary)

            self.assertTrue(annotations_path.exists())
            self.assertTrue(summary_path.exists())
            self.assertEqual(summary["total_rows"], 2)
            self.assertEqual(summary["aux_rows"], 1)


if __name__ == "__main__":
    unittest.main()
