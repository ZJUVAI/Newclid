import pytest

from geosolver.agent.breadth_first_search import BFSDDAR
from geosolver.api import GeometricSolverBuilder


class TestDDAR:
    @pytest.fixture(autouse=True)
    def setUpClass(self):
        self.solver_builder = GeometricSolverBuilder(
            seed=998244353
        ).with_deductive_agent(BFSDDAR)

    def test_translated_obm_phase1_2016_p10(self):
        solver = self.solver_builder.load_problem_from_txt(
            "o = free o; "
            "a = lconst a o 1; "
            "b = s_angle a o b 60o, on_circle b o a; "
            "c = s_angle b o c 60o, on_circle c o a; "
            "d = s_angle c o d 60o, on_circle d o a; "
            "e = s_angle d o e 60o, on_circle e o a; "
            "f = s_angle e o f 60o, on_circle f o a; "
            "x = s_angle a o x 90o, on_circle x o a; "
            "y = s_angle d o y 90o, on_circle y o a; "
            "r = on_line r b f, on_line r a x; "
            "s = on_line s b f, on_line s a y; "
            "t = on_line t b d, on_line t a x; "
            "u = on_line u b d, on_line u a y ? lconst r s 1"
        ).build()
        solver.proof.symbols_graph.display()
