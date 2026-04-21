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
        self.label_difficulty_vlm = load_module(
            "scripts/grpo/label_difficulty_vlm.py", "label_difficulty_vlm"
        )
        self.report_difficulty_drift = load_module(
            "scripts/grpo/report_difficulty_drift.py", "report_difficulty_drift"
        )
        self.select_debug_set = load_module(
            "scripts/grpo/select_debug_set.py", "select_debug_set"
        )

    def _selection_row(
        self,
        sample_id: str,
        *,
        pass_value: float = 0.0,
        greedy_success: bool = False,
        all_invalid: bool = False,
        goal_predicate: str = "eqratio",
        predicate_family_tags: list[str] | None = None,
        aux_segment_count: int = 2,
        aux_points_total: int = 2,
        unique_aux_count: int = 2,
        duplicate_aux_ratio: float = 0.5,
        build_invalid_count: int = 0,
        format_invalid_count: int = 0,
        n_premises: int = 6,
        problem_predicate_count: int = 5,
        problem_clause_count: int = 4,
    ) -> dict:
        return {
            "sample_id": sample_id,
            "query": f"query-{sample_id}",
            "fl_problem": f"problem-{sample_id}",
            "response": f"response-{sample_id}",
            "greedy_success": greedy_success,
            "pass_at_16": pass_value,
            "all_invalid": all_invalid,
            "goal_predicate": goal_predicate,
            "predicate_family_tags": predicate_family_tags or ["ratio_family"],
            "aux_segment_count": aux_segment_count,
            "aux_points_total": aux_points_total,
            "unique_aux_count": unique_aux_count,
            "duplicate_aux_ratio": duplicate_aux_ratio,
            "build_invalid_count": build_invalid_count,
            "format_invalid_count": format_invalid_count,
            "n_premises": n_premises,
            "problem_predicate_count": problem_predicate_count,
            "problem_clause_count": problem_clause_count,
        }

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
            self._selection_row("mastered", pass_value=1.0, greedy_success=True),
            self._selection_row(
                "dead",
                pass_value=0.0,
                all_invalid=True,
                goal_predicate="eqangle",
                predicate_family_tags=["angle_family"],
            ),
            self._selection_row("keep1", pass_value=0.2),
            self._selection_row(
                "keep2",
                pass_value=0.5,
                goal_predicate="perp",
                predicate_family_tags=["parallel_perp_family"],
                aux_segment_count=1,
                aux_points_total=1,
            ),
        ]
        final_rows, report = self.select_debug_set.select_debug_rows(
            rows,
            target_size=2,
            mastered_fallback_min_fill_fraction=0.0,
        )
        self.assertEqual(len(final_rows), 2)
        self.assertEqual(
            sorted(final_rows[0].keys()), ["fl_problem", "query", "response"]
        )
        self.assertEqual(report["removed_mastered"], 1)
        self.assertEqual(report["removed_all_invalid"], 1)
        self.assertEqual(report["selection_policy"], "v3_tiered")
        self.assertEqual(report["tier_selected_rows"]["core"], 2)
        self.assertEqual(report["selected_core_rows"], 2)

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

    def test_select_debug_rows_applies_v3_tiers_and_caps(self):
        rows = [
            self._selection_row("core", pass_value=0.20),
            self._selection_row(
                "near_low",
                pass_value=0.01,
                goal_predicate="perp",
                predicate_family_tags=["parallel_perp_family"],
            ),
            self._selection_row(
                "near_high",
                pass_value=0.80,
                goal_predicate="eqangle",
                predicate_family_tags=["angle_family"],
            ),
            self._selection_row(
                "high_a",
                pass_value=0.0,
                goal_predicate="cyclic",
                predicate_family_tags=["circle_family"],
                unique_aux_count=4,
                duplicate_aux_ratio=0.50,
            ),
            self._selection_row(
                "high_b",
                pass_value=0.0,
                goal_predicate="contri",
                predicate_family_tags=["triangle_family"],
                unique_aux_count=3,
                duplicate_aux_ratio=0.60,
            ),
            self._selection_row(
                "mid_a",
                pass_value=0.0,
                goal_predicate="simtri",
                predicate_family_tags=["triangle_family"],
                unique_aux_count=1,
                duplicate_aux_ratio=0.95,
            ),
            self._selection_row(
                "noisy",
                pass_value=0.0,
                build_invalid_count=4,
                unique_aux_count=1,
                duplicate_aux_ratio=0.98,
            ),
            self._selection_row("mastered", pass_value=0.95, greedy_success=True),
            self._selection_row("dead", pass_value=0.0, all_invalid=True),
        ]

        final_rows, report = self.select_debug_set.select_debug_rows(
            rows,
            target_size=5,
            hard_valid_high_max_fraction=0.20,
            hard_valid_mid_max_fraction=0.20,
            mastered_fallback_min_fill_fraction=0.0,
        )

        self.assertEqual(len(final_rows), 5)
        self.assertEqual(report["tier_available_rows"]["hard_valid_high"], 2)
        self.assertEqual(report["tier_available_rows"]["hard_valid_mid"], 1)
        self.assertEqual(report["discarded_non_dead_rows"], 1)
        self.assertEqual(report["tier_selected_rows"]["core"], 1)
        self.assertEqual(report["tier_selected_rows"]["near"], 2)
        self.assertEqual(report["tier_selected_rows"]["hard_valid_high"], 1)
        self.assertEqual(report["tier_selected_rows"]["hard_valid_mid"], 1)
        self.assertEqual(report["selected_mastered_rows"], 0)
        self.assertEqual(report["selected_nonzero_pass_rows"], 3)
        self.assertEqual(report["selected_zero_pass_rows"], 2)

    def test_select_debug_rows_prefers_more_diverse_rows_within_tier(self):
        rows = [
            self._selection_row(
                "high_strong",
                pass_value=0.0,
                unique_aux_count=4,
                duplicate_aux_ratio=0.50,
            ),
            self._selection_row(
                "high_weak",
                pass_value=0.0,
                unique_aux_count=2,
                duplicate_aux_ratio=0.80,
            ),
        ]

        final_rows, report = self.select_debug_set.select_debug_rows(
            rows,
            target_size=1,
            hard_valid_high_max_fraction=1.0,
            hard_valid_mid_max_fraction=0.0,
            mastered_fallback_min_fill_fraction=0.0,
            multi_segment_min_fraction=0.0,
            multi_point_min_fraction=0.0,
        )

        self.assertEqual(len(final_rows), 1)
        self.assertEqual(final_rows[0]["query"], "query-high_strong")
        self.assertEqual(report["tier_selected_rows"]["hard_valid_high"], 1)
        self.assertAlmostEqual(report["selected_avg_unique_aux_count"], 4.0)

    def test_select_debug_rows_uses_mastered_only_for_low_fill(self):
        rows = [
            self._selection_row("core", pass_value=0.20),
            self._selection_row(
                "near",
                pass_value=0.02,
                goal_predicate="perp",
                predicate_family_tags=["parallel_perp_family"],
            ),
            self._selection_row(
                "mastered_a",
                pass_value=0.95,
                greedy_success=True,
                goal_predicate="eqangle",
                predicate_family_tags=["angle_family"],
            ),
            self._selection_row(
                "mastered_b",
                pass_value=0.98,
                greedy_success=True,
                goal_predicate="cyclic",
                predicate_family_tags=["circle_family"],
            ),
        ]

        final_rows, report = self.select_debug_set.select_debug_rows(
            rows,
            target_size=4,
            mastered_max_fraction=0.50,
            mastered_fallback_min_fill_fraction=0.90,
        )

        self.assertEqual(len(final_rows), 4)
        self.assertTrue(report["mastered_fallback_triggered"])
        self.assertEqual(report["selected_mastered_rows"], 2)
        self.assertEqual(report["tier_selected_rows"]["mastered"], 2)
        self.assertEqual(report["selected_pass_histogram"]["0.9500"], 1)
        self.assertEqual(report["selected_pass_histogram"]["0.9800"], 1)

    def test_filter_candidate_tiers_discards_high_high_tail_for_stage_balanced(self):
        rows = [
            self._selection_row("core", pass_value=0.25),
            self._selection_row("high_mid", pass_value=0.75),
            self._selection_row("high_high", pass_value=0.8125),
        ]

        tier_rows, stats = self.select_debug_set.filter_candidate_tiers(
            rows,
            selection_policy="v10_auxfix_stage_balanced",
            core_min_pass=0.125,
            core_max_pass=0.625,
            mastered_pass_min=0.90,
            hard_valid_build_invalid_max=2,
            hard_valid_format_invalid_max=1,
            hard_valid_unique_aux_min=2,
            hard_valid_duplicate_aux_max=0.875,
            near_high_mid_max_pass=0.75,
            zero_valid_min=0.25,
            zero_valid_max=0.875,
            zero_pass_reward_std_min=0.15,
            reward_mixed_zero_unique_aux_min=2,
        )

        self.assertEqual(stats["discarded_non_dead_rows"], 1)
        self.assertEqual(len(tier_rows["core"]), 1)
        self.assertEqual(len(tier_rows["near_high_mid"]), 1)

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

    def test_select_debug_rows_applies_auxfix_easy_tail_caps(self):
        rows = []
        for idx in range(4):
            rows.append(self._selection_row(f"core_{idx}", pass_value=0.25))
        for idx in range(4):
            rows.append(
                self._selection_row(
                    f"near_low_{idx}",
                    pass_value=0.0625,
                    goal_predicate="perp",
                    predicate_family_tags=["parallel_perp_family"],
                )
            )
        for idx in range(4):
            rows.append(
                self._selection_row(
                    f"pass_one_{idx}",
                    pass_value=1.0,
                    greedy_success=False,
                    goal_predicate="eqangle",
                    predicate_family_tags=["angle_family"],
                )
            )
        for idx in range(4):
            rows.append(
                self._selection_row(
                    f"greedy_{idx}",
                    pass_value=0.75,
                    greedy_success=True,
                    goal_predicate="cyclic",
                    predicate_family_tags=["circle_family"],
                )
            )

        final_rows, report = self.select_debug_set.select_debug_rows(
            rows,
            target_size=10,
            selection_policy="v10_auxfix_stage_balanced",
            near_low_min_fraction=0.20,
            reward_mixed_zero_min_fraction=0.0,
            near_high_mid_min_fraction=0.0,
            greedy_success_max_fraction=0.20,
            pass_one_max_fraction=0.20,
            high_pass_max_fraction=0.30,
            mastered_fallback_min_fill_fraction=0.0,
            multi_segment_min_fraction=0.0,
            multi_point_min_fraction=0.0,
            family_min_fraction=0.0,
            goal_max_fraction=1.0,
            near_low_max_fraction=1.0,
            reward_mixed_zero_max_fraction=1.0,
            near_high_mid_max_fraction=1.0,
            mastered_max_fraction=0.0,
        )

        self.assertEqual(len(final_rows), 10)
        self.assertLessEqual(report["selected_greedy_success_rows"], 2)
        self.assertLessEqual(report["selected_pass_one_rows"], 2)
        self.assertLessEqual(report["selected_high_pass_rows"], 3)
        self.assertEqual(report["selection_policy"], "v10_auxfix_stage_balanced")
        self.assertEqual(report["easy_tail_caps"]["greedy_success"], 2)
        self.assertEqual(report["easy_tail_caps"]["pass_one"], 2)
        self.assertEqual(report["easy_tail_caps"]["high_pass"], 3)

    def test_label_difficulty_vlm_resume_prefix_validation(self):
        rows = [
            {"_shard_index": 0, "sample_id": "a", "query": "q-a", "fl_problem": "p-a"},
            {"_shard_index": 1, "sample_id": "b", "query": "q-b", "fl_problem": "p-b"},
        ]
        existing_rows = [
            {"_shard_index": 0, "sample_id": "a", "query": "q-a", "fl_problem": "p-a"}
        ]
        self.label_difficulty_vlm._validate_resume_prefix(rows, existing_rows)
        bad_existing = [
            {"_shard_index": 0, "sample_id": "z", "query": "q-z", "fl_problem": "p-z"}
        ]
        with self.assertRaises(ValueError):
            self.label_difficulty_vlm._validate_resume_prefix(rows, bad_existing)

    def test_report_difficulty_drift_summarizes_pass_movement(self):
        old_rows = [
            {
                "query": "q1",
                "fl_problem": "p1",
                "pass_at_16": 0.0,
                "greedy_success": False,
                "all_invalid": False,
            },
            {
                "query": "q2",
                "fl_problem": "p2",
                "pass_at_16": 0.5,
                "greedy_success": False,
                "all_invalid": False,
            },
        ]
        new_rows = [
            {
                "query": "q1",
                "fl_problem": "p1",
                "pass_at_16": 0.75,
                "greedy_success": True,
                "all_invalid": False,
            },
            {
                "query": "q2",
                "fl_problem": "p2",
                "pass_at_16": 0.25,
                "greedy_success": False,
                "all_invalid": False,
            },
        ]

        report = self.report_difficulty_drift.build_drift_report(old_rows, new_rows)

        self.assertEqual(report["matched_rows"], 2)
        self.assertEqual(report["movement"]["pass_up"], 1)
        self.assertEqual(report["movement"]["pass_down"], 1)
        self.assertEqual(report["old_stats"]["avg_pass"], 0.25)
        self.assertEqual(report["new_stats"]["avg_pass"], 0.5)


if __name__ == "__main__":
    unittest.main()
