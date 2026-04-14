"""Tests for CSolver light mode and GeometricSolverBuilder API."""

from newclid.api import CSolver, GeometricSolverBuilder


class TestCSolverLightMode:
    def test_light_mode_extracts_points(self):
        solver = CSolver(
            problem="a b c = triangle a b c; h = on_tline h b a c, on_tline h c a b ? perp a h b c",
            problem_name="test",
            seed=123,
            light=True,
        )
        assert len(solver.points) > 0

    def test_light_mode_extracts_premises(self):
        solver = CSolver(
            problem="a b c = triangle a b c; h = on_tline h b a c, on_tline h c a b ? perp a h b c",
            problem_name="test",
            seed=123,
            light=True,
        )
        assert len(solver.premises) > 0

    def test_light_mode_extracts_goals(self):
        solver = CSolver(
            problem="a b c = triangle a b c; h = on_tline h b a c, on_tline h c a b ? perp a h b c",
            problem_name="test",
            seed=123,
            light=True,
        )
        assert len(solver.goals) > 0
        assert solver.goals[0][0] == "perp"

    def test_possible_goals(self):
        solver = CSolver(
            problem="a b c = triangle a b c; h = on_tline h b a c, on_tline h c a b ? perp a h b c",
            problem_name="test",
            seed=123,
            light=True,
        )
        goals = solver.possible_goals()
        assert isinstance(goals, list)


class TestGeometricSolverBuilder:
    def test_chained_api(self):
        solver = (
            GeometricSolverBuilder(seed=123)
            .load_problem_from_txt(
                "a b c = triangle a b c; h = on_tline h b a c, on_tline h c a b ? perp a h b c"
            )
            .build()
        )
        assert solver.run()

    def test_builder_returns_self(self):
        builder = GeometricSolverBuilder(seed=123)
        result = builder.load_problem_from_txt("a b c = triangle a b c")
        assert result is builder

    def test_builder_with_rules(self):
        solver = (
            GeometricSolverBuilder(seed=123)
            .load_problem_from_txt(
                "a b c = triangle a b c; h = on_tline h b a c, on_tline h c a b ? perp a h b c"
            )
            .load_rules_from_txt("")
            .build()
        )
        assert solver is not None

    def test_multiple_builds_different_seeds(self):
        for seed in [1, 42, 999]:
            solver = (
                GeometricSolverBuilder(seed=seed)
                .load_problem_from_txt("a b c = triangle a b c")
                .build()
            )
            assert solver is not None
