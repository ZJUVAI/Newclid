from __future__ import annotations
from typing import TYPE_CHECKING, Generator, Optional
from typing_extensions import Self

from geosolver.dependencies.dependency import Reason, Dependency

from geosolver.numerical.geometries import PointNum

from geosolver.predicates.predicate import Predicate
from geosolver.intrinsic_rules import IntrinsicRules

from geosolver.geometry import Point
from geosolver.statements.statement import Statement, hash_ordered_list_of_points
from geosolver.symbols_graph import SymbolsGraph


if TYPE_CHECKING:
    from geosolver.dependencies.why_graph import WhyHyperGraph
    from geosolver.dependencies.dependency_building import DependencyBody


class SameSide(Predicate):
    """sameside a b c x y z -

    Represent that b is to the same side of a & c as y is to x & z.

    Numerical only.
    """

    NAME = "sameside"

    @staticmethod
    def add(
        args: list[Point],
        dep_body: "DependencyBody",
        dep_graph: "WhyHyperGraph",
        symbols_graph: SymbolsGraph,
        disabled_intrinsic_rules: list[IntrinsicRules],
    ) -> tuple[list[Dependency], list[tuple[Statement, Dependency]]]:
        raise NotImplementedError

    @staticmethod
    def why(
        statements_graph: "WhyHyperGraph", statement: Statement
    ) -> tuple[Optional[Reason], list[Dependency]]:
        return None, []

    @staticmethod
    def check(args: list[Point], symbols_graph: SymbolsGraph) -> bool:
        return SameSide.check_numerical([p.num for p in args])

    @staticmethod
    def check_numerical(args: list[PointNum]) -> bool:
        b, a, c, y, x, z = args
        ba = b - a
        bc = b - c
        yx = y - x
        yz = y - z
        return ba.dot(bc) * yx.dot(yz) > 0

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
        return hash_ordered_list_of_points(cls.NAME, args)
