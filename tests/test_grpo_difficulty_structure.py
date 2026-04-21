import importlib.util
import unittest
from pathlib import Path


def load_module(path: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, Path(path))
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestGRPODifficultyStructure(unittest.TestCase):
    def setUp(self):
        self.module = load_module(
            "scripts/grpo/analyze_difficulty_structure.py",
            "analyze_difficulty_structure",
        )

    def test_rankdata_averages_ties(self):
        self.assertEqual(self.module._rankdata([1.0, 1.0, 3.0]), [1.5, 1.5, 3.0])

    def test_spearman_detects_monotonic_relation(self):
        result = self.module.spearman_correlation(
            [1.0, 2.0, 3.0, 4.0],
            [0.0, 0.25, 0.5, 1.0],
        )
        self.assertEqual(result["n"], 4)
        self.assertAlmostEqual(result["rho"], 1.0)

    def test_grouped_summary_and_models(self):
        rows = []
        rows.extend(
            [
                {
                    "sample_id": "z0",
                    "pass_at_16": 0.0,
                    "aux_points_total": 1,
                    "aux_segment_count": 1,
                    "n_premises": 2,
                },
                {
                    "sample_id": "z1",
                    "pass_at_16": 0.0,
                    "aux_points_total": 2,
                    "aux_segment_count": 1,
                    "n_premises": 3,
                },
            ]
        )
        for idx in range(1, 7):
            pass_value = idx / 8.0
            rows.append(
                {
                    "sample_id": f"s{idx}",
                    "pass_at_16": pass_value,
                    "aux_points_total": idx,
                    "aux_segment_count": min(idx, 3),
                    "n_premises": idx + 1,
                }
            )
            rows.append(
                {
                    "sample_id": f"s{idx}b",
                    "pass_at_16": min(1.0, pass_value + 0.0625),
                    "aux_points_total": idx,
                    "aux_segment_count": min(idx, 3),
                    "n_premises": idx + 1,
                }
            )

        summary = self.module.build_summary(
            rows,
            pass_key="pass_at_16",
            aux_key="aux_points_total",
            aux_segment_key="aux_segment_count",
            premises_key="n_premises",
            num_samples=16,
        )

        self.assertEqual(summary["total_rows"], 14)
        self.assertEqual(summary["usable_rows"], 14)
        self.assertIn("1", summary["grouped_by_aux"])
        self.assertIn("1", summary["grouped_by_aux_segments"])
        self.assertIn("2", summary["grouped_by_premises"])
        self.assertIsNotNone(summary["models"]["binomial_pass_rate"])
        self.assertIsNotNone(summary["models"]["logit_nonzero_pass"])
        self.assertIsNotNone(summary["models"]["binomial_pass_rate_by_aux_segments"])
        self.assertIsNotNone(summary["models"]["logit_nonzero_pass_by_aux_segments"])


if __name__ == "__main__":
    unittest.main()
