from __future__ import annotations
from typing import TYPE_CHECKING, Generator, Optional
from typing_extensions import Self

from geosolver.combinatorics import permutations_pairs
from geosolver.dependencies.dependency import Reason, Dependency


from geosolver.dependencies.why_predicates import why_equal
from geosolver.numerical import close_enough
from geosolver.numerical.geometries import PointNum
from geosolver.predicates.predicate import Predicate
from geosolver.intrinsic_rules import IntrinsicRules

from geosolver.geometry import Length, Point, Segment
from geosolver.statements.statement import Statement, hashed_unordered_two_lines_points
from geosolver.symbols_graph import SymbolsGraph, is_equal

import geosolver.predicates as preds

if TYPE_CHECKING:
    from geosolver.dependencies.why_graph import WhyHyperGraph
    from geosolver.dependencies.dependency_building import DependencyBody


class Cong(Predicate):
    """cong A B C D -
    Represent that segments AB and CD are congruent."""

    NAME = "cong"

    @staticmethod
    def add(
        args: list[Point],
        dep_body: DependencyBody,
        dep_graph: WhyHyperGraph,
        symbols_graph: SymbolsGraph,
        disabled_intrinsic_rules: list[IntrinsicRules],
    ) -> tuple[list[Dependency], list[tuple[Statement, Dependency]]]:
        """Add that two segments (4 points) are congruent."""
        a, b, c, d = args
        ab = symbols_graph.get_or_create_segment(a, b, None)
        cd = symbols_graph.get_or_create_segment(c, d, None)

        cong = Statement(Cong.NAME, [a, b, c, d])
        cong_dep = dep_body.build(dep_graph, cong)
        symbols_graph.make_equal(ab, cd, dep=cong_dep)

        to_cache = [(cong, cong_dep)]
        added = []

        if not is_equal(ab, cd):
            added += [cong_dep]

        if IntrinsicRules.CYCLIC_FROM_CONG in disabled_intrinsic_rules or (
            a not in [c, d] and b not in [c, d]
        ):
            return added, to_cache

        # Make a=c if possible
        if b in [c, d]:
            a, b = b, a
        if a == d:
            c, d = d, c

        cyclic_deps, cyclic_cache = Cong._maybe_add_cyclic_from_cong(
            a, b, d, cong_dep, symbols_graph
        )
        added += cyclic_deps
        to_cache += cyclic_cache
        return added, to_cache

    @staticmethod
    def _maybe_add_cyclic_from_cong(
        a: Point,
        b: Point,
        c: Point,
        cong_ab_ac: Dependency,
        dep_graph: WhyHyperGraph,
        symbols_graph: SymbolsGraph,
        disabled_intrinsic_rules: list[IntrinsicRules],
    ) -> tuple[list[Dependency], list[tuple[Statement, Dependency]]]:
        """Maybe add a new cyclic predicate from given congruent segments."""
        ab = symbols_graph.get_or_create_segment(a, b, None)

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

        if preds.Cyclic.check([b, c, x, y], symbols_graph):
            return [], []

        ax = symbols_graph.get_or_create_segment(a, x, dep=None)
        ay = symbols_graph.get_or_create_segment(a, y, dep=None)
        why = ab._val.why_equal([ax._val, ay._val])
        why += [cong_ab_ac]

        dep_body = DependencyBody(Reason(IntrinsicRules.CYCLIC_FROM_CONG), why=why)
        return preds.Cyclic.add(
            [b, c, x, y], dep_body, dep_graph, symbols_graph, disabled_intrinsic_rules
        )

    @staticmethod
    def why(
        statements_graph: "WhyHyperGraph", statement: "Statement"
    ) -> tuple[Optional[Reason], list[Dependency]]:
        a, b, c, d = statement.args
        ab = statements_graph.symbols_graph.get_segment(a, b)
        cd = statements_graph.symbols_graph.get_segment(c, d)
        return None, why_equal(ab, cd)

    @staticmethod
    def check(args: list[Point], symbols_graph: SymbolsGraph) -> bool:
        a, b, c, d = args
        if {a, b} == {c, d}:
            return True

        ab = symbols_graph.get_segment(a, b)
        cd = symbols_graph.get_segment(c, d)
        if ab is None or cd is None:
            return False
        return is_equal(ab, cd)

    @staticmethod
    def check_numerical(args: list[PointNum]) -> bool:
        a, b, c, d = args
        return close_enough(a.distance(b), c.distance(d))

    @staticmethod
    def enumerate(
        symbols_graph: SymbolsGraph,
    ) -> Generator[tuple[Point, ...], None, None]:
        for lenght in symbols_graph.type2nodes[Length]:
            for s1, s2 in permutations_pairs(lenght.neighbors(Segment)):
                (a, b), (c, d) = s1.points, s2.points
                for x, y in [(a, b), (b, a)]:
                    for m, n in [(c, d), (d, c)]:
                        yield x, y, m, n

    @staticmethod
    def pretty(args: list[str]) -> str:
        a, b, c, d = args
        return f"{a}{b} = {c}{d}"

    @classmethod
    def hash(cls: Self, args: list[Point]) -> tuple[str, ...]:
        return hashed_unordered_two_lines_points(cls.NAME, args)


class Cong2(Predicate):
    NAME = "cong2"

    def add(
        self,
        points: list[Point],
        dep_body: DependencyBody,
        dep_graph: WhyHyperGraph,
        symbols_graph: SymbolsGraph,
        disabled_intrinsic_rules: list[IntrinsicRules],
    ) -> tuple[list[Dependency], list[tuple[Statement, Dependency]]]:
        m, n, a, b = points
        add, to_cache = Cong.add(
            [m, a, n, a], dep_body, dep_graph, symbols_graph, disabled_intrinsic_rules
        )
        _add, _to_cache = Cong.add(
            [m, b, n, b], dep_body, dep_graph, symbols_graph, disabled_intrinsic_rules
        )
        return add + _add, to_cache + _to_cache

    @staticmethod
    def why(
        statements_graph: WhyHyperGraph, statement: Statement
    ) -> tuple[Reason | None, list[Dependency]]:
        raise NotImplementedError

    @staticmethod
    def check(args: list[Point], symbols_graph: SymbolsGraph) -> bool:
        raise NotImplementedError

    @staticmethod
    def check_numerical(args: list[PointNum]) -> bool:
        raise NotImplementedError

    @staticmethod
    def enumerate(
        symbols_graph: SymbolsGraph,
    ) -> Generator[tuple[Point, ...], None, None]:
        raise NotImplementedError

    @staticmethod
    def pretty(args: list[str]) -> str:
        raise NotImplementedError

    @classmethod
    def hash(cls: Self, args: list[Point]) -> tuple[str, ...]:
        return Cong.hash(args)
