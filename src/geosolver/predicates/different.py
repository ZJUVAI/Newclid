from __future__ import annotations
from typing import TYPE_CHECKING, Generator, Optional

from geosolver.dependencies.dependency import Reason, Dependency

from geosolver.numerical.geometries import PointNum

from geosolver.predicates.predicate import Predicate
from geosolver.intrinsic_rules import IntrinsicRules

from geosolver.geometry import Point
from geosolver.statement import Statement, hash_unordered_set_of_points
from geosolver.symbols_graph import SymbolsGraph


if TYPE_CHECKING:
    from geosolver.dependencies.why_graph import DependencyGraph
    from geosolver.dependencies.dependency_building import DependencyBody


class Diff(Predicate):
    """diff a b -

    Represent that a is not equal to b.

    Numerical only.
    """

    NAME = "diff"

    @staticmethod
    def add(
        args: list[Point],
        dep_body: "DependencyBody",
        dep_graph: "DependencyGraph",
        symbols_graph: SymbolsGraph,
        disabled_intrinsic_rules: list[IntrinsicRules],
    ) -> tuple[list[Dependency], list[tuple[Statement, Dependency]]]:
        raise NotImplementedError

    @staticmethod
    def why(
        dep_graph: "DependencyGraph", statement: Statement
    ) -> tuple[Optional[Reason], list[Dependency]]:
        return None, []

    @staticmethod
    def check(args: list[Point], symbols_graph: SymbolsGraph) -> bool:
        return Diff.check_numerical([p.num for p in args])

    @staticmethod
    def check_numerical(args: list[PointNum]) -> bool:
        a, b = args
        return not a.close(b)

    @staticmethod
    def enumerate(
        symbols_graph: SymbolsGraph,
    ) -> Generator[tuple[Point, ...], None, None]:
        raise NotImplementedError

    @staticmethod
    def pretty(args: list[str]) -> str:
        raise NotImplementedError

    @classmethod
    def hash(cls, args: list[Point]) -> tuple[str, ...]:
        return hash_unordered_set_of_points(cls.NAME, args)
