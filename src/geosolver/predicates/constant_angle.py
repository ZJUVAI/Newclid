from __future__ import annotations
from typing import TYPE_CHECKING, Generator, Optional

from geosolver.dependencies.dependency import Reason, Dependency


from geosolver.dependencies.why_predicates import why_equal
from geosolver.numerical import close_enough
from geosolver.numerical.angles import ang_between
from geosolver.numerical.geometries import PointNum
from geosolver.predicates.equal_angles import all_angles
from geosolver.predicates.predicate import Predicate
from geosolver.intrinsic_rules import IntrinsicRules

from geosolver.geometry import Angle, AngleValue, Point, Ratio
from geosolver.predicates.equal_angles import pretty_angle
from geosolver.statements.statement import (
    Statement,
    angle_to_num_den,
    hash_ordered_list_of_points,
    hash_ordered_two_lines_with_value,
)
from geosolver.symbols_graph import SymbolsGraph, is_equal

import geosolver.predicates as preds

from geosolver._lazy_loading import lazy_import

if TYPE_CHECKING:
    from geosolver.dependencies.dependency_building import DependencyBody
    from geosolver.dependencies.why_graph import DependencyGraph

    import numpy

np: "numpy" = lazy_import("numpy")


class ConstantAngle(Predicate):
    """aconst AB CD Y -
    Represent that the rotation needed to go from line AB to line CD,
    oriented on the clockwise direction is Y.

    The syntax of Y is either a fraction of pi like 2pi/3 for radians
    or a number followed by a 'o' like 120o for degree.
    """

    NAME = "aconst"

    @staticmethod
    def add(
        args: list[Point],
        dep_body: "DependencyBody",
        dep_graph: "DependencyGraph",
        symbols_graph: SymbolsGraph,
        disabled_intrinsic_rules: list[IntrinsicRules],
    ) -> tuple[list[Dependency], list[tuple[Statement, Dependency]]]:
        """Add that an angle is equal to some constant."""
        points = list(args)
        a, b, c, d, ang = args

        num, den = angle_to_num_den(ang)
        nd, dn = symbols_graph.get_or_create_const_ang(num, den)

        if nd == symbols_graph.halfpi:
            return preds.Perp.add(
                [a, b, c, d],
                dep_body,
                dep_graph,
                symbols_graph,
                disabled_intrinsic_rules,
            )

        ab, why1 = symbols_graph.get_line_thru_pair_why(a, b)
        cd, why2 = symbols_graph.get_line_thru_pair_why(c, d)

        (a, b), (c, d) = ab.points, cd.points
        if IntrinsicRules.ACONST_FROM_LINES not in disabled_intrinsic_rules:
            args = points[:-1] + [nd]
            aconst = Statement(ConstantAngle, tuple(args))
            dep_body = dep_body.extend_by_why(
                dep_graph,
                aconst,
                why=why1 + why2,
                extention_reason=Reason(IntrinsicRules.ACONST_FROM_LINES),
            )

        symbols_graph.get_node_val(ab, dep=None)
        symbols_graph.get_node_val(cd, dep=None)

        if ab.val == cd.val:
            raise ValueError(f"{ab.name} - {cd.name} cannot be {nd.name}")

        args = [a, b, c, d, nd]
        i = 0
        for x, y, xy in [(a, b, ab), (c, d, cd)]:
            i += 1
            x_, y_ = xy._val._obj.points
            if {x, y} == {x_, y_}:
                continue
            if (
                dep_body
                and IntrinsicRules.ACONST_FROM_PARA not in disabled_intrinsic_rules
            ):
                aconst = Statement(ConstantAngle, tuple(args))
                para = Statement(preds.Para, [x, y, x_, y_])
                dep_body = dep_body.extend(
                    dep_graph,
                    aconst,
                    para,
                    Reason(IntrinsicRules.ACONST_FROM_PARA),
                )
            args[2 * i - 2] = x_
            args[2 * i - 1] = y_

        ab_cd, cd_ab, why = symbols_graph.get_or_create_angle_from_lines(
            ab, cd, dep=None
        )

        aconst = Statement(ConstantAngle, [a, b, c, d, nd])
        if IntrinsicRules.ACONST_FROM_ANGLE not in disabled_intrinsic_rules:
            dep_body = dep_body.extend_by_why(
                dep_graph,
                aconst,
                why=why,
                extention_reason=Reason(IntrinsicRules.ACONST_FROM_ANGLE),
            )

        dab, dcd = ab_cd._d
        a, b = dab._obj.points
        c, d = dcd._obj.points

        ang = int(num) * 180 / int(den)
        add = []
        to_cache = []
        if not is_equal(ab_cd, nd):
            dep1 = dep_body.build(dep_graph, aconst)
            symbols_graph.make_equal(ab_cd, nd, dep=dep1)
            to_cache.append((aconst, dep1))
            add += [dep1]

        aconst2 = Statement(ConstantAngle, [a, b, c, d, nd])
        if not is_equal(cd_ab, dn):
            dep2 = dep_body.build(dep_graph, aconst2)
            symbols_graph.make_equal(cd_ab, dn, dep=dep2)
            to_cache.append((aconst2, dep2))
            add += [dep2]

        return add, to_cache

    @staticmethod
    def why(
        dep_graph: "DependencyGraph", statement: "Statement"
    ) -> tuple[Optional[Reason], list[Dependency]]:
        a, b, c, d, ang0 = statement.args
        symbols_graph = dep_graph.symbols_graph

        measure: AngleValue = ang0._val
        for ang in measure.neighbors(Angle):
            if ang == ang0:
                continue
            d1, d2 = ang._d
            l1, l2 = d1._obj, d2._obj
            (a1, b1), (c1, d1) = l1.points, l2.points

            para_ab = preds.Para.check([a, b, a1, b1], symbols_graph)
            coll_ab = preds.Coll.check([a, b, a1, b1], symbols_graph)
            para_cd = preds.Para.check([c, d, c1, d1], symbols_graph)
            coll_cd = preds.Coll.check([c, d, c1, d1], symbols_graph)
            if not (para_ab or coll_ab) or not (para_cd or coll_cd):
                continue

            why_aconst = []
            for args in [(a, b, a1, b1), (c, d, c1, d1)]:
                if preds.Coll.check(args, symbols_graph):
                    if len(set(args)) <= 2:
                        continue
                    coll = Statement(preds.Coll, args)
                    coll_dep = dep_graph.build_resolved_dependency(
                        coll, use_cache=False
                    )
                    why_aconst.append(coll_dep)
                else:
                    para = Statement(preds.Para, args)
                    para_dep = dep_graph.build_resolved_dependency(
                        para, use_cache=False
                    )
                    why_aconst.append(para_dep)

            why_aconst += why_equal(ang, ang0)
            return None, why_aconst

    @staticmethod
    def check(args: list[Point | Ratio | Angle], symbols_graph: SymbolsGraph) -> bool:
        """Check if the angle is equal to a certain constant."""
        a, b, c, d, angle = args
        num, den = angle_to_num_den(angle)
        ang, _ = symbols_graph.get_or_create_const_ang(int(num), int(den))

        ab = symbols_graph.get_line(a, b)
        cd = symbols_graph.get_line(c, d)
        if not ab or not cd:
            return False

        if not (ab.val and cd.val):
            return False

        for ang1, _, _ in all_angles(ab._val, cd._val):
            if is_equal(ang1, ang):
                return True
        return False

    @staticmethod
    def check_numerical(args: list[PointNum | Angle]) -> bool:
        a, b, c, d, angle = args
        num, den = angle_to_num_den(angle)
        d = d + a - c
        ang = ang_between(a, b, d)
        if ang < 0:
            ang += np.pi
        return close_enough(ang, num * np.pi / den)

    @staticmethod
    def enumerate(
        symbols_graph: SymbolsGraph,
    ) -> Generator[tuple[Point | Angle, ...], None, None]:
        raise NotImplementedError

    @staticmethod
    def pretty(args: list[str]) -> str:
        a, b, c, d, y = args
        return f"{pretty_angle(a, b, c, d)} = {y}"

    @classmethod
    def hash(cls, args: list[Point | Angle]) -> tuple[str | Angle, ...]:
        return hash_ordered_two_lines_with_value(cls.NAME, args)


class SAngle(Predicate):
    """s_angle A B C Y -
    Represent that the angle ABC,
    with vertex at B and going counter clockwise from A to C, is Y.

    The syntax of Y is either a fraction of pi like 2pi/3 for radians
    or a number followed by a 'o' like 120o for degree.
    """

    NAME = "s_angle"

    @staticmethod
    def add(
        args: list[Point | Angle],
        dep_body: DependencyBody,
        dep_graph: DependencyGraph,
        symbols_graph: SymbolsGraph,
        disabled_intrinsic_rules: list[IntrinsicRules],
    ) -> tuple[list[Dependency], list[tuple[Statement, Dependency]]]:
        """Add that an angle abc is equal to constant y."""
        a, b, c, angle = args
        num, den = angle_to_num_den(angle)
        nd, dn = symbols_graph.get_or_create_const_ang(num, den)

        if nd == symbols_graph.halfpi:
            return preds.Perp.add(
                [a, b, b, c],
                dep_body,
                dep_graph,
                symbols_graph,
                disabled_intrinsic_rules,
            )

        ab, why1 = symbols_graph.get_line_thru_pair_why(a, b)
        bx, why2 = symbols_graph.get_line_thru_pair_why(b, c)

        symbols_graph.get_node_val(ab, dep=None)
        symbols_graph.get_node_val(bx, dep=None)

        add, to_cache = [], []

        if ab.val == bx.val:
            return add, to_cache

        sangle = Statement(SAngle, (a, b, c))
        if IntrinsicRules.SANGLE_FROM_LINES not in disabled_intrinsic_rules:
            dep_body = dep_body.extend_by_why(
                dep_graph,
                sangle,
                why=why1 + why2,
                extention_reason=Reason(IntrinsicRules.SANGLE_FROM_LINES),
            )

        if IntrinsicRules.SANGLE_FROM_PARA not in disabled_intrinsic_rules:
            paras = []
            for p, q, pq in [(a, b, ab), (b, c, bx)]:
                p_, q_ = pq.val._obj.points
                if {p, q} == {p_, q_}:
                    continue
                paras.append(Statement(preds.Para, (p, q, p_, q_)))
            if paras:
                dep_body = dep_body.extend_many(
                    dep_graph, sangle, paras, Reason(IntrinsicRules.SANGLE_FROM_PARA)
                )

        xba, abx, why = symbols_graph.get_or_create_angle_from_lines(bx, ab, dep=None)
        if IntrinsicRules.SANGLE_FROM_ANGLE not in disabled_intrinsic_rules:
            aconst = Statement(preds.ConstantAngle, [b, c, a, b, nd])
            dep_body = dep_body.extend_by_why(
                dep_graph,
                aconst,
                why=why,
                extention_reason=Reason(IntrinsicRules.SANGLE_FROM_ANGLE),
            )

        dab, dbx = abx._d
        a, b = dab._obj.points
        c, c = dbx._obj.points

        if not is_equal(xba, nd):
            aconst = Statement(SAngle, [c, c, a, b, nd])
            dep1 = dep_body.build(dep_graph, aconst)
            symbols_graph.make_equal(xba, nd, dep=dep1)
            to_cache.append((aconst, dep1))
            add += [dep1]

        if not is_equal(abx, dn):
            aconst2 = Statement(SAngle, [a, b, c, c, dn])
            dep2 = dep_body.build(dep_graph, aconst2)
            symbols_graph.make_equal(abx, dn, dep=dep2)
            to_cache.append((aconst2, dep2))
            add += [dep2]

        return add, to_cache

    @staticmethod
    def why(
        dep_graph: DependencyGraph, statement: Statement
    ) -> tuple[Optional[Reason], list[Dependency]]:
        raise NotImplementedError

    @staticmethod
    def check(
        args: tuple[Point, Point, Point, Angle], symbols_graph: SymbolsGraph
    ) -> bool:
        a, b, c, angle = args
        num, den = angle_to_num_den(angle)
        ang, _ = symbols_graph.get_or_create_const_ang(num, den)

        ab = symbols_graph.get_line(a, b)
        cb = symbols_graph.get_line(c, b)
        if not ab or not cb:
            return False

        if not (ab.val and cb.val):
            return False

        for ang1, _, _ in all_angles(ab._val, cb._val):
            if is_equal(ang1, ang):
                return True
        return False

    @staticmethod
    def check_numerical(args: tuple[PointNum, PointNum, PointNum, Angle]) -> bool:
        a, b, c, angle = args
        num, den = angle_to_num_den(angle)
        ang = ang_between(b, c, a)
        if ang < 0:
            ang += np.pi
        return close_enough(ang, num * np.pi / den)

    @staticmethod
    def enumerate(
        symbols_graph: SymbolsGraph,
    ) -> Generator[tuple[Point, ...], None, None]:
        raise NotImplementedError

    @staticmethod
    def pretty(args: list[str]) -> str:
        a, b, c, angle = args
        return f"{pretty_angle(a, b, b, c)} = {angle}"

    @classmethod
    def hash(cls, args: list[Point | Angle]) -> tuple[str | Point | Angle]:
        return hash_ordered_list_of_points(cls.NAME, args)
