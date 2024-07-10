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

    def test_translated_imo_2009_p2_extra_points(self):
        solver = (
            self.solver_builder.load_problem_from_txt(
                "m l k = triangle m l k; "
                "w = circle w m l k; "
                "q = on_tline q m w m; "
                "p = mirror p q m; "
                "b = mirror b p k; "
                "c = mirror c q l; "
                "a = on_line a b q, on_line a c p; "
                "o = circle o a b c; "
                "d = eqdistance d l m k, eqdistance d m l k; "
                "e = mirror e k w; "
                "f = mirror f q d ? "
                "cong q o p o"
            )
            .load_rules_from_file(r"rule_sets\imo.txt")
            .with_runtime_cache(Path("tests_output/imo2009p2cache.json"))
            .build()
        )

        success = solver.run()
        assert success
        solver.write_solution(Path("tests_output/imo2009p2_proof.txt"))

    @pytest.mark.skip("not solved by ag either")
    def test_translated_imo_2011_p6_with_orthocenter(self):
        solver = (
            self.solver_builder.load_problem_from_txt(
                "a b c = triangle a b c; "
                "o = circle o a b c; "
                "p = on_circle p o a; "
                "q = on_tline q p o p; "
                "pa = reflect pa p b c; "
                "pb = reflect pb p c a; "
                "pc = reflect pc p a b; "
                "qa = reflect qa q b c; "
                "qb = reflect qb q c a; "
                "qc = reflect qc q a b; "
                "a1 = on_line a1 pb qb, on_line a1 pc qc; "
                "b1 = on_line b1 pa qa, on_line b1 pc qc; "
                "c1 = on_line c1 pa qa, on_line c1 pb qb; "
                "o1 = circle o1 a1 b1 c1; "
                "x = on_circle x o a, on_circle x o1 a1; "
                "h = orthocenter h a b c ? cyclic pa pb c x"
            )
            .load_rules_from_file(r"rule_sets\imo.txt")
            .with_runtime_cache(Path("tests_output/imo2011p6cache.json"))
            .build()
        )

        success = solver.run()
        assert success
        solver.write_solution(Path("tests_output/imo2011p6_proof.txt"))

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
            .with_runtime_cache(Path("tests_output/imo2000p1cache.json"))
            .build()
        )

        solver.draw_figure(False, Path("tests_output/imo2000p1_setup.png"))
        success = solver.run()
        assert success
        solver.write_solution(Path("tests_output/imo2000p1_proof.txt"))

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

    def test_orthocenter_should_exhaust(self):
        solver = (
            self.solver_builder.load_rules_from_file(r"rule_sets\triangles.txt")
            .load_problem_from_txt(
                "a b c = triangle a b c; "
                "d = on_tline d b a c, on_tline d c a b "
                "? perp a d b c"
            )
            .build()
        )
        success = solver.run()
        assert not success

    def test_orthocenter_aux_should_succeed(self):
        solver = (
            self.solver_builder.load_rules_from_file(r"rule_sets\triangles.txt")
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
