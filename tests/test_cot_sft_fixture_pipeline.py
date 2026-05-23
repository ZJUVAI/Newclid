import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments.cot_sft_generation.generate_cot_sft import (
    build_dossier_goal_tail_relations,
    build_hidden_proof_guidance,
    build_scripted_dossier_writer_body,
    build_scripted_dossier_skeleton,
    generate_dossier_thinking,
    low_level_equality_claim_lacks_symbolic_support,
    process_and_generate_sft,
    select_dossier_support_refs_for_relation,
    similar_step_lacks_local_correspondence_support,
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
    "visible_facts": ["line ab is parallel to line cd", "ad equals bc"],
    "image_scan": ["point a looks like the midpoint of bc"],
    "coordinate_checks": [],
    "goal_obstacle": "the target still needs one clean transfer from the helper frame back to the d-side and c-side.",
    "aux_motivation": "a helper should create two local equalities first and then reconnect them to the visible outer frame.",
    "construction": "construct point h such that ah equals dh and bh equals ch.",
    "aux_immediate_effects": ["ah equals dh", "bh equals ch"],
    "bridge_chain": [
        {
            "claim": "ah equals dh",
            "supports": ["aux_immediate_effects[1]"],
            "why_next": "this keeps one helper-side equality explicit before the final close.",
        },
        {
            "claim": "bh equals ch",
            "supports": ["aux_immediate_effects[2]"],
            "why_next": "this keeps the second helper-side equality explicit before the final close.",
        },
    ],
    "goal_closure": [
        {
            "claim": "ad equals bc",
            "supports": ["visible_facts[2]", "bridge_chain[2]"],
            "why_next": "this is the target relation.",
        }
    ],
}

DOSSIER_WRITER_BODY = (
    "The obstacle is to transfer the d-side and c-side through one helper frame before the target equality closes. "
    "The figure also suggests that point a looks like the midpoint of bc, so the outer balance around a, b, and c is worth tracking. "
    "Construct point h such that ah equals dh and bh equals ch. "
    "From the construction, ah equals dh. "
    "The same construction also gives bh equals ch. "
    "These two helper equalities stay available while returning to the visible outer frame. "
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

    def _build_clean_scripted_fallback_fixture(self):
        record = {
            "nl_problem": "Observe the diagram and justify the target relation.",
            "llm_input_renamed": (
                "<problem>g1: cong a d b c [001]; g2: midp g b e [002] ? cong a d b c</problem>"
            ),
            "llm_output_renamed": "<aux> x00 h : midp h a d [008] ; </aux>",
            "point_coords_grid": {
                "a": [134, 196],
                "b": [226, 184],
                "c": [217, 115],
                "d": [124, 128],
                "e": [187, 144],
                "f": [247, 146],
                "g": [206, 164],
            },
        }
        aux_part = "<aux> x00 h : midp h a d [008] ; </aux>"
        sanitized_rest = ""
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
            point_coords=record["point_coords_grid"],
            visible_goal="cong a d b c",
            aux_part=aux_part,
        )
        self.assertTrue(ok, message)
        return record, aux_part, sanitized_rest, cleaned

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
        self.assertTrue(
            "unsupported angle/ratio/similar segments" in message
            or "bridge_chain must not be empty" in message
        )

    def test_similar_step_local_correspondence_gate_rejects_nonaux_similarity_bridge(self):
        step = {
            "relation": "triangles bce and dbe are similar",
            "approved_route_relation": "triangles bce and dbe are similar",
        }
        support_relations = [
            "c, d, e are collinear",
            "ac equals bd",
            "segments ac and be look parallel",
            "angle ab/ad equals angle bd/ab",
        ]

        lacks_support = similar_step_lacks_local_correspondence_support(
            step,
            support_relations,
            ["a", "b", "c", "d", "e", "f", "g"],
        )

        self.assertTrue(lacks_support)

    def test_similar_step_local_correspondence_gate_accepts_ratio_plus_cyclic_support(self):
        step = {
            "relation": "triangles acg and fag are similar",
            "approved_route_relation": "triangles acg and fag are similar",
        }
        support_relations = [
            "a, c, g, h are concyclic",
            "ratio ac to af equals ratio cg to ag",
        ]
        support_refs = [
            "aux_immediate_effects[1]",
            "bridge_chain[1]",
        ]

        lacks_support = similar_step_lacks_local_correspondence_support(
            step,
            support_relations,
            ["a", "b", "c", "d", "e", "f", "g", "h"],
            support_refs=support_refs,
        )

        self.assertFalse(lacks_support)

    def test_validate_dossier_plan_response_rejects_angle_bridge_without_directional_relay(self):
        dossier = {
            "visible_facts": [
                "ac equals bd",
                "g is the midpoint of be",
                "line ad is parallel to line bc",
            ],
            "image_scan": [
                "segments ae and bg look perpendicular",
            ],
            "coordinate_checks": [],
            "goal_obstacle": "the target ratio still lacks one grounded bridge between the helper halves and the visible side.",
            "aux_motivation": "a midpoint helper should create one local balance before any angle or ratio transfer is attempted.",
            "construction": "construct point h as the midpoint of ad.",
            "aux_immediate_effects": ["h is the midpoint of ad"],
            "bridge_chain": [
                {
                    "claim": "angle ab/ah equals angle bg/ac",
                    "supports": [
                        "aux_immediate_effects[1]",
                        "visible_facts[1]",
                        "visible_facts[2]",
                    ],
                    "why_next": "this would start the ratio transfer.",
                }
            ],
            "goal_closure": [
                {
                    "claim": "ratio ae to bd equals ratio eg to bf",
                    "supports": [
                        "bridge_chain[1]",
                        "visible_facts[3]",
                    ],
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
        self.assertIn("missing a directional relay", message)

    def test_validate_dossier_plan_response_rejects_congruent_closure_with_only_coordinate_side_supports(self):
        dossier = {
            "visible_facts": [
                "b, c, d, e are concyclic",
                "ab equals cd",
                "cd equals cf",
                "ab equals be",
            ],
            "image_scan": [
                "segments bc and ef look parallel",
            ],
            "coordinate_checks": [
                {
                    "relation": "bc equals ef",
                    "points": ["b", "c", "e", "f"],
                    "calc_type": "equal_length",
                    "why_it_matters": "this would supply one side comparison near the target triangles.",
                },
                {
                    "relation": "be equals cf",
                    "points": ["b", "e", "c", "f"],
                    "calc_type": "equal_length",
                    "why_it_matters": "this would supply another side comparison near the target triangles.",
                },
            ],
            "goal_obstacle": "the target triangle comparison still lacks one grounded correspondence at the goal side.",
            "aux_motivation": "the helper should create one local direction cue before the final triangle comparison is attempted.",
            "construction": "construct point g such that ab equals cg and line bc is perpendicular to line cg",
            "aux_immediate_effects": [
                "ab equals cg",
                "line bc is perpendicular to line cg",
            ],
            "bridge_chain": [
                {
                    "claim": "angle be/bf equals angle cf/bf",
                    "supports": [
                        "visible_facts[1]",
                        "coordinate_checks[2]",
                        "coordinate_checks[1]",
                    ],
                    "why_next": "this would supply one directional relay near the target triangles.",
                }
            ],
            "goal_closure": [
                {
                    "claim": "triangles bcf and feb are congruent",
                    "supports": [
                        "bridge_chain[1]",
                        "coordinate_checks[1]",
                        "coordinate_checks[2]",
                    ],
                    "why_next": "this is the target relation.",
                }
            ],
        }

        ok, message, _ = validate_dossier_plan_response(
            dossier,
            point_coords={
                "a": [84, 82],
                "b": [135, 119],
                "c": [69, 206],
                "d": [119, 244],
                "e": [77, 144],
                "f": [12, 230],
            },
            visible_goal="contri b c f f e b",
            aux_part="<aux> x00 g : cong a b c g [006] perp b c c g [007] ; </aux>",
        )

        self.assertFalse(ok)
        self.assertTrue(
            "missing a non-coordinate side or triangle correspondence support" in message
            or "missing symbolic directional coverage" in message
        )

    def test_validate_dossier_plan_response_rejects_equality_bridge_without_local_symbolic_support(self):
        dossier = {
            "visible_facts": [
                "bc equals cd",
                "bc equals cf",
            ],
            "image_scan": [
                "segments bf and di look perpendicular",
            ],
            "coordinate_checks": [],
            "goal_obstacle": "the target congruence still lacks a grounded equality transfer through the helper point.",
            "aux_motivation": "the helper should create one local consequence before any transferred equality is claimed.",
            "construction": "construct point j such that line cf is perpendicular to line cj and angle bf/cf equals angle fj/bf",
            "aux_immediate_effects": [
                "line cf is perpendicular to line cj",
                "angle bf/cf equals angle fj/bf",
            ],
            "bridge_chain": [
                {
                    "claim": "cf equals cj",
                    "supports": [
                        "aux_immediate_effects[1]",
                        "visible_facts[1]",
                    ],
                    "why_next": "this would start the helper-side equality transfer.",
                }
            ],
            "goal_closure": [
                {
                    "claim": "triangles bdj and jfb are congruent",
                    "supports": [
                        "bridge_chain[1]",
                        "image_scan[1]",
                    ],
                    "why_next": "this would finish the local congruence.",
                }
            ],
        }

        ok, message, _ = validate_dossier_plan_response(
            dossier,
            point_coords={
                "b": [187, 61],
                "c": [166, 114],
                "d": [113, 93],
                "f": [143, 61],
                "i": [113, 137],
            },
            visible_goal="contrir b d i i f b",
            aux_part="<aux> x00 j : perp c f c j [013] eqangle b f c f f j b f [014] ; </aux>",
        )

        self.assertFalse(ok)
        self.assertIn("missing a local non-coordinate equality support chain", message)

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

    def test_build_scripted_dossier_skeleton_accepts_real_simtri_benchmark_sample_with_ratio_plus_cyclic_similarity_closure(self):
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
        self.assertIsNotNone(dossier)
        goal_step = dossier["goal_closure"][0]
        self.assertEqual(goal_step["claim"], "triangles acg and fag are similar")
        self.assertIn(
            "ratio ac to af equals ratio cg to ag",
            goal_step.get("resolved_supports", []),
        )
        self.assertIn(
            "a, c, g, h are concyclic",
            goal_step.get("resolved_supports", []),
        )

    def test_build_scripted_dossier_skeleton_rejects_real_eqratio_benchmark_sample_with_ungrounded_ratio_closure(self):
        record = self._load_quality_review_record(0)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)

        ok, message, dossier = build_scripted_dossier_skeleton(
            record,
            aux_part,
            sanitized_rest,
            record["point_coords_grid"],
            "eqratio a e b d e g b f",
        )

        self.assertFalse(ok)
        self.assertIn("missing local pairwise support", message)
        self.assertIsNone(dossier)

    def test_build_scripted_dossier_skeleton_rejects_real_simtrir_benchmark_sample_with_ungrounded_goal_closure(self):
        record = self._load_quality_review_record(2)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)

        ok, message, dossier = build_scripted_dossier_skeleton(
            record,
            aux_part,
            sanitized_rest,
            record["point_coords_grid"],
            "simtrir b d e c e g",
        )

        self.assertFalse(ok)
        self.assertTrue(
            "unsupported angle/ratio/similar segments" in message
            or "bridge_chain must not be empty" in message
        )

    def test_build_scripted_dossier_skeleton_keeps_real_simtrir_prefix_bridge_when_tail_only_start_lacks_local_support(self):
        record = self._load_quality_review_record(2)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)

        def passthrough_validate(raw_dossier, *args, **kwargs):
            return True, "forced", raw_dossier

        with patch(
            "experiments.cot_sft_generation.generate_cot_sft.validate_dossier_plan_response",
            side_effect=passthrough_validate,
        ):
            ok, message, dossier = build_scripted_dossier_skeleton(
                record,
                aux_part,
                sanitized_rest,
                record["point_coords_grid"],
                "simtrir b d e c e g",
            )

        self.assertTrue(ok, message)
        self.assertIsNotNone(dossier)
        self.assertGreaterEqual(len(dossier.get("bridge_chain", [])), 1)
        self.assertEqual(dossier["bridge_chain"][0]["claim"], "a, b, f, h are concyclic")

    def test_build_scripted_dossier_skeleton_rejects_real_contri_benchmark_sample_with_coordinate_only_closure(self):
        record = self._load_quality_review_record(4)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)

        ok, message, dossier = build_scripted_dossier_skeleton(
            record,
            aux_part,
            sanitized_rest,
            record["point_coords_grid"],
            "contri b c f f e b",
        )

        self.assertFalse(ok)
        self.assertTrue(
            "missing a non-coordinate side or triangle correspondence support" in message
            or "missing symbolic directional coverage" in message
        )

    def test_build_dossier_goal_tail_relations_prefers_transfer_checkpoint_for_real_contrir_sample(self):
        record = self._load_quality_review_record(5)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)
        proof_guidance = build_hidden_proof_guidance(
            sanitized_rest,
            aux_part,
            "contrir b d i i f b",
        )

        goal_tail_relations = build_dossier_goal_tail_relations(
            proof_guidance,
            "triangles bdi and ifb are congruent",
            list(record["point_coords_grid"]) + ["j"],
        )

        self.assertEqual(
            goal_tail_relations,
            [
                "triangles bdj and jfb are congruent",
                "hj equals hi",
            ],
        )

    def test_build_dossier_goal_tail_relations_prepends_similarity_angle_checkpoint_for_real_late_fact_sample(self):
        record = self._load_quality_review_record(9)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)
        proof_guidance = build_hidden_proof_guidance(
            sanitized_rest,
            aux_part,
            "simtrir a g i i g h",
        )

        goal_tail_relations = build_dossier_goal_tail_relations(
            proof_guidance,
            "triangles agi and igh are similar",
            list(record["point_coords_grid"]) + ["j", "k"],
        )

        self.assertEqual(
            goal_tail_relations[0],
            "angle ag/ai equals angle hi/gi",
        )
        self.assertNotIn(
            "triangles agi and igh are similar",
            goal_tail_relations,
        )

    def test_validate_dossier_plan_response_rejects_bare_point_equality_claim(self):
        record, aux_part, _, _ = self._build_clean_scripted_fallback_fixture()
        dossier = json.loads(json.dumps(DOSSIER_PLAN_OUTPUT))
        dossier["bridge_chain"][0]["claim"] = "j equals i"

        ok, message, _ = validate_dossier_plan_response(
            dossier,
            point_coords=record["point_coords_grid"],
            visible_goal="ad equals bc",
            aux_part=aux_part,
        )

        self.assertFalse(ok)
        self.assertIn("bare equality", message)

    def test_validate_dossier_plan_response_rejects_tautological_angle_claim(self):
        record, aux_part, _, dossier = self._build_clean_scripted_fallback_fixture()
        dossier = json.loads(json.dumps(dossier))
        dossier["goal_closure"][0]["claim"] = "angle be/be equals angle ce/de"

        ok, message, _ = validate_dossier_plan_response(
            dossier,
            point_coords=record["point_coords_grid"],
            visible_goal="ad equals bc",
            aux_part=aux_part,
        )

        self.assertFalse(ok)
        self.assertIn("tautological angle", message)

    def test_low_level_equality_claim_accepts_transitive_symbolic_support_chain(self):
        step = {
            "relation": "af equals ad",
            "approved_route_relation": "af equals ad",
        }
        support_relations = [
            "ac equals af",
            "ac equals bd",
            "ad equals bd",
        ]
        support_refs = [
            "bridge_chain[1]",
            "visible_facts[1]",
            "visible_facts[2]",
        ]

        lacks_support = low_level_equality_claim_lacks_symbolic_support(
            step,
            support_relations,
            ["a", "b", "c", "d", "e", "f"],
            support_refs=support_refs,
        )

        self.assertFalse(lacks_support)

    def test_select_dossier_support_refs_for_equality_prefers_transitive_chain(self):
        support_catalog = [
            {"ref": "bridge_chain[1]", "relation": "ac equals af"},
            {"ref": "visible_facts[1]", "relation": "ac equals bd"},
            {"ref": "visible_facts[2]", "relation": "ad equals bd"},
            {"ref": "visible_facts[3]", "relation": "ab equals ac"},
        ]

        refs = select_dossier_support_refs_for_relation(
            "af equals ad",
            support_catalog,
            ["a", "b", "c", "d", "e", "f"],
            max_supports=4,
        )

        self.assertEqual(len(refs), 3)
        self.assertEqual(
            set(refs),
            {"bridge_chain[1]", "visible_facts[1]", "visible_facts[2]"},
        )

    def test_build_scripted_dossier_skeleton_rejects_real_contrir_transfer_sample_with_ungrounded_equality_chain(self):
        record = self._load_quality_review_record(5)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)

        ok, message, dossier = build_scripted_dossier_skeleton(
            record,
            aux_part,
            sanitized_rest,
            record["point_coords_grid"],
            "contrir b d i i f b",
        )

        self.assertFalse(ok)
        self.assertIn("bridge_chain must not be empty", message)

    def test_build_scripted_dossier_skeleton_rejects_real_late_fact_simtrir_benchmark_sample_with_ungrounded_similarity_closure(self):
        record = self._load_quality_review_record(9)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)

        ok, message, dossier = build_scripted_dossier_skeleton(
            record,
            aux_part,
            sanitized_rest,
            record["point_coords_grid"],
            "simtrir a g i i g h",
        )

        self.assertFalse(ok)
        self.assertTrue(
            "missing local correspondence support" in message
            or "missing local pairwise support" in message
        )
        self.assertIsNone(dossier)

    def test_build_scripted_dossier_skeleton_rejects_real_contrir_benchmark_sample_with_ungrounded_equality_transfer(self):
        record = self._load_quality_review_record(11)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)

        ok, message, dossier = build_scripted_dossier_skeleton(
            record,
            aux_part,
            sanitized_rest,
            record["point_coords_grid"],
            "contrir a c h d b h",
        )

        self.assertFalse(ok)
        self.assertIn("unsupported angle/ratio/similar segments", message)

    def test_build_scripted_dossier_skeleton_rejects_real_eqangle_sample_with_incomplete_directional_coverage(self):
        record = self._load_quality_review_record(1)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)

        ok, message, dossier = build_scripted_dossier_skeleton(
            record,
            aux_part,
            sanitized_rest,
            record["point_coords_grid"],
            "eqangle a b a c a d a e",
        )

        self.assertFalse(ok)
        self.assertTrue(
            "missing symbolic directional coverage" in message
            or "bridge_chain must not be empty" in message
        )

    def test_build_scripted_dossier_skeleton_real_simtri_tail_route_now_has_local_similarity_support(self):
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
        self.assertIsNotNone(dossier)
        goal_step = dossier["goal_closure"][0]
        self.assertFalse(
            similar_step_lacks_local_correspondence_support(
                {
                    "relation": goal_step["claim"],
                    "approved_route_relation": goal_step["claim"],
                },
                goal_step.get("resolved_supports", []),
                list(record["point_coords_grid"]) + ["h"],
                support_refs=goal_step.get("supports", []),
            )
        )

    def test_build_scripted_dossier_skeleton_rejects_real_eqratio_benchmark_sample_with_ungrounded_similarity_bridge(self):
        record = self._load_quality_review_record(6)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)

        ok, message, dossier = build_scripted_dossier_skeleton(
            record,
            aux_part,
            sanitized_rest,
            record["point_coords_grid"],
            "eqratio b e c e d e b e",
        )

        self.assertFalse(ok)
        self.assertTrue(
            "missing local correspondence support" in message
            or "missing local pairwise support" in message
        )
        self.assertIsNone(dossier)

    def test_generate_dossier_thinking_plan_only_falls_back_to_scripted_skeleton(self):
        record, aux_part, sanitized_rest, scripted_dossier = self._build_clean_scripted_fallback_fixture()

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "fixture.png"
            image_path.write_bytes(b"fixture-image")

            with patch(
                "experiments.cot_sft_generation.generate_cot_sft.call_model",
                side_effect=["not a json plan"],
            ), patch(
                "experiments.cot_sft_generation.generate_cot_sft.build_scripted_dossier_skeleton",
                return_value=(True, "Valid dossier", scripted_dossier),
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
        self.assertEqual(result["plan_parsed"]["goal_closure"][-1]["claim"], "ad equals bc")

    def test_generate_dossier_thinking_scripted_fallback_skips_critic_in_full_generation(self):
        record, aux_part, sanitized_rest, scripted_dossier = self._build_clean_scripted_fallback_fixture()
        writer_output = build_scripted_dossier_writer_body(scripted_dossier)

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "fixture.png"
            image_path.write_bytes(b"fixture-image")

            with patch(
                "experiments.cot_sft_generation.generate_cot_sft.call_model",
                side_effect=["not a json plan"],
            ) as call_model_mock, patch(
                "experiments.cot_sft_generation.generate_cot_sft.build_scripted_dossier_skeleton",
                return_value=(True, "Valid dossier", scripted_dossier),
            ), patch(
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
        self.assertIn("Finally, because ah equals dh, ad equals bc.", result["thinking"])

    def test_generate_dossier_thinking_fails_closed_when_scripted_eqratio_fallback_is_invalid_after_writer_failure(self):
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

        self.assertFalse(result["success"])
        writer_mock.assert_not_called()
        self.assertEqual(result["thinking"], "not a json plan")
        self.assertIn("missing local pairwise support", result["error"])

    def test_generate_dossier_thinking_eqratio_planner_failure_stops_before_writer_retries_when_no_valid_scripted_fallback_exists(self):
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

        self.assertFalse(result["success"])
        self.assertEqual(call_model_mock.call_count, 3)
        self.assertEqual(result["thinking"], "final invalid plan output")
        self.assertIn("missing local pairwise support", result["error"])

    def test_generate_dossier_thinking_falls_back_to_scripted_skeleton_after_critic_rejection(self):
        record, aux_part, sanitized_rest, scripted_dossier = self._build_clean_scripted_fallback_fixture()

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "fixture.png"
            image_path.write_bytes(b"fixture-image")

            with patch(
                "experiments.cot_sft_generation.generate_cot_sft.call_model",
                side_effect=[
                    json.dumps(scripted_dossier),
                    json.dumps(DOSSIER_CRITIC_REJECTION_OUTPUT),
                ],
            ), patch(
                "experiments.cot_sft_generation.generate_cot_sft.build_scripted_dossier_skeleton",
                return_value=(True, "Valid dossier", scripted_dossier),
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
        self.assertIn("Finally, because ah equals dh, ad equals bc.", result["thinking"])

    def test_generate_dossier_thinking_falls_back_to_scripted_plan_after_live_plan_rejection(self):
        record, aux_part, sanitized_rest, scripted_dossier = self._build_clean_scripted_fallback_fixture()

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
                    json.dumps(DOSSIER_CRITIC_REJECTION_OUTPUT),
                ],
            ), patch(
                "experiments.cot_sft_generation.generate_cot_sft.build_scripted_dossier_skeleton",
                return_value=(True, "Valid dossier", scripted_dossier),
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
        self.assertIn("Because ah equals dh, dh equals ah.", result["thinking"])
        self.assertNotIn("angle af/df equals angle df/cd", result["thinking"])

    def test_generate_dossier_thinking_eqratio_fails_closed_when_scripted_fallback_is_invalid_and_live_writer_is_weaker(self):
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

        self.assertFalse(result["success"])
        writer_mock.assert_not_called()
        self.assertEqual(result["thinking"], "not a json plan")
        self.assertIn("missing local pairwise support", result["error"])

    def test_generate_dossier_thinking_scripted_fallback_prefers_scripted_writer_when_plan_grounding_is_stronger(self):
        record, aux_part, sanitized_rest, scripted_dossier = self._build_clean_scripted_fallback_fixture()
        live_writer_body = (
            "The target equality around AD and BC still lacks a clear bridge. "
            "Construct point H to help with the comparison. "
            "This creates a helper frame and should facilitate the final congruence without spelling out the actual route."
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "fixture.png"
            image_path.write_bytes(b"fixture-image")

            with patch(
                "experiments.cot_sft_generation.generate_cot_sft.call_model",
                side_effect=["not a json plan"],
            ), patch(
                "experiments.cot_sft_generation.generate_cot_sft.build_scripted_dossier_skeleton",
                return_value=(True, "Valid dossier", scripted_dossier),
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
        self.assertIn("This immediately gives ah equals dh and a, d, h are collinear.", result["thinking"])
        self.assertIn("Finally, because ah equals dh, ad equals bc.", result["thinking"])
        self.assertNotIn("facilitate the final congruence", result["thinking"])

    def test_build_scripted_dossier_writer_body_rejects_real_eqratio_sample_with_ungrounded_ratio_closure(self):
        record = self._load_quality_review_record(0)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)
        ok, message, dossier = build_scripted_dossier_skeleton(
            record,
            aux_part,
            sanitized_rest,
            record["point_coords_grid"],
            "eqratio a e b d e g b f",
        )
        self.assertFalse(ok)
        self.assertIn("missing local pairwise support", message)
        self.assertIsNone(dossier)

    def test_build_scripted_dossier_writer_body_rejects_real_eqangle_sample_with_incomplete_directional_coverage(self):
        record = self._load_quality_review_record(1)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)
        ok, message, dossier = build_scripted_dossier_skeleton(
            record,
            aux_part,
            sanitized_rest,
            record["point_coords_grid"],
            "eqangle a b a c a d a e",
        )
        self.assertFalse(ok)
        self.assertTrue(
            "missing symbolic directional coverage" in message
            or "bridge_chain must not be empty" in message
        )

    def test_build_scripted_dossier_writer_body_rejects_real_simtrir_sample_with_ungrounded_goal_closure(self):
        record = self._load_quality_review_record(2)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)
        ok, message, dossier = build_scripted_dossier_skeleton(
            record,
            aux_part,
            sanitized_rest,
            record["point_coords_grid"],
            "simtrir b d e c e g",
        )
        self.assertFalse(ok)
        self.assertTrue(
            "unsupported angle/ratio/similar segments" in message
            or "bridge_chain must not be empty" in message
        )

    def test_build_scripted_dossier_writer_body_rejects_real_contrir_transfer_sample_with_ungrounded_equality_chain(self):
        record = self._load_quality_review_record(5)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)
        ok, message, dossier = build_scripted_dossier_skeleton(
            record,
            aux_part,
            sanitized_rest,
            record["point_coords_grid"],
            "contrir b d i i f b",
        )
        self.assertFalse(ok)
        self.assertIn("bridge_chain must not be empty", message)

    def test_build_scripted_dossier_writer_body_rejects_real_contri_sample_with_coordinate_only_closure(self):
        record = self._load_quality_review_record(4)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)
        ok, message, dossier = build_scripted_dossier_skeleton(
            record,
            aux_part,
            sanitized_rest,
            record["point_coords_grid"],
            "contri b c f f e b",
        )
        self.assertFalse(ok)
        self.assertTrue(
            "missing a non-coordinate side or triangle correspondence support" in message
            or "missing symbolic directional coverage" in message
        )

    def test_build_scripted_dossier_writer_body_rejects_real_late_fact_simtrir_goal_closure_without_local_similarity_support(self):
        record = self._load_quality_review_record(9)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)
        ok, message, dossier = build_scripted_dossier_skeleton(
            record,
            aux_part,
            sanitized_rest,
            record["point_coords_grid"],
            "simtrir a g i i g h",
        )
        self.assertFalse(ok)
        self.assertIn("missing local correspondence support", message)
        self.assertIsNone(dossier)

    def test_build_scripted_dossier_writer_body_rejects_real_contrir_sample_with_ungrounded_equality_transfer(self):
        record = self._load_quality_review_record(11)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)
        ok, message, dossier = build_scripted_dossier_skeleton(
            record,
            aux_part,
            sanitized_rest,
            record["point_coords_grid"],
            "contrir a c h d b h",
        )
        self.assertFalse(ok)
        self.assertIn("unsupported angle/ratio/similar segments", message)

    def test_build_scripted_dossier_writer_body_rejects_real_eqratio_sample_with_ungrounded_similarity_bridge(self):
        record = self._load_quality_review_record(6)
        aux_part, sanitized_rest = self._extract_aux_and_rest(record)
        ok, message, dossier = build_scripted_dossier_skeleton(
            record,
            aux_part,
            sanitized_rest,
            record["point_coords_grid"],
            "eqratio b e c e d e b e",
        )
        self.assertFalse(ok)
        self.assertTrue(
            "missing local correspondence support" in message
            or "missing local pairwise support" in message
        )
        self.assertIsNone(dossier)

    def test_process_and_generate_sft_runs_offline_dossier_pipeline(self):
        record = {
            "nl_problem": "Observe the diagram and justify the target relation.",
            "llm_input_renamed": (
                "<problem>g1: para a b c d [000]; g2: cong a d b c [001] ? cong a d b c</problem>"
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
                "<problem>g1: para a b c d [000]; g2: cong a d b c [001] ? cong a d b c</problem>"
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
                "<problem>g1: para a b c d [000]; g2: cong a d b c [001] ? cong a d b c</problem>"
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
                "<problem>g1: para a b c d [000]; g2: cong a d b c [001] ? cong a d b c</problem>"
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
