import pytest
import pytest_check as check

from geosolver.api import GeometricSolverBuilder


class TestDDAR:
    @pytest.fixture(autouse=True)
    def setUpClass(self):
        self.solver_builder = GeometricSolverBuilder()

    def test_orthocenter_should_fail(self):
        solver = self.solver_builder.load_problem_from_txt(
            "a b c = triangle a b c; "
            "d = on_tline d b a c, on_tline d c a b "
            "? perp a d b c"
        ).build()
        success = solver.run()
        check.is_false(success)

    def test_orthocenter_aux_should_succeed(self):
        solver = self.solver_builder.load_problem_from_txt(
            "a b c = triangle a b c; "
            "d = on_tline d b a c, on_tline d c a b; "
            "e = on_line e a c, on_line e b d "
            "? perp a d b c"
        ).build()
        success = solver.run()
        check.is_true(success)

    def test_orthocenter_should_succeed_after_reset(self):
        """The solver should be reset (deductive agent and proof state)
        before adding auxiliary construction or attempting a new round of DDAR"""
        solver = self.solver_builder.load_problem_from_txt(
            "a b c = triangle a b c; "
            "d = on_tline d b a c, on_tline d c a b "
            "? perp a d b c"
        ).build()
        success = solver.run()
        check.is_false(success)
        solver.add_auxiliary_construction("e = on_line e a c, on_line e b d")
        success = solver.run()
        check.is_true(success)

    def test_incenter_excenter_should_succeed(self):
        # Note that this same problem should fail with DD only
        solver = self.solver_builder.load_problem_from_txt(
            "a b c = triangle a b c; "
            "d = incenter d a b c; "
            "e = excenter e a b c "
            "? perp d c c e"
        ).build()
        success = solver.run()
        check.is_true(success)
