from __future__ import annotations
from typing import TYPE_CHECKING, Any

from geosolver.dependency.dependency import Dependency
from geosolver.dependency.symbols import Point
from geosolver.predicates.collinearity import Coll
from geosolver.predicates.congruence import Cong
from geosolver.predicates.predicate import IllegalPredicate, Predicate

if TYPE_CHECKING:
    from geosolver.dependency.dependency_graph import DependencyGraph
    from geosolver.statement import Statement


class MidPoint(Predicate):
    """midp M A B -
    Represent that M is the midpoint of the segment AB.

    Can be equivalent to coll M A B and cong A M B M."""

    NAME = "midp"

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> tuple[Any, ...]:
        if len(set(args)) != 3:
            raise IllegalPredicate
        m, a, b = args
        a, b = sorted((a, b))
        return tuple(dep_graph.symbols_graph.names2points((m, a, b)))

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        args: tuple[Point, ...] = statement.args
        m, a, b = args
        return m.num.close((a.num + b.num) / 2)

    @classmethod
    def check(cls, statement: Statement) -> bool:
        args: tuple[Point, ...] = statement.args
        m, a, b = args
        coll = statement.with_new(Coll, (m, a, b))
        cong = statement.with_new(Cong, (m, a, m, b))
        return coll.check() and cong.check()

    @classmethod
    def why(cls, statement: Statement) -> Dependency:
        args: tuple[Point, ...] = statement.args
        m, a, b = args
        coll = statement.with_new(Coll, (m, a, b))
        cong = statement.with_new(Cong, (m, a, m, b))
        return Dependency.mk(statement, "", (coll, cong))

    @classmethod
    def to_repr(cls, statement: Statement) -> str:
        args: tuple[Point, ...] = statement.args
        m, a, b = args
        return f"{a.name}-{m.name}(mid)-{b.name}"
