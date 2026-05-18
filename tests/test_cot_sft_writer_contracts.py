import unittest

from experiments.cot_sft_generation.writer_contracts import (
    build_injected_prefix_block,
    build_plan_coverage_targets,
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

    def test_build_writer_handoff_and_prefix_block_include_expected_fields(self):
        plan = {
            "anchor_points": ["a", "b", "c"],
            "anchor_relation": "triangle abc is the main visible frame",
            "figure_overview": "point d lies on line bc",
            "coordinate_hints": "the near-collinearity of b, c, and d matters",
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
                "opening_sentence_hint": "name d in the opening obstacle",
                "helper_sentence_hint": "name d and e in the helper sentence",
            },
        }
        point_coords = {"a": (0, 0), "b": (2, 0), "c": (1, 2)}

        handoff = build_writer_handoff(plan)
        prefix = build_injected_prefix_block(plan, point_coords)

        self.assertEqual(handoff["bridge_steps"][0]["relation"], "de equals ce")
        self.assertIn("<point>a</point><coord>(0,0)</coord>", prefix)
        self.assertIn("The visible givens also show that ab equals ac.", prefix)


if __name__ == "__main__":
    unittest.main()
