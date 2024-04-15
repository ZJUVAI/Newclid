import pytest
import pytest_check as check

from geosolver.api import GeometricSolverBuilder


class TestConstants:
    @pytest.fixture(autouse=True)
    def setUpClass(self):
        self.solver_builder = GeometricSolverBuilder()

    def test_triangle12_should_give_rconst(self):
        solver = (
            self.solver_builder.load_problem_from_txt(
                "a b c = triangle12 a b c ? rconst a b a c 1/2"
            )
            .load_defs_from_file("new_defs.txt")
            .build()
        )
        success = solver.run()
        check.is_true(success)

    @pytest.mark.xfail
    def test_rconst_precription(self):
        solver = (
            self.solver_builder.load_problem_from_txt(
                "a b = segment a b; "
                "c = free c; "
                "d = rconst_prescription a b c d 3 4; "
                "m = midpoint a b "
                "? coll m a b"
            )
            .load_defs_from_file("new_defs.txt")
            .build()
        )
        success = solver.run()
        check.is_true(success)

    def test_s_angle_sum_angles_triangle_perp(self):
        """Should work for goal is perp"""
        solver = (
            self.solver_builder.load_problem_from_txt(
                "a b = segment a b; "
                "x = s_angle a b x 63; "
                "y = s_angle b a y 153 "
                "? perp b x a y"
            )
            .load_defs_from_file("new_defs.txt")
            .build()
        )
        success = solver.run()
        check.is_true(success)

    @pytest.mark.xfail
    def test_s_angle_in_aconst_out(self):
        """Same as before, but aconst instead of perp (s_angle in degrees, aconst in radians)"""
        solver = (
            self.solver_builder.load_problem_from_txt(
                "a b = segment a b; "
                "x = s_angle a b x 63; "
                "y = s_angle b a y 153 "
                "? aconst b x a y 1pi/2"
            )
            .load_defs_from_file("new_defs.txt")
            .build()
        )
        success = solver.run()
        check.is_true(success)

    @pytest.mark.xfail
    def test_s_angle_in_s_angle_out(self):
        """Same as both above, but s_angle instead of perp (s_angle in degrees, aconst in radians)"""
        solver = (
            self.solver_builder.load_problem_from_txt(
                "a b = segment a b; "
                "x = s_angle a b x 63; "
                "y = s_angle b a y 153; "
                "o = on_line o b x, on_line o a y "
                "? s_angle a o b 90"
            )
            .load_defs_from_file("new_defs.txt")
            .build()
        )
        success = solver.run()
        check.is_true(success)

    @pytest.mark.xfail
    def test_aconst_in(self):
        """Same as three above, but prescribing aconst (s_angle in degrees, aconst in radians)"""
        solver = (
            self.solver_builder.load_problem_from_txt(
                "a b = segment a b; "
                "x = prescribe_aconst a b x 7 20; "
                "y = prescribe_aconst b a y 17 20; "
                "o = on_line o b x, on_line o a y "
                "? perp b x a y"
            )
            .load_defs_from_file("new_defs.txt")
            .build()
        )
        success = solver.run()
        check.is_true(success)

    @pytest.mark.xfail
    def test_alength(self):
        """Same as three above, but prescribing aconst (s_angle in degrees, aconst in radians)"""
        solver = (
            self.solver_builder.load_problem_from_txt(
                "a = free a; " "b = lconst_prescription b a 3 ? lconst b a 3"
            )
            .load_defs_from_file("new_defs.txt")
            .build()
        )
        success = solver.run()
        check.is_true(success)
