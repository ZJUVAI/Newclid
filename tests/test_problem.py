"""Unit tests for problem.py."""

import pytest
from geosolver.api import GeometricSolverBuilder


class TestProblem:
    @pytest.fixture(autouse=True)
    def setUp(self):
        self.solver_builder = GeometricSolverBuilder()

    def test_orthocenter_build(self):
        self.solver_builder.load_problem_from_txt(
            "a b c = triangle a b c; "
            "h = on_tline h b a c, on_tline h c a b "
            "? perp a h b c",
        ).build()

    def test_goal_free_txt_build(self):
        # Reading goal-free problems from txt should be invertible
        txt = "a b c = triangle a b c; h = on_tline h b a c, on_tline h c a b"
        self.solver_builder.load_problem_from_txt(txt).build()

    def test_multiple_build(self):
        self.solver_builder.load_problem_from_txt(
            "a b c = triangle a b c; "
            "h = on_tline h b a c, on_tline h c a b "
            "? perp a h b c",
        ).build()

        self.solver_builder.load_problem_from_txt(
            "a b c = triangle a b c",
        ).build()
