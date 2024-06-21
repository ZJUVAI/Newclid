from __future__ import annotations
from typing import Generator, Optional
from typing_extensions import Self

from geosolver.combinatorics import all_4points, cross_product
from geosolver.dependencies.dependency import Dependency, Reason
from geosolver.dependencies.dependency_building import DependencyBody
from geosolver.dependencies.why_graph import WhyHyperGraph
from geosolver.geometry import Angle, Line, Point, Ratio
from geosolver.intrinsic_rules import IntrinsicRules
from geosolver.numerical.geometries import LineNum, PointNum
from geosolver.predicates.predicate import Predicate
from geosolver.statements.statement import Statement, hashed_unordered_two_lines_points
from geosolver.symbols_graph import SymbolsGraph, is_equal

from geosolver.predicates.coll import Coll
from geosolver.predicates.collx import Collx
from geosolver.predicates.para import Para
from geosolver.predicates.eqangle import EqAngle, why_eqangle_directions


class Perp(Predicate):
    """perp A B C D -
    Represent that the line AB is perpendicular to the line CD.
    """

    NAME = "perp"

    @staticmethod
    def add(
        args: list[Point | Ratio | Angle],
        dep_body: DependencyBody,
        dep_graph: WhyHyperGraph,
        symbols_graph: SymbolsGraph,
        disabled_intrinsic_rules: list[IntrinsicRules],
    ) -> tuple[list[Dependency], list[tuple[Statement, Dependency]]]:
        """Add a new statement that 4 args (2 lines) are perpendicular.

        Also add the corresponding 90-degree angle statement."""

        if IntrinsicRules.PARA_FROM_PERP not in disabled_intrinsic_rules:
            para_from_perp = Perp._maybe_make_para_from_perp(
                args, dep_body, dep_graph, symbols_graph, disabled_intrinsic_rules
            )
            if para_from_perp is not None:
                return para_from_perp

        a, b, c, d = args
        ab, why1 = symbols_graph.get_line_thru_pair_why(a, b)
        cd, why2 = symbols_graph.get_line_thru_pair_why(c, d)

        (a, b), (c, d) = ab.points, cd.points

        if IntrinsicRules.PERP_FROM_LINES not in disabled_intrinsic_rules:
            dep_body = dep_body.extend_by_why(
                dep_graph,
                Statement(Perp.NAME, args),
                extention_reason=Reason(IntrinsicRules.PERP_FROM_LINES),
                why=why1 + why2,
            )

        symbols_graph.get_node_val(ab, dep=None)
        symbols_graph.get_node_val(cd, dep=None)

        if ab.val == cd.val:
            raise ValueError(f"{ab.name} and {cd.name} Cannot be perp.")

        args = [a, b, c, d]
        i = 0
        for x, y, xy in [(a, b, ab), (c, d, cd)]:
            i += 1
            x_, y_ = xy._val._obj.points
            if {x, y} == {x_, y_}:
                continue
            if (
                dep_body
                and IntrinsicRules.PERP_FROM_PARA not in disabled_intrinsic_rules
            ):
                perp = Statement(Perp.NAME, list(args))
                para = Statement(Para.NAME, [x, y, x_, y_])
                dep_body = dep_body.extend(
                    dep_graph,
                    perp,
                    para,
                    extention_reason=Reason(IntrinsicRules.PERP_FROM_PARA),
                )
            args[2 * i - 2] = x_
            args[2 * i - 1] = y_

        a12, a21, why = symbols_graph.get_or_create_angle_from_lines(ab, cd, dep=None)

        perp = Statement(Perp.NAME, [a, b, c, d])
        if IntrinsicRules.PERP_FROM_ANGLE not in disabled_intrinsic_rules:
            dep_body = dep_body.extend_by_why(
                dep_graph,
                perp,
                why=why,
                extention_reason=Reason(IntrinsicRules.PERP_FROM_ANGLE),
            )

        dab, dcd = a12._d
        a, b = dab._obj.points
        c, d = dcd._obj.points

        dep = dep_body.build(dep_graph, perp)
        was_already_equal = is_equal(a12, a21)
        symbols_graph.make_equal(a12, a21, dep=dep)

        eqangle = Statement(EqAngle.NAME, [a, b, c, d, c, d, a, b])
        to_cache = [(perp, dep), (eqangle, dep)]

        if not was_already_equal:
            return [dep], to_cache
        return [], to_cache

    @staticmethod
    def _maybe_make_para_from_perp(
        points: list[Point],
        dep_body: DependencyBody,
        dep_graph: WhyHyperGraph,
        symbols_graph: SymbolsGraph,
        disabled_intrinsic_rules: list[IntrinsicRules],
    ) -> Optional[tuple[list[Dependency], list[tuple[Statement, Dependency]]]]:
        """Maybe add a new parallel predicate from perp predicate."""
        a, b, c, d = points
        halfpi = symbols_graph.aconst[(1, 2)]
        for ang in halfpi.val.neighbors(Angle):
            if ang == halfpi:
                continue
            d1, d2 = ang.directions
            x, y = d1._obj.points
            m, n = d2._obj.points

            for args in [
                (a, b, c, d, x, y, m, n),
                (a, b, c, d, m, n, x, y),
                (c, d, a, b, x, y, m, n),
                (c, d, a, b, m, n, x, y),
            ]:
                para_or_coll = Perp._add_para_or_coll_from_perp(
                    *args, dep_body, dep_graph, symbols_graph, disabled_intrinsic_rules
                )
                if para_or_coll is not None:
                    return para_or_coll

        return None

    @staticmethod
    def _add_para_or_coll_from_perp(
        a: Point,
        b: Point,
        c: Point,
        d: Point,
        x: Point,
        y: Point,
        m: Point,
        n: Point,
        dep_body: DependencyBody,
        dep_graph: WhyHyperGraph,
        symbols_graph: SymbolsGraph,
        disabled_intrinsic_rules: list[IntrinsicRules],
    ) -> tuple[list[Dependency], list[tuple[Statement, Dependency]]]:
        """Add a new parallel or collinear predicate."""
        perp = Statement(Perp.NAME, [a, b, c, d])
        extends = [Statement(Perp.NAME, [x, y, m, n])]
        if {a, b} == {x, y}:
            pass
        elif Para.check([a, b, x, y], symbols_graph):
            extends.append(Statement(Para.NAME, [a, b, x, y]))
        elif Coll.check([a, b, x, y], dep_graph):
            extends.append(Statement(Coll.NAME, set(list([a, b, x, y]))))
        else:
            return None

        if m in [c, d] or n in [c, d] or c in [m, n] or d in [m, n]:
            pass
        elif Coll.check([c, d, m], dep_graph):
            extends.append(Statement(Coll.NAME, [c, d, m]))
        elif Coll.check([c, d, n], dep_graph):
            extends.append(Statement(Coll.NAME, [c, d, n]))
        elif Coll.check([c, m, n], dep_graph):
            extends.append(Statement(Coll.NAME, [c, m, n]))
        elif Coll.check([d, m, n], dep_graph):
            extends.append(Statement(Coll.NAME, [d, m, n]))
        else:
            dep_body = dep_body.extend_many(
                dep_graph,
                perp,
                extends,
                extention_reason=Reason(IntrinsicRules.PARA_FROM_PERP),
            )
            return Para.add(
                [c, d, m, n],
                dep_body,
                dep_graph=dep_graph,
                symbols_graph=symbols_graph,
                disabled_intrinsic_rules=disabled_intrinsic_rules,
            )

        dep_body = dep_body.extend_many(
            dep_graph,
            perp,
            extends,
            extention_reason=Reason(IntrinsicRules.PARA_FROM_PERP),
        )
        return Coll.add(
            list(set([c, d, m, n])),
            dep_body,
            dep_graph=dep_graph,
            symbols_graph=symbols_graph,
            disabled_intrinsic_rules=disabled_intrinsic_rules,
        )

    @staticmethod
    def why(
        statements_graph: WhyHyperGraph, statement: Statement
    ) -> tuple[Reason | None, list[Dependency]]:
        a, b, c, d = statement.args
        ab = statements_graph.symbols_graph.get_line(a, b)
        cd = statements_graph.symbols_graph.get_line(c, d)

        why_perp = []
        for (x, y), xy in zip([(a, b), (c, d)], [ab, cd]):
            if xy is None:
                raise ValueError(
                    f"Line {x.name.capitalize()}{y.name.capitalize()} does not exist"
                )

            x_, y_ = xy.points

            if {x, y} == {x_, y_}:
                continue
            collx = Statement(Collx.NAME, [x, y, x_, y_])
            why_perp.append(
                statements_graph.build_resolved_dependency(collx, use_cache=False)
            )

        why_eqangle = why_eqangle_directions(
            statements_graph, ab._val, cd._val, cd._val, ab._val
        )
        a, b = ab.points
        c, d = cd.points

        perp_repr = Statement(statement.name, [a, b, c, d])
        if perp_repr.hash_tuple != statement.hash_tuple:
            perp_repr_dep = statements_graph.build_dependency_from_statement(
                perp_repr, why=why_eqangle, reason=Reason("_why_perp_repr")
            )
            why_eqangle = [perp_repr_dep]

        if why_eqangle:
            why_perp += why_eqangle
        return None, why_perp

    @staticmethod
    def check(args: list[Point], symbols_graph: SymbolsGraph) -> bool:
        a, b, c, d = args
        ab = symbols_graph.get_line(a, b)
        cd = symbols_graph.get_line(c, d)
        if not ab or not cd:
            return False
        return Perp.check_perpl(ab, cd)

    @staticmethod
    def check_perpl(ab: Line, cd: Line, symbols_graph: SymbolsGraph) -> bool:
        if ab.val is None or cd.val is None:
            return False
        if ab.val == cd.val:
            return False
        a12, a21 = symbols_graph.get_angle(ab.val, cd.val)
        if a12 is None or a21 is None:
            return False
        return is_equal(a12, a21)

    @staticmethod
    def check_numerical(args: list[PointNum]) -> bool:
        a, b, c, d = args
        ab = LineNum(a, b)
        cd = LineNum(c, d)
        return ab.is_perp(cd)

    @staticmethod
    def enumerate(
        symbols_graph: SymbolsGraph,
    ) -> Generator[tuple[Point, ...], None, None]:
        for ang in symbols_graph.vhalfpi.neighbors(Angle):
            d1, d2 = ang.directions
            if d1 is None or d2 is None:
                continue
            if d1 == d2:
                continue
            for l1, l2 in cross_product(d1.neighbors(Line), d2.neighbors(Line)):
                for a, b, c, d in all_4points(l1, l2):
                    yield a, b, c, d

    @staticmethod
    def pretty(args: list[str]) -> str:
        if len(args) == 2:  # this is algebraic derivation.
            ab, cd = args  # ab = 'd( ... )'
            return f"{ab} \u27c2 {cd}"
        a, b, c, d = args
        return f"{a}{b} \u27c2 {c}{d}"

    @classmethod
    def hash(cls: Self, args: list[Point]) -> tuple[str]:
        return hashed_unordered_two_lines_points(cls.NAME, args)
