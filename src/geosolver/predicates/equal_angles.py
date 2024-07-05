from __future__ import annotations
from typing import TYPE_CHECKING, Any

import numpy as np

from geosolver.numerical import close_enough
from geosolver.predicates.predicate import IllegalPredicate, Predicate
from geosolver.tools import reshape

if TYPE_CHECKING:
    from geosolver.dependency.dependency import Dependency
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
            dep_graph.symbols_graph.names2points(sum(sorted(min(groups, groups1)), ()))
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
    def add(cls, dep: Dependency) -> None:
        points: tuple[Point, ...] = dep.statement.args
        table = dep.statement.dep_graph.ar.atable
        symbols_graph = dep.statement.dep_graph.symbols_graph
        i = 4
        while i < len(points):
            table.add_expr(
                table.get_eq4(
                    symbols_graph.line_thru_pair(points[2], points[3]).name,
                    symbols_graph.line_thru_pair(points[0], points[1]).name,
                    symbols_graph.line_thru_pair(points[i + 2], points[i + 3]).name,
                    symbols_graph.line_thru_pair(points[i], points[i + 1]).name,
                ),
                dep,
            )
            i += 4

    @classmethod
    def check(cls, statement: Statement) -> bool:
        points: tuple[Point, ...] = statement.args
        table = statement.dep_graph.ar.atable
        symbols_graph = statement.dep_graph.symbols_graph
        for x, y in reshape(points, 2):
            if x == y:
                return False
        i = 4
        while i < len(points):
            if not table.add_expr(
                table.get_eq4(
                    symbols_graph.line_thru_pair(points[2], points[3]).name,
                    symbols_graph.line_thru_pair(points[0], points[1]).name,
                    symbols_graph.line_thru_pair(points[i + 2], points[i + 3]).name,
                    symbols_graph.line_thru_pair(points[i], points[i + 1]).name,
                ),
                None,
            ):
                return False
            i += 4
        return True

    @classmethod
    def to_tokens(cls, args: tuple[Any, ...]) -> tuple[str, ...]:
        return tuple(p.name for p in args)
