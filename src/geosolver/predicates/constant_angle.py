from __future__ import annotations
from numpy import pi
from typing import TYPE_CHECKING, Any

from geosolver.dependency.symbols import Point
from geosolver.numerical import close_enough
from geosolver.predicates.predicate import IllegalPredicate, Predicate
from geosolver.reasoning_engines.algebraic_reasoning.tables import Angle_Chase, Coef
from geosolver.tools import nd_to_angle, str_to_nd
from geosolver.dependency.dependency import Dependency

if TYPE_CHECKING:
    from geosolver.reasoning_engines.algebraic_reasoning.tables import Table
    from geosolver.reasoning_engines.algebraic_reasoning.tables import SumCV
    from geosolver.dependency.dependency_graph import DependencyGraph
    from geosolver.statement import Statement


class ConstantAngle(Predicate):
    """aconst AB CD Y -
    Represent that the rotation needed to go from line AB to line CD,
    oriented on the clockwise direction is Y.

    The syntax of Y is either a fraction of pi like 2pi/3 for radians
    or a number followed by a 'o' like 120o for degree.
    """

    NAME = "aconst"

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> tuple[Any, ...]:
        a, b, c, d, y = args
        if a == b or c == d:
            raise IllegalPredicate
        a, b = sorted((a, b))
        c, d = sorted((c, d))
        num, denum = str_to_nd(y)
        if (a, b) > (c, d):
            a, b, c, d = c, d, a, b
            num = -num
        return tuple(dep_graph.symbols_graph.names2points((a, b, c, d))) + (
            nd_to_angle(num, denum),
        )

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        args: tuple[Point, Point, Point, Point, str] = statement.args
        a, b, c, d, y = args
        num, denum = str_to_nd(y)
        angle = num / denum * pi
        return close_enough(
            angle, ((c.num - d.num).angle() - (a.num - b.num).angle()) % pi
        )

    @classmethod
    def _prep_ar(cls, statement: Statement) -> tuple[list[SumCV], Table]:
        args: tuple[Point, Point, Point, Point, str] = statement.args
        p0, p1, p2, p3, ang = args
        table = statement.dep_graph.ar.atable
        symbols_graph = statement.dep_graph.symbols_graph
        n, d = str_to_nd(ang)

        return [
            table.get_eq3(
                symbols_graph.line_thru_pair(p2, p3).name,
                symbols_graph.line_thru_pair(p0, p1).name,
                Coef(n / d),
            )
        ], table

    @classmethod
    def add(cls, dep: Dependency) -> None:
        eqs, table = cls._prep_ar(dep.statement)
        for eq in eqs:
            table.add_expr(eq, dep)

    @classmethod
    def why(cls, statement: Statement) -> Dependency:
        eqs, table = cls._prep_ar(statement)
        why: list[Dependency] = []
        for eq in eqs:
            why.extend(table.why(eq))
        if len(why) == 1:
            return why[0].with_new(statement)
        return Dependency.mk(
            statement, Angle_Chase, tuple(dep.statement for dep in why)
        )

    @classmethod
    def check(cls, statement: Statement) -> bool:
        eqs, table = cls._prep_ar(statement)
        return all(table.add_expr(eq, None) for eq in eqs)
