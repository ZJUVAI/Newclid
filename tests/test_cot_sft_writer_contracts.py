import unittest

from experiments.cot_sft_generation.writer_contracts import (
    build_injected_prefix_block,
    build_plan_coverage_targets,
    build_prefix_reuse_guidance,
    build_writer_handoff,
    enrich_bridge_steps_with_targets,
)


class CotSftWriterContractsTest(unittest.TestCase):
    def test_enrich_bridge_steps_with_targets_sets_next_targets(self):
        plan = {
            "goal_finish": "angle abc equals angle def",
            "bridge_steps": [
                {"relation": "ab equals bc", "depends_on": ["a, b, c are collinear"]},
                {"relation": "line ad is parallel to line bc", "depends_on": []},
            ],
        }

        enriched = enrich_bridge_steps_with_targets(plan)

        self.assertEqual(
            enriched["bridge_steps"][0]["next_target_relation"],
            "line ad is parallel to line bc",
        )
        self.assertEqual(
            enriched["bridge_steps"][1]["next_target_relation"],
            "angle abc equals angle def",
        )
        self.assertEqual(enriched["bridge_steps"][0]["required_supports"], ["a, b, c are collinear"])

    def test_build_plan_coverage_targets_tracks_non_anchor_points(self):
        plan = {
            "anchor_points": ["a", "b", "c"],
            "figure_overview": "point d lies on bc while point e lies beyond c on line ac",
            "observation_relations": [
                {
                    "relation": "points b, c, and d are collinear",
                    "points": ["b", "c", "d"],
                }
            ],
            "coordinate_relations": ["points b, c, d are collinear"],
            "visible_relations": ["line ae is parallel to line bd"],
            "bridge_steps": [
                {"relation": "de equals ce"},
            ],
            "goal_finish": "eqangle a d c e",
        }

        coverage = build_plan_coverage_targets(
            plan,
            visible_goal="eqangle a d c e",
            visible_points=["a", "b", "c", "d", "e"],
        )

        self.assertIn("d", coverage["goal_points"])
        self.assertIn("e", coverage["goal_points"])
        self.assertTrue(coverage["non_anchor_points"])
        self.assertTrue(coverage["focus_relations"])
        self.assertEqual(coverage["coordinate_focus_points"], ["d"])
        self.assertEqual(coverage["observation_focus_relations"], ["b, c, d are collinear"])
        self.assertEqual(coverage["coordinate_reuse_min"], 1)

    def test_build_writer_handoff_and_prefix_block_include_expected_fields(self):
        plan = {
            "anchor_points": ["a", "b", "c"],
            "anchor_relation": "triangle abc is the main visible frame",
            "figure_overview": "point d lies on line bc",
            "coordinate_hints": "the near-collinearity of b, c, and d matters",
            "observation_relations": [
                {
                    "relation": "points b, c, and d look nearly collinear",
                    "points": ["b", "c", "d"],
                }
            ],
            "coordinate_relations": ["points b, c, and d look nearly collinear"],
            "visible_relations": ["ab equals ac"],
            "goal_bottleneck": "the target angle still needs a link through d",
            "helper_idea": "a helper should connect d back to the equal sides",
            "construction": "construct point e on line ad",
            "aux_direct_relations": ["a, d, e are collinear"],
            "goal_finish": "angle abc equals angle dce",
            "bridge_steps": [
                {
                    "relation": "de equals ce",
                    "approved_route_relation": "de equals ce",
                    "required_supports": ["a, d, e are collinear"],
                    "min_support_mentions": 1,
                    "focus_points": ["d", "e"],
                    "next_target_purpose": "this supplies the angle comparison needed next.",
                }
            ],
            "coverage_targets": {
                "opening_focus_points": ["d"],
                "bridge_focus_points": ["d", "e"],
                "coordinate_focus_points": ["d"],
                "coordinate_focus_relations": ["points b, c, and d look nearly collinear"],
                "observation_focus_relations": ["points b, c, and d look nearly collinear"],
                "observation_focus_regions": ["around d"],
                "coordinate_reuse_min": 1,
                "opening_sentence_hint": "name d in the opening obstacle",
                "helper_sentence_hint": "name d and e in the helper sentence",
                "coordinate_sentence_hint": "reuse the d-side collinearity early",
            },
        }
        point_coords = {"a": (0, 0), "b": (2, 0), "c": (1, 2)}

        handoff = build_writer_handoff(plan)
        prefix = build_injected_prefix_block(plan, point_coords)

        self.assertEqual(handoff["bridge_steps"][0]["relation"], "de equals ce")
        self.assertEqual(handoff["coordinate_focus_points"], ["d"])
        self.assertEqual(handoff["observation_focus_relations"], ["points b, c, and d look nearly collinear"])
        self.assertTrue(prefix.startswith("The first useful visual checks are"))
        self.assertIn("<point>a</point><coord>(0,0)</coord>", prefix)
        self.assertIn("The visible givens also show that ab equals ac.", prefix)

    def test_build_prefix_reuse_guidance_includes_coordinate_relations(self):
        plan = {
            "coordinate_relations": ["point g looks like the midpoint of cd"],
            "visible_relations": ["line ab is parallel to line cd"],
        }

        guidance = build_prefix_reuse_guidance(plan)

        self.assertIn("point g looks like the midpoint of cd", guidance)
        self.assertIn("midpoint-looking point g on cd", guidance)
        self.assertIn("line ab is parallel to line cd", guidance)

    def test_build_plan_coverage_targets_extends_budget_for_complex_plan(self):
        plan = {
            "anchor_points": ["a", "b", "c", "d", "e"],
            "figure_overview": "points f and g lie on the right side while h, i, and j spread across the lower frame",
            "coordinate_relations": [
                "points e, f, and g are collinear",
                "line hi looks parallel to line cd",
                "fj looks equal to gi",
                "points h, i, and j look nearly collinear",
            ],
            "visible_relations": [
                "line ef is parallel to line bg",
                "fj equals gi",
                "points h, i, and j are collinear",
            ],
            "aux_direct_relations": [
                "fk equals gk",
                "line hk is perpendicular to line ij",
                "h, i, k are collinear",
                "jk equals hk",
            ],
            "bridge_steps": [
                {"relation": "fk equals hk"},
                {"relation": "angle fkh equals angle hij"},
                {"relation": "line hj is parallel to line fg"},
                {"relation": "fj equals gj"},
                {"relation": "ratio fj gj equals hi ij"},
            ],
            "goal_finish": "eqratio f j h i",
        }

        coverage = build_plan_coverage_targets(
            plan,
            visible_goal="eqratio f j h i",
            visible_points=["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"],
        )

        self.assertEqual(len(coverage["bridge_focus_points"]), 5)
        self.assertLessEqual(len(coverage["focus_relations"]), 5)
        self.assertIn("f", coverage["non_anchor_points"])
        self.assertIn("h", coverage["goal_points"])
        self.assertGreaterEqual(coverage["coordinate_reuse_min"], 1)
        self.assertTrue(coverage["coordinate_focus_points"])


if __name__ == "__main__":
    unittest.main()
