from __future__ import annotations
from typing import TYPE_CHECKING, Any
from geosolver.dependency.symbols import Point
from geosolver.numerical.geometries import LineNum
from geosolver.predicates.predicate import Predicate

if TYPE_CHECKING:
    from geosolver.dependency.dependency_graph import DependencyGraph
    from geosolver.statement import Statement


class Para(Predicate):
    """para A B C D -
    Represent that the line AB is parallel to the line CD.
    """

    NAME = "para"

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> tuple[Any, ...]:
        a, b, c, d = args
        a, b = sorted((a, b))
        c, d = sorted((c, d))
        if (a, b) > (c, d):
            a, b, c, d = c, d, a, b
        return tuple(dep_graph.symbols_graph.names2points((a, b, c, d)))

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        a, b, c, d = statement.args
        assert isinstance(a, Point)
        assert isinstance(b, Point)
        assert isinstance(c, Point)
        assert isinstance(d, Point)
        l1 = LineNum(a.num, b.num)
        l2 = LineNum(c.num, d.num)
        return l1.is_parallel(l2)


class NPara(Predicate):
    """npara A B C D -
    Represent that lines AB and CD are NOT parallel.

    It can only be numerically checked
    (angular coefficient of the equations of the lines are different).
    """

    NAME = "npara"

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> tuple[Any, ...]:
        return Para.parse(args, dep_graph)

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        a, b, c, d = statement.args
        assert isinstance(a, Point)
        assert isinstance(b, Point)
        assert isinstance(c, Point)
        assert isinstance(d, Point)
        l1 = LineNum(a.num, b.num)
        l2 = LineNum(c.num, d.num)
        return not l1.is_parallel(l2)
