import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments.cot_sft_generation.core.backtrace_extractor import (
    build_backtrace_writer_handoff,
    extract_backtrace_slots,
)
from experiments.cot_sft_generation.core.backtrace_pipeline import (
    build_backtrace_write_prompt,
    collect_backtrace_writer_issues,
    validate_backtrace_writer_body,
)
from experiments.cot_sft_generation.core.backtrace_schema import BACKTRACE_TEXT_V1
from experiments.cot_sft_generation.core.proof_dag import parse_proof_dag
from experiments.cot_sft_generation.generate_cot_sft import process_and_generate_sft


def _build_backtrace_record():
    problem = (
        "<problem>"
        "g1: cong a b a c [000] ; "
        "g2: coll b c d [001] ; "
        "g3: para a d b e [002] ? "
        "eqratio a b b c b e c e"
        "</problem>"
    )
    aux = "<aux>x00 f : midp f a d [100] ; </aux>"
    proof = (
        "<proof>"
        "cong a b a c [010] AR [000] ; "
        "eqangle a b a c b c b d [011] AR [010] [001] ; "
        "midp f a d [012] AR [100] ; "
        "cong b f c f [013] AR [012] [010] ; "
        "eqangle a b b c b e c e [014] AR [013] [011] [002] ; "
        "eqratio a b b c b e c e [015] AR [014] [010] ; "
        "</proof>"
    )
    return {
        "llm_input_renamed": problem,
        "llm_output_renamed": f"{problem}\n{aux}\n{proof}",
    }


class CotSftBacktraceExtractorTest(unittest.TestCase):
    def test_extract_backtrace_slots_classifies_C1_C2_C3_V_H(self):
        record = _build_backtrace_record()
        dag = parse_proof_dag(record["llm_output_renamed"])

        slots = extract_backtrace_slots(
            dag,
            visible_goal="eqratio a b b c b e c e",
            aux_part="<aux>x00 f : midp f a d [100] ; </aux>",
        )

        self.assertEqual(slots["C1_step_ids"], ["010", "011"])
        self.assertEqual(slots["C2_step_ids"], ["010", "011", "014", "015"])
        self.assertEqual(slots["C3_step_ids"], ["012", "013", "014", "015"])
        self.assertEqual(slots["V_step_ids"], ["014", "015"])
        self.assertEqual(slots["H_step_ids"], ["012", "013"])

    def test_extract_backtrace_slots_builds_V_core_frontier_and_supporting_c1(self):
        record = _build_backtrace_record()
        dag = parse_proof_dag(record["llm_output_renamed"])

        slots = extract_backtrace_slots(
            dag,
            visible_goal="eqratio a b b c b e c e",
            aux_part="<aux>x00 f : midp f a d [100] ; </aux>",
        )

        self.assertEqual(slots["V_core_step_ids"], ["014", "015"])
        self.assertEqual(slots["backtrace_chain_step_ids"], ["015", "014"])
        self.assertEqual(slots["frontier_node_ids"], ["014"])
        self.assertEqual(slots["supporting_c1_by_frontier"], {"014": ["011"]})

    def test_extract_backtrace_slots_builds_aux_and_canonical_nl_fields(self):
        record = _build_backtrace_record()
        dag = parse_proof_dag(record["llm_output_renamed"])

        slots = extract_backtrace_slots(
            dag,
            visible_goal="eqratio a b b c b e c e",
            aux_part="<aux>x00 f : midp f a d [100] ; </aux>",
        )

        self.assertEqual(slots["aux_construction_formal"], "x00 f : midp f a d")
        self.assertEqual(slots["aux_construction_nl"], "construct point f such that f is the midpoint of ad")
        self.assertEqual(slots["goal_nl"], "ratio ab to bc equals ratio be to ce")
        self.assertEqual(
            slots["backtrace_chain_nl"],
            [
                "ratio ab to bc equals ratio be to ce",
                "angle ab/bc equals angle be/ce",
            ],
        )
        self.assertEqual(slots["frontier_nodes_nl"], ["angle ab/bc equals angle be/ce"])
        self.assertEqual(
            slots["supporting_c1_facts_nl"],
            {"angle ab/bc equals angle be/ce": ["angle ab/ac equals angle bc/bd"]},
        )

    def test_build_backtrace_writer_handoff_keeps_minimum_fields(self):
        handoff = build_backtrace_writer_handoff(
            {
                "goal_nl": "ratio ab to bc equals ratio be to ce",
                "backtrace_chain_nl": ["ratio ab to bc equals ratio be to ce"],
                "frontier_nodes_nl": ["angle ab/bc equals angle be/ce"],
                "supporting_c1_facts_nl": {"angle ab/bc equals angle be/ce": ["angle ab/ac equals angle bc/bd"]},
                "aux_construction_nl": "construct point f such that f is the midpoint of ad",
            }
        )

        self.assertEqual(
            handoff,
            {
                "goal_nl": "ratio ab to bc equals ratio be to ce",
                "backtrace_chain_nl": ["ratio ab to bc equals ratio be to ce"],
                "frontier_nodes_nl": ["angle ab/bc equals angle be/ce"],
                "supporting_c1_facts_nl": {
                    "angle ab/bc equals angle be/ce": ["angle ab/ac equals angle bc/bd"]
                },
                "aux_construction_nl": "construct point f such that f is the midpoint of ad",
            },
        )

    def test_build_backtrace_write_prompt_includes_fixed_contract(self):
        handoff = build_backtrace_writer_handoff(
            {
                "goal_nl": "ratio ab to bc equals ratio be to ce",
                "backtrace_chain_nl": ["ratio ab to bc equals ratio be to ce", "angle ab/bc equals angle be/ce"],
                "frontier_nodes_nl": ["angle ab/bc equals angle be/ce"],
                "supporting_c1_facts_nl": {"angle ab/bc equals angle be/ce": ["angle ab/ac equals angle bc/bd"]},
                "aux_construction_nl": "construct point f such that f is the midpoint of ad",
            }
        )

        prompt = build_backtrace_write_prompt(_build_backtrace_record(), handoff)

        self.assertIn("goal -> backtrace -> frontier -> support insufficiency -> aux", prompt)
        self.assertIn("[Writer Handoff]", prompt)
        self.assertNotIn("[Visible Point Coordinates]", prompt)
        self.assertNotIn("planner", prompt.lower())

    def test_validate_backtrace_writer_body_accepts_ordered_text_only_body(self):
        record = _build_backtrace_record()
        dag = parse_proof_dag(record["llm_output_renamed"])
        slots = extract_backtrace_slots(
            dag,
            visible_goal="eqratio a b b c b e c e",
            aux_part="<aux>x00 f : midp f a d [100] ; </aux>",
        )
        handoff = build_backtrace_writer_handoff(slots)
        body = (
            "The target is ratio ab to bc equals ratio be to ce. "
            "Working backward, that would be available once angle ab/bc equals angle be/ce is secured. "
            "But that backtrace stalls there, because angle ab/ac equals angle bc/bd is still not enough by itself to connect the e-side. "
            "So we need a new helper: construct point f such that f is the midpoint of ad."
        )

        ok, message = validate_backtrace_writer_body(
            body,
            writer_handoff=handoff,
            backtrace_slots=slots,
            aux_part="<aux>x00 f : midp f a d [100] ; </aux>",
        )

        self.assertTrue(ok, msg=message)

    def test_process_and_generate_sft_runs_backtrace_text_v1_without_image_inputs(self):
        record = _build_backtrace_record()

        body = (
            "The target is ratio ab to bc equals ratio be to ce. "
            "Working backward, that would be available once angle ab/bc equals angle be/ce is secured. "
            "But that backtrace stalls there, because angle ab/ac equals angle bc/bd is still not enough by itself to connect the e-side. "
            "So we need a new helper: construct point f such that f is the midpoint of ad."
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            input_path = temp_dir_path / "input.jsonl"
            output_path = temp_dir_path / "out.jsonl"
            run_dir = temp_dir_path / "artifacts"
            input_path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")

            with patch(
                "experiments.cot_sft_generation.generate_cot_sft.call_model",
                side_effect=[body],
            ), patch(
                "experiments.cot_sft_generation.generate_cot_sft._encode_image_base64",
                side_effect=AssertionError("backtrace_text_v1 must not encode images"),
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
                    generation_style=BACKTRACE_TEXT_V1,
                    run_dir=run_dir,
                )

            output_records = [
                json.loads(line)
                for line in output_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            item_records = [
                json.loads(line)
                for line in (run_dir / "item_records.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(result["summary"]["generation_style"], BACKTRACE_TEXT_V1)
        self.assertEqual(len(output_records), 1)
        self.assertNotIn("image_path", output_records[0])
        self.assertEqual(item_records[0]["plan_prompt"], None)
        self.assertEqual(item_records[0]["plan_output"], None)
        self.assertEqual(item_records[0]["plan_parsed"], None)
        self.assertEqual(item_records[0]["insight_plan_parsed"], None)
        self.assertIsInstance(item_records[0]["backtrace_slots"], dict)
        self.assertIsInstance(item_records[0]["writer_handoff"], dict)
        self.assertEqual(item_records[0]["writer_validation_issues"], [])
        self.assertTrue(item_records[0]["thinking"].startswith("<thinking>"))
        self.assertNotIn("missing_image", item_records[0]["source_audit"]["issues"])
        self.assertNotIn("missing_point_coords", item_records[0]["source_audit"]["issues"])

    def test_collect_backtrace_writer_issues_rejects_proof_leak_wrong_order_and_aux_drift(self):
        record = _build_backtrace_record()
        dag = parse_proof_dag(record["llm_output_renamed"])
        slots = extract_backtrace_slots(
            dag,
            visible_goal="eqratio a b b c b e c e",
            aux_part="<aux>x00 f : midp f a d [100] ; </aux>",
        )
        handoff = build_backtrace_writer_handoff(slots)

        leak_issues = collect_backtrace_writer_issues(
            (
                "The target is ratio ab to bc equals ratio be to ce. "
                "From proof [015] with r33, angle ab/bc equals angle be/ce is the key hidden step. "
                "So we need a new helper: construct point f such that f is the midpoint of ad."
            ),
            writer_handoff=handoff,
            backtrace_slots=slots,
            aux_part="<aux>x00 f : midp f a d [100] ; </aux>",
        )
        self.assertIn("proof_marker_leak", leak_issues)

        wrong_order_issues = collect_backtrace_writer_issues(
            (
                "Construct point f such that f is the midpoint of ad. "
                "The target is ratio ab to bc equals ratio be to ce. "
                "Working backward, that would be available once angle ab/bc equals angle be/ce is secured."
            ),
            writer_handoff=handoff,
            backtrace_slots=slots,
            aux_part="<aux>x00 f : midp f a d [100] ; </aux>",
        )
        self.assertIn("narrative_order_violation", wrong_order_issues)

        aux_drift_issues = collect_backtrace_writer_issues(
            (
                "The target is ratio ab to bc equals ratio be to ce. "
                "Working backward, that would be available once angle ab/bc equals angle be/ce is secured. "
                "But that backtrace stalls there, because angle ab/ac equals angle bc/bd is still not enough by itself to connect the e-side. "
                "So we need a new helper: construct point g such that g lies on ad."
            ),
            writer_handoff=handoff,
            backtrace_slots=slots,
            aux_part="<aux>x00 f : midp f a d [100] ; </aux>",
        )
        self.assertIn("aux_construction_misaligned", aux_drift_issues)

    def test_process_and_generate_sft_persists_writer_validation_issues_on_bad_sample(self):
        record = _build_backtrace_record()
        bad_body = (
            "Construct point f such that f is the midpoint of ad. "
            "The target is ratio ab to bc equals ratio be to ce. "
            "Working backward, that would be available once angle ab/bc equals angle be/ce is secured."
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            input_path = temp_dir_path / "input.jsonl"
            output_path = temp_dir_path / "out.jsonl"
            run_dir = temp_dir_path / "artifacts"
            input_path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")

            with patch(
                "experiments.cot_sft_generation.generate_cot_sft.call_model",
                side_effect=[bad_body],
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
                    generation_style=BACKTRACE_TEXT_V1,
                    run_dir=run_dir,
                )

            output_records = [
                json.loads(line)
                for line in output_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            item_records = [
                json.loads(line)
                for line in (run_dir / "item_records.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(result["summary"]["surface_fail_items"], 1)
        self.assertEqual(output_records, [])
        self.assertIn("narrative_order_violation", item_records[0]["writer_validation_issues"])


if __name__ == "__main__":
    unittest.main()
