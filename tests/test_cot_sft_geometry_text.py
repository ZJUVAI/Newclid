import unittest

from experiments.cot_sft_generation.geometry_text import (
    align_bridge_steps_to_hidden_route,
    build_canonical_construction,
    build_hidden_coordinate_candidates,
    build_hidden_coordinate_guidance,
    build_multi_aux_instruction,
    build_public_problem_text,
    extract_relation_segment_tokens,
    extract_problem_goal,
    normalize_relation_surface,
    relation_text_keywords,
    relations_semantically_match,
    select_support_relations_for_step,
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
        self.assertEqual(
            normalize_relation_surface("points b, d, and f look nearly collinear"),
            "b, d, f are collinear",
        )
        self.assertEqual(
            normalize_relation_surface("the line through e, f, and g stays nearly collinear"),
            "e, f, g are collinear",
        )
        self.assertEqual(
            normalize_relation_surface("points a, c, and e lie on a straight line"),
            "a, c, e are collinear",
        )
        self.assertEqual(
            normalize_relation_surface("lines ae and cf intersect at right angles"),
            "line ae is perpendicular to line cf",
        )
        self.assertEqual(
            normalize_relation_surface("point g appears to be equidistant from b and e"),
            "gb equals ge",
        )

    def test_relations_semantically_match_accepts_surface_variants(self):
        self.assertTrue(
            relations_semantically_match(
                "triangle afg is similar to triangle cfg",
                "triangles afg and cfg are similar",
                ["a", "c", "f", "g"],
            )
        )
        self.assertTrue(
            relations_semantically_match(
                "points b, d, and f look nearly collinear",
                "b, d, f are collinear",
                ["b", "d", "f"],
            )
        )

    def test_relation_text_keywords_does_not_treat_triangles_as_angle_relations(self):
        self.assertEqual(
            relation_text_keywords("triangles abf and acf are congruent"),
            {"equal"},
        )
        self.assertEqual(
            relation_text_keywords("triangles agi and igh are similar"),
            {"similar"},
        )
        self.assertEqual(
            relation_text_keywords("angle ab/ac equals angle ad/ae"),
            {"angle", "equal"},
        )

    def test_extract_relation_segment_tokens_and_support_ranking_handle_natural_collinear_cues(self):
        self.assertEqual(
            extract_relation_segment_tokens("points b, d, and f look nearly collinear"),
            {"bd", "bf", "df"},
        )

        supports = [
            "points b, d, and f look nearly collinear",
            "b, f, g, k are concyclic",
            "c, d, k are collinear",
            "ab is parallel to cd",
        ]
        ranked = select_support_relations_for_step(
            "b, d, f are collinear",
            supports,
            ["a", "b", "c", "d", "f", "g", "k"],
            next_target_relation="angle bd/bg equals angle fk/dk",
            max_supports=3,
        )

        self.assertEqual(ranked[0], "points b, d, and f look nearly collinear")

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

    def test_build_hidden_coordinate_candidates_and_guidance(self):
        point_coords = {
            "a": (0, 0),
            "b": (4, 0),
            "c": (1, 3),
            "d": (5, 3),
        }

        candidates = build_hidden_coordinate_candidates(point_coords, max_items=8, relax_type_limits=True)
        guidance = build_hidden_coordinate_guidance(point_coords, max_items=4)

        self.assertTrue(any(item["relation_type"] == "parallel" for item in candidates))
        self.assertTrue(any(item["relation_type"] == "equal_length" for item in candidates))
        self.assertIn("segments ab and cd look parallel", guidance)


if __name__ == "__main__":
    unittest.main()
