from __future__ import annotations
from typing import Callable, Optional
import pytest

from geosolver.agent.human_agent import HumanAgent
from geosolver.api import GeometricSolverBuilder
from tests.fixtures import build_until_works


class HumanAgentWithPredefinedInput(HumanAgent):
    def __init__(self, inputs_given: Optional[list[str]] = None) -> None:
        super().__init__()
        self.inputs_given = inputs_given if inputs_given is not None else []

    def _ask_input(self, input_txt: str) -> str:
        next_input = self.inputs_given.pop(0)
        if isinstance(next_input, Callable):
            next_input = next_input(self)
        print(input_txt + next_input)
        return next_input


class TestHumanAgent:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.human_agent = HumanAgentWithPredefinedInput()
        self.solver_builder = (
            GeometricSolverBuilder()
            .load_problem_from_txt(
                "a b c = triangle a b c; "
                "d = on_tline d b a c, on_tline d c a b "
                "? perp a d b c",
                translate=False,
            )
            .with_deductive_agent(self.human_agent)
        )

    def test_should_stop(self):
        self.human_agent.inputs_given = ["stop"]
        solver = self.solver_builder.build()
        success = solver.run()
        assert not success
        assert not solver.run_infos["timeout"]
        assert not solver.run_infos["overstep"]
        assert solver.run_infos["step"] == 1

    def test_should_match_and_apply_theorem(self):
        self.human_agent.inputs_given = [
            "match",
            "r21",
            "apply",
            "r21 a d c b",
            "stop",
        ]
        solver = self.solver_builder.load_problem_from_txt(
            "b = free b; "
            "c = free c; "
            "d = free d; "
            "a = on_circum a b c d, on_pline a d b c "
            "? eqangle b a d a d a d c",
            translate=False,
        ).build()
        success = solver.run()
        assert success

    def test_should_resolve_and_apply_derivation(self):
        self.human_agent.inputs_given = [
            "resolve derivations",
            "derive",
            "aconst d(bx) d(ay) 1 2",
            "stop",
        ]

        solver = build_until_works(
            self.solver_builder.load_problem_from_txt(
                "a b = segment a b; "
                "x = s_angle a b x 63o; "
                "y = s_angle b a y 153o "
                "? perp b x a y",
                translate=False,
            )
        )
        success = solver.run()
        assert success

    def test_should_solve_othrocenter_aux(self):
        self.human_agent.inputs_given = [
            "match",
            "r30",
            "apply",
            lambda self: list(self._mappings.keys())[-1],
            "match",
            "r08",
            "apply",
            lambda self: list(self._mappings.keys())[-1],
            "apply",
            lambda self: list(self._mappings.keys())[-1],
            "match",
            "r34",
            "apply",
            lambda self: list(self._mappings.keys())[-1],
            "match",
            "r39",
            "apply",
            lambda self: list(self._mappings.keys())[-1],
            "stop",
        ]

        solver = self.solver_builder.load_problem_from_txt(
            "a b c = triangle a b c; "
            "d = on_tline d b a c, on_tline d c a b; "
            "e = on_line e a c, on_line e b d "
            "? perp a d b c",
            translate=False,
        ).build()
        success = solver.run()
        assert success
