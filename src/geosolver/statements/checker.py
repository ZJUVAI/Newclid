from typing import TYPE_CHECKING

from geosolver.predicates.coll import Coll
from geosolver.predicates.para import Para
from geosolver.predicates.perp import Perp
from geosolver.statements.statement import Statement, angle_to_num_den, ratio_to_num_den
from geosolver.predicates.predicate_name import PredicateName
from geosolver.geometry import (
    Angle,
    Circle,
    Length,
    Point,
    Ratio,
    all_angles,
    all_lengths,
    all_ratios,
)
from geosolver.numerical.check import check_sameside_numerical

from geosolver.listing import list_eqratio3
from geosolver.symbols_graph import is_equal


if TYPE_CHECKING:
    from geosolver.symbols_graph import SymbolsGraph

from collections import defaultdict


class StatementChecker:
    def __init__(
        self,
        symbols_graph: "SymbolsGraph",
    ) -> None:
        self.symbols_graph = symbols_graph
        self.PREDICATE_TO_CHECK = {
            PredicateName.MIDPOINT: self.check_midp,
            PredicateName.CONGRUENT: self.check_cong,
            PredicateName.CIRCLE: self.check_circle,
            PredicateName.CYCLIC: self.check_cyclic,
            PredicateName.EQANGLE6: self.check_const_or_eqangle,
            PredicateName.EQRATIO: self.check_const_or_eqratio,
            PredicateName.EQRATIO3: self.check_eqratio3,
            PredicateName.EQRATIO6: self.check_const_or_eqratio,
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

    def check_const_or_eqratio(self, args: list[Point]) -> bool:
        if len(args) == 5:
            return self.check_rconst(args)
        return self.check_eqratio(args)

    # Basic checks

    def check_cong(self, points: list[Point]) -> bool:
        a, b, c, d = points
        if {a, b} == {c, d}:
            return True

        ab = self.symbols_graph.get_segment(a, b)
        cd = self.symbols_graph.get_segment(c, d)
        if ab is None or cd is None:
            return False
        return is_equal(ab, cd)

    # Angles and ratios checks

    def check_eqratio(self, points: list[Point]) -> bool:
        """Check if 8 points make an eqratio predicate."""
        a, b, c, d, m, n, p, q = points

        if {a, b} == {c, d} and {m, n} == {p, q}:
            return True
        if {a, b} == {m, n} and {c, d} == {p, q}:
            return True

        ab = self.symbols_graph.get_segment(a, b)
        cd = self.symbols_graph.get_segment(c, d)
        mn = self.symbols_graph.get_segment(m, n)
        pq = self.symbols_graph.get_segment(p, q)

        if {a, b} == {c, d} and mn and pq and is_equal(mn, pq):
            return True
        if {a, b} == {m, n} and cd and pq and is_equal(cd, pq):
            return True
        if {p, q} == {m, n} and ab and cd and is_equal(ab, cd):
            return True
        if {p, q} == {c, d} and ab and mn and is_equal(ab, mn):
            return True

        if not ab or not cd or not mn or not pq:
            return False

        if is_equal(ab, cd) and is_equal(mn, pq):
            return True
        if is_equal(ab, mn) and is_equal(cd, pq):
            return True

        if not (ab.val and cd.val and mn.val and pq.val):
            return False

        if (ab.val, cd.val) == (mn.val, pq.val) or (ab.val, mn.val) == (
            cd.val,
            pq.val,
        ):
            return True

        for rat1, _, _ in all_ratios(ab._val, cd._val):
            for rat2, _, _ in all_ratios(mn._val, pq._val):
                if is_equal(rat1, rat2):
                    return True
        return False

    def check_eqratio3(self, points: list[Point]) -> bool:
        for ratio in list_eqratio3(points):
            if not self.check_eqratio(ratio):
                return False
        return True

    # Algebraic checks

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

    # High order checks

    def check_midp(self, points: list[Point]) -> bool:
        if not self.check_coll(points):
            return False
        m, a, b = points
        return self.check_cong([m, a, m, b])

    def check_circle(self, points: list[Point]) -> bool:
        o, a, b, c = points
        return self.check_cong([o, a, o, b]) and self.check_cong([o, a, o, c])

    def check_cyclic(self, points: list[Point]) -> bool:
        points = list(set(points))
        if len(points) < 4:
            return True
        circle2count = defaultdict(lambda: 0)
        for p in points:
            for c in p.neighbors(Circle):
                circle2count[c] += 1
        return any([count == len(points) for _, count in circle2count.items()])

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
        if Coll.check(points):
            return False
        return not Coll.check_numerical([p.num for p in points])

    def check_npara(self, points: list[Point]) -> bool:
        if Para.check(points):
            return False
        return not Para.check_numerical([p.num for p in points])

    def check_nperp(self, points: list[Point]) -> bool:
        if Perp.check(points):
            return False
        return not Perp.check_numerical([p.num for p in points])

    # Numerical only checks

    def check_sameside(self, points: list[Point]) -> bool:
        return check_sameside_numerical([p.num for p in points])

    def check_diff(self, points: list[Point]) -> bool:
        a, b = points
        return not a.num.close(b.num)
