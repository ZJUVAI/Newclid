from __future__ import annotations
from typing import TYPE_CHECKING, Any

from geosolver import predicates
from geosolver.dependency.dependency import Dependency
from geosolver.dependency.symbols import Point
from geosolver.numerical import ATOM
from geosolver.predicates.predicate import Predicate

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
        a, b = sorted((a, b))
        c, d = sorted((c, d))
        if (a, b) > (c, d):
            a, b, c, d = c, d, a, b
        return tuple(dep_graph.symbols_graph.names2points((a, b, c, d)))

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        a, b, c, d = statement.args
        assert (
            isinstance(a, Point)
            and isinstance(b, Point)
            and isinstance(c, Point)
            and isinstance(d, Point)
        )
        return abs((a.num - b.num).dot(c.num - d.num)) < ATOM

    @classmethod
    def check(cls, statement: Statement) -> bool:
        a, b, c, d = statement.args
        assert (
            isinstance(a, Point)
            and isinstance(b, Point)
            and isinstance(c, Point)
            and isinstance(d, Point)
        )
        return statement.dep_graph.ar.check(
            predicates.EqAngle, (a, b, c, d, c, d, a, b)
        )

    @classmethod
    def add(cls, dep: Dependency):
        a, b, c, d = dep.statement.args
        assert (
            isinstance(a, Point)
            and isinstance(b, Point)
            and isinstance(c, Point)
            and isinstance(d, Point)
        )
        return dep.statement.dep_graph.ar.add(
            predicates.EqAngle, (a, b, c, d, c, d, a, b), dep
        )


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
