from __future__ import annotations
from typing import TYPE_CHECKING, Any

from geosolver.dependency.dependency import Dependency
from geosolver.dependency.symbols import Point
from geosolver.numerical import close_enough
from geosolver.predicates.predicate import IllegalPredicate, Predicate
from geosolver.tools import reshape


if TYPE_CHECKING:
    from geosolver.dependency.dependency import Dependency
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
        if len(args) % 2 != 0:
            raise IllegalPredicate
        for a, b in zip(args[::2], args[1::2]):
            if a > b:
                a, b = b, a
            if a == b:
                raise IllegalPredicate
            segs.append((a, b))
        segs.sort()
        points: list[str] = []
        for a, b in segs:
            points.append(a)
            points.append(b)
        return tuple(dep_graph.symbols_graph.names2points(points))

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        args: tuple[Point] = statement.args
        length = None
        for a, b in reshape(list(args), 2):
            _length = a.num.distance2(b.num)
            if length is not None and not close_enough(length, _length):
                return False
            length = _length
        return True

    @classmethod
    def add(cls, dep: Dependency) -> None:
        points: tuple[Point, ...] = dep.statement.args
        table = dep.statement.dep_graph.ar.rtable
        i = 2
        while i < len(points):
            table.add_expr(
                table.get_eq2(
                    table.get_length(points[0], points[1]),
                    table.get_length(points[i], points[i + 1]),
                ),
                dep,
            )
            i += 2

    @classmethod
    def check(cls, statement: Statement) -> bool:
        points: tuple[Point, ...] = statement.args
        table = statement.dep_graph.ar.rtable
        i = 2
        while i < len(points):
            if not table.add_expr(
                table.get_eq2(
                    table.get_length(points[0], points[1]),
                    table.get_length(points[i], points[i + 1]),
                ),
                None,
            ):
                return False
            i += 2
        return True

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
        if len(set(args)) != 4:
            raise IllegalPredicate
        m, n, a, b = args
        m, n = sorted((m, n))
        a, b = sorted((a, b))
        return tuple(dep_graph.symbols_graph.names2points((m, n, a, b)))

    @classmethod
    def _get_2cong(cls, statement: Statement) -> tuple[Statement, Statement]:
        points: tuple[Point, ...] = statement.args
        m, n, a, b = points
        return statement.with_new(Cong, (m, a, n, a)), statement.with_new(
            Cong, (m, b, n, b)
        )

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        c0, c1 = cls._get_2cong(statement)
        return c0.check_numerical() and c1.check_numerical()

    @classmethod
    def check(cls, statement: Statement) -> bool:
        c0, c1 = cls._get_2cong(statement)
        return c0.check() and c1.check()

    @classmethod
    def add(cls, dep: Dependency) -> None:
        c0, c1 = cls._get_2cong(dep.statement)
        dep.with_new(c0).add()
        dep.with_new(c1).add()

    @classmethod
    def to_repr(cls, statement: Statement) -> str:
        points: tuple[Point, Point, Point, Point] = statement.args
        m, n, a, b = points
        return "cong2:" + f"{a}<{m}{n}>{b}"
