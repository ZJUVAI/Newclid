from __future__ import annotations
from typing import TYPE_CHECKING, Any
from geosolver.dependency.dependency import Dependency
from geosolver.dependency.symbols import Line, Point
from geosolver.numerical.geometries import LineNum
from geosolver.predicates.predicate import IllegalPredicate, Predicate

if TYPE_CHECKING:
    from geosolver.dependency.dependency_graph import DependencyGraph
    from geosolver.statement import Statement


class Coll(Predicate):
    """coll A B C ... -
    Represent that the 3 (or more) points in the arguments are collinear."""

    NAME = "coll"

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> tuple[Any, ...]:
        if len(args) <= 2 or len(args) != len(set(args)):
            raise IllegalPredicate
        return tuple(dep_graph.symbols_graph.names2points(sorted(args)))

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        points: tuple[Point, ...] = tuple(statement.args)
        line = LineNum(points[0].num, points[1].num)
        return all(line.point_at(p.num.x, p.num.y) is not None for p in points[2:])

    @classmethod
    def check(cls, statement: Statement) -> bool:
        return Line.check_coll(statement.args)

    @classmethod
    def add(cls, dep: Dependency):
        rep, merged = Line.make_coll(dep.statement.args, dep)
        table = dep.statement.dep_graph.ar.atable
        for line in merged:
            table.add_expr(table.get_eq2(rep.name, line.name), dep)

    @classmethod
    def to_repr(cls, statement: Statement) -> str:
        return f"coll/{''.join(repr(p) for p in statement.args)}/"

    @classmethod
    def to_tokens(cls, args: tuple[Any, ...]) -> tuple[str, ...]:
        return tuple(p.name for p in args)


class NColl(Predicate):
    """ncoll A B C ... -
    Represent that any of the 3 (or more) points is not aligned with the others.

    Numerical only.
    """

    NAME = "ncoll"

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> tuple[Any, ...]:
        return Coll.parse(args, dep_graph)

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        return not Coll.check_numerical(statement)

    @classmethod
    def check(cls, statement: Statement) -> bool:
        return not statement.with_new(Coll, None).check_numerical()

    @classmethod
    def to_repr(cls, statement: Statement) -> str:
        return f"ncoll/{''.join(repr(p) for p in statement.args)}\\"
