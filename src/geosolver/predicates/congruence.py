from __future__ import annotations
from typing import TYPE_CHECKING, Any

from geosolver.dependency.symbols import Point
from geosolver.numerical import close_enough
from geosolver.predicates.predicate import IllegalPredicate, Predicate
from geosolver.reasoning_engines.algebraic_reasoning.tables import Ratio_Chase
from geosolver.tools import reshape
from geosolver.dependency.dependency import Dependency

if TYPE_CHECKING:
    from geosolver.reasoning_engines.algebraic_reasoning.tables import Table
    from geosolver.reasoning_engines.algebraic_reasoning.tables import SumCV
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
    def _prep_ar(cls, statement: Statement) -> tuple[list[SumCV], Table]:
        points: tuple[Point, ...] = statement.args
        table = statement.dep_graph.ar.rtable
        eqs: list[SumCV] = []
        i = 2
        while i < len(points):
            eqs.append(
                table.get_eq2(
                    table.get_length(points[0], points[1]),
                    table.get_length(points[i], points[i + 1]),
                ),
            )
            i += 2
        return eqs, table

    @classmethod
    def add(cls, dep: Dependency) -> None:
        eqs, table = cls._prep_ar(dep.statement)
        for eq in eqs:
            table.add_expr(eq, dep)

    @classmethod
    def check(cls, statement: Statement) -> bool:
        eqs, table = cls._prep_ar(statement)
        return all(table.add_expr(eq, None) for eq in eqs)

    @classmethod
    def why(cls, statement: Statement) -> Dependency:
        eqs, table = cls._prep_ar(statement)
        why: list[Dependency] = []
        for eq in eqs:
            why.extend(table.why(eq))
        if len(why) == 1:
            return why[0].with_new(statement)
        return Dependency.mk(
            statement, Ratio_Chase, tuple(dep.statement for dep in why)
        )

    @classmethod
    def to_constructive(cls, point: str, args: tuple[str, ...]) -> str:
        a, b, c, d = args
        if point in [c, d]:
            a, b, c, d = c, d, a, b
        if point == b:
            a, b = b, a
        if point == d:
            c, d = d, c
        if a == c and a == point:
            return f"on_bline {a} {b} {d}"
        if b in [c, d]:
            if b == d:
                c, d = d, c
            return f"on_circle {a} {b} {d}"
        return f"eqdistance {a} {b} {c} {d}"

    @classmethod
    def pretty(cls, statement: Statement) -> str:
        args = statement.args
        return " = ".join(
            f"{a.pretty_name}{b.pretty_name}" for a, b in zip(args[::2], args[1::2])
        )

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
    def pretty(cls, statement: Statement) -> str:
        points: tuple[Point, Point, Point, Point] = statement.args
        m, n, a, b = points
        return (
            "cong2:" + f"{a.pretty_name}<{m.pretty_name}{n.pretty_name}>{b.pretty_name}"
        )
