from __future__ import annotations
from copy import copy
from typing import TYPE_CHECKING, Any

from geosolver.dependency.symbols import Point
from geosolver.numerical import close_enough
from geosolver.predicates.predicate import Predicate
from geosolver.tools import reshape


if TYPE_CHECKING:
    from geosolver.statement import Statement
    from geosolver.dependency.dependency_graph import DependencyGraph


class Cong(Predicate):
    """cong A B C D -
    Represent that segments AB and CD are congruent."""

    NAME = "cong"

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> tuple[Any, ...]:
        segs: list[tuple[str, str]] = []
        assert len(args) % 2 == 0
        for a, b in zip(args[::2], args[1::2]):
            if a > b:
                a, b = b, a
            segs.append((a, b))
        segs.sort()
        points: list[str] = []
        for a, b in segs:
            points.append(a)
            points.append(b)
        return tuple(dep_graph.symbols_graph.names2points(points))

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        length = None
        for a, b in reshape(list(statement.args), 2):
            a: Point
            b: Point
            _length = a.num.distance2(b.num)
            if length is not None and not close_enough(length, _length):
                return False
            length = _length
        return True

    @classmethod
    def check(cls, statement: Statement) -> bool:
        return statement.dep_graph.ar.check(statement.predicate, statement.args)

    @classmethod
    def to_repr(cls, statement: Statement) -> str:
        args = statement.args
        return "=".join(f"{a}{b}" for a, b in zip(args[::2], args[1::2]))

    @classmethod
    def to_tokens(cls, args: tuple[Any, ...]) -> tuple[str, ...]:
        return tuple(p.name for p in args)


class Cong2(Predicate):
    NAME = "cong2"

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> tuple[Any, ...]:
        m, n, a, b = args
        m, n = sorted((m, n))
        a, b = sorted((a, b))
        return tuple(dep_graph.symbols_graph.names2points((m, n, a, b)))

    @classmethod
    def _two_cong(cls, statement: Statement) -> tuple[Statement, Statement]:
        points: tuple[Point, Point, Point, Point] = statement.args
        m, n, a, b = points
        statement0 = copy(statement)
        statement0.predicate = Cong
        statement0.args = (m, a, n, a)
        statement1 = copy(statement0)
        statement1.args = (m, b, n, b)
        return statement0, statement1

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        s0, s1 = cls._two_cong(statement)
        return s0.check_numerical() and s1.check_numerical()

    @classmethod
    def to_repr(cls, statement: Statement) -> str:
        points: tuple[Point, Point, Point, Point] = statement.args
        m, n, a, b = points
        return "cong2:" + f"{a}<{m}{n}>{b}"
