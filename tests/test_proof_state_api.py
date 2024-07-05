from pathlib import Path

import pytest
from geosolver.api import GeometricSolverBuilder
from geosolver.dependency.symbols import Point
import geosolver.predicates as preds
from geosolver.statement import Statement


MAX_LEVEL = 10


def test_false_problem_draw(tmp_path: Path):
    false_problem_str = (
        "a b = segment a b; "
        "c = on_tline c a a b, on_circle c a b; "
        "e = s_angle b a e 55o, on_circle e a b; "
        "d = s_angle b a d 30o, on_circle d a b; "
        "f = on_line f a e, on_line f b c; "
        "g = on_line g a d, on_line g b c "
        "? cong c f g b"
    )

    solver = (
        GeometricSolverBuilder()
        .load_problem_from_txt(false_problem_str)
        .del_goal()
        .build()
    )
    solver.draw_figure(False, tmp_path / "figure.png")


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
        self.dep_graph = self.proof.dep_graph

    @pytest.skip()
    def test_add_auxiliary_construction(self):
        solver = (
            GeometricSolverBuilder()
            .load_problem_from_txt(
                "a b c = triangle a b c; "
                "d = on_tline d b a c, on_tline d c a b "
                "? perp a d b c",
            )
            .build()
        )
        # solver.proof.add_construction("e = on_line e a c, on_line e b d")
        success = solver.run()
        assert success

    @pytest.skip()
    def test_auxiliary_construction_build_error(self):
        """Should raise an error when trying an impossible construction though the api."""
        with pytest.raises(ValueError, match="Auxiliary construction failed"):
            pass
            # solver = (
            #     GeometricSolverBuilder()
            #     .load_problem_from_txt(
            #         "a b c = ieq_triangle a b c; m = midpoint m a b; n = midpoint n m a",
            #     )
            #     .build()
            # )
            # solver.add_auxiliary_construction("e = on_circle e n a, on_line e b c")

    def test_build_points(self):
        all_points = self.symbols_graph.nodes_of_type(Point)
        assert {p.name for p in all_points} == {
            "a",
            "b",
            "c",
            "g",
            "h",
            "o",
            "g1",
            "g2",
            "g3",
            "h1",
            "h2",
            "h3",
        }

    def test_build_predicates(self):
        (a, b, c, g, h, o, g1, g2, g3, h1, h2, h3) = [
            "a",
            "b",
            "c",
            "g",
            "h",
            "o",
            "g1",
            "g2",
            "g3",
            "h1",
            "h2",
            "h3",
        ]

        # Explicit statements:
        assert Statement(preds.Cong, (b, g1, g1, c), self.dep_graph).check()
        assert Statement(preds.Cong, (c, g2, g2, a), self.dep_graph).check()
        assert Statement(preds.Cong, (a, g3, g3, b), self.dep_graph).check()
        assert Statement(preds.Perp, (a, h1, b, c), self.dep_graph).check()
        assert Statement(preds.Perp, (b, h2, c, a), self.dep_graph).check()
        assert Statement(preds.Perp, (c, h3, a, b), self.dep_graph).check()
        assert Statement(preds.Cong, (o, a, o, b), self.dep_graph).check()
        assert Statement(preds.Cong, (o, b, o, c), self.dep_graph).check()
        assert Statement(preds.Cong, (o, a, o, c), self.dep_graph).check()
        assert Statement(preds.Coll, (a, g, g1), self.dep_graph).check()
        assert Statement(preds.Coll, (b, g, g2), self.dep_graph).check()
        assert Statement(preds.Coll, (g1, b, c), self.dep_graph).check()
        assert Statement(preds.Coll, (g2, c, a), self.dep_graph).check()
        assert Statement(preds.Coll, (g3, a, b), self.dep_graph).check()
        assert Statement(preds.Perp, (a, h, b, c), self.dep_graph).check()
        assert Statement(preds.Perp, (b, h, c, a), self.dep_graph).check()

        # These are NOT part of the premises:
        assert not Statement(preds.Perp, (c, h, a, b), self.dep_graph).check()
        assert not Statement(preds.Coll, (c, g, g3), self.dep_graph).check()

        # These are automatically inferred by the graph datastructure:
        assert Statement(
            preds.EqAngle, (a, h1, b, c, b, h2, c, a), self.dep_graph
        ).check()
        assert Statement(
            preds.EqAngle, (a, h1, b, h2, b, c, c, a), self.dep_graph
        ).check()
        assert Statement(
            preds.EqRatio, (b, g1, g1, c, c, g2, g2, a), self.dep_graph
        ).check()
        assert Statement(
            preds.EqRatio, (b, g1, g1, c, o, a, o, b), self.dep_graph
        ).check()
        assert Statement(preds.Para, (a, h, a, h1), self.dep_graph).check()
        assert Statement(preds.Para, (b, h, b, h2), self.dep_graph).check()
        assert Statement(preds.Coll, (a, h, h1), self.dep_graph).check()
        assert Statement(preds.Coll, (b, h, h2), self.dep_graph).check()
