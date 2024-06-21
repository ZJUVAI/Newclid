from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Generator, Optional
from typing_extensions import Self

from geosolver.geometry import Point, Ratio, Angle
from geosolver.dependencies.dependency import Reason
from geosolver.statements.statement import Statement


if TYPE_CHECKING:
    from geosolver.dependencies.dependency import Dependency
    from geosolver.dependencies.dependency_building import DependencyBody
    from geosolver.dependencies.why_graph import WhyHyperGraph

    from geosolver.numerical.geometries import PointNum
    from geosolver.intrinsic_rules import IntrinsicRules
    from geosolver.statements.adder import ToCache
    from geosolver.symbols_graph import SymbolsGraph

PredicateArgument = Point | Ratio | Angle


class Predicate(ABC):
    NAME: str

    @abstractmethod
    @staticmethod
    def add(
        args: list[PredicateArgument],
        dep_body: "DependencyBody",
        dep_graph: "WhyHyperGraph",
        symbols_graph: "SymbolsGraph",
        disabled_intrinsic_rules: list["IntrinsicRules"],
    ) -> tuple[list["Dependency"], list["ToCache"]]:
        """Make a dependency body into a list of dependencies
        with the given arguments."""

    @abstractmethod
    @staticmethod
    def why(
        statements_graph: "WhyHyperGraph", statement: "Statement"
    ) -> tuple[Optional[Reason], list[Dependency]]:
        """Resolve the reason and list of dependencies
        justifying why this predicate could be true."""

    @abstractmethod
    @staticmethod
    def check(args: list[PredicateArgument], symbols_graph: SymbolsGraph) -> bool:
        """Symbolicaly checks if the predicate is true for the given arguments."""

    @abstractmethod
    @staticmethod
    def check_numerical(args: list["PointNum" | Ratio | Angle]) -> bool:
        """Numericaly checks if the predicate is true for the given arguments."""

    @abstractmethod
    @staticmethod
    def enumerate(
        symbols_graph: "SymbolsGraph",
    ) -> Generator[tuple[Point, ...], None, None]:
        """Enumerate all sets of arguments for which the predicate is true."""

    @abstractmethod
    @staticmethod
    def pretty(args: list[str]) -> str:
        """Write the predicate in a natural language."""

    @abstractmethod
    @classmethod
    def hash(
        cls: Self, args: list[PredicateArgument]
    ) -> tuple[str | PredicateArgument]:
        """Hash the predicate into a tuple of strings."""
