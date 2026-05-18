import json
import tempfile
import unittest
from pathlib import Path

from experiments.cot_sft_generation.maintenance_smoke_check import (
    validate_all_benchmark_manifests,
    validate_benchmark_manifest,
)


class CotSftMaintenanceSmokeTest(unittest.TestCase):
    def test_validate_benchmark_manifest_accepts_fixed_inputs(self):
        manifest_path = Path("experiments/cot_sft_generation/benchmarks/fixed_v104sample_manifest.json")
        summary = validate_benchmark_manifest(manifest_path)

        self.assertEqual(summary["records"], 4)
        self.assertGreaterEqual(summary["subsets"], 1)
        self.assertEqual(summary["benchmark_name"], "fixed_v104sample")

    def test_validate_benchmark_manifest_rejects_out_of_range_subset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            manifest_path = temp_dir_path / "manifest.json"
            input_path = temp_dir_path / "input.jsonl"

            input_path.write_text('{"a": 1}\n{"a": 2}\n', encoding="utf-8")
            manifest = {
                "benchmark_name": "temp",
                "input_jsonl": str(input_path),
                "records": [
                    {"sample_order": 0, "goal_type": "eqangle", "aux_type": "single_point", "focus_tags": ["tag"]},
                    {"sample_order": 1, "goal_type": "eqratio", "aux_type": "multi_point", "focus_tags": ["tag"]},
                ],
                "subsets": {
                    "bad": [0, 2],
                },
            }
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

            with self.assertRaises(ValueError) as ctx:
                validate_benchmark_manifest(manifest_path)

            self.assertIn("out-of-range index", str(ctx.exception))

    def test_validate_benchmark_manifest_rejects_missing_focus_tags(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            manifest_path = temp_dir_path / "manifest.json"
            input_path = temp_dir_path / "input.jsonl"

            input_path.write_text('{"a": 1}\n', encoding="utf-8")
            manifest = {
                "benchmark_name": "temp",
                "input_jsonl": str(input_path),
                "records": [
                    {"sample_order": 0, "goal_type": "eqangle", "aux_type": "single_point", "focus_tags": []},
                ],
                "subsets": {"all": [0]},
            }
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

            with self.assertRaises(ValueError) as ctx:
                validate_benchmark_manifest(manifest_path)

            self.assertIn("focus_tags", str(ctx.exception))

    def test_validate_all_benchmark_manifests_accepts_repo_benchmarks(self):
        summary = validate_all_benchmark_manifests(
            Path("experiments/cot_sft_generation/benchmarks")
        )

        self.assertGreaterEqual(summary["manifests"], 1)
        self.assertGreaterEqual(summary["records"], 4)
        self.assertIn("fixed_v104sample", summary["benchmark_names"])


if __name__ == "__main__":
    unittest.main()
