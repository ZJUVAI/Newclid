import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments.cot_sft_generation.core.insight_extractor import extract_insight_slots
from experiments.cot_sft_generation.core.insight_pipeline import (
    build_scripted_insight_plan,
    build_scripted_insight_writer_body,
    validate_insight_plan_response,
    validate_insight_writer_body,
)
from experiments.cot_sft_generation.core.proof_dag import parse_proof_dag
from experiments.cot_sft_generation.generate_cot_sft import (
    build_visible_text_facts,
    extract_aux_and_rest,
    get_point_coords,
    process_and_generate_sft,
)


BENCHMARK_FILE = Path("experiments/cot_sft_generation/benchmarks/quality_review_v1/quality_review_v1_input.jsonl")


def _load_record(index: int):
    with open(BENCHMARK_FILE, "r", encoding="utf-8") as f:
        for row_index, line in enumerate(f):
            if row_index == index:
                return json.loads(line)
    raise IndexError(index)


class CotSftInsightPipelineTest(unittest.TestCase):
    def test_extract_insight_slots_from_real_benchmark_record(self):
        record = _load_record(1)
        aux_part, _ = extract_aux_and_rest(record["llm_output_renamed"])
        dag = parse_proof_dag(record["llm_output_renamed"])

        slots = extract_insight_slots(
            dag,
            visible_goal=record["llm_input_renamed"].split("?", 1)[1].replace("</problem>", "").strip(),
            aux_part=aux_part,
        )

        self.assertIsInstance(slots, dict)
        self.assertEqual(slots["goal_family"], "eqangle")
        self.assertEqual(slots["goal_gap_type"], "angle_transfer")
        self.assertIn("concyclic", slots["required_aux_effect"])
        self.assertTrue(slots["evidence_windows"])

    def test_validate_insight_plan_response_accepts_scripted_plan(self):
        record = _load_record(1)
        aux_part, _ = extract_aux_and_rest(record["llm_output_renamed"])
        visible_goal = record["llm_input_renamed"].split("?", 1)[1].replace("</problem>", "").strip()
        dag = parse_proof_dag(record["llm_output_renamed"])
        slots = extract_insight_slots(dag, visible_goal=visible_goal, aux_part=aux_part)

        plan = build_scripted_insight_plan(
            record,
            aux_part=aux_part,
            insight_slots=slots,
            visible_text_facts=build_visible_text_facts(record),
            image_scan_candidates=["points b, d, and e appear nearly collinear"],
        )

        ok, message, cleaned = validate_insight_plan_response(
            plan,
            point_coords=get_point_coords(record),
            visible_goal=visible_goal,
            aux_part=aux_part,
            visible_text_facts=build_visible_text_facts(record),
            insight_slots=slots,
        )

        self.assertTrue(ok, msg=message)
        self.assertEqual(cleaned["generation_style"], "insight_v1")
        self.assertEqual(cleaned["insight_version"], "insight_v1")
        self.assertEqual(cleaned["goal_gap_type"], slots["goal_gap_type"])

    def test_validate_insight_plan_response_requires_stage_order_for_multi_point_aux(self):
        point_coords = {"a": (0, 0), "b": (4, 0), "c": (0, 4), "d": (4, 4)}
        insight_slots = {
            "goal_family": "eqratio",
            "goal_gap_type": "ratio_transfer",
            "required_aux_effect": "h is the midpoint of ad",
            "first_bridge_checkpoint": "k is the midpoint of bc",
            "pre_goal_checkpoint": "ratio ad/hd equals ratio bc/ck",
            "stage_order": ["first create h as the midpoint of ad", "then create k as the midpoint of bc"],
            "evidence_windows": [],
        }
        plan = {
            "visible_facts": ["ab equals cd"],
            "image_scan": ["line ab and line cd look parallel"],
            "goal_gap_type": "ratio_transfer",
            "goal_gap_text": "the visible givens still do not transfer the needed ratio from the a-side onto the d-side",
            "required_aux_effect": "h is the midpoint of ad",
            "aux_construction": "construct point h such that h is the midpoint of ad. then construct point k such that k is the midpoint of bc",
            "aux_immediate_effects": ["h is the midpoint of ad", "k is the midpoint of bc"],
            "aux_selection_reason": "the midpoint at h starts the ratio carrier and the midpoint at k reconnects that carrier before ratio ad/hd equals ratio bc/ck closes",
        }

        ok, message, _ = validate_insight_plan_response(
            plan,
            point_coords=point_coords,
            visible_goal="eqratio a d a h b c c h",
            aux_part="<aux> x00 h : midp h a d [001] ; x00 k : midp k b c [002] ; </aux>",
            visible_text_facts=[{"relation": "ab equals cd"}],
            insight_slots=insight_slots,
        )

        self.assertFalse(ok)
        self.assertIn("stage_order", message)

    def test_validate_insight_writer_body_rejects_proof_echo(self):
        plan = {
            "required_aux_effect": "a, c, d, f are concyclic",
            "aux_construction": "construct point f such that a, c, d, f are concyclic and b, d, f are collinear",
            "goal_gap_text": "the visible givens still do not transfer the angle at a onto the d-side",
        }
        body = (
            "The gap is that the visible givens still do not transfer the angle at a onto the d-side. "
            "Construct point f such that a, c, d, f are concyclic and b, d, f are collinear. "
            "Because a, c, d, f are concyclic, because b, d, f are collinear, because [012] AR, "
            "the hidden proof closes."
        )

        ok, message = validate_insight_writer_body(body, plan=plan)

        self.assertFalse(ok)
        self.assertIn("proof", message.lower())

    def test_process_and_generate_sft_runs_insight_v1_and_persists_artifacts(self):
        record = dict(_load_record(1))
        record["image_path"] = "fixture.png"
        aux_part, _ = extract_aux_and_rest(record["llm_output_renamed"])
        visible_goal = record["llm_input_renamed"].split("?", 1)[1].replace("</problem>", "").strip()
        slots = extract_insight_slots(parse_proof_dag(record["llm_output_renamed"]), visible_goal, aux_part)
        scripted_plan = build_scripted_insight_plan(
            record,
            aux_part=aux_part,
            insight_slots=slots,
            visible_text_facts=build_visible_text_facts(record),
            image_scan_candidates=["points b, d, and e appear nearly collinear"],
        )
        writer_body = build_scripted_insight_writer_body(scripted_plan)

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
                    generation_style="insight_v1",
                    run_dir=run_dir,
                )

            self.assertEqual(result["summary"]["generation_style"], "insight_v1")
            output_records = [
                json.loads(line)
                for line in output_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(output_records), 1)
            self.assertIn("<thinking>", output_records[0]["thinking"])
            self.assertTrue(output_records[0]["output"].endswith(output_records[0]["aux"]))

            item_records = [
                json.loads(line)
                for line in (run_dir / "item_records.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(item_records[0]["generation_style"], "insight_v1")
            self.assertIsInstance(item_records[0]["insight_slots"], dict)
            self.assertIsInstance(item_records[0]["insight_plan_parsed"], dict)


if __name__ == "__main__":
    unittest.main()
