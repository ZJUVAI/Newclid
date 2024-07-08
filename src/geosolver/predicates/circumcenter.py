from __future__ import annotations
from typing import TYPE_CHECKING, Any
from geosolver.dependency.dependency import Dependency
from geosolver.numerical import close_enough
from geosolver.numerical.geometries import CircleNum
from geosolver.predicates.congruence import Cong
from geosolver.predicates.cyclic import Cyclic
from geosolver.predicates.predicate import IllegalPredicate, Predicate


if TYPE_CHECKING:
    from geosolver.dependency.symbols import Point
    from geosolver.statement import Statement
    from geosolver.dependency.dependency_graph import DependencyGraph


class Circumcenter(Predicate):
    """circle O A B C -
    Represent that O is the center of the circle through A, B, and C
    (circumcenter of triangle ABC).

    Can be equivalent to cong O A O B and cong O A O C,
    and equivalent pairs of congruences.
    """

    NAME = "circle"

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> tuple[Any, ...]:
        if len(args) <= 2 or len(args) != len(set(args)):
            raise IllegalPredicate
        return tuple(dep_graph.symbols_graph.names2points([args[0]] + sorted(args[1:])))

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        points: tuple[Point, ...] = statement.args
        circle = CircleNum(points[0].num, points[0].num.distance(points[1].num))
        return all(
            close_enough(circle.radius, circle.center.distance(p.num))
            for p in points[2:]
        )

    @classmethod
    def check(cls, statement: Statement) -> bool:
        points: tuple[Point, ...] = statement.args
        o = points[0]
        p0 = points[1]
        for p1 in points[2:]:
            cong = statement.with_new(Cong, (o, p0, o, p1))
            if not cong.check():
                return False
        return True

    @classmethod
    def add(cls, dep: Dependency) -> None:
        points: tuple[Point, ...] = dep.statement.args
        o = points[0]
        p0 = points[1]
        for p1 in points[2:]:
            cong = dep.with_new(dep.statement.with_new(Cong, (o, p0, o, p1)))
            cong.add()
        if len(points) > 4:
            dep.with_new(dep.statement.with_new(Cyclic, points[1:])).add()

    @classmethod
    def why(cls, statement: Statement) -> Dependency:
        points: tuple[Point, ...] = statement.args
        o = points[0]
        p0 = points[1]
        return Dependency.mk(
            statement,
            "",
            tuple(statement.with_new(Cong, (o, p0, o, p1)) for p1 in points[2:]),
        )

    @classmethod
    def to_repr(cls, statement: Statement) -> str:
        points: tuple[Point, ...] = statement.args
        o = points[0]
        return f"{o}({''.join(p.name for p in points[1:])})"
