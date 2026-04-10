"""Tests for problem parsing and building."""

import pytest
from newclid.api import GeometricSolverBuilder


@pytest.fixture
def builder():
    return GeometricSolverBuilder(seed=998244353)


class TestProblemBuild:
    def test_triangle_with_orthocenter(self, builder):
        solver = builder.load_problem_from_txt(
            "a b c = triangle a b c; "
            "h = on_tline h b a c, on_tline h c a b "
            "? perp a h b c"
        ).build()
        assert solver.run()

    def test_goal_free_problem(self, builder):
        """Goal-free problems should build without error."""
        solver = builder.load_problem_from_txt(
            "a b c = triangle a b c; h = on_tline h b a c, on_tline h c a b"
        ).build()
        assert solver is not None

    def test_build_multiple_problems_sequentially(self, builder):
        """Builder should support loading and building different problems."""
        solver1 = builder.load_problem_from_txt(
            "a b c = triangle a b c; "
            "h = on_tline h b a c, on_tline h c a b "
            "? perp a h b c",
        ).build()
        assert solver1.run()

        solver2 = builder.load_problem_from_txt(
            "a b c = triangle a b c",
        ).build()
        assert solver2 is not None

    def test_simple_midpoint_problem(self, builder):
        solver = builder.load_problem_from_txt(
            "a b = segment a b; m = midpoint m a b ? rconst m a a b 1/2"
        ).build()
        assert solver.run()
