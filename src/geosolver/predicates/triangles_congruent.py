from __future__ import annotations
from typing import TYPE_CHECKING, Generator, Optional

import geosolver.predicates as preds
from geosolver.combinatorics import enum_sides, enum_triangle, enum_triangle_reflect
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


class Contri(Predicate):
    """contri A B C P Q R -

    Represent that triangles ABC and PQR are similar under orientation-preserving
    transformations taking A to P, B to Q and C to R.

    It is equivalent to the three eqangle and eqratio predicates
    on the corresponding angles and sides.
    """

    NAME = "contri"

    @staticmethod
    def add(
        args: list[Point],
        dep_body: "DependencyBody",
        dep_graph: "DependencyGraph",
        symbols_graph: SymbolsGraph,
        disabled_intrinsic_rules: list[IntrinsicRules],
    ) -> tuple[list[Dependency], list[tuple[Statement, Dependency]]]:
        """Add two congruent triangles."""
        add, to_cache = [], []
        hashs = [dep.statement.hash_tuple for dep in dep_body.why]
        for args in enum_triangle(args):
            eqangle6 = Statement(preds.EqAngle6, args)
            if eqangle6.hash_tuple in hashs:
                continue
            _add, _to_cache = preds.EqAngle.add(
                args, dep_body, dep_graph, symbols_graph, disabled_intrinsic_rules
            )
            add += _add
            to_cache += _to_cache

        for args in enum_sides(args):
            cong = Statement(preds.Cong, args)
            if cong.hash_tuple in hashs:
                continue
            _add, _to_cache = preds.Cong.add(
                args, dep_body, dep_graph, symbols_graph, disabled_intrinsic_rules
            )
            add += _add
            to_cache += _to_cache

        statement = Statement(Contri, tuple(args))
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
        """Check abc and xyz are unreflected congruant triangles."""
        a, b, c, x, y, z = args
        contri = (
            preds.Cong.check([a, b, x, y], symbols_graph)
            and preds.Cong.check([b, c, y, z], symbols_graph)
            and preds.Cong.check([c, a, z, x], symbols_graph)
        )
        return contri and preds.Simtri.check(args)

    @staticmethod
    def check_numerical(args: list[PointNum]) -> bool:
        """Check if 6 points make a pair of congurant triangle."""
        a, b, c, x, y, z = args
        ab = a.distance(b)
        bc = b.distance(c)
        ca = c.distance(a)
        xy = x.distance(y)
        yz = y.distance(z)
        zx = z.distance(x)
        return close_enough(ab, xy) and close_enough(bc, yz) and close_enough(ca, zx)

    @staticmethod
    def enumerate(
        symbols_graph: SymbolsGraph,
    ) -> Generator[tuple[Point, ...], None, None]:
        raise NotImplementedError

    @staticmethod
    def pretty(args: list[str]) -> str:
        a, b, c, x, y, z = args
        return f"\u0394{a}{b}{c} is similar unreflected to \u0394{x}{y}{z}"

    @classmethod
    def hash(cls, args: list[Point]) -> tuple[str, ...]:
        return hash_triangle(cls.NAME, args)


class ContriReflect(Predicate):
    """contrir A B C P Q R -

    Represent that triangles ABC and PQR are similar under orientation-preserving
    transformations taking A to P, B to Q and C to R.

    It is equivalent to the three eqangle and eqratio predicates
    on the corresponding angles and sides.
    """

    NAME = "contrir"

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
        for args in enum_triangle_reflect(args):
            eqangle6 = Statement(preds.EqAngle6, args)
            if eqangle6.hash_tuple in hashs:
                continue
            _add, _to_cache = preds.EqAngle6.add(
                args, dep_body, dep_graph, symbols_graph, disabled_intrinsic_rules
            )
            add += _add
            to_cache += _to_cache

        for args in enum_triangle(args):
            eqratio6 = Statement(preds.EqRatio6, args)
            if eqratio6.hash_tuple in hashs:
                continue
            _add, _to_cache = preds.EqRatio6.add(
                args, dep_body, dep_graph, symbols_graph, disabled_intrinsic_rules
            )
            add += _add
            to_cache += _to_cache

        statement = Statement(ContriReflect, tuple(args))
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
        """Check abc and xyz are reflected congruant triangles."""
        a, b, c, x, y, z = args
        contri = (
            preds.Cong.check([a, b, x, y], symbols_graph)
            and preds.Cong.check([b, c, y, z], symbols_graph)
            and preds.Cong.check([c, a, z, x], symbols_graph)
        )
        return contri and preds.SimtriReflect.check(args)

    @staticmethod
    def check_numerical(args: list[PointNum]) -> bool:
        """Check if 6 points make a pair of congurant triangle."""
        a, b, c, x, y, z = args
        ab = a.distance(b)
        bc = b.distance(c)
        ca = c.distance(a)
        xy = x.distance(y)
        yz = y.distance(z)
        zx = z.distance(x)
        return close_enough(ab, xy) and close_enough(bc, yz) and close_enough(ca, zx)

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
