from __future__ import annotations
from collections import defaultdict
from typing import TYPE_CHECKING, Generator, Optional

from geosolver.dependencies.dependency import Reason, Dependency

from geosolver.dependencies.why_predicates import why_equal
from geosolver.numerical import close_enough
from geosolver.numerical.geometries import PointNum
from geosolver.predicates.predicate import Predicate
from geosolver.intrinsic_rules import IntrinsicRules

from geosolver.geometry import Angle, Length, Point, Ratio, Segment
from geosolver.combinatorics import permutations_triplets
from geosolver.statement import Statement, hash_point_then_set_of_points
from geosolver.symbols_graph import SymbolsGraph

import geosolver.predicates as preds


if TYPE_CHECKING:
    from geosolver.dependencies.why_graph import DependencyGraph
    from geosolver.dependencies.dependency_building import DependencyBody


class Circumcenter(Predicate):
    """circle O A B C -
    Represent that O is the center of the circle through A, B, and C
    (circumcenter of triangle ABC).

    Can be equivalent to cong O A O B and cong O A O C,
    and equivalent pairs of congruences.
    """

    NAME = "circle"

    @staticmethod
    def add(
        args: list[Point | Ratio | Angle],
        dep_body: "DependencyBody",
        dep_graph: "DependencyGraph",
        symbols_graph: SymbolsGraph,
        disabled_intrinsic_rules: list[IntrinsicRules],
    ) -> tuple[list[Dependency], list[tuple[Statement, Dependency]]]:
        o, a, b, c = args
        add_ab, to_cache_ab = preds.Cong.add(
            [o, a, o, b], dep_body, dep_graph, symbols_graph, disabled_intrinsic_rules
        )
        add_ac, to_cache_ac = preds.Cong.add(
            [o, a, o, c], dep_body, dep_graph, symbols_graph, disabled_intrinsic_rules
        )
        return add_ab + add_ac, to_cache_ab + to_cache_ac

    @staticmethod
    def why(
        dep_graph: "DependencyGraph", statement: "Statement"
    ) -> tuple[Optional[Reason], list[Dependency]]:
        o, a, b, c = statement.args
        oa = dep_graph.symbols_graph.get_segment(o, a)
        ob = dep_graph.symbols_graph.get_segment(o, b)
        oc = dep_graph.symbols_graph.get_segment(o, c)
        return None, why_equal(oa, ob) + why_equal(oa, oc)

    @staticmethod
    def check(args: list[Point], symbols_graph: SymbolsGraph) -> bool:
        o, a, b, c = args
        cong_ab = preds.Cong.check([o, a, o, b], symbols_graph)
        cong_ac = preds.Cong.check([o, a, o, c], symbols_graph)
        return cong_ab and cong_ac

    @staticmethod
    def check_numerical(args: list[PointNum]) -> bool:
        if len(args) != 4:
            return False
        o, a, b, c = args
        oa, ob, oc = o.distance(a), o.distance(b), o.distance(c)
        return close_enough(oa, ob) and close_enough(ob, oc)

    @staticmethod
    def enumerate(
        symbols_graph: SymbolsGraph,
    ) -> Generator[tuple[Point, ...], None, None]:
        for lenght in symbols_graph.type2nodes[Length]:
            p2p = defaultdict(list)
            for s in lenght.neighbors(Segment):
                a, b = s.points
                p2p[a].append(b)
                p2p[b].append(a)
            for p, ps in p2p.items():
                if len(ps) >= 3:
                    for a, b, c in permutations_triplets(ps):
                        yield p, a, b, c

    @staticmethod
    def pretty(args: list[str]) -> str:
        o, a, b, c = args
        return f"{o} is the circumcenter of \\Delta {a}{b}{c}"

    @classmethod
    def hash(cls, args: list[Point]) -> tuple[str, ...]:
        return hash_point_then_set_of_points(cls.NAME, args)
