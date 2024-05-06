from geosolver.agent.breadth_first_search import BFSDDAR

import pytest_check as check

from geosolver.api import GeometricSolverBuilder
from tests.fixtures import build_until_works


def test_ar_whatever():
    solver = build_until_works(
        GeometricSolverBuilder()
        .load_problem_from_txt(
            "a b = segment a b; "
            "o = s_angle b a o 70o, s_angle a b o 120o; "
            "c = s_angle o a c 10o, s_angle o b c 160o; "
            "d = on_line d o b, on_line d c a; "
            "e = on_line e o a, on_line e c b; "
            "f = on_pline f d a b, on_line f b c; "
            "g = on_line g f a, on_line g d b "
            "? aconst c b c a 1pi/9"
        )
        .with_deductive_agent(BFSDDAR())
    )

    success = solver.run()
    check.is_true(success)


def test_ar_whatever2():
    solver = build_until_works(
        GeometricSolverBuilder()
        .load_problem_from_txt(
            "a b = segment a b; "
            "c = s_angle b a c 140o, s_angle a b c 60o; "
            "e = on_tline e c a c, eqdistance e c a c; "
            "d = s_angle c e d 40o, on_tline d c c b "
            "? aconst d b a c 11pi/36"
        )
        .with_deductive_agent(BFSDDAR())
    )

    success = solver.run()
    check.is_true(success)
