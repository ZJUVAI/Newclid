from __future__ import annotations
from abc import ABC
from typing import TYPE_CHECKING, Any, Optional


if TYPE_CHECKING:
    from geosolver.dependency.dependency import Dependency
    from geosolver.dependency.dependency_graph import DependencyGraph
    from geosolver.statement import Statement


class IllegalPredicate(Exception):
    ...


class Predicate(ABC):
    NAME: str

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> tuple[Any, ...]:
        raise NotImplementedError(f"{cls.NAME} parsing not implemented")

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        """Numericaly checks if the predicate is true for the given arguments."""
        raise NotImplementedError(f"{cls.NAME} check numerical not implemented")

    @classmethod
    def check(cls, statement: Statement) -> bool:
        return False

    @classmethod
    def add(cls, dep: Dependency) -> None:
        """Make a dependency body into a list of dependencies
        with the given arguments."""
        return

    @classmethod
    def why(cls, statement: Statement) -> Optional[Dependency]:
        """Resolve the reason and list of dependencies
        justifying why this predicate could be true."""
        return None

    @classmethod
    def pretty(cls, statement: Statement) -> str:
        """Write the predicate in a natural language."""
        return cls.to_repr(statement)

    @classmethod
    def to_repr(cls, statement: Statement) -> str:
        res = cls.NAME + "["
        for a in statement.args:
            res += repr(a) + ","
        res += "]"
        return res

    @classmethod
    def to_tokens(cls, args: tuple[Any, ...]) -> tuple[str, ...]:
        raise NotImplementedError(f"{cls.NAME} to_tokens not implemented")
