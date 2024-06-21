"""Unit testing for the trace_back code."""


import pytest
import pytest_check as check

from geosolver.predicates.coll import Coll
from geosolver.predicates.predicate_name import PredicateName
from geosolver.statements.statement import Statement
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

        goal_args = solver.proof_state.symbols_graph.names2nodes(
            solver.problem.goal.args
        )
        goal = Statement(solver.problem.goal.name, goal_args)
        setup, aux, _, _ = get_logs(goal, solver.proof_state, merge_trivials=False)

        setup = [p.statement.hash_tuple for p in setup]
        check.equal(
            set(setup),
            {
                (PredicateName.PERPENDICULAR.value, "a", "c", "b", "d"),
                (PredicateName.PERPENDICULAR.value, "a", "b", "c", "d"),
            },
        )

        aux = [p.statement.hash_tuple for p in aux]
        check.equal(
            set(aux),
            {(Coll.NAME, "a", "c", "e"), (Coll.NAME, "b", "d", "e")},
        )
