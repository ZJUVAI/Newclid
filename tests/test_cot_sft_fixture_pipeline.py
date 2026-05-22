import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments.cot_sft_generation.generate_cot_sft import (
    build_scripted_dossier_writer_body,
    build_scripted_dossier_skeleton,
    generate_dossier_thinking,
    process_and_generate_sft,
    validate_dossier_plan_response,
    validate_dossier_writer_body,
)
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

DOSSIER_PARTIAL_CRITIC_OUTPUT = {
    "approved": False,
    "issues": ["tighten the final closure wording."],
    "summary": "the route works after a small closing adjustment.",
    "revised_dossier": {
        "goal_closure": [
            {
                "claim": "ad equals bc",
                "supports": ["bridge_chain[1]", "visible_facts[2]"],
                "why_next": "this is the target relation.",
            }
        ]
    },
}

DOSSIER_INVALID_CRITIC_PATCH_OUTPUT = {
    "approved": False,
    "issues": ["the bridge support refs need cleanup."],
    "summary": "the route is close, but this patch is malformed.",
    "revised_dossier": {
        "bridge_chain": [
            {
                "claim": "ah equals bh",
                "supports": ["aux_direct_relations[1]"],
                "why_next": "this malformed patch should be ignored in favor of the original validated dossier.",
            }
        ]
    },
}

DOSSIER_CRITIC_REJECTION_OUTPUT = {
    "approved": False,
    "issues": ["the route does not directly prove the goal yet."],
    "summary": "reject and request a cleaner route.",
}

DOSSIER_WEAK_EQANGLE_PLAN_OUTPUT = {
    "visible_facts": [
        "angle ab/bc equals angle bc/ac",
        "ab equals ac",
        "ad equals bc",
        "angle ab/bc equals angle bc/bd",
        "ae equals bc",
        "angle ab/bc equals angle bc/be",
    ],
    "image_scan": [
        "points a, c, d appear to lie on a circle",
        "points b, d seem collinear",
        "angles at b and c suggest symmetry around bc",
    ],
    "coordinate_checks": [],
    "goal_obstacle": "the visible figure does not directly show how angles at a relate across ab, ac, ad, and ae.",
    "aux_motivation": "adding a helper point f can create cyclic properties and collinearities that link the angles at a.",
    "construction": "construct point f such that a, c, d, f are concyclic and b, d, f are collinear",
    "aux_immediate_effects": [
        "a, c, d, f are concyclic",
        "b, d, f are collinear",
    ],
    "bridge_chain": [
        {
            "claim": "angle ac/ad equals angle cf/df",
            "supports": ["aux_immediate_effects[0]", "image_scan[0]"],
            "why_next": "this uses the cyclic property to relate angles at a and f.",
        },
        {
            "claim": "angle ac/af equals angle cd/df",
            "supports": ["aux_immediate_effects[0]", "bridge_chain[0]"],
            "why_next": "this extends the cyclic angle relation further along the circle.",
        },
        {
            "claim": "angle ad/af equals angle cd/cf",
            "supports": ["aux_immediate_effects[0]", "bridge_chain[1]"],
            "why_next": "this completes the angle relations within the cyclic quadrilateral.",
        },
        {
            "claim": "angle af/df equals angle df/cd",
            "supports": ["aux_immediate_effects[0]", "bridge_chain[2]"],
            "why_next": "this ties the angles at f back to the original points.",
        },
    ],
    "goal_closure": [
        {
            "claim": "angle ab/ac equals angle ad/ae",
            "supports": [
                "visible_facts[0]",
                "visible_facts[3]",
                "visible_facts[5]",
                "bridge_chain[3]",
            ],
            "why_next": "this combines the given angle equalities with the constructed angle relations to reach the target.",
        }
    ],
}

WRITER_BODY = (
    "The obstacle is to transfer the d-side and c-side into one local helper frame before the final equality closes. "
    "Using a=(0,0), b=(4,0), and c=(0,2), the midpoint of bc is (2.0, 1.0), which differs from a by residual 2.2361 and the collinearity residual is 1.7889, so point a looks like the midpoint of bc. "
    "Construct point h such that ah equals dh and bh equals ch. "
    "Because point a looks like the midpoint of bc and ac equals bd, ah equals bh, and this creates the first shared equality in the helper frame. "
    "Because ah equals bh and ac equals bd, dh equals ch, and this transfers the helper equality to the d-side and c-side. "
    "Therefore ad equals bc."
)

DOSSIER_PLAN_OUTPUT = {
    "visible_facts": ["line ab is parallel to line cd", "ac equals bd"],
    "image_scan": ["point a looks like the midpoint of bc"],
    "coordinate_checks": [
        {
            "relation": "point a looks like the midpoint of bc",
            "points": ["a", "b", "c"],
            "calc_type": "midpoint",
            "why_it_matters": "this gives one image-based balance cue before the helper is added.",
        }
    ],
    "goal_obstacle": "the target still needs one clean transfer from the helper frame back to the d-side and c-side.",
    "aux_motivation": "a helper should create two local equalities first and then reconnect them to the visible outer frame.",
    "construction": "construct point h such that ah equals dh and bh equals ch.",
    "aux_immediate_effects": ["ah equals dh", "bh equals ch"],
    "bridge_chain": [
        {
            "claim": "ah equals bh",
            "supports": ["visible_facts[2]", "coordinate_checks[1]"],
            "why_next": "this creates one shared balance inside the helper frame.",
        },
        {
            "claim": "dh equals ch",
            "supports": ["aux_immediate_effects[1]", "bridge_chain[1]"],
            "why_next": "this transfers the helper balance to the d-side and c-side.",
        },
    ],
    "goal_closure": [
        {
            "claim": "ad equals bc",
            "supports": ["bridge_chain[2]", "visible_facts[2]"],
            "why_next": "this is the target relation.",
        }
    ],
}

DOSSIER_WRITER_BODY = (
    "The obstacle is to transfer the d-side and c-side through one helper frame before the target equality closes. "
    "The figure also suggests that point a looks like the midpoint of bc, so the outer balance around a, b, and c is worth tracking. "
    "Construct point h such that ah equals dh and bh equals ch. "
    "From the construction, ah equals dh and bh equals ch. "
    "These equalities give ah equals bh, which creates one shared balance inside the helper frame. "
    "Then dh equals ch, so that helper balance reaches the d-side and c-side. "
    "Therefore ad equals bc."
)


class CotSftFixturePipelineTest(unittest.TestCase):
    @staticmethod
    def _extract_aux_and_rest(record):
        llm_output = record.get("llm_output_renamed", "")
        aux_start = llm_output.lower().find("<aux>")
        aux_end = llm_output.lower().find("</aux>")
        aux_part = llm_output[aux_start: aux_end + 6] if aux_start >= 0 and aux_end >= 0 else ""
        sanitized_rest = llm_output[aux_end + 6:] if aux_end >= 0 else llm_output
        return aux_part, sanitized_rest

    @staticmethod
    def _load_quality_review_record(index):
        benchmark_path = Path("experiments/cot_sft_generation/benchmarks/quality_review_v1/quality_review_v1_input.jsonl")
        records = [
            json.loads(line)
            for line in benchmark_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return records[index]

    def test_validate_dossier_plan_response_accepts_zero_based_supports_and_canonicalizes_aux(self):
        dossier = {
            "visible_facts": ["ad equals bc", "g is the midpoint of be"],
            "image_scan": [
                "points a, c, and e lie on a straight line",
                "lines ae and cf intersect at right angles",
            ],
            "goal_obstacle": "the target ratio still needs one helper link back to the visible figure.",
            "aux_motivation": "a midpoint helper can create one local balance first and then reconnect it to the old figure.",
            "construction": "construct point h as the midpoint of ad.",
            "aux_immediate_effects": [
                "ah equals dh",
                "h lies on the line segment ad",
            ],
            "bridge_chain": [
                {
                    "claim": "ah equals dh",
                    "supports": ["aux_immediate_effects[0]"],
                    "why_next": "this states the first local balance from the midpoint construction.",
                },
                {
                    "claim": "dh equals ah",
                    "supports": ["bridge_chain[0]"],
                    "why_next": "this keeps the same helper equality available when we return to the visible target.",
                },
            ],
            "goal_closure": [
                {
                    "claim": "ad equals bc",
                    "supports": ["visible_facts[0]", "bridge_chain[0]"],
                    "why_next": "this is the target equality relation.",
                }
            ],
        }

        ok, message, cleaned = validate_dossier_plan_response(
            dossier,
            point_coords={
                "a": [134, 196],
                "b": [226, 184],
                "c": [217, 115],
                "d": [124, 128],
                "e": [187, 144],
                "f": [247, 146],
                "g": [206, 164],
            },
            visible_goal="cong a d b c",
            aux_part="<aux> x00 h : midp h a d [008] ; </aux>",
        )

        self.assertTrue(ok, message)
        self.assertEqual(cleaned["image_scan"][0], "a, c, e are collinear")
        self.assertEqual(cleaned["image_scan"][1], "line ae is perpendicular to line cf")
        self.assertEqual(cleaned["construction"], "construct point h such that h is the midpoint of ad")
        self.assertEqual(cleaned["aux_immediate_effects"][1], "a, d, h are collinear")
        self.assertEqual(cleaned["bridge_chain"][0]["resolved_supports"][0], "ah equals dh")
        self.assertEqual(cleaned["bridge_chain"][1]["resolved_supports"][0], "ah equals dh")

    def test_validate_dossier_plan_response_rejects_unsupported_similarity_bridge(self):
        dossier = {
            "visible_facts": [
                "line ac is perpendicular to line be",
                "a, c, e are collinear",
                "line ae is perpendicular to line cf",
                "g is the midpoint of be",
            ],
            "image_scan": [
                "a, c, e are collinear",
                "line ae is perpendicular to line cf",
                "line bd is perpendicular to line bf",
            ],
            "goal_obstacle": "the target ratio still lacks one grounded helper route back to the visible figure.",
            "aux_motivation": "a midpoint helper should first create a local balance and then reconnect it to the visible outer frame.",
            "construction": "construct point h as the midpoint of ad.",
            "aux_immediate_effects": ["ah equals dh", "a, d, h are collinear"],
            "bridge_chain": [
                {
                    "claim": "triangles ahe and bhf are similar",
                    "supports": ["visible_facts[2]", "visible_facts[3]", "aux_immediate_effects[1]"],
                    "why_next": "this would start the ratio transfer.",
                },
                {
                    "claim": "ratio ae to bd equals ratio eh to fh",
                    "supports": ["bridge_chain[1]"],
                    "why_next": "this would push the helper ratio toward the goal.",
                },
            ],
            "goal_closure": [
                {
                    "claim": "ratio ae to bd equals ratio eg to bf",
                    "supports": ["bridge_chain[2]", "visible_facts[4]"],
                    "why_next": "this is the target ratio relation.",
                }
            ],
        }

        ok, message, _ = validate_dossier_plan_response(
            dossier,
            point_coords={
                "a": [134, 196],
                "b": [226, 184],
                "c": [217, 115],
                "d": [124, 128],
                "e": [187, 144],
                "f": [247, 146],
                "g": [206, 164],
            },
            visible_goal="eqratio a e b d e g b f",
            aux_part="<aux> x00 h : midp h a d [008] ; </aux>",
        )

        self.assertFalse(ok)
        self.assertIn("unsupported angle/ratio/similar segments", message)

    def test_validate_dossier_writer_body_rejects_internal_planning_refs(self):
        ok, message, cleaned = validate_dossier_plan_response(
            DOSSIER_PLAN_OUTPUT,
            point_coords={
                "a": [0, 0],
                "b": [4, 0],
                "c": [0, 2],
                "d": [4, 2],
            },
            visible_goal="cong a d b c",
            aux_part="<aux>x00 h : cong a h d h; cong b h c h</aux>",
        )
        self.assertTrue(ok, message)

        bad_body = (
            "The obstacle is to transfer the d-side and c-side through one helper frame before the target equality closes. "
            "Construct point h such that ah equals dh and bh equals ch. "
            "From aux_immediate_effects[0], ah equals dh, and bridge_chain[0] then gives ah equals bh inside the helper frame. "
            "Finally goal_closure[0] gives ad equals bc."
        )

        writer_ok, writer_message = validate_dossier_writer_body(
            bad_body,
            visible_goal="cong a d b c",
            plan=cleaned,
        )

        self.assertFalse(writer_ok)
        self.assertIn("Internal planning reference detected", writer_message)

    def test_build_scripted_dossier_skeleton_accepts_real_simtri_benchmark_sample(self):
        record = self._load_quality_review_record(3)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)

        ok, message, dossier = build_scripted_dossier_skeleton(
            record,
            aux_part,
            sanitized_rest,
            record["point_coords_grid"],
            "simtri a c g f a g",
        )

        self.assertTrue(ok, message)
        self.assertGreaterEqual(len(dossier["bridge_chain"]), 3)
        self.assertEqual(dossier["goal_closure"][-1]["claim"], "triangles acg and fag are similar")

    def test_build_scripted_dossier_skeleton_accepts_real_eqratio_benchmark_sample(self):
        record = self._load_quality_review_record(0)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)

        ok, message, dossier = build_scripted_dossier_skeleton(
            record,
            aux_part,
            sanitized_rest,
            record["point_coords_grid"],
            "eqratio a e b d e g b f",
        )

        self.assertTrue(ok, message)
        self.assertGreaterEqual(len(dossier["coordinate_checks"]), 1)
        bridge_claims = [step["claim"] for step in dossier["bridge_chain"]]
        self.assertEqual(
            bridge_claims,
            [
                "angle ab/ah equals angle bg/ac",
                "ratio ah to dh equals ratio eg to bg",
                "ratio ad to ah equals ratio be to eg",
                "line cf is parallel to line eg",
                "ratio ac to ae equals ratio cf to eg",
            ],
        )
        self.assertCountEqual(
            dossier["bridge_chain"][3]["resolved_supports"],
            [
                "segments be and cf look parallel",
                "line be is parallel to line eg",
            ],
        )
        self.assertEqual(dossier["goal_closure"][-1]["claim"], "ratio ae to bd equals ratio eg to bf")

    def test_build_scripted_dossier_skeleton_accepts_real_simtrir_benchmark_sample(self):
        record = self._load_quality_review_record(2)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)

        ok, message, dossier = build_scripted_dossier_skeleton(
            record,
            aux_part,
            sanitized_rest,
            record["point_coords_grid"],
            "simtrir b d e c e g",
        )

        self.assertTrue(ok, message)
        self.assertGreaterEqual(len(dossier["coordinate_checks"]), 1)
        bridge_claims = [step["claim"] for step in dossier["bridge_chain"]]
        self.assertEqual(
            bridge_claims,
            [
                "triangles bch and cfh are similar",
                "ratio bh to ch equals ratio ch to fh",
                "ratio bd to be equals ratio ce to cg",
            ],
        )
        self.assertEqual(dossier["goal_closure"][-1]["claim"], "triangles bde and ceg are similar")

    def test_build_scripted_dossier_skeleton_keeps_aux_reconnect_for_real_contrir_transfer_sample(self):
        record = self._load_quality_review_record(5)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)

        ok, message, dossier = build_scripted_dossier_skeleton(
            record,
            aux_part,
            sanitized_rest,
            record["point_coords_grid"],
            "contrir b d i i f b",
        )

        self.assertTrue(ok, message)
        self.assertEqual(dossier["bridge_chain"][0]["claim"], "cf equals cj")
        self.assertEqual(dossier["goal_closure"][-1]["claim"], "triangles bdi and ifb are congruent")

    def test_build_scripted_dossier_skeleton_accepts_real_late_fact_simtrir_benchmark_sample(self):
        record = self._load_quality_review_record(9)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)

        ok, message, dossier = build_scripted_dossier_skeleton(
            record,
            aux_part,
            sanitized_rest,
            record["point_coords_grid"],
            "simtrir a g i i g h",
        )

        self.assertTrue(ok, message)
        self.assertIn("line dh is parallel to line eg", dossier["visible_facts"])
        self.assertIn("b, d, h, i are concyclic", dossier["visible_facts"])
        self.assertEqual(dossier["goal_closure"][-1]["claim"], "triangles agi and igh are similar")

    def test_build_scripted_dossier_skeleton_accepts_real_contrir_benchmark_sample(self):
        record = self._load_quality_review_record(11)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)

        ok, message, dossier = build_scripted_dossier_skeleton(
            record,
            aux_part,
            sanitized_rest,
            record["point_coords_grid"],
            "contrir a c h d b h",
        )

        self.assertTrue(ok, message)
        self.assertIn("d, g, h are collinear", dossier["visible_facts"])
        self.assertEqual(
            [step["claim"] for step in dossier["bridge_chain"]],
            [
                "a, c, i are collinear",
                "bh equals ch",
                "angle bi/bh equals angle ch/ci",
            ],
        )
        self.assertEqual(dossier["goal_closure"][-1]["claim"], "triangles ach and dbh are congruent")

    def test_build_scripted_dossier_skeleton_preserves_goal_side_tail_steps_for_real_eqangle_sample(self):
        record = self._load_quality_review_record(1)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)

        ok, message, dossier = build_scripted_dossier_skeleton(
            record,
            aux_part,
            sanitized_rest,
            record["point_coords_grid"],
            "eqangle a b a c a d a e",
        )

        self.assertTrue(ok, message)
        bridge_claims = [step["claim"] for step in dossier["bridge_chain"]]
        self.assertEqual(
            bridge_claims,
            [
                "triangles adf and cfd are similar",
                "ad equals cf",
                "bc equals cf",
            ],
        )
        self.assertEqual(dossier["goal_closure"][-1]["claim"], "angle ab/ac equals angle ad/ae")

    def test_build_scripted_dossier_skeleton_prefers_tail_only_route_for_real_simtri_sample(self):
        record = self._load_quality_review_record(3)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)

        ok, message, dossier = build_scripted_dossier_skeleton(
            record,
            aux_part,
            sanitized_rest,
            record["point_coords_grid"],
            "simtri a c g f a g",
        )

        self.assertTrue(ok, message)
        self.assertEqual(
            [step["claim"] for step in dossier["bridge_chain"]],
            [
                "triangles afh and ehg are similar",
                "ratio af to ah equals ratio eh to eg",
                "ratio ac to af equals ratio cg to ag",
            ],
        )
        self.assertEqual(dossier["goal_closure"][-1]["claim"], "triangles acg and fag are similar")

    def test_generate_dossier_thinking_plan_only_falls_back_to_scripted_skeleton(self):
        record = self._load_quality_review_record(3)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "fixture.png"
            image_path.write_bytes(b"fixture-image")

            with patch(
                "experiments.cot_sft_generation.generate_cot_sft.call_model",
                side_effect=["not a json plan"],
            ):
                result = generate_dossier_thinking(
                    record=record,
                    image_path=image_path,
                    aux_part=aux_part,
                    sanitized_rest=sanitized_rest,
                    model_name="fixture-model",
                    max_retries=1,
                    verbose=True,
                    plan_mode="plan_only",
                )

        self.assertTrue(result["success"])
        self.assertEqual(result["generation_style"], "dossier_v1")
        self.assertIsNotNone(result["plan_parsed"])
        self.assertEqual(result["plan_parsed"]["goal_closure"][-1]["claim"], "triangles acg and fag are similar")

    def test_generate_dossier_thinking_scripted_fallback_skips_critic_in_full_generation(self):
        record = self._load_quality_review_record(3)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)
        writer_output = (
            "The obstacle is to reconnect the helper circles to the target triangle comparison. "
            "Construct point h so that a, b, e, h are concyclic and a, c, g, h are concyclic. "
            "This immediately gives a, b, e, h are concyclic and a, c, g, h are concyclic. "
            "Then angle ac/ag equals angle ch/gh, so one goal-side direction is now available. "
            "Next angle ac/ah equals angle cg/gh, which keeps the route tied to triangles around a, c, g, and h. "
            "After that ratio ac to af equals ratio cg to ag, so the side comparison needed for the target is in place. "
            "Therefore triangles acg and fag are similar."
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "fixture.png"
            image_path.write_bytes(b"fixture-image")

            with patch(
                "experiments.cot_sft_generation.generate_cot_sft.call_model",
                side_effect=["not a json plan"],
            ) as call_model_mock, patch(
                "experiments.cot_sft_generation.generate_cot_sft.run_plan_critic_stage",
            ) as critic_mock, patch(
                "experiments.cot_sft_generation.generate_cot_sft.run_writer_stage",
                return_value={
                    "success": True,
                    "output": writer_output,
                    "attempts_used": 1,
                    "elapsed_seconds": 0.01,
                    "error": None,
                },
            ) as writer_mock, patch(
                "experiments.cot_sft_generation.generate_cot_sft.validate_thinking_response",
                return_value=(True, "Valid thinking"),
            ):
                result = generate_dossier_thinking(
                    record=record,
                    image_path=image_path,
                    aux_part=aux_part,
                    sanitized_rest=sanitized_rest,
                    model_name="fixture-model",
                    max_retries=1,
                    verbose=True,
                )

        self.assertTrue(result["success"])
        self.assertEqual(call_model_mock.call_count, 1)
        critic_mock.assert_not_called()
        writer_mock.assert_called_once()
        self.assertIn("triangles acg and fag are similar", result["thinking"])

    def test_generate_dossier_thinking_scripted_fallback_uses_scripted_writer_after_writer_failure(self):
        record = self._load_quality_review_record(0)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "fixture.png"
            image_path.write_bytes(b"fixture-image")

            with patch(
                "experiments.cot_sft_generation.generate_cot_sft.call_model",
                side_effect=["not a json plan"],
            ), patch(
                "experiments.cot_sft_generation.generate_cot_sft.run_writer_stage",
                return_value={
                    "success": False,
                    "output": None,
                    "attempts_used": 1,
                    "elapsed_seconds": 0.01,
                    "error": "Writer body must explicitly realize bridge_chain[1]",
                },
            ), patch(
                "experiments.cot_sft_generation.generate_cot_sft.validate_thinking_response",
                return_value=(True, "Valid thinking"),
            ):
                result = generate_dossier_thinking(
                    record=record,
                    image_path=image_path,
                    aux_part=aux_part,
                    sanitized_rest=sanitized_rest,
                    model_name="fixture-model",
                    max_retries=1,
                    verbose=True,
                )

        self.assertTrue(result["success"])
        self.assertIn("ratio ae to bd equals ratio eg to bf", result["thinking"])

    def test_generate_dossier_thinking_scripted_fallback_short_circuits_writer_retries(self):
        record = self._load_quality_review_record(0)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "fixture.png"
            image_path.write_bytes(b"fixture-image")

            with patch(
                "experiments.cot_sft_generation.generate_cot_sft.call_model",
                side_effect=[
                    "not a json plan",
                    "still not a json plan",
                    "final invalid plan output",
                    "This target still needs the desired ratio before the helper can finish.",
                ],
            ) as call_model_mock, patch(
                "experiments.cot_sft_generation.generate_cot_sft.validate_thinking_response",
                return_value=(True, "Valid thinking"),
            ):
                result = generate_dossier_thinking(
                    record=record,
                    image_path=image_path,
                    aux_part=aux_part,
                    sanitized_rest=sanitized_rest,
                    model_name="fixture-model",
                    max_retries=3,
                    verbose=True,
                )

        self.assertTrue(result["success"])
        self.assertEqual(call_model_mock.call_count, 4)
        self.assertIn("ratio ae to bd equals ratio eg to bf", result["thinking"])

    def test_generate_dossier_thinking_falls_back_to_scripted_skeleton_after_critic_rejection(self):
        record = self._load_quality_review_record(1)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)
        ok, message, dossier = build_scripted_dossier_skeleton(
            record,
            aux_part,
            sanitized_rest,
            record["point_coords_grid"],
            "eqangle a b a c a d a e",
        )
        self.assertTrue(ok, message)

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "fixture.png"
            image_path.write_bytes(b"fixture-image")

            with patch(
                "experiments.cot_sft_generation.generate_cot_sft.call_model",
                side_effect=[
                    json.dumps(dossier),
                    json.dumps(DOSSIER_CRITIC_REJECTION_OUTPUT),
                ],
            ), patch(
                "experiments.cot_sft_generation.generate_cot_sft.run_writer_stage",
                return_value={
                    "success": False,
                    "output": None,
                    "attempts_used": 1,
                    "elapsed_seconds": 0.01,
                    "error": "Writer body must explicitly realize goal_closure[0]",
                },
            ), patch(
                "experiments.cot_sft_generation.generate_cot_sft.validate_thinking_response",
                return_value=(True, "Valid thinking"),
            ):
                result = generate_dossier_thinking(
                    record=record,
                    image_path=image_path,
                    aux_part=aux_part,
                    sanitized_rest=sanitized_rest,
                    model_name="fixture-model",
                    max_retries=1,
                    verbose=True,
                )

        self.assertTrue(result["success"])
        self.assertIn("angle ab/ac equals angle ad/ae", result["thinking"])

    def test_generate_dossier_thinking_prefers_scripted_plan_when_goal_tail_route_is_stronger(self):
        record = self._load_quality_review_record(1)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)
        ok, message, scripted_dossier = build_scripted_dossier_skeleton(
            record,
            aux_part,
            sanitized_rest,
            record["point_coords_grid"],
            "eqangle a b a c a d a e",
        )
        self.assertTrue(ok, message)

        captured_bridge_chain = []

        def fake_run_writer_stage(*args, **kwargs):
            captured_bridge_chain[:] = [step["claim"] for step in kwargs["plan"]["bridge_chain"]]
            return {
                "success": True,
                "output": build_scripted_dossier_writer_body(kwargs["plan"]),
                "attempts_used": 1,
                "elapsed_seconds": 0.01,
                "error": None,
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "fixture.png"
            image_path.write_bytes(b"fixture-image")

            with patch(
                "experiments.cot_sft_generation.generate_cot_sft.call_model",
                side_effect=[
                    json.dumps(DOSSIER_WEAK_EQANGLE_PLAN_OUTPUT),
                    json.dumps(PLAN_CRITIC_OUTPUT),
                ],
            ), patch(
                "experiments.cot_sft_generation.generate_cot_sft.run_writer_stage",
                side_effect=fake_run_writer_stage,
            ), patch(
                "experiments.cot_sft_generation.generate_cot_sft.validate_thinking_response",
                return_value=(True, "Valid thinking"),
            ):
                result = generate_dossier_thinking(
                    record=record,
                    image_path=image_path,
                    aux_part=aux_part,
                    sanitized_rest=sanitized_rest,
                    model_name="fixture-model",
                    max_retries=1,
                    verbose=True,
                )

        expected_bridge_chain = [step["claim"] for step in scripted_dossier["bridge_chain"]]
        self.assertTrue(result["success"])
        self.assertEqual(captured_bridge_chain, expected_bridge_chain)
        self.assertEqual(
            [step["claim"] for step in result["plan_parsed"]["bridge_chain"]],
            expected_bridge_chain,
        )
        self.assertIn("triangles adf and cfd are similar", result["thinking"])
        self.assertNotIn("angle af/df equals angle df/cd", result["thinking"])

    def test_generate_dossier_thinking_scripted_fallback_prefers_scripted_writer_when_audit_is_better(self):
        record = self._load_quality_review_record(0)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)
        live_writer_body = (
            "The target ratio around segments AE, BD, EG, and BF lacks a clear bridge. "
            "To connect these segments, construct point H as the midpoint of AD. "
            "Since AD is parallel to BC, A, D, and H are collinear. "
            "Next, observe that CF is parallel to EG and AC equals BD. "
            "With AC perpendicular to BE and AE perpendicular to CF, the ratio AC to AE equals the ratio CF to EG. "
            "Since BD is perpendicular to BF and AE appears perpendicular to BG, the ratio AE to BD equals the ratio EG to BF. "
            "This completes the route by linking all necessary segment comparisons."
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "fixture.png"
            image_path.write_bytes(b"fixture-image")

            with patch(
                "experiments.cot_sft_generation.generate_cot_sft.call_model",
                side_effect=["not a json plan"],
            ), patch(
                "experiments.cot_sft_generation.generate_cot_sft.run_writer_stage",
                return_value={
                    "success": True,
                    "output": live_writer_body,
                    "attempts_used": 1,
                    "elapsed_seconds": 0.01,
                    "error": None,
                },
            ), patch(
                "experiments.cot_sft_generation.generate_cot_sft.validate_thinking_response",
                return_value=(True, "Valid thinking"),
            ):
                result = generate_dossier_thinking(
                    record=record,
                    image_path=image_path,
                    aux_part=aux_part,
                    sanitized_rest=sanitized_rest,
                    model_name="fixture-model",
                    max_retries=1,
                    verbose=True,
                )

        self.assertTrue(result["success"])
        self.assertIn("the figure also shows segments ae and bg look perpendicular", result["thinking"])
        self.assertNotIn("AE appears perpendicular to BG", result["thinking"])

    def test_generate_dossier_thinking_scripted_fallback_prefers_scripted_writer_when_plan_grounding_is_stronger(self):
        record = self._load_quality_review_record(2)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)
        live_writer_body = (
            "The target triangle comparison around B, D, E, C, E, and G lacks enough direct side or angle correspondences. "
            "To connect the missing angle relation, construct point H such that line BD is parallel to line FH and line BD is perpendicular to line BH. "
            "This creates a perpendicular link and a parallel link. "
            "Since AB is parallel to EF and AF is parallel to BE, angle AB/AF equals angle BH/FH, moving us closer to the goal. "
            "Given BC equals BE and CE equals CF, along with CF being parallel to CG, the ratio BD to BE equals the ratio CE to CG. "
            "Line DE is perpendicular to line EG, and angle AB/BC equals angle BC/BD. "
            "Therefore, triangles BDE and CEG are similar by these angle and side ratios. "
            "The construction of H facilitates this similarity proof by bridging the necessary angle relations."
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "fixture.png"
            image_path.write_bytes(b"fixture-image")

            with patch(
                "experiments.cot_sft_generation.generate_cot_sft.call_model",
                side_effect=["not a json plan"],
            ), patch(
                "experiments.cot_sft_generation.generate_cot_sft.run_writer_stage",
                return_value={
                    "success": True,
                    "output": live_writer_body,
                    "attempts_used": 1,
                    "elapsed_seconds": 0.01,
                    "error": None,
                },
            ), patch(
                "experiments.cot_sft_generation.generate_cot_sft.validate_thinking_response",
                return_value=(True, "Valid thinking"),
            ):
                result = generate_dossier_thinking(
                    record=record,
                    image_path=image_path,
                    aux_part=aux_part,
                    sanitized_rest=sanitized_rest,
                    model_name="fixture-model",
                    max_retries=1,
                    verbose=True,
                )

        self.assertTrue(result["success"])
        self.assertIn("This immediately gives line bd is parallel to line fh and line bd is perpendicular to line bh", result["thinking"])
        self.assertNotIn("facilitates this similarity proof", result["thinking"])

    def test_build_scripted_dossier_writer_body_validates_for_real_eqratio_sample(self):
        record = self._load_quality_review_record(0)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)
        ok, message, dossier = build_scripted_dossier_skeleton(
            record,
            aux_part,
            sanitized_rest,
            record["point_coords_grid"],
            "eqratio a e b d e g b f",
        )
        self.assertTrue(ok, message)

        body = build_scripted_dossier_writer_body(dossier)
        writer_ok, writer_message = validate_dossier_writer_body(
            body,
            visible_goal="eqratio a e b d e g b f",
            plan=dossier,
        )

        self.assertTrue(writer_ok, writer_message)
        self.assertIn("line cf is parallel to line eg", body)
        self.assertIn("segments be and cf look parallel", body)
        self.assertIn("line be is parallel to line eg", body)
        self.assertNotIn("Because line cf is parallel to line eg, line cf is parallel to line eg.", body)
        self.assertIn("ratio ae to bd equals ratio eg to bf", body)

    def test_build_scripted_dossier_writer_body_grounds_real_eqangle_goal_closure(self):
        record = self._load_quality_review_record(1)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)
        ok, message, dossier = build_scripted_dossier_skeleton(
            record,
            aux_part,
            sanitized_rest,
            record["point_coords_grid"],
            "eqangle a b a c a d a e",
        )
        self.assertTrue(ok, message)

        body = build_scripted_dossier_writer_body(dossier)
        writer_ok, writer_message = validate_dossier_writer_body(
            body,
            visible_goal="eqangle a b a c a d a e",
            plan=dossier,
        )

        self.assertTrue(writer_ok, writer_message)
        self.assertIn("ad equals ae", body)
        self.assertIn("angle ab/bc equals angle bc/ac", body)
        self.assertIn("angle ab/bc equals angle bc/be", body)
        self.assertNotIn("Because ad equals ae, ad equals ae.", body)

    def test_build_scripted_dossier_writer_body_grounds_real_simtrir_goal_closure(self):
        record = self._load_quality_review_record(2)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)
        ok, message, dossier = build_scripted_dossier_skeleton(
            record,
            aux_part,
            sanitized_rest,
            record["point_coords_grid"],
            "simtrir b d e c e g",
        )
        self.assertTrue(ok, message)

        body = build_scripted_dossier_writer_body(dossier)
        writer_ok, writer_message = validate_dossier_writer_body(
            body,
            visible_goal="simtrir b d e c e g",
            plan=dossier,
        )

        self.assertTrue(writer_ok, writer_message)
        self.assertIn("ratio bd to be equals ratio ce to cg", body)
        self.assertIn("line de is perpendicular to line eg", body)
        self.assertIn("angle ab/bc equals angle bc/bd", body)

    def test_build_scripted_dossier_writer_body_grounds_real_contrir_transfer_goal_closure(self):
        record = self._load_quality_review_record(5)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)
        ok, message, dossier = build_scripted_dossier_skeleton(
            record,
            aux_part,
            sanitized_rest,
            record["point_coords_grid"],
            "contrir b d i i f b",
        )
        self.assertTrue(ok, message)

        body = build_scripted_dossier_writer_body(dossier)
        writer_ok, writer_message = validate_dossier_writer_body(
            body,
            visible_goal="contrir b d i i f b",
            plan=dossier,
        )

        self.assertTrue(writer_ok, writer_message)
        self.assertIn("cf equals cj", body)
        self.assertIn("j equals i", body)
        self.assertIn("triangles bdi and ifb are congruent", body)

    def test_build_scripted_dossier_writer_body_grounds_real_late_fact_simtrir_goal_closure(self):
        record = self._load_quality_review_record(9)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)
        ok, message, dossier = build_scripted_dossier_skeleton(
            record,
            aux_part,
            sanitized_rest,
            record["point_coords_grid"],
            "simtrir a g i i g h",
        )
        self.assertTrue(ok, message)

        body = build_scripted_dossier_writer_body(dossier)
        writer_ok, writer_message = validate_dossier_writer_body(
            body,
            visible_goal="simtrir a g i i g h",
            plan=dossier,
        )

        self.assertTrue(writer_ok, writer_message)
        self.assertIn("b, d, h, i are concyclic", body)
        self.assertIn("ratio ab to bi equals ratio dh to di", body)
        self.assertIn("triangles agi and igh are similar", body)

    def test_build_scripted_dossier_writer_body_grounds_real_contrir_goal_closure(self):
        record = self._load_quality_review_record(11)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)
        ok, message, dossier = build_scripted_dossier_skeleton(
            record,
            aux_part,
            sanitized_rest,
            record["point_coords_grid"],
            "contrir a c h d b h",
        )
        self.assertTrue(ok, message)

        body = build_scripted_dossier_writer_body(dossier)
        writer_ok, writer_message = validate_dossier_writer_body(
            body,
            visible_goal="contrir a c h d b h",
            plan=dossier,
        )

        self.assertTrue(writer_ok, writer_message)
        self.assertIn("bh equals ch", body)
        self.assertIn("angle bi/bh equals angle ch/ci", body)
        self.assertIn("triangles ach and dbh are congruent", body)

    def test_build_scripted_dossier_writer_body_prefers_non_coordinate_supports_for_real_simtri_sample(self):
        record = self._load_quality_review_record(3)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)
        ok, message, dossier = build_scripted_dossier_skeleton(
            record,
            aux_part,
            sanitized_rest,
            record["point_coords_grid"],
            "simtri a c g f a g",
        )
        self.assertTrue(ok, message)

        body = build_scripted_dossier_writer_body(dossier)
        writer_ok, writer_message = validate_dossier_writer_body(
            body,
            visible_goal="simtri a c g f a g",
            plan=dossier,
        )

        self.assertTrue(writer_ok, writer_message)
        self.assertIn("triangles afh and ehg are similar", body)
        self.assertIn("a, c, g, h are concyclic", body)
        coordinate_mentions = [
            relation
            for relation in [
                "line af is perpendicular to line ag",
                "line ac is perpendicular to line cg",
            ]
            if relation in body
        ]
        self.assertEqual(len(coordinate_mentions), 1)

    def test_process_and_generate_sft_runs_offline_dossier_pipeline(self):
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
                    "generation_style": "dossier_v1",
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
                side_effect=[json.dumps(DOSSIER_PLAN_OUTPUT), json.dumps(PLAN_CRITIC_OUTPUT), DOSSIER_WRITER_BODY],
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
            self.assertEqual(result["summary"]["generation_style"], "dossier_v1")
            dataset_records = [
                json.loads(line)
                for line in output_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(dataset_records), 1)
            self.assertIn("point a looks like the midpoint of bc", dataset_records[0]["thinking"])
            self.assertEqual(dataset_records[0]["aux"], "<aux>x00 h : cong a h d h; cong b h c h</aux>")

            item_records = [
                json.loads(line)
                for line in (run_dir / "item_records.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(item_records), 1)
            self.assertTrue(item_records[0]["surface_pass"])
            self.assertEqual(item_records[0]["attempts_used"], 3)
            self.assertEqual(item_records[0]["generation_style"], "dossier_v1")
            self.assertIn("bridge_chain", item_records[0]["plan_parsed"])

    def test_process_and_generate_sft_accepts_partial_dossier_critic_revision(self):
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
                    "generation_style": "dossier_v1",
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
                side_effect=[
                    json.dumps(DOSSIER_PLAN_OUTPUT),
                    json.dumps(DOSSIER_PARTIAL_CRITIC_OUTPUT),
                    DOSSIER_WRITER_BODY,
                ],
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
            item_records = [
                json.loads(line)
                for line in (run_dir / "item_records.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertTrue(item_records[0]["surface_pass"])
            self.assertEqual(item_records[0]["plan_parsed"]["goal_closure"][0]["claim"], "ad equals bc")

    def test_process_and_generate_sft_ignores_invalid_dossier_critic_revision_patch(self):
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
                    "generation_style": "dossier_v1",
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
                side_effect=[
                    json.dumps(DOSSIER_PLAN_OUTPUT),
                    json.dumps(DOSSIER_INVALID_CRITIC_PATCH_OUTPUT),
                    DOSSIER_WRITER_BODY,
                ],
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
            item_records = [
                json.loads(line)
                for line in (run_dir / "item_records.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertTrue(item_records[0]["surface_pass"])
            self.assertEqual(item_records[0]["plan_parsed"]["goal_closure"][0]["claim"], DOSSIER_PLAN_OUTPUT["goal_closure"][0]["claim"])

    def test_process_and_generate_sft_routes_to_legacy_pipeline_when_requested(self):
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
                    generation_style="model_evidence_legacy",
                    run_metadata=run_metadata,
                    run_dir=run_dir,
                )

            self.assertEqual(result["summary"]["surface_pass_items"], 1)
            self.assertEqual(result["summary"]["generation_style"], "model_evidence_legacy")


if __name__ == "__main__":
    unittest.main()
