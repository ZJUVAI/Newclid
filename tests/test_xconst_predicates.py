"""Tests for constant predicates (aconst, rconst, lconst, s_angle, compute)."""

import pytest
from newclid.api import GeometricSolverBuilder
from tests.fixtures import build_until_works

# Shared definitions used by multiple tests
ACONST_DEFS = "\n".join(
    [
        "segment a b",
        "",
        " =",
        "a : ; b :",
        "segment",
        "",
        "free a",
        "a : a",
        " =",
        "a :",
        "free",
        "",
        "aconst a b c x r",
        "x : x a b c",
        "a b c = diff a b",
        "x : aconst a b c x r",
        "aconst a b c r",
        "",
    ]
)

S_ANGLE_DEFS = "\n".join(
    [
        "segment a b",
        "",
        " =",
        "a : ; b :",
        "segment",
        "",
        "s_angle a b x y",
        "x : a b x",
        "a b = diff a b",
        "x : aconst a b b x y",
        "s_angle a b y",
        "",
    ]
)

RCONST_DEFS = "\n".join(
    [
        "segment a b",
        "",
        " =",
        "a : ; b :",
        "segment",
        "",
        "free a",
        "a : a",
        " =",
        "a :",
        "free",
        "",
        "rconst a b c x r",
        "x : a b c x",
        "a b c = diff a b",
        "x : rconst a b c x r",
        "rconst a b c r",
        "",
    ]
)

TRIANGLE12_DEFS = "\n".join(
    [
        "triangle12 a b c",
        "c : a b c",
        " =",
        "a : ; b : ; c : rconst a b a c 1/2",
        "triangle12",
        "",
    ]
)


@pytest.fixture
def builder():
    return GeometricSolverBuilder(seed=233)


class TestAngleConstants:
    def test_aconst_deg(self, builder):
        solver = build_until_works(
            builder.load_defs_from_txt(ACONST_DEFS).load_problem_from_txt(
                "a b = segment a b; c = free c; x = aconst a b c x 63o; "
                "y = aconst a b c y 153o ? aconst c x c y 90o"
            )
        )
        assert solver.run()

    def test_aconst_pi_frac(self, builder):
        solver = build_until_works(
            builder.load_defs_from_txt(ACONST_DEFS).load_problem_from_txt(
                "a b = segment a b; c = free c; x = aconst a b c x 7pi/20; "
                "y = aconst a b c y 17pi/20 ? aconst c x c y 1pi/2"
            )
        )
        assert solver.run()

    def test_acompute(self, builder):
        solver = build_until_works(
            builder.load_defs_from_txt(ACONST_DEFS).load_problem_from_txt(
                "a b = segment a b; c = free c; x = aconst a b c x 63o; "
                "y = aconst a b c y 153o ? acompute c x c y"
            )
        )
        assert solver.run()


class TestSAngle:
    def test_s_angle_deg(self, builder):
        solver = build_until_works(
            builder.load_defs_from_txt(S_ANGLE_DEFS).load_problem_from_txt(
                "a b = segment a b; x = s_angle a b x 63o; "
                "y = s_angle a b y 153o ? aconst x b b y 90o"
            )
        )
        assert solver.run()

    def test_s_angle_deg_not_perp(self, builder):
        solver = build_until_works(
            builder.load_defs_from_txt(S_ANGLE_DEFS).load_problem_from_txt(
                "a b = segment a b; x = s_angle a b x 63o; "
                "y = s_angle a b y 143o ? aconst x b b y 80o"
            )
        )
        assert solver.run()

    def test_s_angle_pi_frac(self, builder):
        solver = build_until_works(
            builder.load_defs_from_txt(S_ANGLE_DEFS).load_problem_from_txt(
                "a b = segment a b; x = s_angle a b x 7pi/20; "
                "y = s_angle a b y 17pi/20 ? aconst x b b y 1pi/2"
            )
        )
        assert solver.run()

    def test_s_angle_in_perp_out(self, builder):
        solver = build_until_works(
            builder.load_defs_from_txt(S_ANGLE_DEFS).load_problem_from_txt(
                "a b = segment a b; x = s_angle a b x 63o; "
                "y = s_angle b a y 153o ? perp b x a y"
            )
        )
        assert solver.run()

    def test_s_angle_in_aconst_out(self, builder):
        solver = build_until_works(
            builder.load_defs_from_txt(S_ANGLE_DEFS).load_problem_from_txt(
                "a b = segment a b; x = s_angle a b x 63o; "
                "y = s_angle b a y 153o ? aconst b x a y 1pi/2"
            )
        )
        assert solver.run()


class TestRatioConstants:
    def test_rconst(self, builder):
        solver = build_until_works(
            builder.load_defs_from_txt(RCONST_DEFS).load_problem_from_txt(
                "a b = segment a b; c = free c; d = rconst a b c d 3/4 "
                "? rconst a b c d 3/4"
            )
        )
        assert solver.run()

    def test_rconst_as_theorem_conclusion(self, builder):
        solver = builder.load_problem_from_txt(
            "a b = segment a b; m = midpoint m a b ? rconst m a a b 1/2"
        ).build()
        assert solver.run()

    def test_rcompute(self, builder):
        solver = builder.load_problem_from_txt(
            "a b = segment a b; m = midpoint m a b ? rcompute m a a b"
        ).build()
        assert solver.run()

    def test_triangle12_in_rconst_out(self, builder):
        solver = build_until_works(
            builder.load_problem_from_txt(
                "a b c = triangle12 a b c ? rconst a b a c 1/2"
            ).load_defs_from_txt(TRIANGLE12_DEFS)
        )
        assert solver.run()


class TestLengthConstants:
    def test_lconst(self, builder):
        solver = builder.load_problem_from_txt(
            "a = free a; b = lconst b a 3 ? lconst b a 3"
        ).build()
        assert solver.run()

    def test_lcompute(self, builder):
        solver = builder.load_problem_from_txt(
            "a = free a; b = lconst b a 3 ? lcompute a b"
        ).build()
        assert solver.run()
