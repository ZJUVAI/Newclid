"""Unit tests for dd."""
import pytest
import pytest_check as check

from geosolver.deductive.breadth_first_search import BFSDeductor, do_deduction
from geosolver.proof import Proof
from geosolver.problem import Definition, Problem, Theorem


MAX_LEVEL = 10


class TestDD:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.defs = Definition.from_txt_file("defs.txt", to_dict=True)
        self.rules = Theorem.from_txt_file("rules.txt", to_dict=True)

    def test_imo_2022_p4_should_succeed(self):
        problem = Problem.from_txt(
            "a b = segment a b; g1 = on_tline g1 a a b; g2 = on_tline g2 b b a; m ="
            " on_circle m g1 a, on_circle m g2 b; n = on_circle n g1 a, on_circle n"
            " g2 b; c = on_pline c m a b, on_circle c g1 a; d = on_pline d m a b,"
            " on_circle d g2 b; e = on_line e a c, on_line e b d; p = on_line p a"
            " n, on_line p c d; q = on_line q b n, on_line q c d ? cong e p e q"
        )
        proof, _ = Proof.build_problem(problem, self.defs)
        goal_args = proof.symbols_graph.names2nodes(problem.goal.args)

        deductive_agent = BFSDeductor(problem)

        success = False
        while deductive_agent.level < MAX_LEVEL:
            added, _derives, _eq4s, _branching = do_deduction(
                deductive_agent, proof, self.rules
            )
            if proof.check(problem.goal.name, goal_args):
                success = True
                break
            if not added:  # saturated
                break

        check.is_true(success)

    def test_incenter_excenter_should_fail(self):
        problem = Problem.from_txt(
            "a b c = triangle a b c; d = incenter d a b c; e = excenter e a b c ?"
            " perp d c c e"
        )
        proof, _ = Proof.build_problem(problem, self.defs)
        goal_args = proof.symbols_graph.names2nodes(problem.goal.args)

        deductive_agent = BFSDeductor(problem)

        success = False
        while deductive_agent.level < MAX_LEVEL:
            added, _derives, _eq4s, _branching = do_deduction(
                deductive_agent, proof, self.rules
            )
            if proof.check(problem.goal.name, goal_args):
                success = True
                break
            if not added:  # saturated
                break

        check.is_false(success)
