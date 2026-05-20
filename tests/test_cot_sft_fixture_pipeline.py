import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments.cot_sft_generation.generate_cot_sft import process_and_generate_sft
from experiments.cot_sft_generation.run_artifacts import build_run_config


PLAN_OUTPUT = {
    "selected_text_fact_ids": ["T1", "T2"],
    "selected_coordinate_candidate_ids": ["C1"],
    "image_observations": ["point a looks like the midpoint of bc"],
    "coordinate_derivations": [
        {
            "candidate_id": "C1",
            "relation": "point a looks like the midpoint of bc",
            "points": ["a", "b", "c"],
            "calc_type": "midpoint",
            "render_mode": "midpoint",
            "why_it_matters": "this gives one image-based balance check inside the visible triangle before the helper is added.",
        }
    ],
    "goal_bottleneck": "the target still needs one local equality that can transfer the d-side to the c-side.",
    "helper_idea": "a helper should create two local equalities around one new point before the final transfer.",
    "construction": "construct point h such that ah equals dh and bh equals ch.",
    "aux_direct_relations": ["ah equals dh", "bh equals ch"],
    "bridge_steps": [
        {
            "relation": "ah equals bh",
            "support_refs": ["T2", "C1"],
            "why_it_helps": "this creates the first shared equality in the helper frame.",
            "proof_alignment": "bridge",
            "focus_points": ["a", "b", "h"],
        },
        {
            "relation": "dh equals ch",
            "support_refs": ["B1", "T2"],
            "why_it_helps": "this transfers the helper equality to the d-side and c-side.",
            "proof_alignment": "goal_finish",
            "focus_points": ["c", "d", "h"],
        },
    ],
    "goal_finish": "ad equals bc",
}

PLAN_CRITIC_OUTPUT = {
    "approved": True,
    "issues": [],
    "summary": "the selected supports and the ending are coherent.",
}

WRITER_BODY = (
    "The obstacle is to transfer the d-side and c-side into one local helper frame before the final equality closes. "
    "Using a=(0,0), b=(4,0), and c=(0,2), the midpoint of bc is (2.0, 1.0), which differs from a by residual 2.2361 and the collinearity residual is 1.7889, so point a looks like the midpoint of bc. "
    "Construct point h such that ah equals dh and bh equals ch. "
    "Because point a looks like the midpoint of bc and ac equals bd, ah equals bh, and this creates the first shared equality in the helper frame. "
    "Because ah equals bh and ac equals bd, dh equals ch, and this transfers the helper equality to the d-side and c-side. "
    "Therefore ad equals bc."
)


class CotSftFixturePipelineTest(unittest.TestCase):
    def test_process_and_generate_sft_runs_offline_fixture_pipeline(self):
        record = {
            "nl_problem": "Observe the diagram and justify the target relation.",
            "llm_input_renamed": (
                "<problem>g1: para a b c d [000]; g2: cong a c b d [001] ? cong a d b c</problem>"
            ),
            "llm_output_renamed": (
                "<aux>x00 h : cong a h d h; cong b h c h</aux> "
                "<proof>cong a h b h; cong d h c h; cong a d b c</proof>"
            ),
            "point_coords_grid": {
                "a": [0, 0],
                "b": [4, 0],
                "c": [0, 2],
                "d": [4, 2],
            },
            "image_path": "fixture.png",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            input_path = temp_dir_path / "input.jsonl"
            output_path = temp_dir_path / "out.jsonl"
            run_dir = temp_dir_path / "artifacts"

            input_path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
            (temp_dir_path / "fixture.png").write_bytes(b"fixture-image")

            run_metadata = build_run_config(
                args_dict={
                    "input": str(input_path),
                    "output": str(output_path),
                    "num_samples": 1,
                    "num_workers": 1,
                    "model_name": "fixture-model",
                    "max_retries": 1,
                    "sequential": True,
                    "verbose": True,
                },
                output_jsonl=str(output_path),
                run_dir=str(run_dir),
                model_name="fixture-model",
                script_path="experiments/cot_sft_generation/generate_cot_sft.py",
                cwd=str(temp_dir_path),
                repo_root=str(Path.cwd()),
                default_input_jsonl=str(input_path),
                api_base_url="https://example.invalid/v1",
                api_timeout_seconds=180,
                api_call_retries=3,
                api_retry_backoff_seconds=3,
            )

            with patch(
                "experiments.cot_sft_generation.generate_cot_sft.call_model",
                side_effect=[json.dumps(PLAN_OUTPUT), json.dumps(PLAN_CRITIC_OUTPUT), WRITER_BODY],
            ):
                result = process_and_generate_sft(
                    input_jsonl=str(input_path),
                    output_jsonl=str(output_path),
                    sample_size=1,
                    num_workers=1,
                    model_name="fixture-model",
                    verbose=True,
                    random_sample=False,
                    process_all=False,
                    max_retries=1,
                    run_metadata=run_metadata,
                    run_dir=run_dir,
                )

            self.assertEqual(result["summary"]["surface_pass_items"], 1)
            dataset_records = [
                json.loads(line)
                for line in output_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(dataset_records), 1)
            self.assertIn("a=(0,0)", dataset_records[0]["thinking"])
            self.assertEqual(dataset_records[0]["aux"], "<aux>x00 h : cong a h d h; cong b h c h</aux>")

            item_records = [
                json.loads(line)
                for line in (run_dir / "item_records.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(item_records), 1)
            self.assertTrue(item_records[0]["surface_pass"])
            self.assertEqual(item_records[0]["attempts_used"], 3)
            self.assertIn("coordinate_derivations", item_records[0]["plan_parsed"])


if __name__ == "__main__":
    unittest.main()
