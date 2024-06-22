from __future__ import annotations
from typing import TYPE_CHECKING, Generator, Optional

from geosolver.dependencies.dependency import Reason, Dependency

from geosolver.dependencies.why_predicates import why_equal
from geosolver.numerical import close_enough
from geosolver.numerical.geometries import PointNum
from geosolver.predicates.predicate import Predicate
from geosolver.intrinsic_rules import IntrinsicRules

from geosolver.geometry import Angle, Line, Point, Ratio
from geosolver.combinatorics import permutations_triplets
from geosolver.statements.statement import Statement, hash_point_and_line
from geosolver.symbols_graph import SymbolsGraph

import geosolver.predicates as preds


if TYPE_CHECKING:
    from geosolver.dependencies.why_graph import DependencyGraph
    from geosolver.dependencies.dependency_building import DependencyBody


class MidPoint(Predicate):
    """midp M A B -
    Represent that M is the midpoint of the segment AB.

    Can be equivalent to coll M A B and cong A M B M."""

    NAME = "midp"

    @staticmethod
    def add(
        args: list[Point | Ratio | Angle],
        dep_body: "DependencyBody",
        dep_graph: "DependencyGraph",
        symbols_graph: SymbolsGraph,
        disabled_intrinsic_rules: list[IntrinsicRules],
    ) -> tuple[list[Dependency], list[tuple[Statement, Dependency]]]:
        m, a, b = args
        add_coll, to_cache_coll = preds.Coll.add(
            args, dep_body, dep_graph, symbols_graph, disabled_intrinsic_rules
        )
        add_cong, to_cache_cong = preds.Cong.add(
            [m, a, m, b], dep_body, dep_graph, symbols_graph, disabled_intrinsic_rules
        )
        return add_coll + add_cong, to_cache_coll + to_cache_cong

    @staticmethod
    def why(
        dep_graph: "DependencyGraph", statement: "Statement"
    ) -> tuple[Optional[Reason], list[Dependency]]:
        m, a, b = statement.args
        ma = dep_graph.symbols_graph.get_segment(m, a)
        mb = dep_graph.symbols_graph.get_segment(m, b)
        coll = Statement(preds.Coll, [m, a, b])
        coll_dep = dep_graph.build_resolved_dependency(coll, use_cache=False)
        return None, [coll_dep] + why_equal(ma, mb)

    @staticmethod
    def check(args: list[Point], symbols_graph: SymbolsGraph) -> bool:
        if not preds.Coll.check(args, symbols_graph):
            return False
        m, a, b = args
        return preds.Cong.check([m, a, m, b], symbols_graph)

    @staticmethod
    def check_numerical(args: list[PointNum]) -> bool:
        a, b, c = args
        coll = preds.Coll.check_numerical(args)
        return coll and close_enough(a.distance(b), a.distance(c))

    @staticmethod
    def enumerate(
        symbols_graph: SymbolsGraph,
    ) -> Generator[tuple[Point, ...], None, None]:
        for line in symbols_graph.type2nodes[Line]:
            for a, b, c in permutations_triplets(line.neighbors(Point)):
                if preds.Cong.check([a, b, a, c], symbols_graph):
                    yield a, b, c

    @staticmethod
    def pretty(args: list[str]) -> str:
        x, a, b = args
        return f"{x} is midpoint of {a}{b}"

    @classmethod
    def hash(cls, args: list[Point]) -> tuple[str, ...]:
        return hash_point_and_line(cls.NAME, args)
