import unittest

from experiments.cot_sft_generation.geometry_text import (
    align_bridge_steps_to_hidden_route,
    build_canonical_construction,
    build_multi_aux_instruction,
    build_public_problem_text,
    extract_problem_goal,
    normalize_relation_surface,
    relations_semantically_match,
)


class CotSftGeometryTextTest(unittest.TestCase):
    def test_normalize_relation_surface_handles_formal_and_plain_forms(self):
        self.assertEqual(normalize_relation_surface("AB = CD"), "ab equals cd")
        self.assertEqual(
            normalize_relation_surface("point g lies on line ab"),
            "a, b, g are collinear",
        )
        self.assertEqual(
            normalize_relation_surface("triangles AFG and CFG are similar"),
            "triangles afg and cfg are similar",
        )

    def test_relations_semantically_match_accepts_surface_variants(self):
        self.assertTrue(
            relations_semantically_match(
                "triangle afg is similar to triangle cfg",
                "triangles afg and cfg are similar",
                ["a", "c", "f", "g"],
            )
        )

    def test_build_canonical_construction_and_multi_aux_instruction(self):
        aux_part = "<aux>x00 h : coll h a b [001] cong a h b h; x00 k : perp k h a b</aux>"
        construction = build_canonical_construction(aux_part)
        self.assertIn("construct point h such that", construction)
        self.assertIn("are collinear", construction)
        self.assertIn("ah equals bh", construction)
        self.assertIn("then construct point k such that line kh is perpendicular to line ab", construction)

        instruction = build_multi_aux_instruction(aux_part)
        self.assertIn("multiple new points", instruction)
        self.assertIn("h:", instruction)
        self.assertIn("are collinear", instruction)
        self.assertIn("k: line kh is perpendicular to line ab", instruction)

    def test_problem_text_and_goal_extraction(self):
        record = {
            "nl_problem": "observe the diagram",
            "llm_input_renamed": "<problem>Given ab = ac ? eqangle a b c d</problem>",
        }
        public_problem = build_public_problem_text(record)
        self.assertTrue(public_problem.startswith("<nl_problem>observe the diagram</nl_problem>"))
        self.assertEqual(extract_problem_goal(record), "eqangle a b c d")

    def test_align_bridge_steps_to_hidden_route_is_ordered(self):
        bridge_steps = [
            {"relation": "ab equals cd"},
            {"relation": "line ad is parallel to line bc"},
        ]
        hidden_route = [
            "ab equals cd",
            "line ad is parallel to line bc",
            "angle bad equals angle dcb",
        ]
        alignment = align_bridge_steps_to_hidden_route(bridge_steps, hidden_route, ["a", "b", "c", "d"])
        self.assertEqual(alignment["matches"][0]["index"], 0)
        self.assertEqual(alignment["matches"][1]["index"], 1)
        self.assertEqual(alignment["unmatched"], [])


if __name__ == "__main__":
    unittest.main()
