import unittest
from pathlib import Path

from experiments.cot_sft_generation.audits import (
    audit_generation_quality,
    audit_source_record,
    bridge_step_relation_realized,
    build_visible_premise_summaries,
    count_relation_mentions,
    extract_visible_formal_facts,
    get_point_coords,
)


class CotSftAuditsTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
