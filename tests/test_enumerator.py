"""Unit tests for graph.py."""
import pytest
import pytest_check as check
from geosolver.api import GeometricSolverBuilder
from geosolver.numerical.check import (
    check_circle_numerical,
    check_cong_numerical,
    check_cyclic_numerical,
    check_eqratio_numerical,
    check_midp_numerical,
)
from geosolver.predicates import Coll, Para, Perp
from geosolver.predicates.eqangle import EqAngle
from geosolver.predicates.predicate import Predicate
from geosolver.predicates.predicate_name import PredicateName


class TestProof:
    @pytest.fixture(autouse=True)
    def setup(self):
        solver = (
            GeometricSolverBuilder()
            .load_problem_from_txt(
                "a b c = triangle a b c; "
                "h = orthocenter a b c; "
                "h1 = foot a b c; "
                "h2 = foot b c a; "
                "h3 = foot c a b; "
                "g1 g2 g3 g = centroid g1 g2 g3 g a b c; "
                "o = circle a b c "
                "? coll h g o",
                translate=False,
            )
            .build()
        )
        self.proof = solver.proof_state
        self.symbols_graph = self.proof.symbols_graph
        self.checker = self.proof.statements.checker
        self.enumerator = self.proof.statements.enumerator

    @pytest.mark.slow
    @pytest.mark.parametrize("predicate", (Coll, Para, Perp, EqAngle))
    def test_enumerate(self, predicate: Predicate):
        for points in predicate.enumerate(self.symbols_graph):
            check.is_true(predicate.check(points))
            check.is_true(predicate.check_numerical([p.num for p in points]))

    def test_enumerate_congs(self):
        for a, b, c, d in self.enumerator.all(PredicateName.CONGRUENT):
            check.is_true(self.checker.check_cong([a, b, c, d]))
            check.is_true(check_cong_numerical([a.num, b.num, c.num, d.num]))

    def test_enumerate_cyclics(self):
        for a, b, c, d, x, y, z, t in self.enumerator.all(PredicateName.CYCLIC):
            check.is_true(self.checker.check_cyclic([a, b, c, d, x, y, z, t]))
            check.is_true(check_cyclic_numerical([a.num, b.num, c.num, d.num]))

    def test_enumerate_midps(self):
        for a, b, c in self.enumerator.all(PredicateName.MIDPOINT):
            check.is_true(self.checker.check_midp([a, b, c]))
            check.is_true(check_midp_numerical([a.num, b.num, c.num]))

    def test_enumerate_circles(self):
        for a, b, c, d in self.enumerator.all(PredicateName.CIRCLE):
            check.is_true(self.checker.check_circle([a, b, c, d]))
            check.is_true(check_circle_numerical([a.num, b.num, c.num, d.num]))

    @pytest.mark.slow
    def test_enumerate_eqratios(self):
        for a, b, c, d, x, y, z, t in self.enumerator.all(PredicateName.EQRATIO):
            check.is_true(self.checker.check_eqratio([a, b, c, d, x, y, z, t]))
            check.is_true(
                check_eqratio_numerical(
                    [a.num, b.num, c.num, d.num, x.num, y.num, z.num, t.num]
                )
            )
