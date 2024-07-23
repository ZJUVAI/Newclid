from __future__ import annotations
from typing import TYPE_CHECKING, Any

from geosolver.dependency.symbols import Point
from geosolver.predicates.predicate import IllegalPredicate, Predicate

if TYPE_CHECKING:
    from geosolver.dependency.dependency_graph import DependencyGraph
    from geosolver.statement import Statement


class MidPoint(Predicate):
    """midp M A B -
    Represent that M is the midpoint of the segment AB.

    Can be equivalent to coll M A B and cong A M B M."""

    NAME = "midp"

    @classmethod
    def preparse(cls, args: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(args)) != 3:
            raise IllegalPredicate
        m, a, b = args
        a, b = sorted((a, b))
        return (m, a, b)

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> tuple[Any, ...]:
        return tuple(dep_graph.symbols_graph.names2points(cls.preparse(args)))

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        args: tuple[Point, ...] = statement.args
        m, a, b = args
        return m.num.close_enough((a.num + b.num) / 2)

    @classmethod
    def pretty(cls, statement: Statement) -> str:
        args: tuple[Point, ...] = statement.args
        m, a, b = args
        return f"{m.pretty_name} is the midpoint of {a.pretty_name}{b.pretty_name}"
