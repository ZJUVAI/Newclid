from __future__ import annotations
from typing import TYPE_CHECKING, Any

from geosolver.dependency.dependency import BY_CONSTRUCTION, Dependency
from geosolver.dependency.symbols import Point
from geosolver.numerical import ATOM
from geosolver.predicates.predicate import IllegalPredicate, Predicate


if TYPE_CHECKING:
    from geosolver.dependency.dependency_graph import DependencyGraph
    from geosolver.statement import Statement


class SameSide(Predicate):
    """sameside a b c x y z -

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
        return tuple(
            dep_graph.symbols_graph.names2points(
                min(
                    (a, b, c, x, y, z),
                    (c, b, a, z, y, x),
                    (x, y, z, a, b, c),
                    (z, y, x, c, b, a),
                )
            )
        )

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        args: tuple[Point, ...] = statement.args
        a, b, c, x, y, z = args
        return (b.num - a.num).dot(c.num - a.num) * (y.num - x.num).dot(
            z.num - x.num
        ) > ATOM

    @classmethod
    def check(cls, statement: Statement) -> bool:
        return statement.check_numerical()

    @classmethod
    def why(cls, statement: Statement) -> Dependency:
        return Dependency.mk(statement, BY_CONSTRUCTION, ())

    @classmethod
    def add(cls, dep: Dependency):
        return

    @classmethod
    def pretty(cls, statement: Statement) -> str:
        args: tuple[Point, ...] = statement.args
        a, b, c, x, y, z = args
        return f"{a.pretty_name} is to the same side of {b.pretty_name}->{c.pretty_name} as {x.pretty_name} is to {y.pretty_name}->{z.pretty_name}"
