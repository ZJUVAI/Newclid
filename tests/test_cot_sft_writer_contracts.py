import unittest

from experiments.cot_sft_generation.writer_contracts import (
    build_coordinate_derivation_block,
    build_instruction_text,
    build_writer_handoff,
    join_natural_list,
    render_coordinate_derivation_snippet,
)


class CotSftWriterContractsTest(unittest.TestCase):
    def test_build_instruction_text_mentions_goal_route(self):
        text = build_instruction_text()
        self.assertIn("auxiliary construction", text)
        self.assertIn("goal", text)

    def test_join_natural_list_formats_three_items(self):
        text = join_natural_list(["a", "b", "c"])
        self.assertEqual(text, "a, b, and c")

    def test_render_coordinate_derivation_snippet_parallel(self):
        snippet = render_coordinate_derivation_snippet(
            {
                "relation": "segments ab and cd look parallel",
                "points": ["a", "b", "c", "d"],
                "calc_type": "parallel",
                "witness": {"vector_1": [4, 0], "vector_2": [4, 0], "cross": 0},
            },
            {"a": (0, 0), "b": (4, 0), "c": (0, 2), "d": (4, 2)},
        )

        self.assertIn("a=(0,0)", snippet)
        self.assertIn("vec(ab)", snippet)
        self.assertIn("cross product is 0", snippet)

    def test_build_coordinate_derivation_block_renders_all_items(self):
        plan = {
            "coordinate_derivations": [
                {
                    "relation": "segments ab and cd look parallel",
                    "points": ["a", "b", "c", "d"],
                    "calc_type": "parallel",
                    "witness": {"vector_1": [4, 0], "vector_2": [4, 0], "cross": 0},
                },
                {
                    "relation": "points a, c, and e look nearly collinear",
                    "points": ["a", "c", "e"],
                    "calc_type": "collinear",
                    "witness": {"area_residual": 0},
                },
            ]
        }
        block = build_coordinate_derivation_block(
            plan,
            {"a": (0, 0), "b": (4, 0), "c": (0, 2), "d": (4, 2), "e": (0, 4)},
        )

        self.assertIn("segments ab and cd look parallel", block)
        self.assertIn("signed area test", block)

    def test_build_writer_handoff_keeps_new_schema_fields(self):
        handoff = build_writer_handoff(
            {
                "selected_text_fact_ids": ["T1"],
                "selected_coordinate_candidate_ids": ["C1"],
                "visible_relations": ["line ab is parallel to line cd"],
                "coordinate_relations": ["segments ab and cd look parallel"],
                "bridge_steps": [{"relation": "angle abc equals angle cda"}],
                "goal_finish": "angle abc equals angle dcb",
            }
        )

        self.assertEqual(handoff["selected_text_fact_ids"], ["T1"])
        self.assertEqual(handoff["selected_coordinate_candidate_ids"], ["C1"])
        self.assertEqual(handoff["goal_finish"], "angle abc equals angle dcb")


if __name__ == "__main__":
    unittest.main()
