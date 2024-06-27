from __future__ import annotations
from typing import TYPE_CHECKING, Generator, Optional, TypeVar

from geosolver.combinatorics import cross_product, permutations_pairs
from geosolver.dependencies.dependency import Dependency, Reason

from geosolver.dependencies.why_predicates import (
    find_equal_pair,
    why_equal,
    why_maybe_make_equal_pairs,
)
from geosolver.geometry import (
    Angle,
    Direction,
    Length,
    Point,
    Ratio,
    RatioValue,
    Segment,
    bfs_backtrack,
)
from geosolver.intrinsic_rules import IntrinsicRules
from geosolver.numerical import close_enough
from geosolver.numerical.geometries import PointNum
from geosolver.predicates.predicate import Predicate

from geosolver.statement import (
    Statement,
    hash_two_times_two_unorded_lines,
)
from geosolver.symbols_graph import SymbolsGraph, is_equal, maybe_make_equal_pairs

import geosolver.predicates as preds


if TYPE_CHECKING:
    from geosolver.dependencies.dependency_building import DependencyBody
    from geosolver.dependencies.why_graph import DependencyGraph


T = TypeVar("T")


class EqRatio(Predicate):
    """eqratio AB CD EF GH -

    Represent that AB/CD=EF/GH, as ratios between lengths of segments.
    """

    NAME = "eqratio"

    @staticmethod
    def add(
        args: list[Point],
        dep_body: "DependencyBody",
        dep_graph: "DependencyGraph",
        symbols_graph: SymbolsGraph,
        disabled_intrinsic_rules: list[IntrinsicRules],
    ) -> tuple[list[Dependency], list[tuple[Statement, Dependency]]]:
        """Add a new eqratio from 8 points."""
        if dep_body:
            dep_body = dep_body.copy()
        a, b, c, d, m, n, p, q = args
        ab = symbols_graph.get_or_create_segment(a, b, deps=[])
        cd = symbols_graph.get_or_create_segment(c, d, deps=[])
        mn = symbols_graph.get_or_create_segment(m, n, deps=[])
        pq = symbols_graph.get_or_create_segment(p, q, deps=[])

        lines = (ab, cd, mn, pq)
        if IntrinsicRules.CONG_FROM_EQRATIO not in disabled_intrinsic_rules:
            add = maybe_make_equal_pairs(
                *args, *lines, dep_body, dep_graph, symbols_graph
            )
            if add is not None:
                return add

        symbols_graph.get_or_create_node_val(ab, deps=[])
        symbols_graph.get_or_create_node_val(cd, deps=[])
        symbols_graph.get_or_create_node_val(mn, deps=[])
        symbols_graph.get_or_create_node_val(pq, deps=[])

        add = []
        to_cache = []
        if (
            ab.val != cd.val
            and mn.val != pq.val
            and (ab.val != mn.val or cd.val != pq.val)
        ):
            points = (a, b, c, d, m, n, p, q)
            lines = (ab, cd, mn, pq)
            _add, _to_cache = EqRatio._add_eqratio8(
                *points,
                *lines,
                dep_body,
                dep_graph,
                symbols_graph,
                disabled_intrinsic_rules,
            )
            add += _add
            to_cache += _to_cache

        if (
            ab.val != mn.val
            and cd.val != pq.val
            and (ab.val != cd.val or mn.val != pq.val)
        ):
            points = (a, b, m, n, c, d, p, q)
            lines = (ab, mn, cd, pq)
            _add, _to_cache = EqRatio._add_eqratio8(
                *points,
                *lines,
                dep_body,
                dep_graph,
                symbols_graph,
                disabled_intrinsic_rules,
            )
            add += _add
            to_cache += _to_cache
        return add, to_cache

    @staticmethod
    def _add_eqratio8(
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
        dep_body: "DependencyBody",
        dep_graph: "DependencyGraph",
        symbols_graph: SymbolsGraph,
        disabled_intrinsic_rules: list[IntrinsicRules],
    ) -> tuple[list[Dependency], list[tuple["Statement", "Dependency"]]]:
        """Add a new eqratio from 8 points (core)."""
        if dep_body:
            dep_body = dep_body.copy()

        args = [a, b, c, d, m, n, p, q]
        i = 0
        for x, y, xy in [(a, b, ab), (c, d, cd), (m, n, mn), (p, q, pq)]:
            if {x, y} == set(xy.points):
                continue
            x_, y_ = list(xy.points)
            if (
                dep_body
                and IntrinsicRules.EQRATIO_FROM_CONG not in disabled_intrinsic_rules
            ):
                eqratio = Statement(EqRatio, tuple(args))
                cong = Statement(preds.Cong, [x, y, x_, y_])
                dep_body = dep_body.extend(
                    dep_graph,
                    eqratio,
                    cong,
                    extention_reason=Reason(IntrinsicRules.EQRATIO_FROM_CONG),
                )
            args[2 * i - 2] = x_
            args[2 * i - 1] = y_

        add = []
        ab_cd, cd_ab, why1 = symbols_graph.get_or_create_ratio_from_segments(
            ab, cd, deps=[]
        )
        mn_pq, pq_mn, why2 = symbols_graph.get_or_create_ratio_from_segments(
            mn, pq, deps=[]
        )

        if (
            IntrinsicRules.EQRATIO_FROM_PROPORTIONAL_SEGMENTS
            not in disabled_intrinsic_rules
        ):
            dep_body = dep_body.extend_by_why(
                dep_graph,
                Statement(EqRatio, tuple(args)),
                why=why1 + why2,
                extention_reason=Reason(
                    IntrinsicRules.EQRATIO_FROM_PROPORTIONAL_SEGMENTS
                ),
            )

        lab, lcd = ab_cd._l
        lmn, lpq = mn_pq._l

        a, b = lab._obj.points
        c, d = lcd._obj.points
        m, n = lmn._obj.points
        p, q = lpq._obj.points

        to_cache = []

        dep1 = None
        eqratio = Statement(EqRatio, [a, b, c, d, m, n, p, q])
        dep1 = dep_body.build(dep_graph, eqratio)
        if not is_equal(ab_cd, mn_pq):
            add += [dep1]
        to_cache.append((eqratio, dep1))
        symbols_graph.make_equal(ab_cd, mn_pq, dep=dep1)

        dep2 = None
        eqratio_sym = Statement(EqRatio, [c, d, a, b, p, q, m, n])
        dep2 = dep_body.build(dep_graph, eqratio_sym)
        if not is_equal(cd_ab, pq_mn):
            add += [dep2]
        to_cache.append((eqratio_sym, dep2))
        symbols_graph.make_equal(cd_ab, pq_mn, dep=dep2)
        return add, to_cache

    @staticmethod
    def why(
        dep_graph: "DependencyGraph", statement: Statement
    ) -> tuple[Optional[Reason], list[Dependency]]:
        a, b, c, d, m, n, p, q = statement.args
        ab = dep_graph.symbols_graph.get_segment(a, b)
        cd = dep_graph.symbols_graph.get_segment(c, d)
        mn = dep_graph.symbols_graph.get_segment(m, n)
        pq = dep_graph.symbols_graph.get_segment(p, q)

        why_eqratio = []
        if ab is None or cd is None or mn is None or pq is None:
            congruent_points = None
            if {a, b} == {m, n}:
                congruent_points = [c, d, p, q]
            elif {a, b} == {c, d}:
                congruent_points = [p, q, m, n]
            elif {c, d} == {p, q}:
                congruent_points = [a, b, m, n]
            elif {p, q} == {m, n}:
                congruent_points = [a, b, c, d]

            if congruent_points is not None:
                cong = Statement(preds.Cong, congruent_points)
                cong_dep = dep_graph.build_resolved_dependency(cong, use_cache=False)
                why_eqratio = [cong_dep]
            return None, why_eqratio

        if ab._val and cd._val and mn._val and pq._val:
            why_eqratio_from_directions = _why_eqratio_directions(
                dep_graph, ab._val, cd._val, mn._val, pq._val
            )
            if why_eqratio_from_directions:
                why_eqratio += why_eqratio_from_directions

        if (ab == cd and mn == pq) or (ab == mn and cd == pq):
            return None, []

        equal_pair_points, equal_pair_lines = find_equal_pair(
            a, b, c, d, m, n, p, q, ab, cd, mn, pq
        )
        if equal_pair_points is not None:
            why_eqratio += why_maybe_make_equal_pairs(
                dep_graph, *equal_pair_points, *equal_pair_lines
            )
            return None, why_eqratio

        if is_equal(ab, mn) or is_equal(cd, pq):
            cong1 = Statement(preds.Cong, [a, b, m, n])
            dep1 = dep_graph.build_resolved_dependency(cong1, use_cache=False)
            cong2 = Statement(preds.Cong, [c, d, p, q])
            dep2 = dep_graph.build_resolved_dependency(cong2, use_cache=False)
            why_eqratio += [dep1, dep2]
        elif is_equal(ab, cd) or is_equal(mn, pq):
            cong1 = Statement(preds.Cong, [a, b, c, d])
            dep1 = dep_graph.build_resolved_dependency(cong1, use_cache=False)
            cong2 = Statement(preds.Cong, [m, n, p, q])
            dep2 = dep_graph.build_resolved_dependency(cong2, use_cache=False)
            why_eqratio += [dep1, dep2]
        elif ab._val and cd._val and mn._val and pq._val:
            why_eqratio = _why_eqratio_directions(
                dep_graph, ab._val, cd._val, mn._val, pq._val
            )

        return None, why_eqratio

    @staticmethod
    def check(args: list[Point], symbols_graph: SymbolsGraph) -> bool:
        """Check if 8 points make an eqratio."""
        a, b, c, d, m, n, p, q = args

        if {a, b} == {c, d} and {m, n} == {p, q}:
            return True
        if {a, b} == {m, n} and {c, d} == {p, q}:
            return True

        ab = symbols_graph.get_segment(a, b)
        cd = symbols_graph.get_segment(c, d)
        mn = symbols_graph.get_segment(m, n)
        pq = symbols_graph.get_segment(p, q)

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

    @staticmethod
    def check_numerical(args: list[PointNum]) -> bool:
        a, b, c, d, e, f, g, h = args
        ab = a.distance(b)
        cd = c.distance(d)
        ef = e.distance(f)
        gh = g.distance(h)
        return close_enough(ab * gh, cd * ef)

    @staticmethod
    def enumerate(
        symbols_graph: SymbolsGraph,
    ) -> Generator[tuple[Point, ...], None, None]:
        """List all sets of 8 points that make two equal ratios."""
        ratss = []
        for value in symbols_graph.type2nodes[RatioValue]:
            rats = value.neighbors(Ratio)
            ratss.append(rats)

        # include the rats that do not have any val.
        ratss.extend(
            [[rat] for rat in symbols_graph.type2nodes[Ratio] if rat.val is None]
        )

        seg_pairss = []
        for rats in ratss:
            seg_pairs = set()
            for rat in rats:
                l1, l2 = rat.lengths
                if l1 is None or l2 is None:
                    continue
                s1s = l1.neighbors(Segment)
                s2s = l2.neighbors(Segment)
                seg_pairs.update(cross_product(s1s, s2s))
            seg_pairss.append(seg_pairs)

        # include (l1, l2) in which l1 does not have any ratio.
        norat_ls = [
            lenght
            for lenght in symbols_graph.type2nodes[Length]
            if not lenght.neighbors(Ratio)
        ]

        for l1 in norat_ls:
            for l2 in symbols_graph.type2nodes[Length]:
                if l1 == l2:
                    continue
                s1s = l1.neighbors(Segment)
                s2s = l2.neighbors(Segment)
                if len(s1s) < 2 and len(s2s) < 2:
                    continue
                seg_pairss.append(set(cross_product(s1s, s2s)))
                seg_pairss.append(set(cross_product(s2s, s1s)))

        # include Seg that does not have any Length.
        nolen_ss = [s for s in symbols_graph.type2nodes[Segment] if s.val is None]

        for seg in nolen_ss:
            for lenght in symbols_graph.type2nodes[Length]:
                s1s = lenght.neighbors(Segment)
                if len(s1s) == 1:
                    continue
                s2s = [seg]
                seg_pairss.append(set(cross_product(s1s, s2s)))
                seg_pairss.append(set(cross_product(s2s, s1s)))

        record = set()
        for seg_pairs in seg_pairss:
            for pair1, pair2 in permutations_pairs(list(seg_pairs)):
                (s1, s2), (s3, s4) = pair1, pair2
                if s1 == s2 or s3 == s4:
                    continue
                if (s1, s2) == (s3, s4):
                    continue
                if (s1, s2, s3, s4) in record:
                    continue
                record.add((s1, s2, s3, s4))
                a, b = s1.points
                c, d = s2.points
                e, f = s3.points
                g, h = s4.points

                for x, y in [(a, b), (b, a)]:
                    for z, t in [(c, d), (d, c)]:
                        for m, n in [(e, f), (f, e)]:
                            for p, q in [(g, h), (h, g)]:
                                yield (x, y, z, t, m, n, p, q)

        segss = []
        # finally the list of ratios that is equal to 1.0
        for length in symbols_graph.type2nodes[Length]:
            segs = length.neighbors(Segment)
            segss.append(tuple(segs))

        segs_pair = list(permutations_pairs(list(segss)))
        segs_pair += list(zip(segss, segss))
        for segs1, segs2 in segs_pair:
            for s1, s2 in permutations_pairs(list(segs1)):
                for s3, s4 in permutations_pairs(list(segs2)):
                    if (s1, s2) == (s3, s4) or (s1, s3) == (s2, s4):
                        continue
                    if (s1, s2, s3, s4) in record:
                        continue
                    record.add((s1, s2, s3, s4))
                    a, b = s1.points
                    c, d = s2.points
                    e, f = s3.points
                    g, h = s4.points

                    for x, y in [(a, b), (b, a)]:
                        for z, t in [(c, d), (d, c)]:
                            for m, n in [(e, f), (f, e)]:
                                for p, q in [(g, h), (h, g)]:
                                    yield (x, y, z, t, m, n, p, q)

    @staticmethod
    def pretty(args: list[str]) -> str:
        return _ratio_pretty(args)

    @classmethod
    def hash(cls, args: list[Point]) -> tuple[str, ...]:
        return hash_two_times_two_unorded_lines(cls.NAME, args)


class EqRatio6(EqRatio):
    """eqratio AB CD EF -"""

    NAME = "eqratio6"

    @classmethod
    def hash(cls, args: list[Point]) -> tuple[str, ...]:
        return EqRatio.hash(args)

    @staticmethod
    def enumerate(
        symbols_graph: SymbolsGraph,
    ) -> Generator[tuple[Point, ...], None, None]:
        """List all sets of 6 points that make two equal ratios."""
        record = set()
        for a, b, c, d, e, f, g, h in EqRatio.enumerate(symbols_graph):
            if (
                a not in (c, d)
                and b not in (c, d)
                or e not in (g, h)
                and f not in (g, h)
            ):
                continue
            if b in (c, d):
                a, b = b, a
            if f in (g, h):
                e, f = f, e
            if a == d:
                c, d = d, c
            if e == h:
                g, h = h, g
            if (a, b, c, d, e, f, g, h) in record:
                continue
            record.add((a, b, c, d, e, f, g, h))
            yield a, b, c, d, e, f, g, h  # now a==c, e==g


class EqRatio3(Predicate):
    """eqratio AB CD EF -

    Represent three eqratios through a list of 6 points (due to parallel lines).
    It can be viewed as in an instance of Thales theorem which has AB // MN // CD.

    It thus represent the corresponding eqratios:
    MA / MC = NB / ND and AM / AC = BN / BD and MC / AC = ND / BD

    ::

          a -- b
         m ---- n
        c ------ d


    """

    NAME = "eqratio3"

    @staticmethod
    def add(
        args: list[Point | Ratio | Angle],
        dep_body: "DependencyBody",
        dep_graph: "DependencyGraph",
        symbols_graph: SymbolsGraph,
        disabled_intrinsic_rules: list[IntrinsicRules],
    ) -> tuple[list[Dependency], list[tuple[Statement, Dependency]]]:
        """Add three eqratios through a list of 6 points (due to parallel lines)."""
        add, to_cache = [], []
        ratios = EqRatio3._list(args)
        for ratio_points in ratios:
            _add, _to_cache = EqRatio.add(
                ratio_points,
                dep_body,
                dep_graph,
                symbols_graph,
                disabled_intrinsic_rules,
            )
            add += _add
            to_cache += _to_cache

        statement = Statement(EqRatio3, tuple(args))
        dep = dep_graph.build_dependency(statement, dep_body)
        add.append(dep)
        to_cache.append((statement, dep))
        return add, to_cache

    @staticmethod
    def why(
        dep_graph: "DependencyGraph", statement: Statement
    ) -> tuple[Optional[Reason], list[Dependency]]:
        raise NotImplementedError

    @staticmethod
    def check(args: list[Point], symbols_graph: SymbolsGraph) -> bool:
        for ratio in EqRatio3._list(args):
            if not EqRatio.check(ratio, symbols_graph):
                return False
        return True

    @staticmethod
    def check_numerical(args: list[PointNum]) -> bool:
        for ratio in EqRatio3._list(args):
            if not EqRatio.check_numerical(ratio):
                return False
        return True

    @staticmethod
    def enumerate(
        symbols_graph: SymbolsGraph,
    ) -> Generator[tuple[Point, ...], None, None]:
        raise NotImplementedError

    @staticmethod
    def pretty(args: list[str]) -> str:
        return " & ".join(_ratio_pretty(ratio) for ratio in EqRatio3._list(args))

    @classmethod
    def hash(cls, args: list[Point]) -> tuple[str, ...]:
        a, b, c, d, o, o = args
        (a, c), (b, d) = sorted([(a, c), (b, d)], key=sorted)
        (a, b), (c, d) = sorted([(a, b), (c, d)], key=sorted)
        return (cls.NAME, a, b, c, d, o, o)

    @staticmethod
    def _list(points: list[T]) -> list[list[T]]:
        a, b, c, d, m, n = points
        ratios = [
            [m, a, m, c, n, b, n, d],
            [a, m, a, c, b, n, b, d],
            [c, m, c, a, d, n, d, b],
        ]
        if m == n:
            ratios.append([m, a, m, c, a, b, c, d])
        return ratios


def all_ratios(
    d1: Direction, d2: Direction
) -> Generator[Ratio, list[Direction], list[Direction]]:
    d1s = d1.equivs_upto()
    d2s = d2.equivs_upto()

    for ratio in d1.rep().neighbors(Ratio):
        d1_, d2_ = ratio._l
        if d1_ in d1s and d2_ in d2s:
            yield ratio, d1s, d2s


def _why_eqratio_directions(
    dep_graph: "DependencyGraph",
    d1: Direction,
    d2: Direction,
    d3: Direction,
    d4: Direction,
) -> Optional[list[Dependency]]:
    """Why two ratios are equal, returns a Dependency objects."""
    all12 = list(all_ratios(d1, d2))
    all34 = list(all_ratios(d3, d4))

    if not all12 or not all34:
        return None

    min_why = None
    for ang12, d1s, d2s in all12:
        for ang34, d3s, d4s in all34:
            why0 = why_equal(ang12, ang34)
            if why0 is None:
                continue
            d1_, d2_ = ang12._l
            d3_, d4_ = ang34._l
            why1 = bfs_backtrack(d1, [d1_], d1s)
            why2 = bfs_backtrack(d2, [d2_], d2s)
            why3 = bfs_backtrack(d3, [d3_], d3s)
            why4 = bfs_backtrack(d4, [d4_], d4s)
            why = why0 + why1 + why2 + why3 + why4
            if min_why is None or len(why) < len(min_why[0]):
                min_why = why, ang12, ang34, why0, why1, why2, why3, why4

    _, ang12, ang34, why0, why1, why2, why3, why4 = min_why
    d1_, d2_ = ang12._l
    d3_, d4_ = ang34._l

    if d1 == d1_ and d2 == d2_ and d3 == d3_ and d4 == d4_:
        return why0

    (a_, b_), (c_, d_) = d1_._obj.points, d2_._obj.points
    (e_, f_), (g_, h_) = d3_._obj.points, d4_._obj.points
    deps = []
    if why0:
        eqratio = Statement(EqRatio, [a_, b_, c_, d_, e_, f_, g_, h_])
        deps.append(
            dep_graph.build_dependency_from_statement(
                eqratio, why=why0, reason=Reason("")
            )
        )

    (a, b), (c, d) = d1._obj.points, d2._obj.points
    (e, f), (g, h) = d3._obj.points, d4._obj.points
    for why, (x, y), (x_, y_) in zip(
        [why1, why2, why3, why4],
        [(a, b), (c, d), (e, f), (g, h)],
        [(a_, b_), (c_, d_), (e_, f_), (g_, h_)],
    ):
        if not why:
            continue
        cong = Statement(preds.Cong, [x, y, x_, y_])
        deps.append(
            dep_graph.build_dependency_from_statement(cong, why=why, reason=Reason(""))
        )

    return deps


def _ratio_pretty(args: list[str]):
    return "{}{}:{}{} = {}{}:{}{}".format(*args)
