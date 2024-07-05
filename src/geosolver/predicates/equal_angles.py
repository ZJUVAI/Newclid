from __future__ import annotations
from typing import TYPE_CHECKING, Any

import numpy as np

from geosolver.numerical import close_enough
from geosolver.predicates.predicate import Predicate
from geosolver.tools import reshape

if TYPE_CHECKING:
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
            a, b = sorted((a, b))
            c, d = sorted((c, d))
            groups.append((a, b, c, d))
            groups1.append((c, d, a, b))
        return tuple(
            dep_graph.symbols_graph.names2points(sum(sorted(min(groups, groups1)), ()))
        )

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        angle = None
        for a, b, c, d in reshape(list(statement.args), 4):
            a: Point
            b: Point
            c: Point
            d: Point
            _angle = ((d.num - c.num).angle() - (b.num - a.num).angle()) % np.pi
            if angle is not None and not close_enough(angle, _angle):
                return False
            angle = _angle
        return True


class EqAngle6(EqAngle):
    """eqangle6 AB CD EF -"""

    NAME = "eqangle6"
