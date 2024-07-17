from __future__ import annotations
from typing import TYPE_CHECKING, Any

from geosolver.dependency.symbols import Point
from geosolver.numerical import close_enough
from geosolver.predicates.predicate import IllegalPredicate, Predicate
from geosolver.reasoning_engines.algebraic_reasoning.tables import Ratio_Chase
from geosolver.tools import parse_len, str_to_nd
from geosolver.dependency.dependency import Dependency

if TYPE_CHECKING:
    from geosolver.reasoning_engines.algebraic_reasoning.tables import Table
    from geosolver.reasoning_engines.algebraic_reasoning.tables import SumCV
    from geosolver.dependency.dependency_graph import DependencyGraph
    from geosolver.statement import Statement


class ConstantLength(Predicate):
    """lconst A B L -
    Represent that the length of segment AB is L

    L should be given as a float.
    """

    NAME = "lconst"

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> tuple[Any, ...]:
        a, b, length = args
        if a == b:
            raise IllegalPredicate
        a, b = sorted((a, b))
        return tuple(dep_graph.symbols_graph.names2points((a, b))) + (
            parse_len(length),
        )

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        args: tuple[Point, Point, str] = statement.args
        a, b, length = args
        n, d = str_to_nd(length)
        return close_enough(a.num.distance(b.num), n / d)

    @classmethod
    def _prep_ar(cls, statement: Statement) -> tuple[list[SumCV], Table]:
        args: tuple[Point, Point, str] = statement.args
        p0, p1, _ = args
        table = statement.dep_graph.ar.rtable

        return [table.get_eq1(table.get_length(p0, p1))], table

    @classmethod
    def add(cls, dep: Dependency) -> None:
        eqs, table = cls._prep_ar(dep.statement)
        for eq in eqs:
            table.add_expr(eq, dep)

    @classmethod
    def check(cls, statement: Statement) -> bool:
        eqs, table = cls._prep_ar(statement)
        return all(table.expr_delta(eq) for eq in eqs)

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
    def to_tokens(cls, args: tuple[Any, ...]) -> tuple[str, ...]:
        return (args[0].name, args[1].name, args[2])

    @classmethod
    def pretty(cls, statement: Statement) -> str:
        a, b, length = statement.args
        return f"{a.pretty_name}{b.pretty_name} = {length}"
