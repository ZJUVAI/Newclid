from __future__ import annotations
from typing import TYPE_CHECKING, Any

from numpy import log

from geosolver.dependency.dependency import Dependency
from geosolver.dependency.symbols import Point
from geosolver.numerical import close_enough
from geosolver.predicates.predicate import IllegalPredicate, Predicate
from geosolver.reasoning_engines.algebraic_reasoning.tables import Coef
from geosolver.tools import nd_to_ratio, str_to_nd

if TYPE_CHECKING:
    from geosolver.statement import Statement
    from geosolver.dependency.dependency_graph import DependencyGraph


class ConstantRatio(Predicate):
    """rconst A B C D r -
    Represent that AB / CD = r

    r should be given with numerator and denominator separated by '/', as in 2/3.
    """

    NAME = "rconst"

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> tuple[Any, ...]:
        a, b, c, d, r = args
        if a == b or c == d:
            raise IllegalPredicate
        num, denum = str_to_nd(r)
        a, b = sorted((a, b))
        c, d = sorted((c, d))
        if (a, b) > (c, d):
            a, b, c, d = c, d, a, b
            num, denum = denum, num
        return tuple(dep_graph.symbols_graph.names2points((a, b, c, d))) + (
            nd_to_ratio(num, denum),
        )

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        args: tuple[Point, Point, Point, Point, str] = statement.args
        a, b, c, d, r = args
        num, denum = str_to_nd(r)
        return close_enough(a.num.distance(b.num) / c.num.distance(d.num), num / denum)

    @classmethod
    def add(cls, dep: Dependency) -> None:
        args: tuple[Point, Point, Point, Point, str] = dep.statement.args
        p0, p1, p2, p3, k = args
        table = dep.statement.dep_graph.ar.rtable
        l0 = table.get_length(p0, p1)
        l1 = table.get_length(p2, p3)
        n, d = str_to_nd(k)
        table.add_expr(table.get_eq3(l0, l1, Coef(log(n / d))), dep)

    @classmethod
    def check(cls, statement: Statement) -> bool:
        args: tuple[Point, Point, Point, Point, str] = statement.args
        p0, p1, p2, p3, k = args
        table = statement.dep_graph.ar.rtable
        l0 = table.get_length(p0, p1)
        l1 = table.get_length(p2, p3)
        n, d = str_to_nd(k)
        return table.add_expr(table.get_eq3(l0, l1, Coef(log(n / d))), None)

    @classmethod
    def to_repr(cls, statement: Statement) -> str:
        args: tuple[Point, Point, Point, Point, str] = statement.args
        a, b, c, d, r = args
        assert isinstance(a, Point)
        assert isinstance(b, Point)
        assert isinstance(c, Point)
        assert isinstance(d, Point)
        return f"{a.name}{b.name}:{c.name}{d.name}={r}"
