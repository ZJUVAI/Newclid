import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments.cot_sft_generation.core.insight_pipeline import INSIGHT_IMAGE_V1
from experiments.cot_sft_generation.core.insight_extractor import extract_insight_slots
from experiments.cot_sft_generation.core.insight_pipeline import (
    build_scripted_insight_plan,
    build_scripted_insight_writer_body,
)
from experiments.cot_sft_generation.core.proof_dag import parse_proof_dag
from experiments.cot_sft_generation.generate_cot_sft import process_and_generate_sft
from experiments.cot_sft_generation.generate_cot_sft import build_visible_text_facts
from experiments.cot_sft_generation.replay_artifact_checks import recheck_item_record, recheck_run_dir
from experiments.cot_sft_generation.run_artifacts import build_run_config

BENCHMARK_FILE = Path("experiments/cot_sft_generation/benchmarks/quality_review_v1/quality_review_v1_input.jsonl")


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


def _load_record(index: int):
    with open(BENCHMARK_FILE, "r", encoding="utf-8") as f:
        for row_index, line in enumerate(f):
            if row_index == index:
                return json.loads(line)
    raise IndexError(index)


def _build_scripted_insight_fixture(index: int = 1):
    record = dict(_load_record(index))
    aux_part = record["llm_output_renamed"].split("</aux>", 1)[0] + "</aux>"
    visible_goal = record["llm_input_renamed"].split("?", 1)[1].replace("</problem>", "").strip()
    slots = extract_insight_slots(parse_proof_dag(record["llm_output_renamed"]), visible_goal, aux_part)
    scripted_plan = build_scripted_insight_plan(
        record,
        aux_part=aux_part,
        insight_slots=slots,
        visible_text_facts=build_visible_text_facts(record),
    )
    writer_body = build_scripted_insight_writer_body(scripted_plan)
    return record, scripted_plan, writer_body


class CotSftReplayArtifactChecksTest(unittest.TestCase):
    def test_recheck_run_dir_replays_current_checks_on_verbose_fixture_run(self):
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
                    "generation_style": "model_evidence_legacy",
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
                    generation_style="model_evidence_legacy",
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

            run_recheck = recheck_run_dir(run_dir)
            self.assertEqual(run_recheck["summary"]["total_items"], 1)
            self.assertEqual(run_recheck["summary"]["current_all_checks_pass_items"], 1)

    def test_recheck_item_record_keeps_insight_soft_audit_issue_exportable(self):
        record, scripted_plan, writer_body = _build_scripted_insight_fixture(1)
        record["image_path"] = "fixture.png"

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            input_path = temp_dir_path / "input.jsonl"
            output_path = temp_dir_path / "out.jsonl"
            run_dir = temp_dir_path / "artifacts"

            input_path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
            (temp_dir_path / "fixture.png").write_bytes(b"fixture-image")

            with patch(
                "experiments.cot_sft_generation.generate_cot_sft.call_model",
                side_effect=[json.dumps(scripted_plan, ensure_ascii=False), writer_body],
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
                    generation_style=INSIGHT_IMAGE_V1,
                    run_dir=run_dir,
                )

            item_record = json.loads((run_dir / "item_records.jsonl").read_text(encoding="utf-8").splitlines()[0])
            with patch(
                "experiments.cot_sft_generation.replay_artifact_checks.audit_generation_quality",
                return_value={"issues": ["goal_gap_specificity"], "has_issue": True},
            ):
                replay_row = recheck_item_record(item_record)

            self.assertTrue(replay_row["current_surface_pass"])
            self.assertTrue(replay_row["current_exported_to_dataset"])
            self.assertIsNone(replay_row["current_dataset_filter_reason"])
            self.assertTrue(replay_row["current_all_checks_pass"])

    def test_recheck_item_record_blocks_insight_hard_audit_issue_export(self):
        record, scripted_plan, writer_body = _build_scripted_insight_fixture(1)
        record["image_path"] = "fixture.png"

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            input_path = temp_dir_path / "input.jsonl"
            output_path = temp_dir_path / "out.jsonl"
            run_dir = temp_dir_path / "artifacts"

            input_path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
            (temp_dir_path / "fixture.png").write_bytes(b"fixture-image")

            with patch(
                "experiments.cot_sft_generation.generate_cot_sft.call_model",
                side_effect=[json.dumps(scripted_plan, ensure_ascii=False), writer_body],
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
                    generation_style=INSIGHT_IMAGE_V1,
                    run_dir=run_dir,
                )

            item_record = json.loads((run_dir / "item_records.jsonl").read_text(encoding="utf-8").splitlines()[0])
            with patch(
                "experiments.cot_sft_generation.replay_artifact_checks.audit_generation_quality",
                return_value={"issues": ["no_proof_echo"], "has_issue": True},
            ):
                replay_row = recheck_item_record(item_record)

            self.assertTrue(replay_row["current_surface_pass"])
            self.assertFalse(replay_row["current_exported_to_dataset"])
            self.assertEqual(replay_row["current_dataset_filter_reason"], "generation_audit_hard_issue")
            self.assertFalse(replay_row["current_all_checks_pass"])


if __name__ == "__main__":
    unittest.main()
