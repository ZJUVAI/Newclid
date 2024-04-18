from typing import TYPE_CHECKING, Optional
from geosolver.algebraic.algebraic_manipulator import AlgebraicManipulator
from geosolver.concepts import ConceptName
from geosolver.geometry import (
    Angle,
    Circle,
    Line,
    Point,
    Ratio,
    all_angles,
    all_ratios,
    is_equal,
)
from geosolver.numerical.check import (
    check_coll_numerical,
    check_para_numerical,
    check_perp_numerical,
    check_sameside_numerical,
)

from geosolver.symbols_graph import SymbolsGraph

if TYPE_CHECKING:
    from geosolver.problem import Construction


from collections import defaultdict


class StatementChecker:
    def __init__(
        self,
        symbols_graph: SymbolsGraph,
        alegbraic_manipulator: AlgebraicManipulator,
    ) -> None:
        self.symbols_graph = symbols_graph
        self.alegbraic_manipulator = alegbraic_manipulator
        self.NAME_TO_CHECK = {
            ConceptName.COLLINEAR.value: self.check_coll,
            ConceptName.PARALLEL.value: self.check_para,
            ConceptName.PERPENDICULAR.value: self.check_perp,
            ConceptName.MIDPOINT.value: self.check_midp,
            ConceptName.CONGRUENT.value: self.check_cong,
            ConceptName.CIRCLE.value: self.check_circle,
            ConceptName.CYCLIC.value: self.check_cyclic,
            ConceptName.EQANGLE.value: self.check_const_or_eqangle,
            ConceptName.EQANGLE6.value: self.check_const_or_eqangle,
            ConceptName.EQRATIO.value: self.check_const_or_eqratio,
            ConceptName.EQRATIO6.value: self.check_const_or_eqratio,
            ConceptName.SIMILAR_TRIANGLE.value: self.check_simtri,
            ConceptName.SIMILAR_TRIANGLE_REFLECTED.value: self.check_simtri,
            ConceptName.SIMILAR_TRIANGLE_BOTH.value: self.check_simtri,
            ConceptName.CONTRI_TRIANGLE.value: self.check_contri,
            ConceptName.CONTRI_TRIANGLE_REFLECTED.value: self.check_contri,
            ConceptName.CONTRI_TRIANGLE_BOTH.value: self.check_contri,
            ConceptName.CONSTANT_ANGLE.value: self.check_aconst,
            ConceptName.S_ANGLE.value: self.check_sangle,
            ConceptName.CONSTANT_RATIO.value: self.check_rconst,
            ConceptName.COMPUTE_ANGLE.value: self.check_acompute,
            ConceptName.COMPUTE_RATIO.value: self.check_rcompute,
            ConceptName.SAMESIDE.value: self.check_sameside,
            ConceptName.DIFFERENT.value: self.check_diff,
            ConceptName.NON_COLLINEAR.value: self.check_ncoll,
            ConceptName.NON_PARALLEL.value: self.check_npara,
            ConceptName.NON_PERPENDICULAR.value: self.check_nperp,
        }

    def check(self, name: str, args: list[Point]) -> bool:
        """Symbolically check if a predicate is True."""
        return self.NAME_TO_CHECK[name](args)

    def check_goal(self, goal: Optional["Construction"]):
        success = False
        if goal is not None:
            goal_args = self.symbols_graph.names2points(goal.args)
            if self.check(goal.name, goal_args):
                success = True
        return success

    def check_const_or_eqangle(self, args: list[Point]) -> bool:
        if len(args) == 5:
            return self.check_aconst(args)
        return self.check_eqangle(args)

    def check_const_or_eqratio(self, args: list[Point]) -> bool:
        if len(args) == 5:
            return self.check_rconst(args)
        return self.check_eqratio(args)

    # Basic checks

    def check_coll(self, points: list[Point]) -> bool:
        points = list(set(points))
        if len(points) < 3:
            return True
        line2count = defaultdict(lambda: 0)
        for p in points:
            for line in p.neighbors(Line):
                line2count[line] += 1
        return any([count == len(points) for _, count in line2count.items()])

    def check_para(self, points: list[Point]) -> bool:
        a, b, c, d = points
        if (a == b) or (c == d):
            return False
        ab = self.symbols_graph.get_line(a, b)
        cd = self.symbols_graph.get_line(c, d)
        if not ab or not cd:
            return False

        return is_equal(ab, cd)

    def check_para_or_coll(self, points: list[Point]) -> bool:
        return self.check_para(points) or self.check_coll(points)

    def check_perpl(self, ab: Line, cd: Line) -> bool:
        if ab.val is None or cd.val is None:
            return False
        if ab.val == cd.val:
            return False
        a12, a21 = self.symbols_graph.get_angle(ab.val, cd.val)
        if a12 is None or a21 is None:
            return False
        return is_equal(a12, a21)

    def check_perp(self, points: list[Point]) -> bool:
        a, b, c, d = points
        ab = self.symbols_graph.get_line(a, b)
        cd = self.symbols_graph.get_line(c, d)
        if not ab or not cd:
            return False
        return self.check_perpl(ab, cd)

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

    def check_eqangle(self, points: list[Point]) -> bool:
        """Check if two angles are equal."""
        a, b, c, d, m, n, p, q = points

        if {a, b} == {c, d} and {m, n} == {p, q}:
            return True
        if {a, b} == {m, n} and {c, d} == {p, q}:
            return True

        if (a == b) or (c == d) or (m == n) or (p == q):
            return False
        ab = self.symbols_graph.get_line(a, b)
        cd = self.symbols_graph.get_line(c, d)
        mn = self.symbols_graph.get_line(m, n)
        pq = self.symbols_graph.get_line(p, q)

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

        for ang1, _, _ in all_angles(ab._val, cd._val):
            for ang2, _, _ in all_angles(mn._val, pq._val):
                if is_equal(ang1, ang2):
                    return True

        if self.check_perp([a, b, m, n]) and self.check_perp([c, d, p, q]):
            return True
        if self.check_perp([a, b, p, q]) and self.check_perp([c, d, m, n]):
            return True

        return False

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

    # Algebraic checks

    def check_aconst(self, points: list[Point], verbose: bool = False) -> bool:
        """Check if the angle is equal to a certain constant."""
        a, b, c, d, nd = points
        _ = verbose
        if isinstance(nd, str):
            name = nd
        else:
            name = nd.name
        num, den = name.split("pi/")
        ang, _ = self.alegbraic_manipulator.get_or_create_const_ang(int(num), int(den))

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

    def check_sangle(self, points: list[Point], verbose: bool = False) -> bool:
        a, b, c, nd = points
        if isinstance(nd, str):
            name = nd
        else:
            name = nd.name
        num, den = map(int, name.split("pi/"))
        ang, _ = self.alegbraic_manipulator.get_or_create_const_ang(num, den)

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

    def check_rconst(self, points: list[Point], verbose: bool = False) -> bool:
        """Check whether a ratio is equal to some given constant."""
        _ = verbose
        a, b, c, d, nd = points
        if isinstance(nd, str):
            name = nd
        else:
            name = nd.name
        num, den = name.split("/")
        rat, _ = self.alegbraic_manipulator.get_or_create_const_rat(int(num), int(den))

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

    def check_acompute(self, points: list[Point]) -> bool:
        """Check if an angle has a constant value."""
        a, b, c, d = points
        ab = self.symbols_graph.get_line(a, b)
        cd = self.symbols_graph.get_line(c, d)
        if not ab or not cd:
            return False

        if not (ab.val and cd.val):
            return False

        for ang0 in self.alegbraic_manipulator.aconst.values():
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

        for rat0 in self.alegbraic_manipulator.rconst.values():
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

    def check_contri(self, points: list[Point]) -> bool:
        a, b, c, x, y, z = points
        return (
            self.check_cong([a, b, x, y])
            and self.check_cong([b, c, y, z])
            and self.check_cong([c, a, z, x])
        )

    # Negative checks (with numerical double check)

    def check_ncoll(self, points: list[Point]) -> bool:
        if self.check_coll(points):
            return False
        return not check_coll_numerical([p.num for p in points])

    def check_npara(self, points: list[Point]) -> bool:
        if self.check_para(points):
            return False
        return not check_para_numerical([p.num for p in points])

    def check_nperp(self, points: list[Point]) -> bool:
        if self.check_perp(points):
            return False
        return not check_perp_numerical([p.num for p in points])

    # Numerical only checks

    def check_sameside(self, points: list[Point]) -> bool:
        return check_sameside_numerical([p.num for p in points])

    def check_diff(self, points: list[Point]) -> bool:
        a, b = points
        return not a.num.close(b.num)
