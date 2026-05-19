import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments.cot_sft_generation.generate_cot_sft import process_and_generate_sft
from experiments.cot_sft_generation.replay_artifact_checks import recheck_item_record, recheck_run_dir
from experiments.cot_sft_generation.run_artifacts import build_run_config


PLAN_OUTPUT_COORD_SUPPORT = {
    "anchor_points": ["a", "b", "c", "e"],
    "anchor_relation": "triangle abc is the visible frame and point e sits on the lower side of the wider figure.",
    "figure_overview": (
        "points d, f, g, and j sit outside the anchor frame, so the target ratio must be "
        "transferred through the outer right side."
    ),
    "coordinate_relations": [
        "point f looks like the midpoint of ac",
        "point g looks like the midpoint of cd",
        "points b, d, and f look nearly collinear",
    ],
    "visible_relations": [
        "ab is parallel to cd",
        "ad is parallel to bc",
        "ab equals bc",
    ],
    "coordinate_hints": (
        "point f looks like the midpoint of ac, point g looks like the midpoint of cd, "
        "and points b, d, and f look nearly collinear."
    ),
    "goal_bottleneck": (
        "the target ratio still needs a route from the outer d-side configuration back to ae, af, ce, and cj."
    ),
    "helper_idea": (
        "a helper through k should connect the outer line through d and g to the cyclic relation around b, f, and g."
    ),
    "construction": "construct point k such that b, f, g, k are concyclic and c, d, k are collinear.",
    "aux_direct_relations": [
        "b, f, g, k are concyclic",
        "c, d, k are collinear",
    ],
    "bridge_steps": [
        {
            "relation": "c, g, k are collinear",
            "depends_on": [
                "b, f, g, k are concyclic",
                "c, d, k are collinear",
                "c, d, g are collinear",
            ],
            "why_it_helps": "this aligns k with the outer d-g line before the angle transfer.",
        },
        {
            "relation": "b, d, f are collinear",
            "depends_on": [
                "b, f, g, k are concyclic",
                "c, d, k are collinear",
                "ab is parallel to cd",
                "f is the midpoint of ac",
            ],
            "why_it_helps": "this fixes the line needed for the upcoming angle comparison.",
        },
        {
            "relation": "angle bd/bg equals angle fk/dk",
            "depends_on": [
                "b, f, g, k are concyclic",
                "b, d, f are collinear",
                "c, d, k are collinear",
            ],
            "why_it_helps": "this supplies the angle alignment needed before the final ratio route.",
        },
    ],
    "goal_finish": "ratio ae to af equals ratio ce to cj",
}

WRITER_BODY_COORD_SUPPORT = (
    "The remaining obstacle is to connect ae, af, ce, and cj, so points f and j must be tied "
    "back to the outer d-side configuration before the target ratio can close. "
    "Since point f looks like the midpoint of ac and point g looks like the midpoint of cd, "
    "a helper through k can track the outer line through d and g without losing the f-side comparison. "
    "Because c, d, g are collinear and c, d, k are collinear, c, g, k are collinear, and this "
    "places k on the outer d-g line for the next step. "
    "The nearly collinear placement of b, d, and f shows that b, d, f are collinear, and this "
    "fixes the line needed for the angle transfer. "
    "Because b, f, g, k are concyclic and b, d, f are collinear, angle bd/bg equals angle fk/dk, "
    "and this supplies the last angle comparison before the target ratio. "
    "Therefore, ratio ae to af equals ratio ce to cj."
)


class CotSftReplayArtifactChecksTest(unittest.TestCase):
    def test_recheck_run_dir_replays_current_checks_on_verbose_fixture_run(self):
        record = {
            "nl_problem": "Observe the diagram and justify the target ratio.",
            "llm_input_renamed": (
                "<problem>g1: para a b c d [000]; g2: para a d b c [001]; g3: cong a b b c [002] ? "
                "eqratio a e a f c e c j</problem>"
            ),
            "llm_output_renamed": (
                "<aux>x00 k : cyclic b f g k [016] coll c d k [017]</aux> "
                "<proof>coll c g k; coll b d f; eqangle b d b g f k d k; eqratio a e a f c e c j</proof>"
            ),
            "point_coords_grid": {
                "a": [-2, -2],
                "b": [-4, -4],
                "c": [4, 0],
                "d": [6, 2],
                "e": [-1, 6],
                "f": [1, -1],
                "g": [5, 1],
                "j": [4, -3],
            },
            "image_path": "fixture_ratio.png",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            input_path = temp_dir_path / "input.jsonl"
            output_path = temp_dir_path / "out.jsonl"
            run_dir = temp_dir_path / "artifacts"

            input_path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
            (temp_dir_path / "fixture_ratio.png").write_bytes(b"fixture-image")

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
                side_effect=[json.dumps(PLAN_OUTPUT_COORD_SUPPORT), WRITER_BODY_COORD_SUPPORT],
            ):
                process_and_generate_sft(
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

            item_records = [
                json.loads(line)
                for line in (run_dir / "item_records.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(item_records), 1)

            item_recheck = recheck_item_record(item_records[0])
            self.assertTrue(item_recheck["revalidated_plan_ok"])
            self.assertTrue(item_recheck["writer_valid"])
            self.assertTrue(item_recheck["thinking_valid"])
            self.assertTrue(item_recheck["current_all_checks_pass"])
            self.assertEqual(
                item_recheck["revalidated_plan"]["bridge_steps"][1]["required_supports"],
                ["points b, d, and f look nearly collinear"],
            )
            self.assertFalse(item_recheck["generation_audit_changed"])

            run_recheck = recheck_run_dir(run_dir)
            self.assertEqual(run_recheck["summary"]["total_items"], 1)
            self.assertEqual(run_recheck["summary"]["current_all_checks_pass_items"], 1)
            self.assertEqual(run_recheck["summary"]["generation_audit_changed_items"], 0)


if __name__ == "__main__":
    unittest.main()
