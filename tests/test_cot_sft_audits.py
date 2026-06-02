import json
import unittest
from pathlib import Path

from experiments.cot_sft_generation.core.insight_pipeline import INSIGHT_IMAGE_V1, INSIGHT_TEXT_V1
from experiments.cot_sft_generation.audits import (
    audit_generation_quality,
    audit_source_record,
    bridge_step_relation_realized,
    build_visible_premise_summaries,
    count_relation_mentions,
    coordinate_relation_matches_candidate,
    extract_visible_formal_facts,
    get_point_coords,
    relation_mentioned_in_text,
)


class CotSftAuditsTest(unittest.TestCase):
    @staticmethod
    def _load_quality_review_record(index):
        benchmark_path = Path("experiments/cot_sft_generation/benchmarks/quality_review_v1/quality_review_v1_input.jsonl")
        records = [
            json.loads(line)
            for line in benchmark_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return records[index]

    def test_get_point_coords_normalizes_grid_coord(self):
        coords = get_point_coords({"grid_coord": {"A": [1, 2], "b": (3, 4)}})

        self.assertEqual(coords, {"A": (1, 2), "b": (3, 4)})

    def test_extract_visible_formal_facts_ignores_goal_clause(self):
        record = {
            "llm_input_renamed": (
                "<problem>g1: para a b c d [000] ; g2: cong a b a c [001] ? "
                "eqangle a b c d</problem>"
            )
        }

        facts = extract_visible_formal_facts(record)

        self.assertEqual(len(facts), 2)
        self.assertEqual(facts[0]["predicate"], "para")
        self.assertEqual(facts[1]["predicate"], "cong")

    def test_build_visible_premise_summaries_deduplicates_visible_facts(self):
        record = {
            "llm_input_renamed": (
                "<problem>g1: para a b c d [000] ; g2: para a b c d [001] ; "
                "g3: cong a b a c [002] ? eqangle a b c d</problem>"
            )
        }

        summaries = build_visible_premise_summaries(record)

        self.assertEqual(
            summaries,
            ["line ab is parallel to line cd", "ab equals ac"],
        )

    def test_build_visible_premise_summaries_retains_late_goal_grounding_facts_for_real_simtrir_sample(self):
        record = self._load_quality_review_record(9)

        summaries = build_visible_premise_summaries(record)

        self.assertEqual(len(summaries), 12)
        self.assertIn("line dh is parallel to line eg", summaries)
        self.assertIn("b, d, h, i are concyclic", summaries)
        self.assertIn("af equals ag", summaries)

    def test_build_visible_premise_summaries_retains_late_h_facts_for_real_contrir_sample(self):
        record = self._load_quality_review_record(11)

        summaries = build_visible_premise_summaries(record)

        self.assertEqual(len(summaries), 12)
        self.assertIn("d, g, h are collinear", summaries)
        self.assertIn("dg equals dh", summaries)

    def test_audit_source_record_flags_missing_goal_finish_guidance(self):
        record = {
            "llm_input_renamed": "<problem>g1: cong a b a c [000] ? eqangle a b a c</problem>",
            "point_coords_grid": {"a": [0, 0], "b": [1, 0], "c": [0, 1]},
        }

        audit = audit_source_record(
            record,
            image_path=Path("/tmp/nonexistent.png"),
            aux_part="<aux>x00 d : coll d a b [001] ; </aux>",
            visible_goal="eqangle a b a c",
            proof_guidance={},
        )

        self.assertTrue(audit["has_issue"])
        self.assertIn("missing_image", audit["issues"])
        self.assertIn("proof_guidance_missing_goal_finish_relations", audit["issues"])

    def test_audit_source_record_text_variant_skips_missing_image_and_coords(self):
        record = {
            "llm_input_renamed": "<problem>g1: cong a b a c [000] ? eqangle a b a c</problem>",
        }

        audit = audit_source_record(
            record,
            image_path=Path("/tmp/nonexistent.png"),
            aux_part="<aux>x00 d : coll d a b [001] ; </aux>",
            visible_goal="eqangle a b a c",
            proof_guidance={},
            generation_style=INSIGHT_TEXT_V1,
        )

        self.assertNotIn("missing_image", audit["issues"])
        self.assertNotIn("missing_point_coords", audit["issues"])
        self.assertIn("proof_guidance_missing_goal_finish_relations", audit["issues"])

    def test_bridge_step_relation_realized_requires_explicit_relation(self):
        step = {
            "relation": "de equals ce",
            "approved_route_relation": "de equals ce",
        }

        self.assertTrue(
            bridge_step_relation_realized(
                "Because de equals ce, this supplies the equality needed next.",
                step,
            )
        )
        self.assertFalse(
            bridge_step_relation_realized(
                "This prepares the next equality without naming the relation.",
                step,
            )
        )

    def test_count_relation_mentions_uses_visible_point_pool_for_coordinate_cues(self):
        text = (
            "The target ratio around e, f, and j still needs a helper through the outer frame. "
            "A helper on the right side can reconnect the missing route around f and g."
        )
        relations = ["point h looks like the midpoint of ac", "points i, j, and k look nearly collinear"]

        mentions = count_relation_mentions(text, relations, point_names=["a", "c", "e", "f", "g", "h", "i", "j", "k"])

        self.assertEqual(mentions, 0)

    def test_count_relation_mentions_does_not_treat_point_overlap_as_coordinate_reuse(self):
        text = (
            "The d-side obstacle still has to be tied back to e and f before the target equality can close. "
            "A helper around f and g is needed to reconnect the outer structure."
        )
        relations = ["points d, e, and f look nearly collinear"]

        mentions = count_relation_mentions(text, relations, point_names=["d", "e", "f", "g"])

        self.assertEqual(mentions, 0)

    def test_count_relation_mentions_does_not_merge_two_collinear_relations_into_a_third(self):
        text = (
            "Because c, d, k are collinear and c, g, k are collinear, the helper point stays on the d-side line."
        )
        relations = ["c, d, g are collinear"]

        mentions = count_relation_mentions(text, relations, point_names=["c", "d", "g", "k"])

        self.assertEqual(mentions, 0)

    def test_count_relation_mentions_recognizes_midpoint_paraphrase(self):
        text = (
            "A helper point is needed on the line cd to transfer angle and ratio information, "
            "leveraging the fact that f appears to split ac evenly and e appears to split ad evenly."
        )
        relations = [
            "point f looks like the midpoint of ac",
            "point e looks like the midpoint of ad",
        ]

        mentions = count_relation_mentions(text, relations, point_names=["a", "c", "d", "e", "f"])

        self.assertEqual(mentions, 2)

    def test_count_relation_mentions_matches_midpoint_of_segment_surface_to_split_paraphrase(self):
        text = (
            "A helper is needed on the line cd, using the fact that f appears to split ac evenly "
            "and g appears to split cd evenly before the cyclic step."
        )
        relations = [
            "point f looks like the midpoint of segment ac",
            "point g looks like the midpoint of segment cd",
        ]

        mentions = count_relation_mentions(text, relations, point_names=["a", "c", "d", "f", "g"])

        self.assertEqual(mentions, 2)

    def test_relation_mentioned_in_text_accepts_article_wrapped_ratio_surface(self):
        sentence = (
            "Then the ratio ac to af equals the ratio cg to ag, which is the side comparison needed next."
        )

        self.assertTrue(
            relation_mentioned_in_text(
                sentence,
                "ratio ac to af equals ratio cg to ag",
            )
        )

    def test_relation_mentioned_in_text_accepts_equaling_ratio_surface(self):
        sentence = "This leads to the ratio ac to ae equaling the ratio cf to eg."

        self.assertTrue(
            relation_mentioned_in_text(
                sentence,
                "ratio ac to ae equals ratio cf to eg",
            )
        )

    def test_relation_mentioned_in_text_accepts_ratio_of_surface(self):
        sentence = "This leads to the ratio of ac to ae equals the ratio of cf to eg."

        self.assertTrue(
            relation_mentioned_in_text(
                sentence,
                "ratio ac to ae equals ratio cf to eg",
            )
        )

    def test_relation_mentioned_in_text_accepts_midpoint_construction_paraphrase(self):
        sentence = "Construct point h as the midpoint of ad so the helper sits on the needed segment."

        self.assertTrue(
            relation_mentioned_in_text(
                sentence,
                "h is the midpoint of ad",
            )
        )

    def test_relation_mentioned_in_text_accepts_collinear_and_variant(self):
        sentence = "Since a, d, and h are collinear, the helper stays on the old side line."

        self.assertTrue(
            relation_mentioned_in_text(
                sentence,
                "a, d, h are collinear",
            )
        )

    def test_coordinate_relation_matches_candidate_accepts_verbal_segment_equals_surface(self):
        candidate = {
            "relation_type": "equal_length",
            "points": ["a", "c", "b", "d"],
            "summary": "segments ac and bd look equal in length",
        }

        self.assertTrue(coordinate_relation_matches_candidate("ac equals bd", candidate))

    def test_audit_generation_quality_flags_unused_coordinate_cues(self):
        record = {
            "point_coords_grid": {
                "a": [0, 0],
                "b": [4, 0],
                "c": [1, 3],
                "d": [5, 3],
                "e": [6, 1],
                "f": [7, 1],
                "g": [8, 1],
            }
        }
        generation = {
            "plan_parsed": {
                "anchor_points": ["a", "b", "c"],
                "coordinate_relations": [
                    "line ab looks perpendicular to line ac",
                    "points e, f, and g look nearly collinear",
                ],
                "coverage_targets": {
                    "coordinate_focus_points": ["e", "f", "g"],
                    "coordinate_focus_relations": ["points e, f, and g look nearly collinear"],
                    "coordinate_reuse_min": 1,
                    "early_coordinate_reuse_min": 1,
                },
                "aux_direct_relations": ["ah equals dh"],
                "bridge_steps": [{"relation": "dh equals ch"}],
                "goal_finish": "ad equals bc",
            },
            "write_output": "The target still needs one equality, so a helper should connect the d-side back to the main frame. Because ah equals dh, dh equals ch, and therefore ad equals bc.",
        }

        audit = audit_generation_quality(record, generation, "<aux>x00 h : cong a h d h</aux>")

        self.assertIn("coordinate_cues_not_reused_in_body", audit["issues"])
        self.assertIn("non_anchor_coordinate_cues_unused", audit["issues"])
        self.assertIn("early_non_anchor_coordinate_cue_missing", audit["issues"])

    def test_audit_generation_quality_flags_unused_observation_cues(self):
        record = {
            "point_coords_grid": {
                "a": [0, 0],
                "b": [4, 0],
                "c": [1, 3],
                "d": [5, 3],
                "e": [6, 1],
                "f": [7, 1],
                "g": [8, 1],
            }
        }
        generation = {
            "plan_parsed": {
                "anchor_points": ["a", "b", "c"],
                "observation_relations": [
                    {
                        "relation": "points e, f, and g look nearly collinear",
                        "points": ["e", "f", "g"],
                    }
                ],
                "coordinate_relations": [],
                "coverage_targets": {
                    "observation_focus_relations": ["points e, f, and g look nearly collinear"],
                    "observation_focus_regions": ["around e, f, and g"],
                },
                "aux_direct_relations": ["ah equals dh"],
                "bridge_steps": [{"relation": "dh equals ch"}],
                "goal_finish": "ad equals bc",
            },
            "write_output": "The target still needs one equality, so a helper should connect the d-side back to the main frame. Because ah equals dh, dh equals ch, and therefore ad equals bc.",
        }

        audit = audit_generation_quality(record, generation, "<aux>x00 h : cong a h d h</aux>")

        self.assertIn("observation_cues_not_reused_in_body", audit["issues"])
        self.assertIn("early_observation_cue_missing", audit["issues"])

    def test_audit_generation_quality_accepts_reused_observation_cues(self):
        record = {
            "point_coords_grid": {
                "a": [0, 0],
                "b": [4, 0],
                "c": [1, 3],
                "d": [5, 3],
                "e": [6, 1],
                "f": [7, 1],
                "g": [8, 1],
            }
        }
        generation = {
            "plan_parsed": {
                "anchor_points": ["a", "b", "c"],
                "observation_relations": [
                    {
                        "relation": "points e, f, and g look nearly collinear",
                        "points": ["e", "f", "g"],
                    }
                ],
                "coordinate_relations": [],
                "coverage_targets": {
                    "observation_focus_relations": ["points e, f, and g look nearly collinear"],
                    "observation_focus_regions": ["around e, f, and g"],
                },
                "aux_direct_relations": ["ah equals dh"],
                "bridge_steps": [{"relation": "dh equals ch"}],
                "goal_finish": "ad equals bc",
            },
            "write_output": "The line through e, f, and g stays nearly collinear, so the outer right side should be tracked with the helper. Because ah equals dh, dh equals ch, and therefore ad equals bc.",
        }

        audit = audit_generation_quality(record, generation, "<aux>x00 h : cong a h d h</aux>")

        self.assertNotIn("observation_cues_not_reused_in_body", audit["issues"])
        self.assertNotIn("early_observation_cue_missing", audit["issues"])

    def test_audit_generation_quality_accepts_reused_coordinate_cues(self):
        record = {
            "point_coords_grid": {
                "a": [0, 0],
                "b": [4, 0],
                "c": [1, 3],
                "d": [5, 3],
                "e": [6, 1],
                "f": [7, 1],
                "g": [8, 1],
            }
        }
        generation = {
            "plan_parsed": {
                "anchor_points": ["a", "b", "c"],
                "coordinate_relations": [
                    "line ab looks perpendicular to line ac",
                    "points e, f, and g look nearly collinear",
                ],
                "coverage_targets": {
                    "coordinate_focus_points": ["e", "f", "g"],
                    "coordinate_focus_relations": ["points e, f, and g look nearly collinear"],
                    "coordinate_reuse_min": 1,
                    "early_coordinate_reuse_min": 1,
                },
                "aux_direct_relations": ["ah equals dh"],
                "bridge_steps": [{"relation": "dh equals ch"}],
                "goal_finish": "ad equals bc",
            },
            "write_output": "The line through e, f, and g stays nearly collinear, so the outer right side should be tracked with the helper. Because ah equals dh, dh equals ch, and therefore ad equals bc.",
        }

        audit = audit_generation_quality(record, generation, "<aux>x00 h : cong a h d h</aux>")

        self.assertNotIn("coordinate_cues_not_reused_in_body", audit["issues"])
        self.assertNotIn("non_anchor_coordinate_cues_unused", audit["issues"])
        self.assertNotIn("early_non_anchor_coordinate_cue_missing", audit["issues"])

    def test_audit_generation_quality_adds_downstream_overclaim_for_remote_hidden_bridge_claim(self):
        record = {
            "point_coords_grid": {
                "a": [0, 0],
                "b": [2, 0],
                "c": [1, 2],
                "d": [4, 2],
                "e": [5, 1],
                "f": [3, 1],
            }
        }
        generation = {
            "plan_parsed": {
                "insight_version": INSIGHT_IMAGE_V1,
                "goal_gap_type": "angle_transfer",
                "goal_gap_text": "the visible givens still do not transfer the angle from b and c onto d and e in one local frame",
                "required_aux_effect": "a, c, d, f are concyclic",
                "aux_selection_reason": "the cyclic helper around a, c, d, and f is the first local frame before b, e, and f can be revisited near d and e",
                "canonical_aux_direct_consequences": [
                    "a, c, d, f are concyclic",
                    "b, d, f are collinear",
                ],
                "insight_slots": {
                    "required_aux_effect": "a, c, d, f are concyclic",
                    "first_bridge_checkpoint": "b, e, f are collinear",
                    "pre_goal_checkpoint": "angle ab/bf equals angle cd/ef",
                },
            },
            "write_output": (
                "The visible givens still do not transfer the angle from the b-side onto the d-side in one local frame. "
                "Construct point f such that a, c, d, f are concyclic and b, d, f are collinear. "
                "This cyclic step means the angle at e can now be transferred."
            ),
        }

        audit = audit_generation_quality(
            record,
            generation,
            "<aux>x00 f : cyclic a c d f [001] ; x00 f : coll b d f [002] ; </aux>",
        )

        self.assertIn("downstream_overclaim", audit["issues"])

    def test_audit_generation_quality_does_not_flag_cautious_local_unlock_as_downstream_overclaim(self):
        record = {
            "point_coords_grid": {
                "a": [0, 0],
                "b": [2, 0],
                "c": [1, 2],
                "d": [4, 2],
                "f": [3, 1],
            }
        }
        generation = {
            "plan_parsed": {
                "insight_version": INSIGHT_IMAGE_V1,
                "goal_gap_type": "angle_transfer",
                "goal_gap_text": "the visible givens still do not transfer the angle from b and c onto d and f in one local frame",
                "required_aux_effect": "a, c, d, f are concyclic",
                "aux_selection_reason": "the cyclic helper around a, c, d, and f is the first local frame before the old figure is revisited",
                "canonical_aux_direct_consequences": [
                    "a, c, d, f are concyclic",
                ],
                "insight_slots": {
                    "required_aux_effect": "a, c, d, f are concyclic",
                    "first_bridge_checkpoint": "b, e, f are collinear",
                    "pre_goal_checkpoint": "angle ab/bf equals angle cd/ef",
                },
            },
            "write_output": (
                "The visible givens still do not transfer the angle from the b-side onto the d-side in one local frame. "
                "Construct point f such that a, c, d, f are concyclic. "
                "This creates one local angle carrier around a, c, d, and f and gives one local frame that can be reused later."
            ),
        }

        audit = audit_generation_quality(
            record,
            generation,
            "<aux>x00 f : cyclic a c d f [001] ; </aux>",
        )

        self.assertNotIn("downstream_overclaim", audit["issues"])

    def test_audit_generation_quality_allows_long_visible_only_insight_body(self):
        record = {
            "point_coords_grid": {
                "a": [0, 0],
                "b": [2, 0],
                "c": [1, 2],
                "d": [4, 2],
                "f": [3, 1],
            }
        }
        generation = {
            "plan_parsed": {
                "insight_version": INSIGHT_IMAGE_V1,
                "goal_gap_type": "angle_transfer",
                "goal_gap_text": "the visible givens still do not transfer the angle from b and c onto d and f in one local frame",
                "required_aux_effect": "a, c, d, f are concyclic",
                "aux_selection_reason": "the cyclic helper around a, c, d, and f is the first local frame before b, d, and f can be reused near the d-side",
                "canonical_aux_direct_consequences": [
                    "a, c, d, f are concyclic",
                    "b, d, f are collinear",
                ],
                "insight_slots": {
                    "required_aux_effect": "a, c, d, f are concyclic",
                    "first_bridge_checkpoint": "b, d, f are collinear",
                    "pre_goal_checkpoint": "angle ab/bf equals angle cd/df",
                },
            },
            "write_output": (
                "The visible givens still do not move the needed angle from the b-side onto the d-side inside one local frame. "
                "Point b and point d already define the old corridor, but nothing visible yet turns that corridor through a helper circle. "
                "The scan also suggests that the line through b, d, and f can be reused once f is chosen. "
                "Construct point f such that a, c, d, and f are concyclic and b, d, f are collinear. "
                "That circle relation creates a fresh angle carrier around a, c, d, and f. "
                "Because the helper stays local to a, c, d, and f, it adds the missing carrier without pretending the target is already solved. "
                "Because b, d, and f remain on one line, the old side still touches the new carrier at the same visible track. "
                "Because those two effects meet at f, the next comparison can stay short and local before the argument returns to b and d."
            ),
        }

        audit = audit_generation_quality(
            record,
            generation,
            "<aux>x00 f : cyclic a c d f [001] ; x00 f : coll b d f [002] ; </aux>",
        )

        self.assertNotIn("no_proof_echo", audit["issues"])
        self.assertNotIn("visible_only_boundary", audit["issues"])
        self.assertNotIn("downstream_overclaim", audit["issues"])

    def test_audit_generation_quality_flags_remote_connection_claim_as_downstream_overclaim(self):
        record = {
            "point_coords_grid": {
                "a": [0, 0],
                "b": [2, 0],
                "c": [1, 2],
                "d": [4, 2],
                "e": [5, 1],
                "g": [6, 1],
                "h": [3, 2],
            }
        }
        generation = {
            "plan_parsed": {
                "insight_version": INSIGHT_IMAGE_V1,
                "goal_gap_type": "ratio_transfer",
                "goal_gap_text": "the visible givens still do not transfer the ratio from a and d onto b and e in one local frame",
                "required_aux_effect": "h is the midpoint of ad",
                "aux_selection_reason": "the midpoint at h is the first local frame before the b, e, and g side can be revisited",
                "canonical_aux_direct_consequences": [
                    "h is the midpoint of ad",
                ],
                "insight_slots": {
                    "required_aux_effect": "h is the midpoint of ad",
                    "first_bridge_checkpoint": "ratio ad to ah equals ratio be to eg",
                    "pre_goal_checkpoint": "ratio ae to ah equals ratio be to bg",
                },
            },
            "write_output": (
                "The visible givens still do not transfer the ratio from the a-side onto the b-side in one local frame. "
                "Construct point h so that h is the midpoint of ad. "
                "With h established, the ratio around ad and ah can now be linked to the segments be and eg."
            ),
        }

        audit = audit_generation_quality(
            record,
            generation,
            "<aux>x00 h : midp h a d [001] ; </aux>",
        )

        self.assertIn("downstream_overclaim", audit["issues"])

    def test_audit_generation_quality_does_not_flag_downstream_claim_when_intermediate_relation_is_stated(self):
        record = {
            "point_coords_grid": {
                "a": [0, 0],
                "b": [2, 0],
                "c": [1, 2],
                "d": [4, 2],
                "e": [5, 1],
                "f": [3, 1],
            }
        }
        generation = {
            "plan_parsed": {
                "insight_version": INSIGHT_IMAGE_V1,
                "goal_gap_type": "angle_transfer",
                "goal_gap_text": "the visible givens still do not transfer the angle from b and c onto d and e in one local frame",
                "required_aux_effect": "a, c, d, f are concyclic",
                "aux_selection_reason": "the cyclic helper around a, c, d, and f is the first local frame before b, e, and f can be revisited near d and e",
                "canonical_aux_direct_consequences": [
                    "a, c, d, f are concyclic",
                    "b, d, f are collinear",
                ],
                "insight_slots": {
                    "required_aux_effect": "a, c, d, f are concyclic",
                    "first_bridge_checkpoint": "b, e, f are collinear",
                    "pre_goal_checkpoint": "angle ab/bf equals angle cd/ef",
                },
            },
            "write_output": (
                "The visible givens still do not transfer the angle from the b-side onto the d-side in one local frame. "
                "Construct point f such that a, c, d, f are concyclic and b, d, f are collinear. "
                "Because b, e, f are collinear, the angle at e can now be transferred."
            ),
        }

        audit = audit_generation_quality(
            record,
            generation,
            "<aux>x00 f : cyclic a c d f [001] ; x00 f : coll b d f [002] ; </aux>",
        )

        self.assertNotIn("downstream_overclaim", audit["issues"])

    def test_audit_generation_quality_ignores_generic_wording_without_downstream_claim(self):
        record = {
            "point_coords_grid": {
                "a": [0, 0],
                "b": [2, 0],
                "c": [1, 2],
                "d": [4, 2],
                "e": [5, 1],
                "f": [3, 1],
            }
        }
        generation = {
            "plan_parsed": {
                "insight_version": INSIGHT_IMAGE_V1,
                "goal_gap_type": "angle_transfer",
                "goal_gap_text": "the visible givens still do not transfer the angle from b and c onto d and e in one local frame",
                "required_aux_effect": "a, c, d, f are concyclic",
                "aux_selection_reason": "the cyclic helper around a, c, d, and f is the first local frame before b, e, and f can be revisited near d and e",
                "canonical_aux_direct_consequences": [
                    "a, c, d, f are concyclic",
                    "b, d, f are collinear",
                ],
                "insight_slots": {
                    "required_aux_effect": "a, c, d, f are concyclic",
                    "first_bridge_checkpoint": "b, e, f are collinear",
                    "pre_goal_checkpoint": "angle ab/bf equals angle cd/ef",
                },
            },
            "write_output": (
                "The visible givens still do not transfer the angle from the b-side onto the d-side in one local frame. "
                "Construct point f such that a, c, d, f are concyclic and b, d, f are collinear. "
                "This keeps the helper local and leaves the later route short."
            ),
        }

        audit = audit_generation_quality(
            record,
            generation,
            "<aux>x00 f : cyclic a c d f [001] ; x00 f : coll b d f [002] ; </aux>",
        )

        self.assertNotIn("downstream_overclaim", audit["issues"])

    def test_audit_generation_quality_flags_shallow_coordinate_reuse(self):
        record = {
            "point_coords_grid": {
                "a": [0, 0],
                "b": [4, 0],
                "c": [1, 3],
                "d": [5, 3],
                "e": [6, 1],
                "f": [7, 1],
                "g": [8, 1],
            }
        }
        generation = {
            "plan_parsed": {
                "anchor_points": ["a", "b", "c"],
                "coordinate_relations": [
                    "points e, f, and g look nearly collinear",
                    "line ab looks perpendicular to line ac",
                ],
                "coverage_targets": {
                    "coordinate_focus_points": ["e", "f", "g"],
                    "coordinate_focus_relations": [
                        "points e, f, and g look nearly collinear",
                        "line ab looks perpendicular to line ac",
                    ],
                    "coordinate_reuse_min": 2,
                    "early_coordinate_reuse_min": 1,
                },
                "aux_direct_relations": ["ah equals dh"],
                "bridge_steps": [{"relation": "dh equals ch"}],
                "goal_finish": "ad equals bc",
            },
            "write_output": "The line through e, f, and g stays nearly collinear, so the outer right side should be tracked with the helper. Because ah equals dh, dh equals ch, and therefore ad equals bc.",
        }

        audit = audit_generation_quality(record, generation, "<aux>x00 h : cong a h d h</aux>")

        self.assertIn("coordinate_cue_reuse_too_shallow:1/2", audit["issues"])

    def test_audit_generation_quality_flags_bridge_sentence_that_uses_conclusion_as_self_support(self):
        record = {
            "point_coords_grid": {
                "a": [-2, -2],
                "b": [-4, -4],
                "c": [4, 0],
                "d": [6, 2],
                "e": [-1, 6],
                "f": [1, -1],
                "g": [5, 1],
                "j": [4, -3],
            }
        }
        generation = {
            "plan_parsed": {
                "anchor_points": ["a", "b", "c", "e"],
                "coordinate_relations": [
                    "point f looks like the midpoint of ac",
                    "point g looks like the midpoint of cd",
                    "points b, d, and f look nearly collinear",
                ],
                "coverage_targets": {
                    "coordinate_focus_points": ["f", "d", "g"],
                    "coordinate_focus_relations": [
                        "point f looks like the midpoint of ac",
                        "point g looks like the midpoint of cd",
                    ],
                    "coordinate_reuse_min": 1,
                    "early_coordinate_reuse_min": 1,
                },
                "aux_direct_relations": [
                    "b, f, g, k are concyclic",
                    "c, d, k are collinear",
                ],
                "bridge_steps": [
                    {
                        "relation": "c, g, k are collinear",
                        "required_supports": [
                            "c, d, g are collinear",
                            "c, d, k are collinear",
                        ],
                        "min_support_mentions": 2,
                    },
                    {
                        "relation": "b, d, f are collinear",
                        "required_supports": ["points b, d, and f look nearly collinear"],
                        "min_support_mentions": 1,
                    },
                ],
                "goal_finish": "ratio ae to af equals ratio ce to cj",
            },
            "write_output": (
                "The remaining obstacle is to connect ae, af, ce, and cj, so points f and j must be tied back to the outer d-side configuration before the target ratio can close. "
                "Since point f looks like the midpoint of ac and point g looks like the midpoint of cd, a helper through k can track the outer line through d and g without losing the f-side comparison. "
                "Because c, d, g are collinear and c, d, k are collinear, c, g, k are collinear, and this places k on the outer d-g line for the next step. "
                "Because b, f, g, k are concyclic and c, d, k are collinear, b, d, f are collinear, and this fixes the line needed for the angle transfer. "
                "Therefore, ratio ae to af equals ratio ce to cj."
            ),
        }

        audit = audit_generation_quality(
            record,
            generation,
            "<aux>x00 k : cyclic b f g k [016] coll c d k [017]</aux>",
        )

        self.assertIn("bridge_supports_missing_in_body:1", audit["issues"])

    def test_audit_generation_quality_uses_dossier_specific_checks(self):
        record = {
            "point_coords_grid": {
                "a": [0, 0],
                "b": [4, 0],
                "c": [0, 2],
                "d": [4, 2],
            }
        }
        generation = {
            "plan_parsed": {
                "dossier_version": "dossier_v1",
                "image_scan": ["point a looks like the midpoint of bc"],
                "coordinate_relations": ["point a looks like the midpoint of bc"],
                "aux_immediate_effects": ["ah equals dh", "bh equals ch"],
                "bridge_chain": [
                    {
                        "claim": "ah equals bh",
                        "supports": ["visible_facts[2]", "coordinate_checks[1]"],
                        "why_next": "this creates the helper balance.",
                    },
                    {
                        "claim": "dh equals ch",
                        "supports": ["aux_immediate_effects[1]", "bridge_chain[1]"],
                        "why_next": "this transfers the helper balance.",
                    },
                ],
                "goal_closure": [
                    {
                        "claim": "ad equals bc",
                        "supports": ["bridge_chain[2]", "visible_facts[2]"],
                        "why_next": "this is the target relation.",
                    }
                ],
            },
            "write_output": (
                "The obstacle is to transfer the d-side and c-side through one helper frame before the target equality closes. "
                "The figure also suggests that point a looks like the midpoint of bc, so the outer balance around a, b, and c is worth tracking. "
                "Construct point h such that ah equals dh and bh equals ch. "
                "From the construction, ah equals dh and bh equals ch. "
                "These equalities give ah equals bh, which creates one shared balance inside the helper frame. "
                "Then dh equals ch, so that helper balance reaches the d-side and c-side. "
                "Therefore ad equals bc."
            ),
        }

        audit = audit_generation_quality(record, generation, "<aux>x00 h : cong a h d h; cong b h c h</aux>")

        self.assertNotIn("bridge_supports_missing_in_body:0", audit["issues"])
        self.assertNotIn("bridge_supports_missing_in_body:1", audit["issues"])
        self.assertNotIn("goal_closure_missing_in_body:0", audit["issues"])


if __name__ == "__main__":
    unittest.main()
