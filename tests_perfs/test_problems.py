from pathlib import Path
import sys
import pytest

from newclid.__main__ import main
from newclid.agent.ddarn import DDARN
from newclid.api import GeometricSolverBuilder


class TestDDAR:
    @pytest.fixture(autouse=True)
    def setUpClass(self):
        self.solver_builder = GeometricSolverBuilder(
            seed=998244353
        ).with_deductive_agent(DDARN())

    def test_translated_obm_phase1_2016_p10(self):
        solver = (
            self.solver_builder.load_problem_from_txt(
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
            )
            .with_problem_path(Path(r"./tests_output/imo2016p10"))
            .build()
        )

        success = solver.run()
        assert success
        solver.write_all_outputs()

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
                "sameclock d l m k l m; cong q o p o"
                # "sameclock d l m k l m; acompute l d c o; acompute q b b o"
                # "sameclock d l m k l m; eqangle l d c o q b b o"
                # "sameclock d l m k m l; eqangle l d c o q b b o"
                # "sameclock d l m k m l; para b q k m; eqangle l m d l l m k m; eqangle a b a o b o a b; para c f d l; para c p l m; eqangle a c a o c o a c; eqangle b q b o c o c f"
            )
            .with_problem_path(Path(r"./tests_output/imo2009p2"))
            .build()
        )
        solver.draw_figure(out_file=Path(r"./tests_output/imo2009p2beforesolver.svg"))

        success = solver.run()
        assert success, str(solver.run_infos)
        solver.write_proof_steps(Path(r"./tests_output/imo2009p2_proof.txt"))
        solver.draw_figure(out_file=Path(r"./tests_output/imo2009p2.svg"))

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
            .with_problem_path(Path(r"./tests_output/imo2011p6"))
            .build()
        )

        success = solver.run()
        assert success
        solver.write_proof_steps(Path(r"./tests_output/imo2011p6_proof.txt"))

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
            .with_problem_path(Path(r"./tests_output/imo2000p1"))
            .build()
        )

        success = solver.run()
        assert success
        solver.write_all_outputs()


def test_imo2009p2():
    sys.argv = [
        "newclid",
        "--problem-name",
        "imo2009p2",
        "--env",
        "tests-exp",
        "--seed",
        "123",
        "--quiet",
    ]
    main()
