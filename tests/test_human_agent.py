"""Tests for the HumanAgent deductive agent."""

from newclid.agent.human_agent import HumanAgent
from newclid.api import GeometricSolverBuilder


def test_human_agent_builds():
    """HumanAgent should be usable as a deductive agent in solver building."""
    builder = GeometricSolverBuilder(seed=998244353).with_deductive_agent(HumanAgent())
    solver = builder.load_problem_from_txt(
        "a b c = triangle a b c; h = on_tline h b a c, on_tline h c a b ? perp a h b c"
    ).build()
    assert solver is not None
