"""Unit tests for graph.py."""
import pytest
from geosolver.api import GeometricSolverBuilder
import geosolver.predicates as preds
from geosolver.predicates.predicate import Predicate


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
            )
            .build()
        )
        self.proof = solver.proof
        self.symbols_graph = self.proof.symbols_graph

    @pytest.mark.skip
    @pytest.mark.slow
    @pytest.mark.parametrize(
        "predicate",
        (
            preds.Coll,
            preds.Para,
            preds.Perp,
            preds.EqAngle,
            preds.Cong,
            preds.Cyclic,
            preds.MidPoint,
            preds.Circumcenter,
            preds.EqRatio,
        ),
    )
    def test_enumerate(self, predicate: Predicate):
        pass
        # enumerated_points = predicate.enumerate(self.symbols_graph)
        # for points in enumerated_points:
        #     check.is_true(predicate.check(points, self.symbols_graph))
        #     check.is_true(predicate.check_numerical([p.num for p in points]))
