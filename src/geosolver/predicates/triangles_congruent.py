from __future__ import annotations
from typing import TYPE_CHECKING, Any
from geosolver.dependency.dependency import Dependency
from geosolver.dependency.symbols import Point
from geosolver.numerical import close_enough
from geosolver.numerical.check import same_clock
from geosolver.predicates.predicate import Predicate
from geosolver.predicates.triangles_similar import two_triangles


if TYPE_CHECKING:
    from geosolver.dependency.dependency import Dependency
    from geosolver.dependency.dependency_graph import DependencyGraph
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
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> tuple[Any, ...]:
        return tuple(dep_graph.symbols_graph.names2points(two_triangles(*args)))

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        args: tuple[Point, ...] = statement.args
        a, b, c, p, q, r = args
        return (
            close_enough(a.num.distance(b.num) - p.num.distance(q.num), 0)
            and close_enough(a.num.distance(c.num) - p.num.distance(r.num), 0)
            and close_enough(b.num.distance(c.num) - q.num.distance(r.num), 0)
            and same_clock(a.num, b.num, c.num, p.num, q.num, r.num)
        )

    @classmethod
    def add(cls, dep: Dependency) -> None:
        dep.with_new(dep.statement.with_new(ContriAny, None)).add()

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
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> tuple[Any, ...]:
        return tuple(dep_graph.symbols_graph.names2points(two_triangles(*args)))

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        args: tuple[Point, ...] = statement.args
        a, b, c, p, q, r = args
        return (
            close_enough(a.num.distance(b.num) - p.num.distance(q.num), 0)
            and close_enough(a.num.distance(c.num) - p.num.distance(r.num), 0)
            and close_enough(b.num.distance(c.num) - q.num.distance(r.num), 0)
            and not same_clock(a.num, b.num, c.num, p.num, q.num, r.num)
        )

    @classmethod
    def add(cls, dep: Dependency) -> None:
        dep.with_new(dep.statement.with_new(ContriAny, None)).add()

    @classmethod
    def to_tokens(cls, args: tuple[Any, ...]) -> tuple[str, ...]:
        return tuple(p.name for p in args)


class ContriAny(Predicate):
    """contri* A B C P Q R -

    Represent that triangles ABC and PQR are congruent.

    It is equivalent to the three eqangle and eqratio predicates
    on the corresponding angles and sides.
    """

    NAME = "contri*"

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> tuple[Any, ...]:
        return tuple(dep_graph.symbols_graph.names2points(two_triangles(*args)))

    @classmethod
    def add(cls, dep: Dependency) -> None:
        args: tuple[Point, ...] = dep.statement.args
        a, b, c, p, q, r = args
        if same_clock(a.num, b.num, c.num, p.num, q.num, r.num):
            dep.with_new(dep.statement.with_new(ContriClock, None)).add()
        else:
            dep.with_new(dep.statement.with_new(ContriReflect, None)).add()

    @classmethod
    def check(cls, statement: Statement) -> bool:
        return (
            statement.with_new(ContriClock, None).check()
            or statement.with_new(ContriReflect, None).check()
        )

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        args: tuple[Point, ...] = statement.args
        a, b, c, p, q, r = args
        return (
            close_enough(a.num.distance(b.num) - p.num.distance(q.num), 0)
            and close_enough(a.num.distance(c.num) - p.num.distance(r.num), 0)
            and close_enough(b.num.distance(c.num) - q.num.distance(r.num), 0)
        )

    @classmethod
    def to_tokens(cls, args: tuple[Any, ...]) -> tuple[str, ...]:
        return tuple(p.name for p in args)
