import io
import sys
from geosolver.agent.human_agent import HumanAgent
from geosolver.api import GeometricSolverBuilder
import pytest


class TestHumanAgent:
    @pytest.fixture(autouse=True)
    def setUpClass(self):
        self.solver_builder = GeometricSolverBuilder(
            seed=998244353
        ).with_deductive_agent(HumanAgent)

    @pytest.mark.skip("need a person to close the window that pops up")
    def test_graphics(self):
        sys.stdin = io.StringIO("1\n5\n")
        solver = (
            self.solver_builder.load_problem_from_txt(
                "a b c = triangle;"
                "h = on_tline h b a c, on_tline h c a b ? perp a h b c"
            )
            .load_rules_from_txt("")
            .build()
        )
        solver.run()

    def test_add_construction(self):
        sys.stdin = io.StringIO("2\nd = on_line d a c, on_line d b h\n3\n7\n")
        solver = self.solver_builder.load_problem_from_txt(
            "a b c = triangle;"
            "h = on_tline h b a c, on_tline h c a b ? "
            "perp a h b c"
        ).build()
        assert solver.run()
