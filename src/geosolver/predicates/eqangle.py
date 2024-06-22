from __future__ import annotations
from typing import TYPE_CHECKING, Generator, Optional
from typing_extensions import Self

from geosolver.combinatorics import all_8points, cross_product, permutations_pairs
from geosolver.dependencies.dependency import Dependency, Reason

from geosolver.dependencies.why_predicates import (
    find_equal_pair,
    why_equal,
    why_maybe_make_equal_pairs,
)
from geosolver.geometry import (
    Angle,
    AngleValue,
    Direction,
    Line,
    Point,
    bfs_backtrack,
)
from geosolver.intrinsic_rules import IntrinsicRules
from geosolver.numerical import close_enough
from geosolver.numerical.geometries import LineNum, PointNum, bring_together
import geosolver.predicates.coll
from geosolver.predicates.predicate import Predicate
from geosolver.pretty_angle import pretty_angle
from geosolver.statements.adder import ToCache, maybe_make_equal_pairs
from geosolver.statements.statement import Statement, hash_two_times_two_unorded_lines
from geosolver.symbols_graph import SymbolsGraph, is_equal

import geosolver.predicates as preds

from geosolver._lazy_loading import lazy_import


if TYPE_CHECKING:
    from geosolver.dependencies.dependency_building import DependencyBody
    from geosolver.dependencies.why_graph import WhyHyperGraph

    import numpy

np: "numpy" = lazy_import("numpy")


def all_angles(
    d1: Direction, d2: Direction
) -> Generator[Angle, list[Direction], list[Direction]]:
    d1s = d1.equivs_upto()
    d2s = d2.equivs_upto()

    for angle in d1.rep().neighbors(Angle):
        d1_, d2_ = angle._d
        if d1_ in d1s and d2_ in d2s:
            yield angle, d1s, d2s


class EqAngle(Predicate):
    """eqangle AB CD EF GH -
    Represent that one can rigidly move the crossing of lines AB and CD
    to get on top of the crossing of EF and GH, respectively (no reflections allowed).

    In particular, eqangle AB CD CD AB is only true if AB is perpendicular to CD.
    """

    NAME = "eqangle"

    @staticmethod
    def add(
        args: list[Point],
        dep_body: "DependencyBody",
        dep_graph: "WhyHyperGraph",
        symbols_graph: SymbolsGraph,
        disabled_intrinsic_rules: list[IntrinsicRules],
    ) -> tuple[list[Dependency], list[tuple[Statement, Dependency]]]:
        """Add eqangle made by 8 points."""
        if dep_body:
            dep_body = dep_body.copy()
        a, b, c, d, m, n, p, q = args
        ab, why1 = symbols_graph.get_line_thru_pair_why(a, b)
        cd, why2 = symbols_graph.get_line_thru_pair_why(c, d)
        mn, why3 = symbols_graph.get_line_thru_pair_why(m, n)
        pq, why4 = symbols_graph.get_line_thru_pair_why(p, q)

        a, b = ab.points
        c, d = cd.points
        m, n = mn.points
        p, q = pq.points

        if IntrinsicRules.EQANGLE_FROM_LINES not in disabled_intrinsic_rules:
            eqangle = Statement(EqAngle.NAME, args)
            dep_body = dep_body.extend_by_why(
                dep_graph,
                eqangle,
                why=why1 + why2 + why3 + why4,
                extention_reason=Reason(IntrinsicRules.EQANGLE_FROM_LINES),
            )

        if IntrinsicRules.PARA_FROM_EQANGLE not in disabled_intrinsic_rules:
            points = (a, b, c, d, m, n, p, q)
            lines = (ab, cd, mn, pq)
            maybe_pairs = maybe_make_equal_pairs(
                *points, *lines, dep_body, dep_graph, symbols_graph
            )
            if maybe_pairs is not None:
                return maybe_pairs

        symbols_graph.get_node_val(ab, dep=None)
        symbols_graph.get_node_val(cd, dep=None)
        symbols_graph.get_node_val(mn, dep=None)
        symbols_graph.get_node_val(pq, dep=None)

        add, to_cache = [], []

        if (
            ab.val != cd.val
            and mn.val != pq.val
            and (ab.val != mn.val or cd.val != pq.val)
        ):
            _add, _to_cache = EqAngle._add_eqangle8(
                a, b, c, d, m, n, p, q, ab, cd, mn, pq, dep_body
            )
            add += _add
            to_cache += _to_cache

        if (
            ab.val != mn.val
            and cd.val != pq.val
            and (ab.val != cd.val or mn.val != pq.val)
        ):
            _add, _to_cache = EqAngle._add_eqangle8(
                a, b, m, n, c, d, p, q, ab, mn, cd, pq, dep_body
            )
            add += _add
            to_cache += _to_cache

        return add, to_cache

    @staticmethod
    def _add_eqangle8(
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
        dep_body: DependencyBody,
        dep_graph: "WhyHyperGraph",
        symbols_graph: SymbolsGraph,
        disabled_intrinsic_rules: list[IntrinsicRules],
    ) -> tuple[list[Dependency], list[ToCache]]:
        """Add eqangle core."""
        if dep_body:
            dep_body = dep_body.copy()

        args = [a, b, c, d, m, n, p, q]
        i = 0
        for x, y, xy in [(a, b, ab), (c, d, cd), (m, n, mn), (p, q, pq)]:
            i += 1
            x_, y_ = xy._val._obj.points
            if {x, y} == {x_, y_}:
                continue
            if (
                dep_body
                and IntrinsicRules.EQANGLE_FROM_PARA not in disabled_intrinsic_rules
            ):
                eqangle = Statement(EqAngle.NAME, tuple(args))
                para = Statement(preds.Para.NAME, [x, y, x_, y_])
                dep_body = dep_body.extend(
                    dep_graph,
                    eqangle,
                    para,
                    extention_reason=Reason(IntrinsicRules.EQANGLE_FROM_PARA),
                )
                args[2 * i - 2] = x_
                args[2 * i - 1] = y_

        ab_cd, cd_ab, why1 = symbols_graph.get_or_create_angle_from_lines(
            ab, cd, dep=None
        )
        mn_pq, pq_mn, why2 = symbols_graph.get_or_create_angle_from_lines(
            mn, pq, dep=None
        )

        if IntrinsicRules.EQANGLE_FROM_CONGRUENT_ANGLE not in disabled_intrinsic_rules:
            eqangle = Statement(EqAngle.NAME, args)
            dep_body = dep_body.extend_by_why(
                dep_graph,
                eqangle,
                why=why1 + why2,
                extention_reason=Reason(IntrinsicRules.EQANGLE_FROM_CONGRUENT_ANGLE),
            )

        dab, dcd = ab_cd._d
        dmn, dpq = mn_pq._d

        a, b = dab._obj.points
        c, d = dcd._obj.points
        m, n = dmn._obj.points
        p, q = dpq._obj.points

        add = []
        to_cache = []

        dep1 = None
        eqangle = Statement(EqAngle.NAME, [a, b, c, d, m, n, p, q])
        if dep_body:
            dep1 = dep_body.build(dep_graph, eqangle)
        if not is_equal(ab_cd, mn_pq):
            add += [dep1]
        to_cache.append((eqangle, dep1))
        symbols_graph.make_equal(ab_cd, mn_pq, dep=dep1)

        dep2 = None
        eqangle_sym = Statement(EqAngle.NAME, [c, d, a, b, p, q, m, n])
        if dep_body:
            dep2 = dep_body.build(dep_graph, eqangle_sym)
        if not is_equal(cd_ab, pq_mn):
            add += [dep2]
        to_cache.append((eqangle_sym, dep2))
        symbols_graph.make_equal(cd_ab, pq_mn, dep=dep2)

        return add, to_cache

    @staticmethod
    def why(
        statements_graph: "WhyHyperGraph", statement: Statement
    ) -> tuple[Optional[Reason], list[Dependency]]:
        a, b, c, d, m, n, p, q = statement.args

        ab, why1 = statements_graph.symbols_graph.get_line_thru_pair_why(a, b)
        cd, why2 = statements_graph.symbols_graph.get_line_thru_pair_why(c, d)
        mn, why3 = statements_graph.symbols_graph.get_line_thru_pair_why(m, n)
        pq, why4 = statements_graph.symbols_graph.get_line_thru_pair_why(p, q)

        if ab is None or cd is None or mn is None or pq is None:
            para_points = None
            if {a, b} == {m, n}:
                para_points = [c, d, p, q]
            elif {a, b} == {c, d}:
                para_points = [p, q, m, n]
            elif {c, d} == {p, q}:
                para_points = [a, b, m, n]
            elif {p, q} == {m, n}:
                para_points = [a, b, c, d]
            para = Statement(preds.Para.NAME, para_points)
            para_dep = statements_graph.build_resolved_dependency(para, use_cache=False)
            return None, [para_dep]

        why_eqangle = []
        for (x, y), xy, whyxy in zip(
            [(a, b), (c, d), (m, n), (p, q)],
            [ab, cd, mn, pq],
            [why1, why2, why3, why4],
        ):
            x_, y_ = xy.points
            if {x, y} == {x_, y_}:
                continue
            collx = Statement(geosolver.predicates.coll.Collx.NAME, [x, y, x_, y_])
            collx_dep = statements_graph.build_dependency_from_statement(
                collx, why=whyxy, reason=Reason("_why_eqangle_collx")
            )
            why_eqangle.append(collx_dep)

        a, b = ab.points
        c, d = cd.points
        m, n = mn.points
        p, q = pq.points

        representent_statement = Statement(statement.name, [a, b, c, d, m, n, p, q])
        different_from_repr = representent_statement.hash_tuple != statement.hash_tuple

        why_eqangle_values = None
        if ab._val and cd._val and mn._val and pq._val:
            why_eqangle_values = why_eqangle_directions(
                statements_graph, ab._val, cd._val, mn._val, pq._val
            )

        if why_eqangle_values:
            if different_from_repr:
                eqangle = Statement(EqAngle.NAME, [a, b, c, d, m, n, p, q])
                eqangle_dep = statements_graph.build_dependency_from_statement(
                    eqangle,
                    why=why_eqangle_values,
                    reason=Reason("_why_eqangle_eqangle"),
                )
                why_eqangle_values = [eqangle_dep]
            return None, why_eqangle + why_eqangle_values

        if (ab == cd and mn == pq) or (ab == mn and cd == pq):
            return None, why_eqangle

        equal_pair_points, equal_pair_lines = find_equal_pair(
            a, b, c, d, m, n, p, q, ab, cd, mn, pq
        )
        if equal_pair_points is not None and equal_pair_lines is not None:
            why_eqangle += why_maybe_make_equal_pairs(
                statements_graph, *equal_pair_points, *equal_pair_lines
            )
            return None, why_eqangle

        if is_equal(ab, mn) or is_equal(cd, pq):
            para1 = Statement(preds.Para.NAME, [a, b, m, n])
            dep1 = statements_graph.build_resolved_dependency(para1, use_cache=False)
            para2 = Statement(preds.Para.NAME, [c, d, p, q])
            dep2 = statements_graph.build_resolved_dependency(para2, use_cache=False)
            why_eqangle += [dep1, dep2]

        elif is_equal(ab, cd) or is_equal(mn, pq):
            para1 = Statement(preds.Para.NAME, [a, b, c, d])
            dep1 = statements_graph.build_resolved_dependency(para1, use_cache=False)
            para2 = Statement(preds.Para.NAME, [m, n, p, q])
            dep2 = statements_graph.build_resolved_dependency(para2, use_cache=False)
            why_eqangle += [dep1, dep2]
        elif ab._val and cd._val and mn._val and pq._val:
            why_eqangle = why_eqangle_directions(
                statements_graph, ab._val, cd._val, mn._val, pq._val
            )

        return None, why_eqangle

    @staticmethod
    def check(args: list[Point], symbols_graph: SymbolsGraph) -> bool:
        """Check if two angles are equal."""
        a, b, c, d, m, n, p, q = args

        if {a, b} == {c, d} and {m, n} == {p, q}:
            return True
        if {a, b} == {m, n} and {c, d} == {p, q}:
            return True

        if (a == b) or (c == d) or (m == n) or (p == q):
            return False
        ab = symbols_graph.get_line(a, b)
        cd = symbols_graph.get_line(c, d)
        mn = symbols_graph.get_line(m, n)
        pq = symbols_graph.get_line(p, q)

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

        if preds.Perp.check([a, b, m, n], symbols_graph) and preds.Perp.check(
            [c, d, p, q], symbols_graph
        ):
            return True
        if preds.Perp.check([a, b, p, q], symbols_graph) and preds.Perp.check(
            [c, d, m, n], symbols_graph
        ):
            return True

        return False

    @staticmethod
    def check_numerical(args: list[PointNum]) -> bool:
        """Check if 8 points make 2 equal angles."""
        a, b, c, d, e, f, g, h = args

        ab = LineNum(a, b)
        cd = LineNum(c, d)
        ef = LineNum(e, f)
        gh = LineNum(g, h)

        if ab.is_parallel(cd):
            return ef.is_parallel(gh)
        if ef.is_parallel(gh):
            return ab.is_parallel(cd)

        a, b, c, d = bring_together(a, b, c, d)
        e, f, g, h = bring_together(e, f, g, h)

        ba = b - a
        dc = d - c
        fe = f - e
        hg = h - g

        sameclock = (ba.x * dc.y - ba.y * dc.x) * (fe.x * hg.y - fe.y * hg.x) > 0
        # sameclock = (ba.x * dc.y - ba.y * dc.x) * (fe.x * hg.y - fe.y * hg.x) > ATOM
        if not sameclock:
            ba = ba * -1.0

        a1 = np.arctan2(fe.y, fe.x)
        a2 = np.arctan2(hg.y, hg.x)
        x = a1 - a2

        a3 = np.arctan2(ba.y, ba.x)
        a4 = np.arctan2(dc.y, dc.x)
        y = a3 - a4

        xy = (x - y) % (2 * np.pi)
        return close_enough(xy, 0) or close_enough(xy, 2 * np.pi)

    @staticmethod
    def enumerate(
        symbols_graph: SymbolsGraph,
    ) -> Generator[tuple[Point, ...], None, None]:
        """List all sets of 8 points that make two equal angles."""
        # Case 1: (l1-l2) = (l3-l4), including because l1//l3, l2//l4 (para-para)
        angss = []
        for measure in symbols_graph.type2nodes[AngleValue]:
            angs = measure.neighbors(Angle)
            angss.append(angs)

        # include the angs that do not have any measure.
        angss.extend(
            [[ang] for ang in symbols_graph.type2nodes[Angle] if ang.val is None]
        )

        line_pairss = []
        for angs in angss:
            line_pairs = set()
            for ang in angs:
                d1, d2 = ang.directions
                if d1 is None or d2 is None:
                    continue
                l1s = d1.neighbors(Line)
                l2s = d2.neighbors(Line)
                line_pairs.update(set(cross_product(l1s, l2s)))
            line_pairss.append(line_pairs)

        # include (d1, d2) in which d1 does not have any angles.
        noang_ds = [
            d for d in symbols_graph.type2nodes[Direction] if not d.neighbors(Angle)
        ]

        for d1 in noang_ds:
            for d2 in symbols_graph.type2nodes[Direction]:
                if d1 == d2:
                    continue
                l1s = d1.neighbors(Line)
                l2s = d2.neighbors(Line)
                if len(l1s) < 2 and len(l2s) < 2:
                    continue
                line_pairss.append(set(cross_product(l1s, l2s)))
                line_pairss.append(set(cross_product(l2s, l1s)))

        # Case 2: d1 // d2 => (d1-d3) = (d2-d3)
        # include lines that does not have any direction.
        nodir_ls = [line for line in symbols_graph.type2nodes[Line] if line.val is None]

        for line in nodir_ls:
            for d in symbols_graph.type2nodes[Direction]:
                l1s = d.neighbors(Line)
                if len(l1s) < 2:
                    continue
                l2s = [line]
                line_pairss.append(set(cross_product(l1s, l2s)))
                line_pairss.append(set(cross_product(l2s, l1s)))

        record = set()
        for line_pairs in line_pairss:
            for pair1, pair2 in permutations_pairs(list(line_pairs)):
                (l1, l2), (l3, l4) = pair1, pair2
                if l1 == l2 or l3 == l4:
                    continue
                if (l1, l2) == (l3, l4):
                    continue
                if (l1, l2, l3, l4) in record:
                    continue
                record.add((l1, l2, l3, l4))
                for a, b, c, d, e, f, g, h in all_8points(l1, l2, l3, l4):
                    yield (a, b, c, d, e, f, g, h)

        for a, b, c, d, e, f, g, h in EqAngle._all_eqangle_same_lines(symbols_graph):
            yield a, b, c, d, e, f, g, h

    def _all_eqangle_same_lines(
        self, symbols_graph: SymbolsGraph
    ) -> Generator[tuple[Point, ...], None, None]:
        for l1, l2 in permutations_pairs(symbols_graph.type2nodes[Line]):
            for a, b, c, d, e, f, g, h in all_8points(l1, l2, l1, l2):
                if (a, b, c, d) != (e, f, g, h):
                    yield a, b, c, d, e, f, g, h

    @staticmethod
    def pretty(args: list[str]) -> str:
        a, b, c, d, e, f, g, h = args
        return f"{pretty_angle(a, b, c, d)} = {pretty_angle(e, f, g, h)}"

    @classmethod
    def hash(cls: Self, args: list[Point]) -> tuple[str, ...]:
        return hash_two_times_two_unorded_lines(cls.NAME, args)


class EqAngle6(EqAngle):
    """eqangle6 AB CD EF -"""

    NAME = "eqangle6"

    @staticmethod
    def enumerate(symbols_graph: SymbolsGraph) -> Generator[ToCache[Point], None, None]:
        """List all sets of 6 points that make two equal angles."""
        record = set()
        for a, b, c, d, e, f, g, h in EqAngle.enumerate(symbols_graph):
            if (
                a not in (c, d)
                and b not in (c, d)
                or e not in (g, h)
                and f not in (g, h)
            ):
                continue

            if b in (c, d):
                a, b = b, a  # now a in c, d
            if f in (g, h):
                e, f = f, e  # now e in g, h
            if a == d:
                c, d = d, c  # now a == c
            if e == h:
                g, h = h, g  # now e == g
            if (a, b, c, d, e, f, g, h) in record:
                continue
            record.add((a, b, c, d, e, f, g, h))
            yield a, b, c, d, e, f, g, h  # where a==c, e==g

    @classmethod
    def hash(cls: Self, args: list[Point]) -> tuple[str, ...]:
        return EqAngle.hash(args)


def why_eqangle_directions(
    statements_graph: "WhyHyperGraph",
    d1: Direction,
    d2: Direction,
    d3: Direction,
    d4: Direction,
) -> Optional[list[Dependency]]:
    """Why two angles are equal, returns a Dependency objects."""
    all12 = list(all_angles(d1, d2))
    all34 = list(all_angles(d3, d4))

    min_why = None
    for ang12, d1s, d2s in all12:
        for ang34, d3s, d4s in all34:
            why0 = why_equal(ang12, ang34)
            if why0 is None:
                continue
            d1_, d2_ = ang12._d
            d3_, d4_ = ang34._d
            why1 = bfs_backtrack(d1, [d1_], d1s)
            why2 = bfs_backtrack(d2, [d2_], d2s)
            why3 = bfs_backtrack(d3, [d3_], d3s)
            why4 = bfs_backtrack(d4, [d4_], d4s)
            why = why0 + why1 + why2 + why3 + why4
            if min_why is None or len(why) < len(min_why[0]):
                min_why = why, ang12, ang34, why0, why1, why2, why3, why4

    if min_why is None:
        return None

    _, ang12, ang34, why0, why1, why2, why3, why4 = min_why
    why0 = why_equal(ang12, ang34)
    d1_, d2_ = ang12._d
    d3_, d4_ = ang34._d

    if d1 == d1_ and d2 == d2_ and d3 == d3_ and d4 == d4_:
        return why0

    (a_, b_), (c_, d_) = d1_._obj.points, d2_._obj.points
    (e_, f_), (g_, h_) = d3_._obj.points, d4_._obj.points
    deps = []
    if why0:
        eqangle = Statement(EqAngle.NAME, [a_, b_, c_, d_, e_, f_, g_, h_])
        deps.append(
            statements_graph.build_dependency_from_statement(
                eqangle, why=why0, reason=Reason("")
            )
        )

    (a, b), (c, d) = d1._obj.points, d2._obj.points
    (e, f), (g, h) = d3._obj.points, d4._obj.points
    for why, d_xy, (x, y), d_xy_, (x_, y_) in zip(
        [why1, why2, why3, why4],
        [d1, d2, d3, d4],
        [(a, b), (c, d), (e, f), (g, h)],
        [d1_, d2_, d3_, d4_],
        [(a_, b_), (c_, d_), (e_, f_), (g_, h_)],
    ):
        xy, xy_ = d_xy._obj, d_xy_._obj
        if why:
            if xy == xy_:
                predicate = geosolver.predicates.coll.Collx.NAME
            else:
                predicate = preds.Para.NAME
            because_statement = Statement(predicate, [x_, y_, x, y])
            deps.append(
                statements_graph.build_dependency_from_statement(
                    because_statement, why=why, reason=Reason("")
                )
            )

    return deps
