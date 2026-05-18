import json
import tempfile
import unittest
from pathlib import Path

from experiments.cot_sft_generation.maintenance_smoke_check import validate_benchmark_manifest


class CotSftMaintenanceSmokeTest(unittest.TestCase):
    def test_validate_benchmark_manifest_accepts_fixed_inputs(self):
        manifest_path = Path("experiments/cot_sft_generation/benchmarks/fixed_v104sample_manifest.json")
        input_path = Path("experiments/cot_sft_generation/benchmarks/fixed_v104sample_input.jsonl")

        summary = validate_benchmark_manifest(manifest_path, input_path)

        self.assertEqual(summary["records"], 4)
        self.assertGreaterEqual(summary["subsets"], 1)

    def test_validate_benchmark_manifest_rejects_out_of_range_subset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            manifest_path = temp_dir_path / "manifest.json"
            input_path = temp_dir_path / "input.jsonl"

            input_path.write_text('{"a": 1}\n{"a": 2}\n', encoding="utf-8")
            manifest = {
                "records": [
                    {"sample_order": 0},
                    {"sample_order": 1},
                ],
                "subsets": {
                    "bad": [0, 2],
                },
            }
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

            with self.assertRaises(ValueError) as ctx:
                validate_benchmark_manifest(manifest_path, input_path)

            self.assertIn("out-of-range index", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
