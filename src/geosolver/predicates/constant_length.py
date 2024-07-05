from __future__ import annotations
from typing import TYPE_CHECKING, Any


from geosolver.dependency.symbols import Point
from geosolver.numerical import close_enough
from geosolver.predicates.predicate import Predicate
from geosolver.tools import parse_len, str_to_nd


if TYPE_CHECKING:
    from geosolver.dependency.dependency_graph import DependencyGraph
    from geosolver.statement import Statement


class ConstantLength(Predicate):
    """lconst A B L -
    Represent that the length of segment AB is L

    L should be given as a float.
    """

    NAME = "lconst"

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> tuple[Any, ...]:
        a, b, length = args
        a, b = sorted((a, b))
        return tuple(dep_graph.symbols_graph.names2points((a, b))) + (
            parse_len(length),
        )

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        args: tuple[Point, Point, str] = statement.args
        a, b, length = args
        n, d = str_to_nd(length)
        return close_enough(a.num.distance(b.num), n / d)

    @classmethod
    def to_repr(cls, statement: Statement) -> str:
        a, b, length = statement.args
        assert isinstance(a, Point)
        assert isinstance(b, Point)
        assert isinstance(length, str)
        return f"len({a.name}{b.name})={length}"
