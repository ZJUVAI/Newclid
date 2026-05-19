import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments.cot_sft_generation.generate_cot_sft import process_and_generate_sft
from experiments.cot_sft_generation.run_artifacts import build_run_config


PLAN_OUTPUT = {
    "anchor_points": ["a", "b", "c"],
    "anchor_relation": "triangle abc is the main visible frame, and line ab is parallel to line cd.",
    "figure_overview": (
        "point d extends the upper side of the figure, so the target still has to compare "
        "the d-side with the opposite side through the larger frame."
    ),
    "coordinate_relations": [
        "segments ab and cd look parallel",
        "segments ac and bd look equal in length",
    ],
    "visible_relations": [
        "line ab is parallel to line cd",
        "ac equals bd",
    ],
    "coordinate_hints": (
        "segments ab and cd look parallel, and segments ac and bd look equal in length, "
        "so the top and bottom sides should be tracked together."
    ),
    "goal_bottleneck": "the target still needs a direct equality that connects side ad to side bc.",
    "helper_idea": (
        "a helper should create two local equal-length transfers around one new point so "
        "that the d-side and the c-side can be compared explicitly."
    ),
    "construction": "construct point h such that ah equals dh and bh equals ch.",
    "aux_direct_relations": [
        "ah equals dh",
        "bh equals ch",
    ],
    "bridge_steps": [
        {
            "relation": "ah equals bh",
            "depends_on": [
                "ah equals dh",
                "bh equals ch",
            ],
            "why_it_helps": "this sets up the next length transfer needed before the target equality.",
        },
        {
            "relation": "dh equals ch",
            "depends_on": [
                "ah equals dh",
                "ah equals bh",
                "bh equals ch",
            ],
            "why_it_helps": "this gives the final local equality needed before the target side comparison.",
        },
    ],
    "goal_finish": "ad equals bc",
}

WRITER_BODY = (
    "The remaining obstacle is to prove ad equals bc, so the comparison must be carried "
    "from d and c into one shared helper frame. "
    "Because segments ac and bd look equal in length across the wider frame, the new point has to transfer the "
    "local equalities back toward those two visible sides. "
    "Because ac equals bd and ah equals dh, ah equals bh, and this gives a common length "
    "at h for the a-side and b-side. "
    "Because ac equals bd, ah equals dh, and ah equals bh, dh equals ch, and this puts d "
    "and c under the same length control from h. "
    "Therefore ad equals bc, which is exactly the target equal-length relation."
)

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
                "c": [1, 3],
                "d": [5, 3],
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
                side_effect=[json.dumps(PLAN_OUTPUT), WRITER_BODY],
            ):
                result = process_and_generate_sft(
                    input_jsonl=str(input_path),
                    output_jsonl=str(output_path),
                    sample_size=1,
                    num_workers=1,
                    model_name="fixture-model",
                    plan_mode="llm",
                    verbose=True,
                    random_sample=False,
                    process_all=False,
                    max_retries=1,
                    run_metadata=run_metadata,
                    run_dir=run_dir,
                )

            self.assertEqual(result["summary"]["surface_pass_items"], 1)
            self.assertEqual(result["summary"]["surface_pass_rate"], 1.0)
            self.assertEqual(result["summary"]["source_audit_issue_items"], 0)
            self.assertEqual(result["summary"]["generation_audit_issue_items"], 0)

            dataset_records = [
                json.loads(line)
                for line in output_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(dataset_records), 1)
            self.assertIn("<thinking>", dataset_records[0]["thinking"])
            self.assertEqual(
                dataset_records[0]["aux"],
                "<aux>x00 h : cong a h d h; cong b h c h</aux>",
            )

            item_records = [
                json.loads(line)
                for line in (run_dir / "item_records.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(item_records), 1)
            self.assertTrue(item_records[0]["surface_pass"])
            self.assertEqual(item_records[0]["attempts_used"], 2)
            self.assertFalse(item_records[0]["source_audit"]["has_issue"])
            self.assertFalse(item_records[0]["generation_audit"]["has_issue"])

            sampled_inputs = [
                json.loads(line)
                for line in (run_dir / "sampled_inputs.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(sampled_inputs), 1)
            self.assertEqual(sampled_inputs[0]["input_index"], 0)

            item_audits = [
                json.loads(line)
                for line in (run_dir / "item_audits.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            semantic_audits = [
                json.loads(line)
                for line in (run_dir / "semantic_audits.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(item_audits), 1)
            self.assertEqual(len(semantic_audits), 1)
            self.assertTrue(item_audits[0]["surface_pass"])
            self.assertIsNone(semantic_audits[0]["semantic_pass"])
            self.assertEqual(semantic_audits[0]["review_status"], "pending")

            run_config = json.loads((run_dir / "run_config.json").read_text(encoding="utf-8"))
            self.assertEqual(run_config["model_name"], "fixture-model")
            self.assertEqual(run_config["resolved_input_jsonl"], str(input_path.resolve()))

    def test_process_and_generate_sft_offline_fixture_keeps_exact_coordinate_support_for_low_level_bridge(self):
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
                result = process_and_generate_sft(
                    input_jsonl=str(input_path),
                    output_jsonl=str(output_path),
                    sample_size=1,
                    num_workers=1,
                    model_name="fixture-model",
                    plan_mode="llm",
                    verbose=True,
                    random_sample=False,
                    process_all=False,
                    max_retries=1,
                    run_metadata=run_metadata,
                    run_dir=run_dir,
                )

            self.assertEqual(result["summary"]["surface_pass_items"], 1)
            self.assertEqual(result["summary"]["surface_pass_rate"], 1.0)
            self.assertEqual(result["summary"]["generation_audit_issue_items"], 0)

            item_records = [
                json.loads(line)
                for line in (run_dir / "item_records.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(item_records), 1)
            self.assertTrue(item_records[0]["surface_pass"])
            self.assertEqual(
                item_records[0]["plan_parsed"]["bridge_steps"][1]["depends_on"][0],
                "points b, d, and f look nearly collinear",
            )
            self.assertEqual(
                item_records[0]["plan_parsed"]["bridge_steps"][1]["required_supports"],
                ["points b, d, and f look nearly collinear"],
            )
            self.assertIn("b, d, f are collinear", item_records[0]["write_output"])
            self.assertFalse(item_records[0]["generation_audit"]["has_issue"])


if __name__ == "__main__":
    unittest.main()
