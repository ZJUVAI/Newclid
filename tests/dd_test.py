"""Unit tests for dd."""
import pytest
import pytest_check as check

from geosolver.deductive import dd_bfs_one_level
from geosolver.api import GeometricSolverBuilder


MAX_LEVEL = 10


class TestDD:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.solver_builder = GeometricSolverBuilder()

    @pytest.mark.slow
    def test_imo_2022_p4_should_succeed(self):
        solver = self.solver_builder.load_problem_from_txt(
            "a b = segment a b; "
            "g1 = on_tline g1 a a b; "
            "g2 = on_tline g2 b b a; "
            "m = on_circle m g1 a, on_circle m g2 b; "
            "n = on_circle n g1 a, on_circle n g2 b; "
            "c = on_pline c m a b, on_circle c g1 a; "
            "d = on_pline d m a b, on_circle d g2 b; "
            "e = on_line e a c, on_line e b d; "
            "p = on_line p a n, on_line p c d; "
            "q = on_line q b n, on_line q c d "
            "? cong e p e q"
        ).build()
        proof = solver.proof_state
        goal_args = proof.symbols_graph.names2nodes(solver.goal.args)

        success = False
        for level in range(MAX_LEVEL):
            added, _, _, _ = dd_bfs_one_level(
                proof, solver.rules, level, solver.problem
            )
            if proof.check(solver.goal.name, goal_args):
                success = True
                break
            if not added:  # saturated
                break

        check.is_true(success)

    def test_incenter_excenter_should_fail(self):
        solver = self.solver_builder.load_problem_from_txt(
            "a b c = triangle a b c; "
            "d = incenter d a b c; "
            "e = excenter e a b c "
            "? perp d c c e"
        ).build()
        proof = solver.proof_state
        goal_args = proof.symbols_graph.names2nodes(solver.goal.args)

        success = False
        for level in range(MAX_LEVEL):
            added, _, _, _ = dd_bfs_one_level(
                proof, solver.rules, level, solver.problem
            )
            if proof.check(solver.goal.name, goal_args):
                success = True
                break
            if not added:  # saturated
                break

        check.is_false(success)
