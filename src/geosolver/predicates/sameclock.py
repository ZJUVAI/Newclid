from __future__ import annotations
from typing import TYPE_CHECKING, Any
from geosolver.dependency.dependency import CONSTRUCTION, Dependency
from geosolver.dependency.symbols import Point
from geosolver.numerical.check import same_clock
from geosolver.predicates.predicate import IllegalPredicate, Predicate


if TYPE_CHECKING:
    from geosolver.dependency.dependency_graph import DependencyGraph
    from geosolver.statement import Statement
    from geosolver.dependency.dependency import Dependency


class SameClock(Predicate):
    """sameclock a b c x y z -"""

    NAME = "sameclock"

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> tuple[Any, ...]:
        a, b, c, x, y, z = args
        if len(set((a, b, c))) < 3 or len(set((x, y, z))) < 3:
            raise IllegalPredicate
        group = min((a, b, c), (b, c, a), (c, a, b))
        group1 = min((x, y, z), (y, z, x), (z, x, y))
        return tuple(
            dep_graph.symbols_graph.names2points(min(group + group1, group1 + group))
        )

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        args: tuple[Point, ...] = statement.args
        a, b, c, x, y, z = args
        return same_clock(a.num, b.num, c.num, x.num, y.num, z.num)

    @classmethod
    def check(cls, statement: Statement) -> bool:
        return statement.check_numerical()

    @classmethod
    def why(cls, statement: Statement) -> Dependency:
        return Dependency.mk(statement, CONSTRUCTION, ())

    @classmethod
    def add(cls, dep: Dependency):
        return
