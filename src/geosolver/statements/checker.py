from typing import TYPE_CHECKING

import geosolver.predicates as preds
from geosolver.predicates.eqangle import all_angles
from geosolver.predicates.eqratio import all_ratios
from geosolver.statements.statement import Statement, angle_to_num_den, ratio_to_num_den
from geosolver.predicate_name import PredicateName
from geosolver.geometry import (
    Angle,
    Length,
    Point,
    Ratio,
    all_lengths,
)
from geosolver.numerical.check import check_sameside_numerical

from geosolver.symbols_graph import is_equal


if TYPE_CHECKING:
    from geosolver.symbols_graph import SymbolsGraph


class StatementChecker:
    def __init__(
        self,
        symbols_graph: "SymbolsGraph",
    ) -> None:
        self.symbols_graph = symbols_graph
        self.PREDICATE_TO_CHECK = {
            PredicateName.SIMILAR_TRIANGLE: self.check_simtri,
            PredicateName.SIMILAR_TRIANGLE_REFLECTED: self.check_simtri_reflected,
            PredicateName.SIMILAR_TRIANGLE_BOTH: self.check_simtri_both,
            PredicateName.CONTRI_TRIANGLE: self.check_contri,
            PredicateName.CONTRI_TRIANGLE_REFLECTED: self.check_contri_reflected,
            PredicateName.CONTRI_TRIANGLE_BOTH: self.check_contri_both,
            PredicateName.CONSTANT_ANGLE: self.check_aconst,
            PredicateName.S_ANGLE: self.check_sangle,
            PredicateName.CONSTANT_RATIO: self.check_rconst,
            PredicateName.CONSTANT_LENGTH: self.check_lconst,
            PredicateName.COMPUTE_ANGLE: self.check_acompute,
            PredicateName.COMPUTE_RATIO: self.check_rcompute,
            PredicateName.SAMESIDE: self.check_sameside,
            PredicateName.DIFFERENT: self.check_diff,
            PredicateName.NON_COLLINEAR: self.check_ncoll,
            PredicateName.NON_PARALLEL: self.check_npara,
            PredicateName.NON_PERPENDICULAR: self.check_nperp,
        }

    def check(self, statement: Statement) -> bool:
        """Symbolically check if a predicate is True."""
        return self.PREDICATE_TO_CHECK[statement.predicate](statement.args)

    def check_aconst(self, points: tuple[Point, Point, Point, Point, Angle]) -> bool:
        """Check if the angle is equal to a certain constant."""
        a, b, c, d, angle = points
        num, den = angle_to_num_den(angle)
        ang, _ = self.symbols_graph.get_or_create_const_ang(int(num), int(den))

        ab = self.symbols_graph.get_line(a, b)
        cd = self.symbols_graph.get_line(c, d)
        if not ab or not cd:
            return False

        if not (ab.val and cd.val):
            return False

        for ang1, _, _ in all_angles(ab._val, cd._val):
            if is_equal(ang1, ang):
                return True
        return False

    def check_sangle(self, points: tuple[Point, Point, Point, Angle]) -> bool:
        a, b, c, angle = points
        num, den = angle_to_num_den(angle)
        ang, _ = self.symbols_graph.get_or_create_const_ang(num, den)

        ab = self.symbols_graph.get_line(a, b)
        cb = self.symbols_graph.get_line(c, b)
        if not ab or not cb:
            return False

        if not (ab.val and cb.val):
            return False

        for ang1, _, _ in all_angles(ab._val, cb._val):
            if is_equal(ang1, ang):
                return True
        return False

    def check_rconst(self, points: tuple[Point, Point, Point, Point, Ratio]) -> bool:
        """Check whether a ratio is equal to some given constant."""
        a, b, c, d, ratio = points
        num, den = ratio_to_num_den(ratio)
        rat, _ = self.symbols_graph.get_or_create_const_rat(int(num), int(den))

        ab = self.symbols_graph.get_segment(a, b)
        cd = self.symbols_graph.get_segment(c, d)

        if not ab or not cd:
            return False

        if not (ab.val and cd.val):
            return False

        for rat1, _, _ in all_ratios(ab._val, cd._val):
            if is_equal(rat1, rat):
                return True
        return False

    def check_lconst(self, points: tuple[Point, Point, Length]) -> bool:
        """Check whether a length is equal to some given constant."""
        a, b, length = points
        ab = self.symbols_graph.get_segment(a, b)

        if not ab or not ab.val:
            return False

        for len1, _ in all_lengths(ab):
            if is_equal(len1, length):
                return True
        return False

    def check_acompute(self, points: list[Point]) -> bool:
        """Check if an angle has a constant value."""
        a, b, c, d = points
        ab = self.symbols_graph.get_line(a, b)
        cd = self.symbols_graph.get_line(c, d)
        if not ab or not cd:
            return False

        if not (ab.val and cd.val):
            return False

        for ang0 in self.symbols_graph.aconst.values():
            for ang in ang0.val.neighbors(Angle):
                d1, d2 = ang.directions
                if ab.val == d1 and cd.val == d2:
                    return True
        return False

    def check_rcompute(self, points: list[Point]) -> bool:
        """Check whether a ratio is equal to some constant."""
        a, b, c, d = points
        ab = self.symbols_graph.get_segment(a, b)
        cd = self.symbols_graph.get_segment(c, d)

        if not ab or not cd:
            return False

        if not (ab.val and cd.val):
            return False

        for rat0 in self.symbols_graph.rconst.values():
            for rat in rat0.val.neighbors(Ratio):
                l1, l2 = rat.lengths
                if ab.val == l1 and cd.val == l2:
                    return True
        return False

    def check_simtri(self, points: list[Point]) -> bool:
        a, b, c, x, y, z = points
        return self.check_eqangle([a, b, a, c, x, y, x, z]) and self.check_eqangle(
            [b, a, b, c, y, x, y, z]
        )

    def check_simtri_reflected(self, points: list[Point]) -> bool:
        a, b, c, x, y, z = points
        return self.check_eqangle([a, b, a, c, x, z, x, y]) and self.check_eqangle(
            [b, a, b, c, y, z, y, x]
        )

    def check_simtri_both(self, points: list[Point]) -> bool:
        return self.check_simtri(points) or self.check_simtri_reflected(points)

    def check_contri(self, points: list[Point]) -> bool:
        return self.check_contri_both(points) and self.check_simtri(points)

    def check_contri_reflected(self, points: list[Point]) -> bool:
        return self.check_contri_both(points) and self.check_simtri_reflected(points)

    def check_contri_both(self, points: list[Point]) -> bool:
        a, b, c, x, y, z = points
        return (
            self.check_cong([a, b, x, y])
            and self.check_cong([b, c, y, z])
            and self.check_cong([c, a, z, x])
        )

    # Negative checks (with numerical double check)

    def check_ncoll(self, points: list[Point]) -> bool:
        if preds.Coll.check(points):
            return False
        return not preds.Coll.check_numerical([p.num for p in points])

    def check_npara(self, points: list[Point]) -> bool:
        if preds.Para.check(points):
            return False
        return not preds.Para.check_numerical([p.num for p in points])

    def check_nperp(self, points: list[Point]) -> bool:
        if preds.Perp.check(points):
            return False
        return not preds.Perp.check_numerical([p.num for p in points])

    # Numerical only checks

    def check_sameside(self, points: list[Point]) -> bool:
        return check_sameside_numerical([p.num for p in points])

    def check_diff(self, points: list[Point]) -> bool:
        a, b = points
        return not a.num.close(b.num)
