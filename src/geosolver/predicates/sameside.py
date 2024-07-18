from __future__ import annotations
from typing import TYPE_CHECKING, Any

from geosolver.dependency.dependency import NUMERICAL_CHECK, Dependency
from geosolver.dependency.symbols import Point
from geosolver.numerical import close_enough
from geosolver.predicates.predicate import IllegalPredicate, Predicate


if TYPE_CHECKING:
    from geosolver.dependency.dependency_graph import DependencyGraph
    from geosolver.statement import Statement


class SameSide(Predicate):
    """sameside a b c x y z

    Represent that a is to the same side of b->c as x is to y->z.

    Numerical only.
    """

    NAME = "sameside"

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> tuple[Any, ...]:
        a, b, c, x, y, z = args
        if len(set((a, b, c))) < 3 or len(set((x, y, z))) < 3:
            raise IllegalPredicate
        p1 = min((a, b, c), (a, c, b))
        p2 = min((x, y, z), (x, z, y))
        return tuple(dep_graph.symbols_graph.names2points(min(p1 + p2, p2 + p1)))

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        args: tuple[Point, ...] = statement.args
        a, b, c, x, y, z = args
        dot = (b.num - a.num).dot(c.num - a.num) * (y.num - x.num).dot(z.num - x.num)
        return dot >= 0 or close_enough(dot, 0)

    @classmethod
    def check(cls, statement: Statement) -> bool:
        return statement.check_numerical()

    @classmethod
    def why(cls, statement: Statement) -> Dependency:
        return Dependency.mk(statement, NUMERICAL_CHECK, ())

    @classmethod
    def pretty(cls, statement: Statement) -> str:
        args: tuple[Point, ...] = statement.args
        a, b, c, x, y, z = args
        return f"{a.pretty_name} is to the same side of {b.pretty_name}->{c.pretty_name} as {x.pretty_name} is to {y.pretty_name}->{z.pretty_name}"


class NSameSide(Predicate):
    """nsameside a b c x y z

    Represent that a is to the different side of b->c as x is to y->z.

    Numerical only.
    """

    NAME = "nsameside"

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> tuple[Any, ...]:
        return SameSide.parse(args, dep_graph)

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        args: tuple[Point, ...] = statement.args
        a, b, c, x, y, z = args
        dot = (b.num - a.num).dot(c.num - a.num) * (y.num - x.num).dot(z.num - x.num)
        return dot <= 0 or close_enough(dot, 0)

    @classmethod
    def check(cls, statement: Statement) -> bool:
        return statement.check_numerical()

    @classmethod
    def why(cls, statement: Statement) -> Dependency:
        return Dependency.mk(statement, NUMERICAL_CHECK, ())

    @classmethod
    def pretty(cls, statement: Statement) -> str:
        args: tuple[Point, ...] = statement.args
        a, b, c, x, y, z = args
        return f"{a.pretty_name} is to the different side of {b.pretty_name}->{c.pretty_name} as {x.pretty_name} is to {y.pretty_name}->{z.pretty_name}"
