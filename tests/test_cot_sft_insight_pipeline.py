import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from experiments.cot_sft_generation.core.insight_extractor import extract_insight_slots
from experiments.cot_sft_generation.core.audits import audit_generation_quality
from experiments.cot_sft_generation.core.insight_pipeline import (
    build_insight_plan_prompt,
    build_insight_write_prompt,
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
    validate_thinking_response,
)


BENCHMARK_FILE = Path("experiments/cot_sft_generation/benchmarks/quality_review_v1/quality_review_v1_input.jsonl")


def _load_record(index: int):
    with open(BENCHMARK_FILE, "r", encoding="utf-8") as f:
        for row_index, line in enumerate(f):
            if row_index == index:
                return json.loads(line)
    raise IndexError(index)


def _windows_by_role(slots: dict) -> dict[str, dict]:
    return {
        str(window.get("role") or ""): window
        for window in (slots.get("evidence_windows") or [])
        if isinstance(window, dict)
    }


def _build_scripted_insight_fixture(index: int = 1):
    record = dict(_load_record(index))
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
    return record, scripted_plan, writer_body


def _run_insight_pipeline(
    record: dict,
    temp_dir_path: Path,
    *,
    call_model_side_effect,
    audit_result=None,
):
    input_path = temp_dir_path / "input.jsonl"
    output_path = temp_dir_path / "out.jsonl"
    run_dir = temp_dir_path / "artifacts"

    input_path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    (temp_dir_path / "fixture.png").write_bytes(b"fixture-image")

    patchers = [
        patch(
            "experiments.cot_sft_generation.generate_cot_sft.call_model",
            side_effect=call_model_side_effect,
        ),
    ]
    if audit_result is not None:
        patchers.append(
            patch(
                "experiments.cot_sft_generation.generate_cot_sft.audit_generation_quality",
                return_value=audit_result,
            )
        )

    with ExitStack() as stack:
        for patcher in patchers:
            stack.enter_context(patcher)
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

    output_records = []
    if output_path.exists():
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
    return result, output_records, item_records


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

    def test_required_aux_effect_window_stays_aligned_with_slot_effect(self):
        record = _load_record(0)
        aux_part, _ = extract_aux_and_rest(record["llm_output_renamed"])
        visible_goal = record["llm_input_renamed"].split("?", 1)[1].replace("</problem>", "").strip()
        slots = extract_insight_slots(parse_proof_dag(record["llm_output_renamed"]), visible_goal, aux_part)

        required_window = _windows_by_role(slots)["required_aux_effect"]

        self.assertEqual(slots["required_aux_effect"], "h is the midpoint of ad")
        self.assertEqual(required_window["relation"], slots["required_aux_effect"])
        self.assertEqual(required_window["predicate"], "midp")
        self.assertEqual(required_window["step_id"], "008")

    def test_bridge_checkpoint_uses_reconnected_old_figure_points(self):
        record = _load_record(1)
        aux_part, _ = extract_aux_and_rest(record["llm_output_renamed"])
        visible_goal = record["llm_input_renamed"].split("?", 1)[1].replace("</problem>", "").strip()
        slots = extract_insight_slots(parse_proof_dag(record["llm_output_renamed"]), visible_goal, aux_part)
        windows = _windows_by_role(slots)

        self.assertEqual(slots["required_aux_effect"], "a, c, d, f are concyclic")
        self.assertEqual(windows["required_aux_effect"]["relation"], slots["required_aux_effect"])
        self.assertEqual(slots["first_bridge_checkpoint"], "b, e, f are collinear")
        self.assertEqual(windows["first_bridge_checkpoint"]["relation"], "b, e, f are collinear")
        self.assertNotEqual(slots["pre_goal_checkpoint"], slots["first_bridge_checkpoint"])
        self.assertIn("ratio", slots["pre_goal_checkpoint"])

    def test_parallel_aux_keeps_distinct_pre_goal_checkpoint(self):
        record = _load_record(2)
        aux_part, _ = extract_aux_and_rest(record["llm_output_renamed"])
        visible_goal = record["llm_input_renamed"].split("?", 1)[1].replace("</problem>", "").strip()
        slots = extract_insight_slots(parse_proof_dag(record["llm_output_renamed"]), visible_goal, aux_part)
        windows = _windows_by_role(slots)

        self.assertEqual(windows["required_aux_effect"]["relation"], slots["required_aux_effect"])
        self.assertIn("similar", slots["first_bridge_checkpoint"])
        self.assertIn("ratio", slots["pre_goal_checkpoint"])
        self.assertNotEqual(slots["pre_goal_checkpoint"], slots["first_bridge_checkpoint"])

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
        self.assertNotIn("aux_immediate_effects", cleaned)

    def test_build_insight_plan_prompt_includes_canonical_aux_construction(self):
        record = _load_record(1)
        aux_part, _ = extract_aux_and_rest(record["llm_output_renamed"])
        visible_goal = record["llm_input_renamed"].split("?", 1)[1].replace("</problem>", "").strip()
        slots = extract_insight_slots(parse_proof_dag(record["llm_output_renamed"]), visible_goal, aux_part)

        prompt = build_insight_plan_prompt(
            record,
            aux_part=aux_part,
            visible_fact_relations=[fact["relation"] for fact in build_visible_text_facts(record)],
            image_scan_candidates=["points b, d, and e appear nearly collinear"],
            insight_slots=slots,
        )

        self.assertIn("[Approved Auxiliary Construction]", prompt)
        self.assertIn("construct point f such that a, c, d, f are concyclic and b, d, f are collinear", prompt)
        self.assertNotIn("at most two short sentences", prompt)

    def test_validate_insight_plan_response_accepts_lists_beyond_old_caps(self):
        point_coords = {"a": (0, 0), "b": (4, 0), "c": (0, 4), "d": (4, 4)}
        visible_text_facts = [
            {"relation": "ab equals cd"},
            {"relation": "ac equals bd"},
            {"relation": "line ab is parallel to line cd"},
            {"relation": "line ac is parallel to line bd"},
            {"relation": "line ab is perpendicular to line ac"},
            {"relation": "a, b, d are collinear"},
            {"relation": "b, c, d are collinear"},
        ]
        insight_slots = {
            "goal_family": "eqratio",
            "goal_gap_type": "ratio_transfer",
            "required_aux_effect": "h is the midpoint of ad",
            "first_bridge_checkpoint": "k is the midpoint of bc",
            "pre_goal_checkpoint": "ratio ad/hd equals ratio bc/ck",
            "stage_order": [
                "first create h on ad",
                "then create k on bc",
            ],
            "evidence_windows": [],
        }
        plan = {
            "visible_facts": [fact["relation"] for fact in visible_text_facts],
            "image_scan": [
                "line ab and line cd look parallel",
                "segments ac and bd look equal",
                "points a, b, and d appear nearly collinear",
                "points b, c, and d appear nearly collinear",
                "line ab and line ac look perpendicular",
            ],
            "goal_gap_type": "ratio_transfer",
            "goal_gap_text": "the visible givens still do not transfer the needed ratio from a and d onto b and c inside one local frame",
            "required_aux_effect": "h is the midpoint of ad",
            "aux_construction": "construct point h such that h is the midpoint of ad, then construct point k such that k is the midpoint of bc",
            "aux_selection_reason": "the midpoint at h sets the first ratio carrier on a and d, the midpoint at k reconnects b and c, and ratio ad/hd equals ratio bc/ck is the local checkpoint before the goal side is revisited",
            "stage_order": [
                "first mark h on segment ad",
                "then lock the midpoint relation at h",
                "next mark k on segment bc",
                "finally align the second midpoint relation at k",
            ],
            "bonus_post_aux_tail": [
                "That gives one balanced segment frame around a and d.",
                "It also places b and c in a matching midpoint setup.",
                "The later ratio comparison can now stay local instead of jumping across the whole figure.",
            ],
        }

        ok, message, cleaned = validate_insight_plan_response(
            plan,
            point_coords=point_coords,
            visible_goal="eqratio a d b c a c b d",
            aux_part="<aux> x00 h : midp h a d [001] ; x00 k : midp k b c [002] ; </aux>",
            visible_text_facts=visible_text_facts,
            insight_slots=insight_slots,
        )

        self.assertTrue(ok, message)
        self.assertEqual(len(cleaned["visible_facts"]), 7)
        self.assertEqual(len(cleaned["image_scan"]), 5)
        self.assertEqual(len(cleaned["stage_order"]), 4)
        self.assertEqual(len(cleaned["bonus_post_aux_tail"]), 3)

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

    def test_validate_insight_plan_response_rejects_required_effect_outside_aux_direct_consequences(self):
        point_coords = {"a": (0, 0), "b": (4, 0), "c": (0, 4), "d": (4, 4)}
        insight_slots = {
            "goal_family": "eqratio",
            "goal_gap_type": "ratio_transfer",
            "required_aux_effect": "k is the midpoint of bc",
            "first_bridge_checkpoint": "ratio ad/hd equals ratio bc/ck",
            "pre_goal_checkpoint": "ratio ad/hd equals ratio bc/ck",
            "evidence_windows": [],
        }
        plan = {
            "visible_facts": ["ab equals cd"],
            "image_scan": ["line ab and line cd look parallel"],
            "goal_gap_type": "ratio_transfer",
            "goal_gap_text": "the visible givens still do not transfer the needed ratio from the a-side onto the d-side",
            "required_aux_effect": "k is the midpoint of bc",
            "aux_construction": "construct point h such that h is the midpoint of ad",
            "aux_selection_reason": "the midpoint at h is the helper frame that the ratio transfer needs before the goal side can be revisited",
        }

        ok, message, _ = validate_insight_plan_response(
            plan,
            point_coords=point_coords,
            visible_goal="eqratio a d a h b c c h",
            aux_part="<aux> x00 h : midp h a d [001] ; </aux>",
            visible_text_facts=[{"relation": "ab equals cd"}],
            insight_slots=insight_slots,
        )

        self.assertFalse(ok)
        self.assertIn("direct consequence", message)

    def test_build_insight_write_prompt_omits_aux_immediate_effects(self):
        prompt = build_insight_write_prompt(
            _load_record(1),
            {
                "visible_facts": ["ab equals ac"],
                "image_scan": ["points b, d, and f appear nearly collinear"],
                "goal_gap_type": "angle_transfer",
                "goal_gap_text": "the visible givens still do not transfer the angle at the b-side onto the d-side",
                "required_aux_effect": "a, c, d, f are concyclic",
                "aux_construction": "construct point f such that a, c, d, f are concyclic and b, d, f are collinear",
                "aux_selection_reason": "this helper creates the cyclic carrier that the slot requires before the old side can be reused",
            },
        )

        self.assertNotIn("aux_immediate_effects", prompt)
        self.assertNotIn('"required_aux_effect"', prompt)
        self.assertNotIn('"goal_gap_type"', prompt)
        self.assertIn('"canonical_aux_construction"', prompt)

    def test_build_insight_write_prompt_forbids_downstream_overclaim_examples(self):
        prompt = build_insight_write_prompt(
            _load_record(1),
            {
                "visible_facts": ["ab equals ac"],
                "image_scan": ["points b, d, and f appear nearly collinear"],
                "goal_gap_text": "the visible givens still do not transfer the angle at the b-side onto the d-side",
                "aux_construction": "construct point f such that a, c, d, f are concyclic and b, d, f are collinear",
                "aux_selection_reason": "the cyclic helper is the missing local frame before the old figure can be revisited",
            },
        )

        self.assertIn("direct local effect", prompt)
        self.assertIn("remote goal-side object", prompt)
        self.assertIn("creates a cyclic angle carrier", prompt)
        self.assertIn("gives one local frame that can be reused later", prompt)
        self.assertIn("the angle at e can now be transferred", prompt)
        self.assertNotIn("one short insight-first", prompt.lower())
        self.assertNotIn("at most one cautious local unlock statement", prompt)
        self.assertNotIn("one or two short follow-up sentences", prompt)

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

    def test_validate_insight_writer_body_accepts_semantic_helper_match_without_verbatim_required_effect(self):
        plan = {
            "required_aux_effect": "h is the midpoint of ad",
            "aux_construction": "construct point h such that h is the midpoint of ad",
            "canonical_aux_construction": "construct point h such that h is the midpoint of ad",
            "canonical_aux_direct_consequences": ["h is the midpoint of ad"],
            "goal_gap_text": "the visible givens still do not transfer the needed ratio from the a-side onto the d-side",
        }
        body = (
            "The visible ratio information still does not connect the a-side to the d-side in one local frame. "
            "Construct point h so that h divides segment ad into two equal parts, which creates the balanced helper relation this gap is missing before the ratio comparison comes back to a and d."
        )

        ok, message = validate_insight_writer_body(body, plan=plan)

        self.assertTrue(ok, message)

    def test_validate_insight_writer_body_accepts_equivalent_parallel_perpendicular_and_cyclic_effects(self):
        cases = [
            (
                {
                    "required_aux_effect": "line ab is parallel to line cd",
                    "aux_construction": "construct point h such that line ab is parallel to line cd",
                    "canonical_aux_construction": "construct point h such that line ab is parallel to line cd",
                    "canonical_aux_direct_consequences": ["line ab is parallel to line cd"],
                    "goal_gap_text": "the visible givens still do not connect the a-side and d-side angle frame",
                },
                "The angle frame still does not connect the a-side to the d-side. Construct point h so the two lines ab and cd stay parallel, and that local direction match is enough to reopen the angle transfer around a and d.",
            ),
            (
                {
                    "required_aux_effect": "line ab is perpendicular to line cd",
                    "aux_construction": "construct point h such that line ab is perpendicular to line cd",
                    "canonical_aux_construction": "construct point h such that line ab is perpendicular to line cd",
                    "canonical_aux_direct_consequences": ["line ab is perpendicular to line cd"],
                    "goal_gap_text": "the visible givens still do not lock one right-angle frame around a and d",
                },
                "The visible picture still lacks one stable right-angle frame around a and d. Construct point h so lines ab and cd intersect at right angles, and that perpendicular frame is the local relation needed before the route returns to the goal objects.",
            ),
            (
                {
                    "required_aux_effect": "a, c, d, f are concyclic",
                    "aux_construction": "construct point f such that a, c, d, f are concyclic and b, e, f are collinear",
                    "canonical_aux_construction": "construct point f such that a, c, d, f are concyclic and b, e, f are collinear",
                    "canonical_aux_direct_consequences": ["a, c, d, f are concyclic", "b, e, f are collinear"],
                    "goal_gap_text": "the visible givens still do not transfer the angle from the b-side onto the d-side",
                },
                "The visible givens still do not move the needed angle from the b-side onto the d-side. Construct point f on the circle through a, c, and d, and that cyclic angle carrier gives the figure one local frame that can be pushed back toward b and d.",
            ),
        ]

        for plan, body in cases:
            with self.subTest(required_aux_effect=plan["required_aux_effect"]):
                ok, message = validate_insight_writer_body(body, plan=plan)
                self.assertTrue(ok, message)

    def test_validate_insight_writer_body_accepts_math_notation_for_helper_relation(self):
        plan = {
            "required_aux_effect": "ab equals cg",
            "aux_construction": "construct point g such that ab equals cg and line bc is perpendicular to line cg",
            "canonical_aux_construction": "construct point g such that ab equals cg and line bc is perpendicular to line cg",
            "canonical_aux_direct_consequences": ["ab equals cg", "line bc is perpendicular to line cg"],
            "goal_gap_text": "the visible givens still do not connect ab to cf inside one congruence frame",
        }
        body = (
            "The visible facts still do not connect ab to cf inside one congruence frame. "
            "Construct point \\( g \\) such that \\( ab = cg \\) and \\( bc \\perp cg \\). "
            "That helper fixes the missing local congruence and right-angle frame before the argument returns to c, f, and g."
        )

        ok, message = validate_insight_writer_body(body, plan=plan)

        self.assertTrue(ok, message)

    def test_validate_insight_writer_body_accepts_long_visible_only_body(self):
        plan = {
            "required_aux_effect": "a, c, d, f are concyclic",
            "aux_construction": "construct point f such that a, c, d, f are concyclic and b, d, f are collinear",
            "canonical_aux_construction": "construct point f such that a, c, d, f are concyclic and b, d, f are collinear",
            "canonical_aux_direct_consequences": ["a, c, d, f are concyclic", "b, d, f are collinear"],
            "goal_gap_text": "the visible givens still do not transfer the angle from the b-side onto the d-side inside one local frame",
        }
        body = (
            "The visible givens still do not move the needed angle from the b-side onto the d-side inside one local frame. "
            "Point b and point d already define the old corridor, but nothing visible yet turns that corridor through a helper circle. "
            "The scan also suggests that the line through b, d, and f can be reused once f is chosen. "
            "Construct point f such that a, c, d, and f are concyclic and b, d, f are collinear. "
            "That circle relation creates a fresh angle carrier around a, c, d, and f. "
            "Because the helper stays local to a, c, d, and f, it adds the missing carrier without pretending the target is already solved. "
            "Because b, d, and f remain on one line, the old side still touches the new carrier at the same visible track. "
            "Because those two effects meet at f, the next comparison can stay short and local before the argument returns to b and d."
        )

        ok, message = validate_insight_writer_body(body, plan=plan)

        self.assertTrue(ok, message)

    def test_validate_insight_plan_response_allows_incompatible_goal_gap_type_with_diagnostic(self):
        point_coords = {"a": (0, 0), "b": (4, 0), "c": (0, 4), "d": (4, 4), "h": (2, 2)}
        insight_slots = {
            "goal_family": "eqratio",
            "goal_gap_type": "ratio_transfer",
            "required_aux_effect": "h is the midpoint of ad",
            "first_bridge_checkpoint": "ratio ad to hd equals ratio bc to ck",
            "pre_goal_checkpoint": "ratio ad to hd equals ratio bc to ck",
            "evidence_windows": [],
        }
        plan = {
            "visible_facts": ["ab equals cd"],
            "image_scan": ["line ab and line cd look parallel"],
            "goal_gap_type": "angle_transfer",
            "goal_gap_text": "the visible givens still do not transfer the needed ratio from the a-side onto the d-side",
            "required_aux_effect": "h is the midpoint of ad",
            "aux_construction": "construct point h such that h is the midpoint of ad",
            "aux_selection_reason": "the midpoint at h is the first local helper relation before the ratio side can be revisited around a and d",
        }

        ok, message, cleaned = validate_insight_plan_response(
            plan,
            point_coords=point_coords,
            visible_goal="eqratio a d a h b c c h",
            aux_part="<aux> x00 h : midp h a d [001] ; </aux>",
            visible_text_facts=[{"relation": "ab equals cd"}],
            insight_slots=insight_slots,
        )

        self.assertTrue(ok, message)
        self.assertIn("goal_family_conflict", cleaned["goal_gap_type_diagnostics"])
        self.assertIn("slot_mismatch", cleaned["goal_gap_type_diagnostics"])

    def test_validate_insight_plan_response_keeps_aux_mismatch_as_audit_signal(self):
        point_coords = {"a": (0, 0), "b": (4, 0), "c": (0, 4), "d": (4, 4), "f": (2, 2)}
        insight_slots = {
            "goal_family": "eqangle",
            "goal_gap_type": "angle_transfer",
            "required_aux_effect": "a, c, d, f are concyclic",
            "first_bridge_checkpoint": "b, e, f are collinear",
            "pre_goal_checkpoint": "angle ab/bf equals angle cd/df",
            "evidence_windows": [],
        }
        plan = {
            "visible_facts": ["ab equals ac"],
            "image_scan": ["points b, d, and e appear nearly collinear"],
            "goal_gap_type": "angle_transfer",
            "goal_gap_text": "the visible givens still do not transfer the angle at the b-side onto the d-side",
            "required_aux_effect": "a, c, d, f are concyclic",
            "aux_construction": "construct point f such that a, c, d, f are concyclic and b, d, f are collinear",
            "aux_selection_reason": "the cyclic helper around a, c, d, and f is the missing local carrier before the d-side can reuse the old frame",
        }

        ok, message, cleaned = validate_insight_plan_response(
            plan,
            point_coords=point_coords,
            visible_goal="eqangle a b b c c d d e",
            aux_part="<aux> x00 f : cyclic a c d f [001] ; x00 f : coll b e f [002] ; </aux>",
            visible_text_facts=[{"relation": "ab equals ac"}],
            insight_slots=insight_slots,
        )

        self.assertTrue(ok, message)
        self.assertFalse(cleaned["aux_construction_matches_canonical"])
        self.assertEqual(cleaned["aux_construction_audit_signal"], "aux_construction_mismatch")

        generation_audit = audit_generation_quality(
            {"grid_coord": point_coords},
            {"plan_parsed": cleaned, "write_output": "", "generation_style": "insight_v1"},
            "<aux> x00 f : cyclic a c d f [001] ; x00 f : coll b e f [002] ; </aux>",
        )
        self.assertIn("aux_construction_mismatch", generation_audit["issues"])

    def test_build_scripted_insight_writer_body_drops_immediate_gives_sentence(self):
        plan = {
            "visible_facts": ["ab equals ac"],
            "image_scan": ["points b, d, and f appear nearly collinear"],
            "goal_gap_text": "the visible givens still do not transfer the angle at the b-side onto the d-side",
            "required_aux_effect": "a, c, d, f are concyclic",
            "aux_construction": "construct point f such that a, c, d, f are concyclic and b, d, f are collinear",
            "aux_selection_reason": "this helper creates the cyclic carrier that the slot requires before the old side can be reused",
        }

        writer_body = build_scripted_insight_writer_body(plan)

        self.assertNotIn("This immediately gives", writer_body)
        self.assertIn("a, c, d, f are concyclic", writer_body)

    def test_process_and_generate_sft_insight_v1_failure_does_not_fallback_to_dossier(self):
        record = dict(_load_record(1))
        record["image_path"] = "fixture.png"
        failed_generation = {
            "success": False,
            "thinking": None,
            "plan_prompt": None,
            "write_prompt": None,
            "plan_output": None,
            "plan_parsed": None,
            "insight_slots": None,
            "insight_plan_parsed": None,
            "attempts_used": 1,
            "elapsed_seconds": 0.0,
            "error": "insight_failed",
            "write_output": None,
            "generation_style": "insight_v1",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            input_path = temp_dir_path / "input.jsonl"
            output_path = temp_dir_path / "out.jsonl"
            run_dir = temp_dir_path / "artifacts"

            input_path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
            (temp_dir_path / "fixture.png").write_bytes(b"fixture-image")

            with patch(
                "experiments.cot_sft_generation.generate_cot_sft.generate_insight_thinking",
                return_value=failed_generation,
            ), patch(
                "experiments.cot_sft_generation.generate_cot_sft.generate_dossier_thinking",
            ) as dossier_mock:
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

            dossier_mock.assert_not_called()
            self.assertEqual(output_path.read_text(encoding="utf-8"), "")
            self.assertEqual(result["summary"]["exported_items"], 0)

            item_records = [
                json.loads(line)
                for line in (run_dir / "item_records.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(item_records[0]["generation_style"], "insight_v1")
            self.assertFalse(item_records[0]["success"])
            self.assertFalse(item_records[0]["exported_to_dataset"])
            self.assertEqual(item_records[0]["dataset_filter_reason"], "generation_failed")
            self.assertEqual(item_records[0]["error"], "insight_failed")

    def test_process_and_generate_sft_insight_v1_writer_failure_does_not_use_scripted_body(self):
        record, scripted_plan, _ = _build_scripted_insight_fixture(1)
        record["image_path"] = "fixture.png"
        invalid_writer_body = (
            "The gap is still unresolved. Because a, c, d, f are concyclic, because [012] AR, "
            "the hidden proof closes."
        )

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "experiments.cot_sft_generation.generate_cot_sft.generate_dossier_thinking",
        ) as dossier_mock:
            result, output_records, item_records = _run_insight_pipeline(
                record,
                Path(temp_dir),
                call_model_side_effect=[
                    json.dumps(scripted_plan, ensure_ascii=False),
                    invalid_writer_body,
                ],
            )

        dossier_mock.assert_not_called()
        self.assertEqual(output_records, [])
        self.assertEqual(result["summary"]["exported_items"], 0)
        self.assertFalse(item_records[0]["success"])
        self.assertFalse(item_records[0]["exported_to_dataset"])
        self.assertEqual(item_records[0]["dataset_filter_reason"], "generation_failed")
        self.assertEqual(item_records[0]["write_output"], invalid_writer_body)

    def test_process_and_generate_sft_insight_v1_hard_audit_issue_blocks_export_only(self):
        record, scripted_plan, writer_body = _build_scripted_insight_fixture(1)
        record["image_path"] = "fixture.png"

        with tempfile.TemporaryDirectory() as temp_dir:
            result, output_records, item_records = _run_insight_pipeline(
                record,
                Path(temp_dir),
                call_model_side_effect=[
                    json.dumps(scripted_plan, ensure_ascii=False),
                    writer_body,
                ],
                audit_result={"issues": ["no_proof_echo"], "has_issue": True},
            )

        self.assertEqual(output_records, [])
        self.assertEqual(result["summary"]["surface_pass_items"], 1)
        self.assertEqual(result["summary"]["exported_items"], 0)
        self.assertEqual(result["summary"]["filtered_generation_audit_items"], 1)
        self.assertEqual(result["summary"]["exported_rate"], 0.0)
        self.assertTrue(item_records[0]["surface_pass"])
        self.assertTrue(item_records[0]["success"])
        self.assertFalse(item_records[0]["exported_to_dataset"])
        self.assertEqual(item_records[0]["dataset_filter_reason"], "generation_audit_hard_issue")

    def test_process_and_generate_sft_insight_v1_soft_audit_issue_still_exports(self):
        record, scripted_plan, writer_body = _build_scripted_insight_fixture(1)
        record["image_path"] = "fixture.png"

        with tempfile.TemporaryDirectory() as temp_dir:
            result, output_records, item_records = _run_insight_pipeline(
                record,
                Path(temp_dir),
                call_model_side_effect=[
                    json.dumps(scripted_plan, ensure_ascii=False),
                    writer_body,
                ],
                audit_result={"issues": ["goal_gap_specificity"], "has_issue": True},
            )

        self.assertEqual(len(output_records), 1)
        self.assertEqual(result["summary"]["generation_audit_issue_items"], 1)
        self.assertEqual(result["summary"]["filtered_generation_audit_items"], 0)
        self.assertEqual(result["summary"]["exported_items"], 1)
        self.assertTrue(item_records[0]["exported_to_dataset"])
        self.assertIsNone(item_records[0]["dataset_filter_reason"])

    def test_process_and_generate_sft_runs_insight_v1_and_persists_artifacts(self):
        record, scripted_plan, writer_body = _build_scripted_insight_fixture(1)
        record["image_path"] = "fixture.png"

        with tempfile.TemporaryDirectory() as temp_dir:
            result, output_records, item_records = _run_insight_pipeline(
                record,
                Path(temp_dir),
                call_model_side_effect=[
                    json.dumps(scripted_plan, ensure_ascii=False),
                    writer_body,
                ],
            )

            self.assertEqual(result["summary"]["generation_style"], "insight_v1")
            self.assertEqual(len(output_records), 1)
            self.assertIn("<thinking>", output_records[0]["thinking"])
            self.assertTrue(output_records[0]["output"].endswith(output_records[0]["aux"]))
            self.assertEqual(result["summary"]["exported_items"], 1)
            self.assertEqual(result["summary"]["filtered_generation_audit_items"], 0)
            self.assertEqual(result["summary"]["exported_rate"], 1.0)
            self.assertEqual(item_records[0]["generation_style"], "insight_v1")
            self.assertIsInstance(item_records[0]["insight_slots"], dict)
            self.assertIsInstance(item_records[0]["insight_plan_parsed"], dict)
            self.assertNotIn("aux_immediate_effects", item_records[0]["insight_plan_parsed"])
            self.assertTrue(item_records[0]["exported_to_dataset"])
            self.assertIsNone(item_records[0]["dataset_filter_reason"])

    def test_process_and_generate_sft_continues_after_unexpected_item_exception(self):
        failing_record = dict(_load_record(0))
        succeeding_record = dict(_load_record(1))
        failing_record["image_path"] = "fixture.png"
        succeeding_record["image_path"] = "fixture.png"
        successful_generation = {
            "success": True,
            "thinking": "<thinking>From the visible figure, one stable fact remains usable. The real gap is that the target still needs one local helper effect around the goal-side objects. So the helper should first create one explicit relation that reconnects the old figure before the last transfer. Construct point h so the needed helper relation is available. That helper keeps the route visible-only and short.</thinking>",
            "plan_prompt": None,
            "write_prompt": None,
            "plan_output": None,
            "plan_parsed": {"generation_style": "insight_v1"},
            "insight_slots": {"goal_gap_type": "angle_transfer"},
            "insight_plan_parsed": {"generation_style": "insight_v1"},
            "attempts_used": 1,
            "elapsed_seconds": 0.0,
            "error": None,
            "write_output": "body",
            "generation_style": "insight_v1",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            input_path = temp_dir_path / "input.jsonl"
            output_path = temp_dir_path / "out.jsonl"
            run_dir = temp_dir_path / "artifacts"
            input_path.write_text(
                "\n".join(
                    [
                        json.dumps(failing_record, ensure_ascii=False),
                        json.dumps(succeeding_record, ensure_ascii=False),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (temp_dir_path / "fixture.png").write_bytes(b"fixture-image")

            def fake_generate_insight_thinking(record, **kwargs):
                del kwargs
                if record["_source_index"] == 0:
                    raise RuntimeError("boom")
                return successful_generation

            with patch(
                "experiments.cot_sft_generation.generate_cot_sft.generate_insight_thinking",
                side_effect=fake_generate_insight_thinking,
            ), patch(
                "experiments.cot_sft_generation.generate_cot_sft.audit_generation_quality",
                return_value={"issues": [], "has_issue": False},
            ):
                result = process_and_generate_sft(
                    input_jsonl=str(input_path),
                    output_jsonl=str(output_path),
                    sample_size=2,
                    num_workers=2,
                    model_name="fixture-model",
                    verbose=True,
                    random_sample=False,
                    process_all=False,
                    max_retries=1,
                    generation_style="insight_v1",
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
            item_audits = [
                json.loads(line)
                for line in (run_dir / "item_audits.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))

            self.assertEqual(len(output_records), 1)
            self.assertEqual(len(item_records), 2)
            self.assertEqual(len(item_audits), 2)
            self.assertEqual(summary["sampled_items"], 2)
            self.assertEqual(summary["surface_fail_items"], 1)
            self.assertEqual(summary["exported_items"], 1)
            self.assertEqual(result["summary"]["exported_items"], 1)

            failed_item = item_records[0]
            succeeded_item = item_records[1]
            self.assertFalse(failed_item["surface_pass"])
            self.assertFalse(failed_item["exported_to_dataset"])
            self.assertEqual(failed_item["dataset_filter_reason"], "generation_failed")
            self.assertIn("unexpected_exception: RuntimeError: boom", failed_item["error"])
            self.assertTrue(succeeded_item["exported_to_dataset"])

    def test_validate_thinking_response_allows_plain_math_layout_but_still_rejects_hidden_markers(self):
        good_thinking = (
            "<thinking>"
            "The visible figure still lacks one local equality frame around a, b, c, and d. "
            "Writing \\(AB = CD\\) just restates the visible length balance, and \\triangle abd can now be compared with \\triangle cbd after the helper is chosen. "
            "Construct point h so that \\overline{AH} = \\overline{HD}, because this midpoint relation is the local bridge the ratio argument was missing before the route returns to a and d."
            "</thinking>"
        )

        ok, message = validate_thinking_response(
            good_thinking,
            {"a": (0, 0), "b": (4, 0), "c": (0, 4), "d": (4, 4), "h": (2, 2)},
            require_coord_tags=False,
            max_total_len=2600,
        )
        self.assertTrue(ok, message)

        bad_thinking = good_thinking.replace("\\triangle abd", "<proof> \\triangle abd")
        ok, message = validate_thinking_response(
            bad_thinking,
            {"a": (0, 0), "b": (4, 0), "c": (0, 4), "d": (4, 4), "h": (2, 2)},
            require_coord_tags=False,
            max_total_len=2600,
        )
        self.assertFalse(ok)
        self.assertIn("Forbidden leakage pattern", message)

    def test_process_and_generate_sft_insight_v1_uses_unbounded_thinking_validation_budget(self):
        record, scripted_plan, writer_body = _build_scripted_insight_fixture(1)
        record["image_path"] = "fixture.png"
        captured = {}

        def fake_validate_thinking_response(
            output_text,
            point_coords,
            require_coord_tags=False,
            max_total_len=2200,
            max_coord_tags=4,
        ):
            del output_text, point_coords, require_coord_tags, max_coord_tags
            captured["max_total_len"] = max_total_len
            return True, "ok"

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "experiments.cot_sft_generation.generate_cot_sft.validate_thinking_response",
            side_effect=fake_validate_thinking_response,
        ):
            result, output_records, item_records = _run_insight_pipeline(
                record,
                Path(temp_dir),
                call_model_side_effect=[
                    json.dumps(scripted_plan, ensure_ascii=False),
                    writer_body,
                ],
                audit_result={"issues": [], "has_issue": False},
            )

        self.assertEqual(captured["max_total_len"], None)
        self.assertEqual(len(output_records), 1)
        self.assertTrue(item_records[0]["surface_pass"])
        self.assertEqual(result["summary"]["exported_items"], 1)


if __name__ == "__main__":
    unittest.main()
