from pathlib import Path
import pytest

from geosolver.agent.breadth_first_search import BFSDDAR
from geosolver.api import GeometricSolverBuilder
from geosolver.predicates.equal_angles import EqAngle
from geosolver.statement import Statement


class TestDDAR:
    @pytest.fixture(autouse=True)
    def setUpClass(self):
        self.solver_builder = GeometricSolverBuilder().with_deductive_agent(BFSDDAR)

    @pytest.mark.skip()
    @pytest.mark.slow
    def test_imo_2000_p1_should_succeed(self):
        solver = (
            self.solver_builder.load_problem_from_txt(
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
            )
            .load_rules_from_file(r"rule_sets\imo.txt")
            .build()
        )

        solver.draw_figure(True, None)
        success = solver.run()
        assert success

    def test_incenter_excenter_should_succeed(self):
        solver = (
            self.solver_builder.load_problem_from_txt(
                "a b c = triangle a b c; "
                "d = incenter d a b c; "
                "e = excenter e a b c "
                "? perp d c c e"
            )
            .load_rules_from_txt("")
            .build()
        )
        success = solver.run()
        assert success

    def test_orthocenter_aux_should_succeed(self):
        solver = (
            self.solver_builder.load_rules_from_file(r"rule_sets\orthocenter.txt")
            .load_problem_from_txt(
                "a b c = triangle a b c; "
                "d = on_tline d b a c, on_tline d c a b; "
                "e = on_line e a c, on_line e b d "
                "? perp a d b c"
            )
            .build()
        )
        assert Statement(
            EqAngle, ("e", "a", "a", "b", "e", "b", "d", "c"), solver.proof.dep_graph
        ).check()
        assert Statement(
            EqAngle, ("e", "a", "a", "b", "e", "d", "d", "c"), solver.proof.dep_graph
        ).check()
        assert Statement(
            EqAngle, ("b", "e", "e", "a", "c", "e", "e", "d"), solver.proof.dep_graph
        ).check()
        success = solver.run()
        solver.write_solution(Path("tests_output/orthocenter_proof.txt"))
        assert success
