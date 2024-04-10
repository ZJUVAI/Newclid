"""Unit tests for dd."""
import pytest
import pytest_check as check

from geosolver.deductive.breadth_first_search import BFSDeductor
from geosolver.deductive.deduction_step import deduce_to_saturation_or_goal
from geosolver.proof import Proof
from geosolver.problem import Definition, Problem, Theorem


MAX_STEPS = 10000


class TestDD:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.defs = Definition.to_dict(Definition.from_txt_file("defs.txt"))
        self.rules = Theorem.from_txt_file("rules.txt")

    @pytest.mark.slow
    def test_imo_2022_p4_should_succeed(self):
        problem = Problem.from_txt(
            "a b = segment a b; g1 = on_tline g1 a a b; g2 = on_tline g2 b b a; m ="
            " on_circle m g1 a, on_circle m g2 b; n = on_circle n g1 a, on_circle n"
            " g2 b; c = on_pline c m a b, on_circle c g1 a; d = on_pline d m a b,"
            " on_circle d g2 b; e = on_line e a c, on_line e b d; p = on_line p a"
            " n, on_line p c d; q = on_line q b n, on_line q c d ? cong e p e q"
        )
        proof, _ = Proof.build_problem(problem, self.defs)
        deductive_agent = BFSDeductor(problem)

        _derives, _eq4s, _branching, _all_added, success = deduce_to_saturation_or_goal(
            deductive_agent, proof, self.rules, problem, timeout=60
        )
        check.is_true(success)

    def test_incenter_excenter_should_fail(self):
        problem = Problem.from_txt(
            "a b c = triangle a b c; d = incenter d a b c; e = excenter e a b c ?"
            " perp d c c e"
        )
        proof, _ = Proof.build_problem(problem, self.defs)
        deductive_agent = BFSDeductor(problem)

        step_times = []
        timeout = 1
        _derives, _eq4s, _branching, _all_added, success = deduce_to_saturation_or_goal(
            deductive_agent,
            proof,
            self.rules,
            problem,
            step_times=step_times,
            timeout=timeout,
        )

        check.is_false(success)
        check.less(sum(step_times), timeout)
