from __future__ import annotations
from typing import TYPE_CHECKING, Any, Optional
from geosolver.dependencies.dependency import NUMERICAL_CHECK, Dependency
from geosolver.dependencies.symbols import Point
from geosolver.numerical.check import same_clock
from geosolver.predicates.predicate import Predicate


if TYPE_CHECKING:
    from geosolver.dependencies.dependency_graph import DependencyGraph
    from geosolver.statement import Statement


class SameClock(Predicate):
    """sameclock a b c x y z -"""

    NAME = "sameclock"

    @classmethod
    def preparse(cls, args: tuple[str, ...]) -> Optional[tuple[str, ...]]:
        a, b, c, x, y, z = args
        if len(set((a, b, c))) < 3 or len(set((x, y, z))) < 3:
            return None
        group = min((a, b, c), (b, c, a), (c, a, b))
        groupr = min((a, c, b), (c, b, a), (b, a, c))
        group1 = min((x, y, z), (y, z, x), (z, x, y))
        group1r = min((x, z, y), (z, y, x), (y, x, z))
        return min(group + group1, group1 + group, groupr + group1r, group1r + groupr)

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> Optional[tuple[Any, ...]]:
        preparse = cls.preparse(args)
        return (
            tuple(dep_graph.symbols_graph.names2points(preparse)) if preparse else None
        )

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        args: tuple[Point, ...] = statement.args
        a, b, c, x, y, z = args
        return same_clock(a.num, b.num, c.num, x.num, y.num, z.num)

    @classmethod
    def check(cls, statement: Statement) -> bool:
        return True

    @classmethod
    def why(cls, statement: Statement) -> Dependency:
        return Dependency.mk(statement, NUMERICAL_CHECK, ())

    @classmethod
    def add(cls, dep: Dependency):
        return

    @classmethod
    def pretty(cls, statement: Statement) -> str:
        args: tuple[Point, ...] = statement.args
        a, b, c, x, y, z = args
        return f"{a.pretty_name}{b.pretty_name}{c.pretty_name} are sameclock to {x.pretty_name}{y.pretty_name}{z.pretty_name}"
