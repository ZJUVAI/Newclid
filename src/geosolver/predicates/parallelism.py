from __future__ import annotations
from typing import TYPE_CHECKING, Any

import numpy as np
from geosolver.dependency.symbols import Point
from geosolver.numerical import close_enough
from geosolver.numerical.geometries import LineNum
from geosolver.predicates.congruence import Cong
from geosolver.predicates.predicate import Predicate
from geosolver.tools import reshape

if TYPE_CHECKING:
    from geosolver.dependency.dependency_graph import DependencyGraph
    from geosolver.dependency.dependency import Dependency
    from geosolver.statement import Statement


class Para(Predicate):
    """para A B C D -
    Represent that the line AB is parallel to the line CD.
    """

    NAME = "para"

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> tuple[Any, ...]:
        return Cong.parse(args, dep_graph)

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        args: tuple[Point] = statement.args
        angle = None
        for a, b in reshape(list(args), 2):
            _angle = (b.num - a.num).angle() % np.pi
            if angle is not None and not close_enough(angle, _angle):
                return False
            angle = _angle
        return True

    @classmethod
    def add(cls, dep: Dependency):
        points: tuple[Point, ...] = dep.statement.args
        table = dep.statement.dep_graph.ar.atable
        symbols_graph = dep.statement.dep_graph.symbols_graph
        assert len(points) % 2 == 0
        i = 2
        while i < len(points):
            table.add_expr(
                table.get_eq2(
                    symbols_graph.line_thru_pair(points[0], points[1]).name,
                    symbols_graph.line_thru_pair(points[i], points[i + 1]).name,
                ),
                dep,
            )
            i += 2

    @classmethod
    def check(cls, statement: Statement) -> bool:
        points: tuple[Point, ...] = statement.args
        table = statement.dep_graph.ar.atable
        symbols_graph = statement.dep_graph.symbols_graph
        assert len(points) % 2 == 0
        i = 2
        while i < len(points):
            if not table.add_expr(
                table.get_eq2(
                    symbols_graph.line_thru_pair(points[0], points[1]).name,
                    symbols_graph.line_thru_pair(points[i], points[i + 1]).name,
                ),
                None,
            ):
                return False
            i += 2
        return True


class NPara(Predicate):
    """npara A B C D -
    Represent that lines AB and CD are NOT parallel.

    It can only be numerically checked
    (angular coefficient of the equations of the lines are different).
    """

    NAME = "npara"

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> tuple[Any, ...]:
        return Para.parse(args, dep_graph)

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        a, b, c, d = statement.args
        assert isinstance(a, Point)
        assert isinstance(b, Point)
        assert isinstance(c, Point)
        assert isinstance(d, Point)
        l1 = LineNum(a.num, b.num)
        l2 = LineNum(c.num, d.num)
        return not l1.is_parallel(l2)
