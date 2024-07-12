from __future__ import annotations
from typing import TYPE_CHECKING, Any

from numpy import log

from geosolver.dependency.dependency import Dependency
from geosolver.dependency.symbols import Point
from geosolver.numerical import close_enough
from geosolver.predicates.predicate import IllegalPredicate, Predicate
from geosolver.reasoning_engines.algebraic_reasoning.tables import Coef, Ratio_Chase
from geosolver.tools import nd_to_ratio, str_to_nd

if TYPE_CHECKING:
    from geosolver.reasoning_engines.algebraic_reasoning.tables import Table
    from geosolver.reasoning_engines.algebraic_reasoning.tables import SumCV
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
    def _prep_ar(cls, statement: Statement) -> tuple[list[SumCV], Table]:
        args: tuple[Point, Point, Point, Point, str] = statement.args
        p0, p1, p2, p3, k = args
        table = statement.dep_graph.ar.rtable
        l0 = table.get_length(p0, p1)
        l1 = table.get_length(p2, p3)
        n, d = str_to_nd(k)
        return [table.get_eq3(l0, l1, Coef(log(n / d)))], table

    @classmethod
    def add(cls, dep: Dependency) -> None:
        eqs, table = cls._prep_ar(dep.statement)
        for eq in eqs:
            table.add_expr(eq, dep)

    @classmethod
    def check(cls, statement: Statement) -> bool:
        eqs, table = cls._prep_ar(statement)
        return all(table.add_expr(eq, None) for eq in eqs)

    @classmethod
    def why(cls, statement: Statement) -> Dependency:
        eqs, table = cls._prep_ar(statement)
        why: list[Dependency] = []
        for eq in eqs:
            why.extend(table.why(eq))
        if len(why) == 1:
            return why[0].with_new(statement)
        return Dependency.mk(
            statement, Ratio_Chase, tuple(dep.statement for dep in why)
        )

    @classmethod
    def pretty(cls, statement: Statement) -> str:
        args: tuple[Point, Point, Point, Point, str] = statement.args
        a, b, c, d, r = args
        return f"{a.pretty_name}{b.pretty_name}:{c.pretty_name}{d.pretty_name}={r}"
