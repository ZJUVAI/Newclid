from __future__ import annotations
from typing import TYPE_CHECKING, Any

import numpy as np

from geosolver.numerical import close_enough
from geosolver.predicates.predicate import IllegalPredicate, Predicate
from geosolver.reasoning_engines.algebraic_reasoning.tables import Angle_Chase
from geosolver.tools import reshape
from geosolver.dependency.dependency import Dependency

if TYPE_CHECKING:
    from geosolver.reasoning_engines.algebraic_reasoning.tables import Table
    from geosolver.reasoning_engines.algebraic_reasoning.tables import SumCV
    from geosolver.dependency.dependency_graph import DependencyGraph
    from geosolver.statement import Statement
    from geosolver.dependency.symbols import Point


class EqAngle(Predicate):
    """eqangle AB CD EF GH -
    Represent that one can rigidly move the crossing of lines AB and CD
    to get on top of the crossing of EF and GH, respectively (no reflections allowed).

    In particular, eqangle AB CD CD AB is only true if AB is perpendicular to CD.
    """

    NAME = "eqangle"

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> tuple[Any, ...]:
        groups: list[tuple[str, str, str, str]] = []
        groups1: list[tuple[str, str, str, str]] = []
        for a, b, c, d in reshape(args, 4):
            if a == b or c == d:
                raise IllegalPredicate
            a, b = sorted((a, b))
            c, d = sorted((c, d))
            groups.append((a, b, c, d))
            groups1.append((c, d, a, b))
        return tuple(
            dep_graph.symbols_graph.names2points(
                sum(min(sorted(groups), sorted(groups1)), ())
            )
        )

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        args: tuple[Point, ...] = statement.args
        angle = None
        for a, b, c, d in reshape(list(args), 4):
            _angle = ((d.num - c.num).angle() - (b.num - a.num).angle()) % np.pi
            if angle is not None and not close_enough(angle, _angle):
                return False
            angle = _angle
        return True

    @classmethod
    def _prep_ar(cls, statement: Statement) -> tuple[list[SumCV], Table]:
        points: tuple[Point, ...] = statement.args
        table = statement.dep_graph.ar.atable
        symbols_graph = statement.dep_graph.symbols_graph
        eqs: list[SumCV] = []
        i = 4
        while i < len(points):
            eqs.append(
                table.get_eq4(
                    symbols_graph.line_thru_pair(points[2], points[3]).name,
                    symbols_graph.line_thru_pair(points[0], points[1]).name,
                    symbols_graph.line_thru_pair(points[i + 2], points[i + 3]).name,
                    symbols_graph.line_thru_pair(points[i], points[i + 1]).name,
                )
            )
            i += 4
        return eqs, table

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
            statement, Angle_Chase, tuple(dep.statement for dep in why)
        )

    @classmethod
    def to_constructive(cls, point: str, args: tuple[str, ...]) -> str:
        a, b, c, d, e, f = args

        if point in [d, e, f]:
            a, b, c, d, e, f = d, e, f, a, b, c

        x, b, y, c, d = b, c, e, d, f
        if point == b:
            a, b, c, d = b, a, d, c

        if point == d and x == y:  # x p x b = x c x p
            return f"angle_bisector {point} {b} {x} {c}"

        if point == x:
            return f"eqangle3 {x} {a} {b} {y} {c} {d}"

        return f"on_aline {a} {x} {b} {c} {y} {d}"

    @classmethod
    def to_tokens(cls, args: tuple[Any, ...]) -> tuple[str, ...]:
        return tuple(p.name for p in args)

    @classmethod
    def pretty(cls, statement: Statement) -> str:
        args: tuple[Point, ...] = statement.args
        return " = ".join(
            f"∠({a.pretty_name}{b.pretty_name},{c.pretty_name}{d.pretty_name})"
            for a, b, c, d in reshape(args, 4)
        )
