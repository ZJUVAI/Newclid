from __future__ import annotations
from typing import Generator
from typing_extensions import Self

from geosolver.combinatorics import all_4points, permutations_pairs
from geosolver.dependencies.dependency import Dependency, Reason
from geosolver.dependencies.dependency_building import DependencyBody
from geosolver.dependencies.why_graph import WhyHyperGraph

from geosolver.geometry import Direction, Line, Point
from geosolver.intrinsic_rules import IntrinsicRules
from geosolver.numerical.geometries import LineNum, PointNum
from geosolver.predicates.predicate import Predicate
from geosolver.statements.statement import Statement, hashed_unordered_two_lines_points

from geosolver.dependencies.why_predicates import why_equal
from geosolver.symbols_graph import SymbolsGraph, is_equal

import geosolver.predicates as preds


class Para(Predicate):
    """para A B C D -
    Represent that the line AB is parallel to the line CD.
    """

    NAME = "para"

    @staticmethod
    def add(
        args: list[Point],
        dep_body: DependencyBody,
        dep_graph: WhyHyperGraph,
        symbols_graph: SymbolsGraph,
        disabled_intrinsic_rules: list[IntrinsicRules],
    ) -> tuple[list[Dependency], list[tuple[Statement, Dependency]]]:
        """Add a new statement that 4 points (2 lines) are parallel."""
        a, b, c, d = args
        ab, why1 = symbols_graph.get_line_thru_pair_why(a, b)
        cd, why2 = symbols_graph.get_line_thru_pair_why(c, d)

        (a, b), (c, d) = ab.points, cd.points

        if IntrinsicRules.PARA_FROM_LINES not in disabled_intrinsic_rules:
            dep_body = dep_body.extend_by_why(
                dep_graph,
                Statement(Para.NAME, args),
                why=why1 + why2,
                extention_reason=Reason(IntrinsicRules.PARA_FROM_LINES),
            )

        para = Statement(Para.NAME, (a, b, c, d))
        dep = dep_body.build(dep_graph, para)
        to_cache = [(para, dep)]

        symbols_graph.make_equal(ab, cd, dep)
        if not is_equal(ab, cd):
            return [dep], to_cache
        return [], to_cache

    @staticmethod
    def why(
        statements_graph: WhyHyperGraph, statement: Statement
    ) -> tuple[Reason | None, list[Dependency]]:
        a, b, c, d = statement.args

        if {a, b} == {c, d}:
            return []

        ab = statements_graph.symbols_graph.get_line(a, b)
        cd = statements_graph.symbols_graph.get_line(c, d)
        if ab == cd:
            if {a, b} == {c, d}:
                return None, []

            coll = Statement(preds.Coll.NAME, list({a, b, c, d}))
            coll_dep = statements_graph.build_resolved_dependency(coll, use_cache=False)
            return None, [coll_dep]

        whypara = []
        for (x, y), xy in zip([(a, b), (c, d)], [ab, cd]):
            x_, y_ = xy.points
            if {x, y} == {x_, y_}:
                continue
            collx = Statement(preds.Coll.NAME, [x, y, x_, y_])
            collx_dep = statements_graph.build_resolved_dependency(
                collx, use_cache=False
            )
            whypara.append(collx_dep)

        return None, whypara + why_equal(ab, cd)

    @staticmethod
    def check(args: list[Point], symbols_graph: SymbolsGraph) -> bool:
        a, b, c, d = args
        if (a == b) or (c == d):
            return False
        ab = symbols_graph.get_line(a, b)
        cd = symbols_graph.get_line(c, d)
        if not ab or not cd:
            return False

        return is_equal(ab, cd)

    @staticmethod
    def check_numerical(args: list[PointNum]) -> bool:
        if preds.Coll.check_numerical(args):
            return True

        a, b, c, d = args
        ab = LineNum(a, b)
        cd = LineNum(c, d)
        if ab.same(cd):
            return False
        return ab.is_parallel(cd)

    @staticmethod
    def enumerate(
        symbols_graph: SymbolsGraph,
    ) -> Generator[tuple[Point, ...], None, None]:
        for d in symbols_graph.type2nodes[Direction]:
            for l1, l2 in permutations_pairs(d.neighbors(Line)):
                for a, b, c, d in all_4points(l1, l2):
                    yield a, b, c, d

    @staticmethod
    def pretty(args: list[str]) -> str:
        if len(args) == 2:  # this is algebraic derivation.
            ab, cd = args  # ab = 'd( ... )'
            return f"{ab} \u2225 {cd}"
        a, b, c, d = args
        return f"{a}{b} \u2225 {c}{d}"

    @classmethod
    def hash(cls: Self, args: list[Point]) -> tuple[str]:
        return hashed_unordered_two_lines_points(cls.NAME, args)
