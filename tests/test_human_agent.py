from __future__ import annotations
from typing import Optional
import pytest

from geosolver.agent.human_agent import HumanAgent
from geosolver.api import GeometricSolverBuilder


class HumanAgentWithPredefinedInput(HumanAgent):
    def __init__(self, inputs_given: Optional[list[str]] = None) -> None:
        super().__init__()
        self.inputs_given = inputs_given if inputs_given is not None else []

    def _ask_input(self, input_txt: str) -> str:
        next_input = self.inputs_given.pop(0)
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

    @pytest.mark.xfail
    def test_should_match_and_apply_theorem(self):
        self.human_agent.inputs_given = [
            "match",
            "r06",
            "apply",
            "r06 m a b n c d",
            "stop",
        ]
        solver = self.solver_builder.load_problem_from_txt(
            "a b = segment a b; "
            "e = midpoint e a b; "
            "c d = segment c d; "
            "f = midpoint f a c "
            "? para e f b c",
            translate=False,
        ).build()
        success = solver.run()
        assert success
