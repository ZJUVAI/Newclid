from __future__ import annotations
from typing import TYPE_CHECKING, Any, Optional
from geosolver.dependencies.symbols import Point
from geosolver.numerical import close_enough
from geosolver.numerical.check import same_clock
from geosolver.predicates.predicate import Predicate
from geosolver.predicates.triangles_similar import two_triangles


if TYPE_CHECKING:
    from geosolver.dependencies.dependency_graph import DependencyGraph
    from geosolver.statement import Statement


class ContriClock(Predicate):
    """contri A B C P Q R -

    Represent that triangles ABC and PQR are congruent under orientation-preserving
    transformations taking A to P, B to Q and C to R.

    It is equivalent to the three eqangle and eqratio predicates
    on the corresponding angles and sides.
    """

    NAME = "contri"

    @classmethod
    def preparse(cls, args: tuple[str, ...]) -> Optional[tuple[str, ...]]:
        return two_triangles(*args)

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> Optional[tuple[Any, ...]]:
        twot = two_triangles(*args)
        return tuple(dep_graph.symbols_graph.names2points(twot)) if twot else None

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        args: tuple[Point, ...] = statement.args
        a, b, c, p, q, r = args
        return (
            close_enough(a.num.distance(b.num), p.num.distance(q.num))
            and close_enough(a.num.distance(c.num), p.num.distance(r.num))
            and close_enough(b.num.distance(c.num), q.num.distance(r.num))
            and same_clock(a.num, b.num, c.num, p.num, q.num, r.num)
        )

    @classmethod
    def to_tokens(cls, args: tuple[Any, ...]) -> tuple[str, ...]:
        return tuple(p.name for p in args)


class ContriReflect(Predicate):
    """contrir A B C P Q R -

    Represent that triangles ABC and PQR are congruent under orientation-preserving
    transformations taking A to P, B to Q and C to R.

    It is equivalent to the three eqangle and eqratio predicates
    on the corresponding angles and sides.
    """

    NAME = "contrir"

    @classmethod
    def preparse(cls, args: tuple[str, ...]) -> Optional[tuple[str, ...]]:
        return two_triangles(*args)

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> Optional[tuple[Any, ...]]:
        twot = two_triangles(*args)
        return tuple(dep_graph.symbols_graph.names2points(twot)) if twot else None

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        args: tuple[Point, ...] = statement.args
        a, b, c, p, q, r = args
        return (
            close_enough(a.num.distance(b.num), p.num.distance(q.num))
            and close_enough(a.num.distance(c.num), p.num.distance(r.num))
            and close_enough(b.num.distance(c.num), q.num.distance(r.num))
            and same_clock(a.num, b.num, c.num, p.num, r.num, q.num)
        )

    @classmethod
    def to_tokens(cls, args: tuple[Any, ...]) -> tuple[str, ...]:
        return tuple(p.name for p in args)
