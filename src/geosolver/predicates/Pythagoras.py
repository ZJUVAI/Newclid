from __future__ import annotations
import logging
from typing import TYPE_CHECKING, Any, Optional

from geosolver.predicates.constant_length import ConstantLength
from geosolver.dependency.dependency import Dependency
from geosolver.dependency.symbols import Point
from geosolver.numerical import close_enough
from geosolver.predicates.perpendicularity import Perp
from geosolver.predicates.predicate import IllegalPredicate, Predicate
from geosolver.tools import InfQuotientError, float_to_len

if TYPE_CHECKING:
    from geosolver.dependency.dependency_graph import DependencyGraph
    from geosolver.statement import Statement


class PythagoreanPremises(Predicate):
    """PythagoreanPremises a b c
    abc is in the form of a right angled triangle. ab is perpendicular to ac
    """

    NAME = "PythagoreanPremises"

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> tuple[Any, ...]:
        a, b, c = args
        if a == b or a == c:
            raise IllegalPredicate
        b, c = sorted((b, c))
        return tuple(dep_graph.symbols_graph.names2points((a, b, c)))

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        args: tuple[Point, ...] = statement.args
        a, b, c = args
        return close_enough(abs((a.num - b.num).dot(a.num - c.num)), 0)

    @classmethod
    def check(cls, statement: Statement) -> bool:
        return statement.why() is not None

    @classmethod
    def pretty(cls, statement: Statement) -> str:
        args: tuple[Point, ...] = statement.args
        a, b, c = args
        return f"Pythagorean Theorem's premises on {a.pretty_name}, {b.pretty_name}, {c.pretty_name} are satisfied"

    @classmethod
    def why(cls, statement: Statement) -> Optional[Dependency]:
        args: tuple[Point, ...] = statement.args
        a, b, c = args
        perp = statement.with_new(Perp, (a, b, a, c))
        perp_check = perp.check()
        table = statement.dep_graph.ar.rtable
        eq0 = table.get_eq1(table.get_length(a, b))
        eq1 = table.get_eq1(table.get_length(a, c))
        eq2 = table.get_eq1(table.get_length(b, c))
        d0 = table.expr_delta(eq0)
        d1 = table.expr_delta(eq1)
        d2 = table.expr_delta(eq2)
        if d0 and d1 and d2:
            return Dependency.mk(
                statement,
                "Pythagoras",
                (
                    statement.with_new(
                        ConstantLength, (a, b, float_to_len(a.num.distance(b.num)))
                    ),
                    statement.with_new(
                        ConstantLength, (a, c, float_to_len(a.num.distance(c.num)))
                    ),
                    statement.with_new(
                        ConstantLength, (b, c, float_to_len(b.num.distance(c.num)))
                    ),
                ),
            )
        if perp_check and d1 and d2:
            return Dependency.mk(
                statement,
                "Pythagoras",
                (
                    perp,
                    statement.with_new(
                        ConstantLength, (a, c, float_to_len(a.num.distance(c.num)))
                    ),
                    statement.with_new(
                        ConstantLength, (b, c, float_to_len(b.num.distance(c.num)))
                    ),
                ),
            )
        if perp_check and d0 and d2:
            return Dependency.mk(
                statement,
                "Pythagoras",
                (
                    statement.with_new(
                        ConstantLength, (a, b, float_to_len(a.num.distance(b.num)))
                    ),
                    perp,
                    statement.with_new(
                        ConstantLength, (b, c, float_to_len(b.num.distance(c.num)))
                    ),
                ),
            )
        if perp_check and d0 and d1:
            return Dependency.mk(
                statement,
                "Pythagoras",
                (
                    statement.with_new(
                        ConstantLength, (a, b, float_to_len(a.num.distance(b.num)))
                    ),
                    statement.with_new(
                        ConstantLength, (a, c, float_to_len(a.num.distance(c.num)))
                    ),
                    perp,
                ),
            )
        return None


class PythagoreanConclusions(Predicate):
    NAME = "PythagoreanConclusions"

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> tuple[Any, ...]:
        return PythagoreanPremises.parse(args, dep_graph)

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        return PythagoreanPremises.check_numerical(statement)

    @classmethod
    def add(cls, dep: Dependency):
        statement = dep.statement
        args: tuple[Point, ...] = statement.args
        a, b, c = args
        perp = statement.with_new(Perp, (a, b, a, c))
        perp_check = perp.check()
        if not perp_check:
            dep.with_new(perp).add()
        table = statement.dep_graph.ar.rtable
        eq0 = table.get_eq1(table.get_length(a, b))
        eq1 = table.get_eq1(table.get_length(a, c))
        eq2 = table.get_eq1(table.get_length(b, c))
        d0 = table.expr_delta(eq0)
        d1 = table.expr_delta(eq1)
        d2 = table.expr_delta(eq2)
        try:
            if not d0:
                dep.with_new(
                    statement.with_new(
                        ConstantLength, (a, b, float_to_len(a.num.distance(b.num)))
                    )
                ).add()
            if not d1:
                dep.with_new(
                    statement.with_new(
                        ConstantLength, (a, c, float_to_len(a.num.distance(c.num)))
                    )
                ).add()
            if not d2:
                dep.with_new(
                    statement.with_new(
                        ConstantLength, (b, c, float_to_len(b.num.distance(c.num)))
                    )
                ).add()
        except InfQuotientError:
            logging.info(
                "lconst result could be added, but the irrational number len cannot be represented."
            )
