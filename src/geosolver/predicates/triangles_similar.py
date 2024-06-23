from __future__ import annotations
from typing import TYPE_CHECKING, Generator, Optional

from geosolver.numerical.check import same_clock
import geosolver.predicates as preds
from geosolver.combinatorics import enum_triangle, enum_triangle_reflect
from geosolver.dependencies.dependency import Reason, Dependency


from geosolver.numerical import close_enough
from geosolver.numerical.geometries import PointNum

from geosolver.predicates.predicate import Predicate
from geosolver.intrinsic_rules import IntrinsicRules

from geosolver.geometry import Point
from geosolver.statements.statement import Statement, hash_triangle
from geosolver.symbols_graph import SymbolsGraph


if TYPE_CHECKING:
    from geosolver.dependencies.dependency_building import DependencyBody
    from geosolver.dependencies.why_graph import DependencyGraph


class SimtriClock(Predicate):
    """simtri A B C P Q R -

    Represent that triangles ABC and PQR are similar under orientation-preserving
    transformations taking A to P, B to Q and C to R.

    It is equivalent to the three eqangle and eqratio predicates
    on the corresponding angles and sides.
    """

    NAME = "simtri"

    @staticmethod
    def add(
        args: list[Point],
        dep_body: "DependencyBody",
        dep_graph: "DependencyGraph",
        symbols_graph: SymbolsGraph,
        disabled_intrinsic_rules: list[IntrinsicRules],
    ) -> tuple[list[Dependency], list[tuple[Statement, Dependency]]]:
        """Add two similar triangles."""
        add, to_cache = [], []
        hashs = [dep.statement.hash_tuple for dep in dep_body.why]

        for points in enum_triangle(args):
            eqangle6 = Statement(preds.EqAngle6, points)
            if eqangle6.hash_tuple in hashs:
                continue
            _add, _to_cache = preds.EqAngle6.add(
                points, dep_body, dep_graph, symbols_graph, disabled_intrinsic_rules
            )
            add += _add
            to_cache += _to_cache

            eqratio6 = Statement(preds.EqRatio6, points)
            if eqratio6.hash_tuple in hashs:
                continue
            _add, _to_cache = preds.EqRatio6.add(
                points, dep_body, dep_graph, symbols_graph, disabled_intrinsic_rules
            )
            add += _add
            to_cache += _to_cache

        statement = Statement(SimtriClock, tuple(args))
        dep = dep_graph.build_dependency(statement, dep_body)
        add.append(dep)
        to_cache.append((statement, dep))
        return add, to_cache

    @staticmethod
    def why(
        dep_graph: "DependencyGraph", statement: Statement
    ) -> tuple[Optional[Reason], list[Dependency]]:
        raise NotImplementedError

    @staticmethod
    def check(args: list[Point], symbols_graph: SymbolsGraph) -> bool:
        """Check abc and xyz are similar triangles."""
        a, b, c, x, y, z = args
        return preds.EqAngle.check(
            [a, b, a, c, x, y, x, z], symbols_graph
        ) and preds.EqAngle.check([b, a, b, c, y, x, y, z], symbols_graph)

    @staticmethod
    def check_numerical(args: list[PointNum]) -> bool:
        """Check if 6 points make a pair of similar triangles."""
        return SimtriAny.check_numerical(args)

    @staticmethod
    def enumerate(
        symbols_graph: SymbolsGraph,
    ) -> Generator[tuple[Point, ...], None, None]:
        raise NotImplementedError

    @staticmethod
    def pretty(args: list[str]) -> str:
        a, b, c, x, y, z = args
        return f"\u0394{a}{b}{c} is similar clockwise to \u0394{x}{y}{z}"

    @classmethod
    def hash(cls, args: list[Point]) -> tuple[str, ...]:
        return hash_triangle(cls.NAME, args)


class SimtriReflect(Predicate):
    """simtrir A B C P Q R -

    Represent that triangles ABC and PQR are similar under orientation-preserving
    transformations taking A to P, B to Q and C to R.

    It is equivalent to the three eqangle and eqratio predicates
    on the corresponding angles and sides.
    """

    NAME = "simtrir"

    @staticmethod
    def add(
        args: list[Point],
        dep_body: "DependencyBody",
        dep_graph: "DependencyGraph",
        symbols_graph: SymbolsGraph,
        disabled_intrinsic_rules: list[IntrinsicRules],
    ) -> tuple[list[Dependency], list[tuple[Statement, Dependency]]]:
        """Add two similar reflected triangles."""
        add, to_cache = [], []
        hashs = [dep.statement.hash_tuple for dep in dep_body.why]
        for points in enum_triangle_reflect(args):
            eqangle6 = Statement(preds.EqAngle6, points)
            if eqangle6.hash_tuple in hashs:
                continue
            _add, _to_cache = eqangle6.add(
                dep_body, dep_graph, symbols_graph, disabled_intrinsic_rules
            )
            add += _add
            to_cache += _to_cache

        for points in enum_triangle(args):
            eqratio6 = Statement(preds.EqRatio6, points)
            if eqratio6.hash_tuple in hashs:
                continue
            _add, _to_cache = eqratio6.add(
                dep_body, dep_graph, symbols_graph, disabled_intrinsic_rules
            )
            add += _add
            to_cache += _to_cache

        statement = Statement(SimtriReflect, tuple(args))
        dep = dep_graph.build_dependency(statement, dep_body)
        add.append(dep)
        to_cache.append((statement, dep))
        return add, to_cache

    @staticmethod
    def why(
        dep_graph: "DependencyGraph", statement: Statement
    ) -> tuple[Optional[Reason], list[Dependency]]:
        raise NotImplementedError

    @staticmethod
    def check(args: list[Point], symbols_graph: SymbolsGraph) -> bool:
        """Check abc and xyz are similar triangles."""
        a, b, c, x, y, z = args
        return preds.EqAngle.check(
            [a, b, a, c, x, z, x, y], symbols_graph
        ) and preds.EqAngle.check([b, a, b, c, y, z, y, x], symbols_graph)

    @staticmethod
    def check_numerical(args: list[PointNum]) -> bool:
        """Check if 6 points make a pair of similar triangles."""
        return SimtriAny.check_numerical(args)

    @staticmethod
    def enumerate(
        symbols_graph: SymbolsGraph,
    ) -> Generator[tuple[Point, ...], None, None]:
        raise NotImplementedError

    @staticmethod
    def pretty(args: list[str]) -> str:
        a, b, c, x, y, z = args
        return f"\u0394{a}{b}{c} is similar reflected to \u0394{x}{y}{z}"

    @classmethod
    def hash(cls, args: list[Point]) -> tuple[str, ...]:
        return hash_triangle(cls.NAME, args)


class SimtriAny(Predicate):
    """simtri* A B C P Q R -

    Represent that triangles ABC and PQR are similar.

    It is equivalent to the three eqangle and eqratio predicates
    on the corresponding angles and sides.
    """

    NAME = "simtri*"

    @staticmethod
    def add(
        args: list[Point],
        dep_body: "DependencyBody",
        dep_graph: "DependencyGraph",
        symbols_graph: SymbolsGraph,
        disabled_intrinsic_rules: list[IntrinsicRules],
    ) -> tuple[list[Dependency], list[tuple[Statement, Dependency]]]:
        """Add two similar triangles."""
        if same_clock(*[p.num for p in args]):
            added, to_cache = SimtriClock.add(
                args, dep_body, dep_graph, symbols_graph, disabled_intrinsic_rules
            )
        else:
            added, to_cache = SimtriReflect.add(
                args, dep_body, dep_graph, symbols_graph, disabled_intrinsic_rules
            )
        statement = Statement(SimtriAny, tuple(args))
        dep = dep_graph.build_dependency(statement, dep_body)
        added.append(dep)
        to_cache.append((statement, dep))
        return added, to_cache

    @staticmethod
    def why(
        dep_graph: "DependencyGraph", statement: Statement
    ) -> tuple[Optional[Reason], list[Dependency]]:
        raise NotImplementedError

    @staticmethod
    def check(args: list[Point], symbols_graph: SymbolsGraph) -> bool:
        """Check abc and xyz are similar triangles."""
        clock = SimtriClock.check(args, symbols_graph)
        reflect = SimtriReflect.check(args, symbols_graph)
        return clock or reflect

    @staticmethod
    def check_numerical(args: list[PointNum]) -> bool:
        """Check if 6 points make a pair of similar triangles."""
        a, b, c, x, y, z = args
        ab = a.distance(b)
        bc = b.distance(c)
        ca = c.distance(a)
        xy = x.distance(y)
        yz = y.distance(z)
        zx = z.distance(x)
        return close_enough(ab * yz, bc * xy) and close_enough(bc * zx, ca * yz)

    @staticmethod
    def enumerate(
        symbols_graph: SymbolsGraph,
    ) -> Generator[tuple[Point, ...], None, None]:
        raise NotImplementedError

    @staticmethod
    def pretty(args: list[str]) -> str:
        a, b, c, x, y, z = args
        return f"\u0394{a}{b}{c} is similar to \u0394{x}{y}{z}"

    @classmethod
    def hash(cls, args: list[Point]) -> tuple[str, ...]:
        return hash_triangle(cls.NAME, args)
