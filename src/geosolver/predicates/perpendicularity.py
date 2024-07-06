from __future__ import annotations
from typing import TYPE_CHECKING, Any

from geosolver.dependency.symbols import Point
from geosolver.numerical import ATOM
from geosolver.predicates.equal_angles import EqAngle
from geosolver.predicates.predicate import IllegalPredicate, Predicate

if TYPE_CHECKING:
    from geosolver.dependency.dependency import Dependency
    from geosolver.dependency.dependency_graph import DependencyGraph
    from geosolver.statement import Statement


class Perp(Predicate):
    """perp A B C D -
    Represent that the line AB is perpendicular to the line CD.
    """

    NAME = "perp"

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> tuple[Any, ...]:
        a, b, c, d = args
        if a == b or c == d:
            raise IllegalPredicate
        a, b = sorted((a, b))
        c, d = sorted((c, d))
        if (a, b) > (c, d):
            a, b, c, d = c, d, a, b
        return tuple(dep_graph.symbols_graph.names2points((a, b, c, d)))

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        args: tuple[Point, ...] = statement.args
        a, b, c, d = args
        return abs((a.num - b.num).dot(c.num - d.num)) < ATOM

    @classmethod
    def check(cls, statement: Statement) -> bool:
        args: tuple[Point, ...] = statement.args
        a, b, c, d = args
        return statement.with_new(EqAngle, (a, b, c, d, c, d, a, b)).check()

    @classmethod
    def add(cls, dep: Dependency):
        args: tuple[Point, ...] = dep.statement.args
        a, b, c, d = args
        dep.with_new(dep.statement.with_new(EqAngle, (a, b, c, d, c, d, a, b))).add()

    @classmethod
    def why(cls, statement: Statement) -> list[Dependency]:
        args: tuple[Point, ...] = statement.args
        a, b, c, d = args
        return [
            dep.with_new(statement)
            for dep in statement.with_new(EqAngle, (a, b, c, d, c, d, a, b)).why()
        ]


class NPerp(Predicate):
    """nperp A B C D -
    Represent that lines AB and CD are NOT perpendicular.

    Numerical only.
    """

    NAME = "nperp"

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> tuple[Any, ...]:
        return Perp.parse(args, dep_graph)

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        return not Perp.check_numerical(statement)
