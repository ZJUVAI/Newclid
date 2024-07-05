from __future__ import annotations
from typing import TYPE_CHECKING, Any
from geosolver.dependency.symbols import Point
from geosolver.numerical import close_enough
from geosolver.numerical.check import same_clock
from geosolver.predicates.predicate import Predicate


if TYPE_CHECKING:
    from geosolver.dependency.dependency_graph import DependencyGraph
    from geosolver.statement import Statement


class SimtriClock(Predicate):
    """simtri A B C P Q R -

    Represent that triangles ABC and PQR are similar under orientation-preserving
    transformations taking A to P, B to Q and C to R.

    It is equivalent to the three eqangle and eqratio predicates
    on the corresponding angles and sides.
    """

    NAME = "simtri"

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> tuple[Any, ...]:
        a, b, c, p, q, r = args
        (a, p), (b, q), (c, r) = sorted(((a, p), (b, q), (c, r)))
        return tuple(
            dep_graph.symbols_graph.names2points(
                min(
                    (a, b, c, p, q, r),
                    (p, q, r, a, b, c),
                )
            )
        )

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        args: tuple[Point, ...] = statement.args
        a, b, c, p, q, r = args
        k = p.num.distance(q.num) / a.num.distance(b.num)
        return (
            close_enough(a.num.distance(c.num) * k - p.num.distance(r.num), 0)
            and close_enough(b.num.distance(c.num) * k - q.num.distance(r.num), 0)
            and same_clock(a.num, b.num, c.num, p.num, q.num, r.num)
        )


class SimtriReflect(Predicate):
    """simtrir A B C P Q R -

    Represent that triangles ABC and PQR are similar under orientation-preserving
    transformations taking A to P, B to Q and C to R.

    It is equivalent to the three eqangle and eqratio predicates
    on the corresponding angles and sides.
    """

    NAME = "simtrir"

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> tuple[Any, ...]:
        a, b, c, p, q, r = args
        (a, p), (b, q), (c, r) = sorted(((a, p), (b, q), (c, r)))
        return tuple(
            dep_graph.symbols_graph.names2points(
                min(
                    (a, b, c, p, q, r),
                    (p, q, r, a, b, c),
                )
            )
        )

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        args: tuple[Point, ...] = statement.args
        a, b, c, p, q, r = args
        k = p.num.distance(q.num) / a.num.distance(b.num)
        return (
            close_enough(a.num.distance(c.num) * k - p.num.distance(r.num), 0)
            and close_enough(b.num.distance(c.num) * k - q.num.distance(r.num), 0)
            and not same_clock(a.num, b.num, c.num, p.num, q.num, r.num)
        )


class SimtriAny(Predicate):
    """simtri* A B C P Q R -

    Represent that triangles ABC and PQR are similar.

    It is equivalent to the three eqangle and eqratio predicates
    on the corresponding angles and sides.
    """

    NAME = "simtri*"

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> tuple[Any, ...]:
        a, b, c, p, q, r = args
        (a, p), (b, q), (c, r) = sorted(((a, p), (b, q), (c, r)))
        return tuple(
            dep_graph.symbols_graph.names2points(
                min(
                    (a, b, c, p, q, r),
                    (p, q, r, a, b, c),
                )
            )
        )

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        args: tuple[Point, ...] = statement.args
        a, b, c, p, q, r = args
        k = p.num.distance(q.num) / a.num.distance(b.num)
        return close_enough(
            a.num.distance(c.num) * k - p.num.distance(r.num), 0
        ) and close_enough(b.num.distance(c.num) * k - q.num.distance(r.num), 0)
