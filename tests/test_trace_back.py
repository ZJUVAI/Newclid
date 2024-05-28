"""Unit testing for the trace_back code."""


import pytest
import pytest_check as check

from geosolver.predicates import Predicate
from geosolver.dependencies.dependency import Dependency
from geosolver.trace_back import get_logs
from geosolver.api import GeometricSolverBuilder


class TestTraceback:
    @pytest.fixture(autouse=True)
    def setUpClass(self):
        self.solver_builder = GeometricSolverBuilder()

    def test_orthocenter_dependency_difference(self):
        solver = self.solver_builder.load_problem_from_txt(
            "a b c = triangle a b c; "
            "d = on_tline d b a c, on_tline d c a b; "
            "e = on_line e a c, on_line e b d "
            "? perp a d b c"
        ).build()

        solver.run()

        goal_args = solver.proof_state.symbols_graph.names2nodes(solver.goal.args)
        query = Dependency(solver.goal.name, goal_args, None, None)
        setup, aux, _, _ = get_logs(query, solver.proof_state, merge_trivials=False)

        # Convert each predicates to its hash string:
        setup = [p.hashed() for p in setup]
        aux = [p.hashed() for p in aux]

        check.equal(
            set(setup),
            {
                (Predicate.PERPENDICULAR.value, "a", "c", "b", "d"),
                ("perp", "a", "b", "c", "d"),
            },
        )

        check.equal(
            set(aux),
            {
                (Predicate.COLLINEAR.value, "a", "c", "e"),
                (Predicate.COLLINEAR.value, "b", "d", "e"),
            },
        )
