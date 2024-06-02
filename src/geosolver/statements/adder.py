from __future__ import annotations
from enum import Enum
from typing import TYPE_CHECKING, Optional, Tuple


import geosolver.combinatorics as comb
from geosolver.statement import Statement, angle_to_num_den, ratio_to_num_den
from geosolver.dependencies.why_predicates import why_dependency
from geosolver.predicates import Predicate
import geosolver.numerical.check as nm


from geosolver.dependencies.dependency import Dependency
from geosolver.dependencies.empty_dependency import EmptyDependency
from geosolver.geometry import (
    Angle,
    Line,
    Node,
    Point,
    Segment,
    is_equal,
    is_equiv,
)
from geosolver.listing import list_eqratio3


ToCache = Tuple[Statement, Dependency]

if TYPE_CHECKING:
    from geosolver.algebraic.algebraic_manipulator import AlgebraicManipulator
    from geosolver.symbols_graph import SymbolsGraph
    from geosolver.statements.checker import StatementChecker
    from geosolver.dependencies.caching import DependencyCache


class IntrinsicRules(Enum):
    PARA_FROM_PERP = "i00"
    CYCLIC_FROM_CONG = "i01"
    CONG_FROM_EQRATIO = "i02"
    PARA_FROM_EQANGLE = "i03"

    POINT_ON_SAME_LINE = "i04"
    PARA_FROM_LINES = "i05"
    PERP_FROM_LINES = "i06"
    PERP_FROM_ANGLE = "i07"
    EQANGLE_FROM_LINES = "i08"
    EQANGLE_FROM_CONGRUENT_ANGLE = "i09"
    EQRATIO_FROM_PROPORTIONAL_SEGMENTS = "i10"
    CYCLIC_FROM_CIRCLE = "i11"

    ACONST_FROM_LINES = "i12"
    ACONST_FROM_ANGLE = "i13"
    SANGLE_FROM_ANGLE = "i14"
    RCONST_FROM_RATIO = "i15"


class StatementAdder:
    def __init__(
        self,
        symbols_graph: "SymbolsGraph",
        alegbraic_manipulator: "AlgebraicManipulator",
        statements_checker: "StatementChecker",
        dependency_cache: "DependencyCache",
        disabled_intrinsic_rules: Optional[list[IntrinsicRules | str]] = None,
    ) -> None:
        self.symbols_graph = symbols_graph
        self.alegbraic_manipulator = alegbraic_manipulator

        self.statements_checker = statements_checker
        self.dependency_cache = dependency_cache

        if disabled_intrinsic_rules is None:
            disabled_intrinsic_rules = []
        self.DISABLED_INTRINSIC_RULES = [
            IntrinsicRules(r) for r in disabled_intrinsic_rules
        ]

        self.NAME_TO_ADDER = {
            Predicate.COLLINEAR: self._add_coll,
            Predicate.COLLINEAR_X: self._add_coll,
            Predicate.PARALLEL: self._add_para,
            Predicate.PERPENDICULAR: self._add_perp,
            Predicate.MIDPOINT: self._add_midp,
            Predicate.CONGRUENT: self._add_cong,
            Predicate.CONGRUENT_2: self._add_cong2,
            Predicate.CIRCLE: self._add_circle,
            Predicate.CYCLIC: self._add_cyclic,
            Predicate.EQANGLE: self._add_eqangle,
            Predicate.EQANGLE6: self._add_eqangle,
            Predicate.S_ANGLE: self._add_s_angle,
            Predicate.EQRATIO: self._add_eqratio,
            Predicate.EQRATIO6: self._add_eqratio,
            Predicate.EQRATIO3: self._add_eqratio3,
            Predicate.EQRATIO4: self._add_eqratio4,
            Predicate.SIMILAR_TRIANGLE: self._add_simtri,
            Predicate.SIMILAR_TRIANGLE_REFLECTED: self._add_simtri_reflect,
            Predicate.SIMILAR_TRIANGLE_BOTH: self._add_simtri_check,
            Predicate.CONTRI_TRIANGLE: self._add_contri,
            Predicate.CONTRI_TRIANGLE_REFLECTED: self._add_contri_reflect,
            Predicate.CONTRI_TRIANGLE_BOTH: self._add_contri_check,
            Predicate.CONSTANT_ANGLE: self._add_aconst,
            Predicate.CONSTANT_RATIO: self._add_rconst,
        }

    def make_equal(self, x: Node, y: Node, deps: Dependency) -> None:
        """Make that two nodes x and y are equal, i.e. merge their value node."""
        if x.val is None:
            x, y = y, x

        self.symbols_graph.get_node_val(x, deps=None)
        self.symbols_graph.get_node_val(y, deps=None)
        vx = x._val
        vy = y._val

        if vx == vy:
            return

        merges = [vx, vy]

        # If eqangle on the same directions switched then they are perpendicular
        if (
            isinstance(x, Angle)
            and x not in self.alegbraic_manipulator.aconst.values()
            and y not in self.alegbraic_manipulator.aconst.values()
            and x.directions == y.directions[::-1]
            and x.directions[0] != x.directions[1]
        ):
            merges = [self.alegbraic_manipulator.vhalfpi, vx, vy]

        self.symbols_graph.merge(merges, deps)

    def add_piece(
        self, statement: Statement, deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add a new predicate."""
        piece_adder = self.NAME_TO_ADDER.get(statement.predicate)
        if piece_adder is not None:
            return piece_adder(statement.args, deps)

        deps_to_cache = []
        # Cached or compute piece
        if statement.predicate in [
            Predicate.COMPUTE_ANGLE,
            Predicate.COMPUTE_RATIO,
            Predicate.FIX_L,
            Predicate.FIX_C,
            Predicate.FIX_B,
            Predicate.FIX_T,
            Predicate.FIX_P,
        ]:
            dep = deps.populate(statement)
            deps_to_cache.append((statement, dep))
            new_deps = [dep]
        elif statement.predicate is Predicate.IND:
            new_deps = []
        else:
            raise ValueError(f"Not recognize predicate {statement.predicate}")

        return new_deps, deps_to_cache

    def add_algebra(
        self, statement: Statement, reason: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        new_deps, to_cache = [], []
        if statement.predicate is Predicate.PARALLEL:
            return self._add_algebra_para(*statement.args, reason=reason)

        elif statement.predicate is Predicate.CONSTANT_ANGLE:
            return self._add_algebra_aconst(
                *statement.args, statement=statement, reason=reason
            )
        elif statement.predicate is Predicate.CONSTANT_RATIO:
            return self._add_rconst(statement.args, reason)

        elif statement.predicate is Predicate.EQANGLE:
            return self._add_eqangle(statement.args, reason)

        elif statement.predicate is Predicate.EQRATIO:
            return self._add_eqratio(statement.args, reason)

        elif statement.predicate in [Predicate.CONGRUENT, Predicate.CONGRUENT_2]:
            return self._add_algebra_cong(*statement.args, reason=reason)

        return new_deps, to_cache

    def _add_algebra_para(
        self, a: Point, b: Point, c: Point, d: Point, reason: EmptyDependency
    ):
        ab = self.symbols_graph.get_line_thru_pair(a, b)
        cd = self.symbols_graph.get_line_thru_pair(c, d)
        if is_equiv(ab, cd):
            return [], []
        return self._add_para((a, b, c, d), reason)

    def _add_algebra_cong(
        self, a: Point, b: Point, c: Point, d: Point, reason: EmptyDependency
    ):
        if not (a != b and c != d and (a != c or b != d)):
            return [], []
        return self._add_cong((a, b, c, d), reason)

    def _add_algebra_aconst(
        self,
        a: Point,
        b: Point,
        c: Point,
        d: Point,
        angle: Angle,
        statement: Statement,
        reason: EmptyDependency,
    ):
        ab = self.symbols_graph.get_line_thru_pair(a, b)
        cd = self.symbols_graph.get_line_thru_pair(c, d)
        ab, ba, why = self.symbols_graph.get_or_create_angle_from_lines(
            ab, cd, deps=None
        )

        if why:
            dep0 = reason.populate(statement)
            reason = EmptyDependency(level=reason.level, rule_name=reason.rule_name)
            reason.why = [dep0] + why

        a, b = ab._d
        (x, y), (m, n) = a._obj.points, b._obj.points

        new_deps = []
        to_cache = []
        if not is_equal(ab, angle):
            if angle == self.alegbraic_manipulator.halfpi:
                _add, _to_cache = self._add_perp([x, y, m, n], reason)
                new_deps += _add
                to_cache += _to_cache
            aconst = Statement(Predicate.CONSTANT_ANGLE, [x, y, m, n, angle])
            dep1 = reason.populate(aconst)
            to_cache.append((aconst, dep1))
            self.make_equal(angle, ab, deps=dep1)
            new_deps.append(dep1)

        opposite_angle = angle.opposite
        if not is_equal(ba, opposite_angle):
            if opposite_angle == self.alegbraic_manipulator.halfpi:
                _add, _to_cache = self._add_perp([m, n, x, y], reason)
                new_deps += _add
                to_cache += _to_cache
            aconst = Statement(Predicate.CONSTANT_ANGLE, [m, n, x, y, opposite_angle])
            dep2 = reason.populate(aconst)
            to_cache.append((aconst, dep2))
            self.make_equal(opposite_angle, ba, deps=dep2)
            new_deps.append(dep2)
        return new_deps, to_cache

    def _add_coll(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add a predicate that `points` are collinear."""
        points = list(set(points))
        og_points = list(points)

        all_lines: list[Line] = []
        for p1, p2 in comb.arrangement_pairs(points):
            all_lines.append(self.symbols_graph.get_line_thru_pair(p1, p2))
        points = sum([line.neighbors(Point) for line in all_lines], [])
        points = list(set(points))

        existed: set[Line] = set()
        new: set[Line] = set()
        for p1, p2 in comb.arrangement_pairs(points):
            if p1.name > p2.name:
                p1, p2 = p2, p1
            if (p1, p2) in self.symbols_graph._pair2line:
                line = self.symbols_graph._pair2line[(p1, p2)]
                existed.add(line)
            else:
                line = self.symbols_graph.get_new_line_thru_pair(p1, p2)
                new.add(line)

        existed: list[Line] = list(sorted(existed, key=lambda node: node.name))
        new: list[Line] = list(sorted(new, key=lambda node: node.name))
        if not existed:
            line0, *lines = new
        else:
            line0, lines = existed[0], existed[1:] + new

        add = []
        to_cache = []
        line0, why0 = line0.rep_and_why()
        a, b = line0.points
        for line in lines:
            c, d = line.points
            args = list({a, b, c, d})
            if len(args) < 3:
                continue

            whys = []
            for x in args:
                if x not in og_points:
                    whys.append(self._coll_dep(og_points, x))

            abcd_deps = deps
            if (
                whys + why0
                and IntrinsicRules.POINT_ON_SAME_LINE
                not in self.DISABLED_INTRINSIC_RULES
            ):
                coll = Statement(Predicate.COLLINEAR, og_points)
                dep0 = deps.populate(coll)
                abcd_deps = EmptyDependency(
                    level=deps.level, rule_name=IntrinsicRules.POINT_ON_SAME_LINE.value
                )
                abcd_deps.why = [dep0] + whys

            is_coll = self.statements_checker.check_coll(args)
            coll = Statement(Predicate.COLLINEAR, args)
            dep = abcd_deps.populate(coll)
            to_cache.append((coll, dep))
            self.symbols_graph.merge_into(line0, [line], dep)

            if not is_coll:
                add += [dep]

        return add, to_cache

    def _coll_dep(self, points: list[Point], p: Point) -> list[Dependency]:
        """Return the dep(.why) explaining why p is coll with points."""
        for p1, p2 in comb.arrangement_pairs(points):
            if self.statements_checker.check_coll([p1, p2, p]):
                coll = Statement(Predicate.COLLINEAR, [p1, p2, p])
                coll_dep = Dependency(coll, None, None)
                coll_dep.why = why_dependency(
                    coll_dep,
                    self.symbols_graph,
                    self.statements_checker,
                    self.dependency_cache,
                    None,
                )
                return coll_dep

    def _add_para(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add a new predicate that 4 points (2 lines) are parallel."""
        a, b, c, d = points
        ab, why1 = self.symbols_graph.get_line_thru_pair_why(a, b)
        cd, why2 = self.symbols_graph.get_line_thru_pair_why(c, d)

        (a, b), (c, d) = ab.points, cd.points

        if (
            why1 + why2
            and IntrinsicRules.PARA_FROM_LINES not in self.DISABLED_INTRINSIC_RULES
        ):
            para = Statement(Predicate.PARALLEL, points)
            dep0 = deps.populate(para)
            deps = EmptyDependency(
                level=deps.level, rule_name=IntrinsicRules.PARA_FROM_LINES.value
            )
            deps.why = [dep0] + why1 + why2

        para = Statement(Predicate.PARALLEL, [a, b, c, d])
        dep = deps.populate(para)
        self.make_equal(ab, cd, dep)
        dep.algebra = ab._val, cd._val

        to_cache = [(para, dep)]
        if not is_equal(ab, cd):
            return [dep], to_cache
        return [], to_cache

    def _add_para_or_coll_from_perp(
        self,
        a: Point,
        b: Point,
        c: Point,
        d: Point,
        x: Point,
        y: Point,
        m: Point,
        n: Point,
        deps: EmptyDependency,
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add a new parallel or collinear predicate."""
        perp = Statement(Predicate.PERPENDICULAR, [a, b, c, d])
        extends = [Statement(Predicate.PERPENDICULAR, [x, y, m, n])]
        if {a, b} == {x, y}:
            pass
        elif self.statements_checker.check_para([a, b, x, y]):
            extends.append(Statement(Predicate.PARALLEL, [a, b, x, y]))
        elif self.statements_checker.check_coll([a, b, x, y]):
            extends.append(Statement(Predicate.COLLINEAR, set(list([a, b, x, y]))))
        else:
            return None

        if m in [c, d] or n in [c, d] or c in [m, n] or d in [m, n]:
            pass
        elif self.statements_checker.check_coll([c, d, m]):
            extends.append(Statement(Predicate.COLLINEAR, [c, d, m]))
        elif self.statements_checker.check_coll([c, d, n]):
            extends.append(Statement(Predicate.COLLINEAR, [c, d, n]))
        elif self.statements_checker.check_coll([c, m, n]):
            extends.append(Statement(Predicate.COLLINEAR, [c, m, n]))
        elif self.statements_checker.check_coll([d, m, n]):
            extends.append(Statement(Predicate.COLLINEAR, [d, m, n]))
        else:
            deps = deps.extend_many(
                self.symbols_graph,
                self.statements_checker,
                self.dependency_cache,
                perp,
                extends,
            )
            return self._add_para([c, d, m, n], deps)

        deps = deps.extend_many(
            self.symbols_graph,
            self.statements_checker,
            self.dependency_cache,
            perp,
            extends,
        )
        return self._add_coll(list(set([c, d, m, n])), deps)

    def _maybe_make_para_from_perp(
        self, points: list[Point], deps: EmptyDependency
    ) -> Optional[Tuple[list[Dependency], list[ToCache]]]:
        """Maybe add a new parallel predicate from perp predicate."""
        a, b, c, d = points
        halfpi = self.alegbraic_manipulator.aconst[(1, 2)]
        for ang in halfpi.val.neighbors(Angle):
            if ang == halfpi:
                continue
            d1, d2 = ang.directions
            x, y = d1._obj.points
            m, n = d2._obj.points

            for args in [
                (a, b, c, d, x, y, m, n),
                (a, b, c, d, m, n, x, y),
                (c, d, a, b, x, y, m, n),
                (c, d, a, b, m, n, x, y),
            ]:
                args = args + (deps,)
                para_or_coll = self._add_para_or_coll_from_perp(*args)
                if para_or_coll is not None:
                    return para_or_coll

        return None

    def _add_perp(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add a new perpendicular predicate from 4 points (2 lines)."""

        if IntrinsicRules.PARA_FROM_PERP not in self.DISABLED_INTRINSIC_RULES:
            para_from_perp = self._maybe_make_para_from_perp(points, deps)
            if para_from_perp is not None:
                return para_from_perp

        a, b, c, d = points
        ab, why1 = self.symbols_graph.get_line_thru_pair_why(a, b)
        cd, why2 = self.symbols_graph.get_line_thru_pair_why(c, d)

        (a, b), (c, d) = ab.points, cd.points

        if (
            why1 + why2
            and IntrinsicRules.PERP_FROM_LINES not in self.DISABLED_INTRINSIC_RULES
        ):
            perp = Statement(Predicate.PERPENDICULAR, points)
            dep0 = deps.populate(perp)
            deps = EmptyDependency(
                level=deps.level, rule_name=IntrinsicRules.PERP_FROM_LINES.value
            )
            deps.why = [dep0] + why1 + why2

        self.symbols_graph.get_node_val(ab, deps=None)
        self.symbols_graph.get_node_val(cd, deps=None)

        if ab.val == cd.val:
            raise ValueError(f"{ab.name} and {cd.name} Cannot be perp.")

        args = [a, b, c, d]
        i = 0
        for x, y, xy in [(a, b, ab), (c, d, cd)]:
            i += 1
            x_, y_ = xy._val._obj.points
            if {x, y} == {x_, y_}:
                continue
            if deps:
                perp = Statement(Predicate.PERPENDICULAR, list(args))
                para = Statement(Predicate.PARALLEL, [x, y, x_, y_])
                deps = deps.extend(self, perp, para)
            args[2 * i - 2] = x_
            args[2 * i - 1] = y_

        a12, a21, why = self.symbols_graph.get_or_create_angle_from_lines(
            ab, cd, deps=None
        )

        perp = Statement(Predicate.PERPENDICULAR, [a, b, c, d])
        if why and IntrinsicRules.PERP_FROM_ANGLE not in self.DISABLED_INTRINSIC_RULES:
            dep0 = deps.populate(perp)
            deps = EmptyDependency(
                level=deps.level, rule_name=IntrinsicRules.PERP_FROM_ANGLE.value
            )
            deps.why = [dep0] + why

        dab, dcd = a12._d
        a, b = dab._obj.points
        c, d = dcd._obj.points

        dep = deps.populate(perp)
        dep.algebra = [dab, dcd]
        self.make_equal(a12, a21, deps=dep)

        eqangle = Statement(Predicate.EQANGLE, [a, b, c, d, c, d, a, b])
        to_cache = [(perp, dep), (eqangle, dep)]

        if not is_equal(a12, a21):
            return [dep], to_cache
        return [], to_cache

    def _add_cong(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add that two segments (4 points) are congruent."""
        a, b, c, d = points
        ab = self.symbols_graph.get_or_create_segment(a, b, deps=None)
        cd = self.symbols_graph.get_or_create_segment(c, d, deps=None)

        cong = Statement(Predicate.CONGRUENT, [a, b, c, d])
        dep = deps.populate(cong)
        self.make_equal(ab, cd, deps=dep)
        dep.algebra = ab._val, cd._val

        to_cache = [(cong, dep)]
        deps = []

        if not is_equal(ab, cd):
            deps += [dep]

        if IntrinsicRules.CYCLIC_FROM_CONG in self.DISABLED_INTRINSIC_RULES or (
            a not in [c, d] and b not in [c, d]
        ):
            return deps, to_cache

        if b in [c, d]:
            a, b = b, a
        if a == d:
            c, d = d, c

        cyclic_deps, cyclic_cache = self._maybe_add_cyclic_from_cong(a, b, d, dep)
        deps += cyclic_deps
        to_cache += cyclic_cache
        return deps, to_cache

    def _add_cong2(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        m, n, a, b = points
        add, to_cache = self._add_cong([m, a, n, a], deps)
        _add, _to_cache = self._add_cong([m, b, n, b], deps)
        return add + _add, to_cache + _to_cache

    def _add_midp(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        m, a, b = points
        add_coll, to_cache_coll = self._add_coll(points, deps=deps)
        add_cong, to_cache_cong = self._add_cong([m, a, m, b], deps)
        return add_coll + add_cong, to_cache_coll + to_cache_cong

    def _add_circle(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        o, a, b, c = points
        add_ab, to_cache_ab = self._add_cong([o, a, o, b], deps=deps)
        add_ac, to_cache_ac = self._add_cong([o, a, o, c], deps=deps)
        return add_ab + add_ac, to_cache_ab + to_cache_ac

    def _add_cyclic(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add a new cyclic predicate that 4 points are concyclic."""
        points = list(set(points))
        og_points = list(points)

        all_circles = []
        for p1, p2, p3 in comb.arrangement_triplets(points):
            all_circles.append(self.symbols_graph.get_circle_thru_triplet(p1, p2, p3))
        points = sum([c.neighbors(Point) for c in all_circles], [])
        points = list(set(points))

        existed = set()
        new = set()
        for p1, p2, p3 in comb.arrangement_triplets(points):
            p1, p2, p3 = sorted([p1, p2, p3], key=lambda x: x.name)

            if (p1, p2, p3) in self.symbols_graph._triplet2circle:
                circle = self.symbols_graph._triplet2circle[(p1, p2, p3)]
                existed.add(circle)
            else:
                circle = self.symbols_graph.get_new_circle_thru_triplet(p1, p2, p3)
                new.add(circle)

        existed = sorted(existed, key=lambda node: node.name)
        new = sorted(new, key=lambda node: node.name)

        existed, new = list(existed), list(new)
        if not existed:
            circle0, *circles = new
        else:
            circle0, circles = existed[0], existed[1:] + new

        add = []
        to_cache = []
        circle0, why0 = circle0.rep_and_why()
        a, b, c = circle0.points
        for circle in circles:
            d, e, f = circle.points
            args = list({a, b, c, d, e, f})
            if len(args) < 4:
                continue
            whys = []
            for x in [a, b, c, d, e, f]:
                if x not in og_points:
                    whys.append(self._cyclic_dep(og_points, x))

            abcdef_deps = deps
            if (
                whys + why0
                and IntrinsicRules.CYCLIC_FROM_CIRCLE
                not in self.DISABLED_INTRINSIC_RULES
            ):
                cyclic = Statement(Predicate.CYCLIC, og_points)
                dep0 = deps.populate(cyclic)
                abcdef_deps = EmptyDependency(
                    level=deps.level, rule_name=IntrinsicRules.CYCLIC_FROM_CIRCLE.value
                )
                abcdef_deps.why = [dep0] + whys

            is_cyclic = self.statements_checker.check_cyclic(args)

            cyclic = Statement(Predicate.CYCLIC, args)
            dep = abcdef_deps.populate(cyclic)
            to_cache.append((cyclic, dep))
            self.symbols_graph.merge_into(circle0, [circle], dep)
            if not is_cyclic:
                add += [dep]

        return add, to_cache

    def _cyclic_dep(self, points: list[Point], p: Point) -> list[Dependency]:
        for p1, p2, p3 in comb.arrangement_triplets(points):
            if self.statements_checker.check_cyclic([p1, p2, p3, p]):
                cyclic = Statement(Predicate.CYCLIC, [p1, p2, p3, p])
                cyclic_dep = Dependency(cyclic, None, None)
                cyclic_dep.why = why_dependency(
                    cyclic_dep,
                    self.symbols_graph,
                    self.statements_checker,
                    self.dependency_cache,
                    None,
                )
                return cyclic_dep

    def _maybe_add_cyclic_from_cong(
        self, a: Point, b: Point, c: Point, cong_ab_ac: Dependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Maybe add a new cyclic predicate from given congruent segments."""
        ab = self.symbols_graph.get_or_create_segment(a, b, deps=None)

        # all eq segs with one end being a.
        segs = [s for s in ab.val.neighbors(Segment) if a in s.points]

        # all points on circle (a, b)
        points = []
        for s in segs:
            x, y = list(s.points)
            points.append(x if y == a else y)

        # for sure both b and c are in points
        points = [p for p in points if p not in [b, c]]

        if len(points) < 2:
            return [], []

        x, y = points[:2]

        if self.statements_checker.check_cyclic([b, c, x, y]):
            return [], []

        ax = self.symbols_graph.get_or_create_segment(a, x, deps=None)
        ay = self.symbols_graph.get_or_create_segment(a, y, deps=None)
        why = ab._val.why_equal([ax._val, ay._val], level=None)
        why += [cong_ab_ac]

        deps = EmptyDependency(cong_ab_ac.level, IntrinsicRules.CYCLIC_FROM_CONG.value)
        deps.why = why

        return self._add_cyclic([b, c, x, y], deps)

    def _add_eqangle(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add eqangle made by 8 points in `points`."""
        if deps:
            deps = deps.copy()
        a, b, c, d, m, n, p, q = points
        ab, why1 = self.symbols_graph.get_line_thru_pair_why(a, b)
        cd, why2 = self.symbols_graph.get_line_thru_pair_why(c, d)
        mn, why3 = self.symbols_graph.get_line_thru_pair_why(m, n)
        pq, why4 = self.symbols_graph.get_line_thru_pair_why(p, q)

        a, b = ab.points
        c, d = cd.points
        m, n = mn.points
        p, q = pq.points

        if (
            deps
            and why1 + why2 + why3 + why4
            and IntrinsicRules.EQANGLE_FROM_LINES not in self.DISABLED_INTRINSIC_RULES
        ):
            eqangle = Statement(Predicate.EQANGLE, points)
            dep0 = deps.populate(eqangle)
            deps = EmptyDependency(
                level=deps.level, rule_name=IntrinsicRules.EQANGLE_FROM_LINES.value
            )
            deps.why = [dep0] + why1 + why2 + why3 + why4

        if IntrinsicRules.PARA_FROM_EQANGLE not in self.DISABLED_INTRINSIC_RULES:
            maybe_pairs = self._maybe_make_equal_pairs(
                a, b, c, d, m, n, p, q, ab, cd, mn, pq, deps
            )
            if maybe_pairs is not None:
                return maybe_pairs

        self.symbols_graph.get_node_val(ab, deps=None)
        self.symbols_graph.get_node_val(cd, deps=None)
        self.symbols_graph.get_node_val(mn, deps=None)
        self.symbols_graph.get_node_val(pq, deps=None)

        add, to_cache = [], []

        if (
            ab.val != cd.val
            and mn.val != pq.val
            and (ab.val != mn.val or cd.val != pq.val)
        ):
            _add, _to_cache = self._add_eqangle8(
                a, b, c, d, m, n, p, q, ab, cd, mn, pq, deps
            )
            add += _add
            to_cache += _to_cache

        if (
            ab.val != mn.val
            and cd.val != pq.val
            and (ab.val != cd.val or mn.val != pq.val)
        ):
            _add, _to_cache = self._add_eqangle8(
                a, b, m, n, c, d, p, q, ab, mn, cd, pq, deps
            )
            add += _add
            to_cache += _to_cache

        return add, to_cache

    def _add_eqangle8(
        self,
        a: Point,
        b: Point,
        c: Point,
        d: Point,
        m: Point,
        n: Point,
        p: Point,
        q: Point,
        ab: Line,
        cd: Line,
        mn: Line,
        pq: Line,
        deps: EmptyDependency,
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add eqangle core."""
        if deps:
            deps = deps.copy()

        args = [a, b, c, d, m, n, p, q]
        i = 0
        for x, y, xy in [(a, b, ab), (c, d, cd), (m, n, mn), (p, q, pq)]:
            i += 1
            x_, y_ = xy._val._obj.points
            if {x, y} == {x_, y_}:
                continue
            if deps:
                eqangle = Statement(Predicate.EQANGLE, tuple(args))
                para = Statement(Predicate.PARALLEL, [x, y, x_, y_])
                deps = deps.extend(self, eqangle, para)
                args[2 * i - 2] = x_
                args[2 * i - 1] = y_

        add = []
        ab_cd, cd_ab, why1 = self.symbols_graph.get_or_create_angle_from_lines(
            ab, cd, deps=None
        )
        mn_pq, pq_mn, why2 = self.symbols_graph.get_or_create_angle_from_lines(
            mn, pq, deps=None
        )

        if (
            why1 + why2
            and IntrinsicRules.EQANGLE_FROM_CONGRUENT_ANGLE
            not in self.DISABLED_INTRINSIC_RULES
        ):
            eqangle = Statement(Predicate.EQANGLE, args)
            dep0 = deps.populate(eqangle)
            deps = EmptyDependency(
                level=deps.level,
                rule_name=IntrinsicRules.EQANGLE_FROM_CONGRUENT_ANGLE.value,
            )
            deps.why = [dep0] + why1 + why2

        dab, dcd = ab_cd._d
        dmn, dpq = mn_pq._d

        a, b = dab._obj.points
        c, d = dcd._obj.points
        m, n = dmn._obj.points
        p, q = dpq._obj.points

        to_cache = []

        deps1 = None
        eqangle = Statement(Predicate.EQANGLE, [a, b, c, d, m, n, p, q])
        if deps:
            deps1 = deps.populate(eqangle)
            deps1.algebra = [dab, dcd, dmn, dpq]
        if not is_equal(ab_cd, mn_pq):
            add += [deps1]
        to_cache.append((eqangle, deps1))
        self.make_equal(ab_cd, mn_pq, deps=deps1)

        deps2 = None
        eqangle_sym = Statement(Predicate.EQANGLE, [c, d, a, b, p, q, m, n])
        if deps:
            deps2 = deps.populate(eqangle_sym)
            deps2.algebra = [dcd, dab, dpq, dmn]
        if not is_equal(cd_ab, pq_mn):
            add += [deps2]
        to_cache.append((eqangle_sym, deps2))
        self.make_equal(cd_ab, pq_mn, deps=deps2)

        return add, to_cache

    def _add_eqratio3(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add three eqratios through a list of 6 points (due to parallel lines).

          a -- b
         m ---- n
        c ------ d

        """
        add, to_cache = [], []
        ratios = list_eqratio3(points)
        for ratio_points in ratios:
            _add, _to_cache = self._add_eqratio(ratio_points, deps)
            add += _add
            to_cache += _to_cache
        return add, to_cache

    def _add_eqratio4(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add four eqratios through a list of 5 points
        (due to parallel lines with common point).

           o
         a - b
        c --- d

        """
        o, a, b, c, d = points
        add, to_cache = self._add_eqratio3([a, b, c, d, o, o], deps)
        _add, _to_cache = self._add_eqratio([o, a, o, c, a, b, c, d], deps)
        return add + _add, to_cache + _to_cache

    def _add_eqratio(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add a new eqratio from 8 points."""
        if deps:
            deps = deps.copy()
        a, b, c, d, m, n, p, q = points
        ab = self.symbols_graph.get_or_create_segment(a, b, deps=None)
        cd = self.symbols_graph.get_or_create_segment(c, d, deps=None)
        mn = self.symbols_graph.get_or_create_segment(m, n, deps=None)
        pq = self.symbols_graph.get_or_create_segment(p, q, deps=None)

        if IntrinsicRules.CONG_FROM_EQRATIO not in self.DISABLED_INTRINSIC_RULES:
            add = self._maybe_make_equal_pairs(
                a, b, c, d, m, n, p, q, ab, cd, mn, pq, deps
            )
            if add is not None:
                return add

        self.symbols_graph.get_node_val(ab, deps=None)
        self.symbols_graph.get_node_val(cd, deps=None)
        self.symbols_graph.get_node_val(mn, deps=None)
        self.symbols_graph.get_node_val(pq, deps=None)

        add = []
        to_cache = []
        if (
            ab.val != cd.val
            and mn.val != pq.val
            and (ab.val != mn.val or cd.val != pq.val)
        ):
            _add, _to_cache = self._add_eqratio8(
                a, b, c, d, m, n, p, q, ab, cd, mn, pq, deps
            )
            add += _add
            to_cache += _to_cache

        if (
            ab.val != mn.val
            and cd.val != pq.val
            and (ab.val != cd.val or mn.val != pq.val)
        ):
            _add, _to_cache = self._add_eqratio8(
                a, b, m, n, c, d, p, q, ab, mn, cd, pq, deps
            )
            add += _add
            to_cache += _to_cache
        return add, to_cache

    def _add_eqratio8(
        self,
        a: Point,
        b: Point,
        c: Point,
        d: Point,
        m: Point,
        n: Point,
        p: Point,
        q: Point,
        ab: Segment,
        cd: Segment,
        mn: Segment,
        pq: Segment,
        deps: EmptyDependency,
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add a new eqratio from 8 points (core)."""
        if deps:
            deps = deps.copy()

        args = [a, b, c, d, m, n, p, q]
        i = 0
        for x, y, xy in [(a, b, ab), (c, d, cd), (m, n, mn), (p, q, pq)]:
            if {x, y} == set(xy.points):
                continue
            x_, y_ = list(xy.points)
            if deps:
                eqratio = Statement(Predicate.EQRATIO, tuple(args))
                cong = Statement(Predicate.CONGRUENT, [x, y, x_, y_])
                deps = deps.extend(self, eqratio, cong)
            args[2 * i - 2] = x_
            args[2 * i - 1] = y_

        add = []
        ab_cd, cd_ab, why1 = self.symbols_graph.get_or_create_ratio_from_segments(
            ab, cd, deps=None
        )
        mn_pq, pq_mn, why2 = self.symbols_graph.get_or_create_ratio_from_segments(
            mn, pq, deps=None
        )

        if (
            why1 + why2
            and IntrinsicRules.EQRATIO_FROM_PROPORTIONAL_SEGMENTS
            not in self.DISABLED_INTRINSIC_RULES
        ):
            eqratio = Statement(Predicate.EQRATIO, args)
            dep0 = deps.populate(eqratio)
            deps = EmptyDependency(
                level=deps.level,
                rule_name=IntrinsicRules.EQRATIO_FROM_PROPORTIONAL_SEGMENTS.value,
            )
            deps.why = [dep0] + why1 + why2

        lab, lcd = ab_cd._l
        lmn, lpq = mn_pq._l

        a, b = lab._obj.points
        c, d = lcd._obj.points
        m, n = lmn._obj.points
        p, q = lpq._obj.points

        to_cache = []

        deps1 = None
        eqratio = Statement(Predicate.EQRATIO, [a, b, c, d, m, n, p, q])
        if deps:
            deps1 = deps.populate(eqratio)
            deps1.algebra = [ab._val, cd._val, mn._val, pq._val]
        if not is_equal(ab_cd, mn_pq):
            add += [deps1]
        to_cache.append((eqratio, deps1))
        self.make_equal(ab_cd, mn_pq, deps=deps1)

        deps2 = None
        eqratio_sym = Statement(Predicate.EQRATIO, [c, d, a, b, p, q, m, n])
        if deps:
            deps2 = deps.populate(eqratio_sym)
            deps2.algebra = [cd._val, ab._val, pq._val, mn._val]
        if not is_equal(cd_ab, pq_mn):
            add += [deps2]
        to_cache.append((eqratio_sym, deps2))
        self.make_equal(cd_ab, pq_mn, deps=deps2)
        return add, to_cache

    def _add_simtri_check(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        if nm.same_clock(*[p.num for p in points]):
            return self._add_simtri(points, deps)
        return self._add_simtri_reflect(points, deps)

    def _add_contri_check(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        if nm.same_clock(*[p.num for p in points]):
            return self._add_contri(points, deps)
        return self._add_contri_reflect(points, deps)

    def _add_simtri(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add two similar triangles."""
        add, to_cache = [], []
        hashs = [dep.statement.hash_tuple for dep in deps.why]

        for args in comb.enum_triangle(points):
            eqangle6 = Statement(Predicate.EQANGLE6, args)
            if eqangle6.hash_tuple in hashs:
                continue
            _add, _to_cache = self._add_eqangle(args, deps=deps)
            add += _add
            to_cache += _to_cache

        for args in comb.enum_triangle(points):
            eqratio6 = Statement(Predicate.EQRATIO6, args)
            if eqratio6.hash_tuple in hashs:
                continue
            _add, _to_cache = self._add_eqratio(args, deps=deps)
            add += _add
            to_cache += _to_cache
        return add, to_cache

    def _add_simtri_reflect(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add two similar reflected triangles."""
        add, to_cache = [], []
        hashs = [dep.statement.hash_tuple for dep in deps.why]
        for args in comb.enum_triangle_reflect(points):
            eqangle6 = Statement(Predicate.EQANGLE6, args)
            if eqangle6.hash_tuple in hashs:
                continue
            _add, _to_cache = self._add_eqangle(args, deps=deps)
            add += _add
            to_cache += _to_cache

        for args in comb.enum_triangle(points):
            eqratio6 = Statement(Predicate.EQRATIO6, args)
            if eqratio6.hash_tuple in hashs:
                continue
            _add, _to_cache = self._add_eqratio(args, deps=deps)
            add += _add
            to_cache += _to_cache

        return add, to_cache

    def _add_contri(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add two congruent triangles."""
        add, to_cache = [], []
        hashs = [dep.statement.hash_tuple for dep in deps.why]
        for args in comb.enum_triangle(points):
            eqangle6 = Statement(Predicate.EQANGLE6, args)
            if eqangle6.hash_tuple in hashs:
                continue
            _add, _to_cache = self._add_eqangle(args, deps=deps)
            add += _add
            to_cache += _to_cache

        for args in comb.enum_sides(points):
            cong = Statement(Predicate.CONGRUENT, args)
            if cong.hash_tuple in hashs:
                continue
            _add, _to_cache = self._add_cong(args, deps=deps)
            add += _add
            to_cache += _to_cache
        return add, to_cache

    def _add_contri_reflect(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add two congruent reflected triangles."""
        add, to_cache = [], []
        hashs = [dep.statement.hash_tuple for dep in deps.why]
        for args in comb.enum_triangle_reflect(points):
            eqangle6 = Statement(Predicate.EQANGLE6, args)
            if eqangle6.hash_tuple in hashs:
                continue
            _add, _to_cache = self._add_eqangle(args, deps=deps)
            add += _add
            to_cache += _to_cache

        for args in comb.enum_sides(points):
            cong = Statement(Predicate.CONGRUENT, args)
            if cong.hash_tuple in hashs:
                continue
            _add, _to_cache = self._add_cong(args, deps=deps)
            add += _add
            to_cache += _to_cache

        return add, to_cache

    def _maybe_make_equal_pairs(
        self,
        a: Point,
        b: Point,
        c: Point,
        d: Point,
        m: Point,
        n: Point,
        p: Point,
        q: Point,
        ab: Line,
        cd: Line,
        mn: Line,
        pq: Line,
        deps: EmptyDependency,
    ) -> Optional[Tuple[list[Dependency], list[ToCache]]]:
        """Add ab/cd = mn/pq in case maybe either two of (ab,cd,mn,pq) are equal."""
        level = deps.level
        if is_equal(ab, cd, level):
            return self._make_equal_pairs(a, b, c, d, m, n, p, q, ab, cd, mn, pq, deps)
        elif is_equal(mn, pq, level):
            return self._make_equal_pairs(m, n, p, q, a, b, c, d, mn, pq, ab, cd, deps)
        elif is_equal(ab, mn, level):
            return self._make_equal_pairs(a, b, m, n, c, d, p, q, ab, mn, cd, pq, deps)
        elif is_equal(cd, pq, level):
            return self._make_equal_pairs(c, d, p, q, a, b, m, n, cd, pq, ab, mn, deps)
        else:
            return None

    def _make_equal_pairs(
        self,
        a: Point,
        b: Point,
        c: Point,
        d: Point,
        m: Point,
        n: Point,
        p: Point,
        q: Point,
        ab: Line,
        cd: Line,
        mn: Line,
        pq: Line,
        deps: EmptyDependency,
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add ab/cd = mn/pq in case either two of (ab,cd,mn,pq) are equal."""
        if isinstance(ab, Segment):
            dep_pred = Predicate.EQRATIO
            eq_pred = Predicate.CONGRUENT
            rule = IntrinsicRules.CONG_FROM_EQRATIO.value
        else:
            dep_pred = Predicate.EQANGLE
            eq_pred = Predicate.PARALLEL
            rule = IntrinsicRules.PARA_FROM_EQANGLE.value

        eq = Statement(dep_pred, [a, b, c, d, m, n, p, q])
        if ab != cd:
            dep0 = deps.populate(eq)
            deps = EmptyDependency(level=deps.level, rule_name=rule)

            because_eq = Statement(eq_pred, [a, b, c, d])
            dep = Dependency(because_eq, None, deps.level)
            dep.why = why_dependency(
                dep,
                self.symbols_graph,
                self.statements_checker,
                self.dependency_cache,
                None,
            )
            deps.why = [dep0, dep]

        elif eq_pred is Predicate.PARALLEL:  # ab == cd.
            colls = [a, b, c, d]
            if len(set(colls)) > 2:
                dep0 = deps.populate(eq)
                deps = EmptyDependency(level=deps.level, rule_name=rule)

                because_collx = Statement(Predicate.COLLINEAR_X, colls)
                dep = Dependency(because_collx, None, deps.level)
                dep.why = why_dependency(
                    dep,
                    self.symbols_graph,
                    self.statements_checker,
                    self.dependency_cache,
                    None,
                )
                deps.why = [dep0, dep]

        because_eq = Statement(eq_pred, [m, n, p, q])
        dep = deps.populate(because_eq)
        self.make_equal(mn, pq, deps=dep)

        dep.algebra = mn._val, pq._val
        to_cache = [(because_eq, dep)]

        if is_equal(mn, pq):
            return [], to_cache
        return [dep], to_cache

    def _add_aconst(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add that an angle is equal to some constant."""
        a, b, c, d, ang = points

        num, den = angle_to_num_den(ang)
        nd, dn = self.alegbraic_manipulator.get_or_create_const_ang(num, den)

        if nd == self.alegbraic_manipulator.halfpi:
            return self._add_perp([a, b, c, d], deps)

        ab, why1 = self.symbols_graph.get_line_thru_pair_why(a, b)
        cd, why2 = self.symbols_graph.get_line_thru_pair_why(c, d)

        (a, b), (c, d) = ab.points, cd.points
        if (
            why1 + why2
            and IntrinsicRules.ACONST_FROM_LINES not in self.DISABLED_INTRINSIC_RULES
        ):
            args = points[:-2] + [nd]
            aconst = Statement(Predicate.CONSTANT_ANGLE, tuple(args))
            dep0 = deps.populate(aconst)
            deps = EmptyDependency(
                level=deps.level, rule_name=IntrinsicRules.ACONST_FROM_LINES.value
            )
            deps.why = [dep0] + why1 + why2

        self.symbols_graph.get_node_val(ab, deps=None)
        self.symbols_graph.get_node_val(cd, deps=None)

        if ab.val == cd.val:
            raise ValueError(f"{ab.name} - {cd.name} cannot be {nd.name}")

        args = [a, b, c, d, nd]
        i = 0
        for x, y, xy in [(a, b, ab), (c, d, cd)]:
            i += 1
            x_, y_ = xy._val._obj.points
            if {x, y} == {x_, y_}:
                continue
            if deps:
                aconst = Statement(Predicate.CONSTANT_ANGLE, tuple(args))
                para = Statement(Predicate.PARALLEL, [x, y, x_, y_])
                deps = deps.extend(self, aconst, para)
            args[2 * i - 2] = x_
            args[2 * i - 1] = y_

        ab_cd, cd_ab, why = self.symbols_graph.get_or_create_angle_from_lines(
            ab, cd, deps=None
        )

        aconst = Statement(Predicate.CONSTANT_ANGLE, [a, b, c, d, nd])
        if (
            why
            and IntrinsicRules.ACONST_FROM_ANGLE not in self.DISABLED_INTRINSIC_RULES
        ):
            dep0 = deps.populate(aconst)
            deps = EmptyDependency(
                level=deps.level, rule_name=IntrinsicRules.ACONST_FROM_ANGLE.value
            )
            deps.why = [dep0] + why

        dab, dcd = ab_cd._d
        a, b = dab._obj.points
        c, d = dcd._obj.points

        ang = int(num) * 180 / int(den)
        add = []
        to_cache = []
        if not is_equal(ab_cd, nd):
            deps1 = deps.populate(aconst)
            deps1.algebra = dab, dcd, ang % 180
            self.make_equal(ab_cd, nd, deps=deps1)
            to_cache.append((aconst, deps1))
            add += [deps1]

        aconst2 = Statement(Predicate.CONSTANT_ANGLE, [a, b, c, d, nd])
        if not is_equal(cd_ab, dn):
            deps2 = deps.populate(aconst2)
            deps2.algebra = dcd, dab, 180 - ang % 180
            self.make_equal(cd_ab, dn, deps=deps2)
            to_cache.append((aconst2, deps2))
            add += [deps2]

        return add, to_cache

    def _add_s_angle(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add that an angle abx is equal to constant y."""
        a, b, x, angle = points
        num, den = angle_to_num_den(angle)
        ang = int(num * 180 / den) % 180
        nd, dn = self.alegbraic_manipulator.get_or_create_const_ang(num, den)

        if nd == self.alegbraic_manipulator.halfpi:
            return self._add_perp([a, b, b, x], deps)

        ab, why1 = self.symbols_graph.get_line_thru_pair_why(a, b)
        bx, why2 = self.symbols_graph.get_line_thru_pair_why(b, x)

        self.symbols_graph.get_node_val(ab, deps=None)
        self.symbols_graph.get_node_val(bx, deps=None)

        add, to_cache = [], []

        if ab.val == bx.val:
            return add, to_cache

        deps.why += why1 + why2

        for p, q, pq in [(a, b, ab), (b, x, bx)]:
            p_, q_ = pq.val._obj.points
            if {p, q} == {p_, q_}:
                continue
            para = Statement(Predicate.PARALLEL, [p, q, p_, q_])
            para_dep = Dependency(para, None, deps.level)
            para_dep.why = why_dependency(
                para_dep,
                self.symbols_graph,
                self.statements_checker,
                self.dependency_cache,
                None,
            )
            deps.why += [para_dep]

        xba, abx, why = self.symbols_graph.get_or_create_angle_from_lines(
            bx, ab, deps=None
        )
        if (
            why
            and IntrinsicRules.SANGLE_FROM_ANGLE not in self.DISABLED_INTRINSIC_RULES
        ):
            aconst = Statement(Predicate.CONSTANT_ANGLE, [b, x, a, b, nd])
            dep0 = deps.populate(aconst)
            deps = EmptyDependency(
                level=deps.level, rule_name=IntrinsicRules.SANGLE_FROM_ANGLE.value
            )
            deps.why = [dep0] + why

        dab, dbx = abx._d
        a, b = dab._obj.points
        c, x = dbx._obj.points

        if not is_equal(xba, nd):
            aconst = Statement(Predicate.S_ANGLE, [c, x, a, b, nd])
            deps1 = deps.populate(aconst)
            deps1.algebra = dbx, dab, ang

            self.make_equal(xba, nd, deps=deps1)
            to_cache.append((aconst, deps1))
            add += [deps1]

        if not is_equal(abx, dn):
            aconst2 = Statement(Predicate.S_ANGLE, [a, b, c, x, dn])
            deps2 = deps.populate(aconst2)
            deps2.algebra = dab, dbx, 180 - ang

            self.make_equal(abx, dn, deps=deps2)
            to_cache.append((aconst2, deps2))
            add += [deps2]

        return add, to_cache

    def _add_rconst(
        self, args: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add new algebraic predicates of type eqratio-constant."""
        a, b, c, d, ratio = args

        num, den = ratio_to_num_den(ratio)
        nd, dn = self.alegbraic_manipulator.get_or_create_const_rat(num, den)

        if num == den:
            return self._add_cong([a, b, c, d], deps)

        ab = self.symbols_graph.get_or_create_segment(a, b, deps=None)
        cd = self.symbols_graph.get_or_create_segment(c, d, deps=None)

        self.symbols_graph.get_node_val(ab, deps=None)
        self.symbols_graph.get_node_val(cd, deps=None)

        if ab.val == cd.val:
            raise ValueError(f"{ab.name} and {cd.name} cannot be equal")

        args = [a, b, c, d, nd]
        i = 0
        for x, y, xy in [(a, b, ab), (c, d, cd)]:
            i += 1
            x_, y_ = list(xy._val._obj.points)
            if {x, y} == {x_, y_}:
                continue
            if deps:
                rconst = Statement(Predicate.CONSTANT_RATIO, tuple(args))
                cong = Statement(Predicate.CONGRUENT, [x, y, x_, y_])
                deps = deps.extend(self, rconst, cong)
            args[2 * i - 2] = x_
            args[2 * i - 1] = y_

        ab_cd, cd_ab, why = self.symbols_graph.get_or_create_ratio_from_segments(
            ab, cd, deps=None
        )

        rconst = Statement(Predicate.CONSTANT_RATIO, [a, b, c, d, nd])
        if (
            why
            and IntrinsicRules.RCONST_FROM_RATIO not in self.DISABLED_INTRINSIC_RULES
        ):
            dep0 = deps.populate(rconst)
            deps = EmptyDependency(
                level=deps.level, rule_name=IntrinsicRules.RCONST_FROM_RATIO.value
            )
            deps.why = [dep0] + why

        lab, lcd = ab_cd._l
        a, b = list(lab._obj.points)
        c, d = list(lcd._obj.points)

        add = []
        to_cache = []
        if not is_equal(ab_cd, nd):
            dep1 = deps.populate(rconst)
            dep1.algebra = ab._val, cd._val, num, den
            self.make_equal(nd, ab_cd, deps=dep1)
            to_cache.append((rconst, dep1))
            add.append(dep1)

        if not is_equal(cd_ab, dn):
            rconst2 = Statement(Predicate.CONSTANT_RATIO, [c, d, a, b, dn])
            dep2 = deps.populate(rconst2)
            dep2.algebra = cd._val, ab._val, num, den
            self.make_equal(dn, cd_ab, deps=dep2)  # TODO FIX THAT
            to_cache.append((rconst2, dep2))
            add.append(dep2)

        return add, to_cache
