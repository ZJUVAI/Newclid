"""Tests for search_runtime auxiliary point DSL parsing."""

import unittest
from newclid.agent.runtime.search_runtime import try_dsl_to_constructions


class TestSearchRuntimeAux(unittest.TestCase):
    """Test try_dsl_to_constructions with single and multiple segments."""

    def test_single_segment_coll(self):
        """Test single auxiliary point with collinearity."""
        result = try_dsl_to_constructions("e : coll a b e [002]")
        self.assertEqual(result, "e = on_line e a b")

    def test_single_segment_perp(self):
        """Test single auxiliary point with perpendicularity."""
        result = try_dsl_to_constructions("f : perp a b f c [003]")
        self.assertIsNotNone(result)
        self.assertIn("f =", result)

    def test_multiple_segments(self):
        """Test multiple auxiliary points separated by semicolon."""
        result = try_dsl_to_constructions(
            "e : coll a b e [002] ; f : perp e f a b [003]"
        )
        self.assertEqual(result, "e = on_line e a b; f = on_tline f e a b")

    def test_multiple_segments_with_x_prefix(self):
        """Test multiple segments - each has x00 prefix (actual data format)."""
        result = try_dsl_to_constructions(
            "x00 e : coll a b e [002] ; x00 f : perp e f a b [003]"
        )
        self.assertEqual(result, "e = on_line e a b; f = on_tline f e a b")

    def test_single_segment_with_x_prefix(self):
        """Test backward compatibility with x00 prefix."""
        result = try_dsl_to_constructions("x00 e : coll a b e [002]")
        self.assertEqual(result, "e = on_line e a b")

    def test_empty_input(self):
        """Test empty and whitespace-only inputs."""
        self.assertIsNone(try_dsl_to_constructions(""))
        self.assertIsNone(try_dsl_to_constructions("   "))

    def test_invalid_format_no_colon(self):
        """Test invalid format without colon separator."""
        self.assertIsNone(try_dsl_to_constructions("e coll a b e"))

    def test_invalid_format_multiple_points(self):
        """Test invalid format with multiple point names."""
        self.assertIsNone(try_dsl_to_constructions("e f : coll a b e [002]"))

    def test_free_point(self):
        """Test free point (no predicates)."""
        result = try_dsl_to_constructions("e : [002]")
        self.assertEqual(result, "e = free e")

    def test_multiple_predicates_single_point(self):
        """Test single point with multiple predicates."""
        result = try_dsl_to_constructions(
            "i : cong a i b c [012] eqangle a b a i a i a c [013]"
        )
        self.assertEqual(result, "i = eqdistance i a b c, angle_bisector i c a b")

    def test_trailing_semicolon(self):
        """Test input with trailing semicolon."""
        result = try_dsl_to_constructions("e : coll a b e [002] ;")
        self.assertEqual(result, "e = on_line e a b")

    def test_multiple_segments_trailing_semicolon(self):
        """Test multiple segments with trailing semicolon."""
        result = try_dsl_to_constructions(
            "x00 e : coll a b e [002] ; x00 f : perp e f a b [003] ;"
        )
        self.assertEqual(result, "e = on_line e a b; f = on_tline f e a b")

    def test_three_segments(self):
        """Test three auxiliary points."""
        result = try_dsl_to_constructions(
            "x00 e : coll a b e [002] ; x00 f : perp e f a b [003] ; x00 g : coll c d g [004]"
        )
        self.assertIsNotNone(result)
        self.assertIn("e =", result)
        self.assertIn("f =", result)
        self.assertIn("g =", result)


if __name__ == "__main__":
    unittest.main()
