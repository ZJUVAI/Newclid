from __future__ import annotations
from typing import TYPE_CHECKING, Any, Optional
from newclid.dependencies.symbols import Point
from newclid.predicates.predicate import Predicate


if TYPE_CHECKING:
    from newclid.dependencies.dependency_graph import DependencyGraph
    from newclid.statement import Statement

class Secant(Predicate):

    NAME = "secant"

    @classmethod
    def preparse(cls, args: tuple[str, ...]) -> Optional[tuple[str, ...]]:
        o, a, b, p = args
        a, b = sorted((a, b), key = cls.custom_key)
        return (o, a, b, p)
        

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> Optional[tuple[Any, ...]]:
        preparse = cls.preparse(args)
        return (
            tuple(dep_graph.symbols_graph.names2points(preparse)) if preparse else None
        )

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        args: tuple[Point, ...] = statement.args
        return True

    @classmethod
    def pretty(cls, statement: Statement) -> str:
        args: tuple[Point, ...] = statement.args
        o, a, b, p = args
        return f"secant {a.pretty_name}{b.pretty_name} of ⊙{o.pretty_name} through {p.pretty_name}"
