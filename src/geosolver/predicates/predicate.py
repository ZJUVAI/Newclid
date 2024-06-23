from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Generator, Optional, Union
from typing_extensions import Self

from geosolver.geometry import Point, Ratio, Angle
from geosolver.dependencies.dependency import Reason
from geosolver.statement import Statement


if TYPE_CHECKING:
    from geosolver.dependencies.dependency import Dependency
    from geosolver.dependencies.dependency_building import DependencyBody
    from geosolver.dependencies.why_graph import DependencyGraph

    from geosolver.numerical.geometries import PointNum
    from geosolver.intrinsic_rules import IntrinsicRules

    from geosolver.symbols_graph import SymbolsGraph

PredicateArgument = Union[Point, Ratio, Angle]


class Predicate(ABC):
    NAME: str

    @staticmethod
    @abstractmethod
    def add(
        args: list[PredicateArgument],
        dep_body: "DependencyBody",
        dep_graph: "DependencyGraph",
        symbols_graph: "SymbolsGraph",
        disabled_intrinsic_rules: list["IntrinsicRules"],
    ) -> tuple[list["Dependency"], list[tuple["Statement", "Dependency"]]]:
        """Make a dependency body into a list of dependencies
        with the given arguments."""

    @staticmethod
    @abstractmethod
    def why(
        dep_graph: "DependencyGraph", statement: "Statement"
    ) -> tuple[Optional[Reason], list[Dependency]]:
        """Resolve the reason and list of dependencies
        justifying why this predicate could be true."""

    @staticmethod
    @abstractmethod
    def check(args: list[PredicateArgument], symbols_graph: SymbolsGraph) -> bool:
        """Symbolicaly checks if the predicate is true for the given arguments."""

    @staticmethod
    @abstractmethod
    def check_numerical(args: list["PointNum" | Ratio | Angle]) -> bool:
        """Numericaly checks if the predicate is true for the given arguments."""

    @staticmethod
    @abstractmethod
    def enumerate(
        symbols_graph: "SymbolsGraph",
    ) -> Generator[tuple[Point, ...], None, None]:
        """Enumerate all sets of arguments for which the predicate is true."""

    @staticmethod
    @abstractmethod
    def pretty(args: list[str]) -> str:
        """Write the predicate in a natural language."""

    @classmethod
    @abstractmethod
    def hash(
        cls: Self, args: list[PredicateArgument]
    ) -> tuple[str | PredicateArgument]:
        """Hash the predicate into a tuple of strings."""

    def __repr__(self) -> str:
        return self.NAME
