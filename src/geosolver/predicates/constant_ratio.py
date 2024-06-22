from __future__ import annotations
from typing import TYPE_CHECKING, Generator, Optional

from geosolver.dependencies.dependency import Reason, Dependency

from geosolver.dependencies.why_predicates import why_equal
from geosolver.numerical import close_enough
from geosolver.numerical.geometries import PointNum

from geosolver.predicates.predicate import Predicate
from geosolver.intrinsic_rules import IntrinsicRules

from geosolver.geometry import AngleValue, Point, Ratio
from geosolver.statements.statement import (
    Statement,
    hash_ordered_two_lines_with_value,
    ratio_to_num_den,
)
from geosolver.symbols_graph import SymbolsGraph, is_equal

import geosolver.predicates as preds
from geosolver.predicates.equal_ratios import all_ratios

if TYPE_CHECKING:
    from geosolver.dependencies.dependency_building import DependencyBody
    from geosolver.dependencies.why_graph import DependencyGraph


class ConstantRatio(Predicate):
    """rconst A B C D r -
    Represent that AB / CD = r

    r should be given with numerator and denominator separated by '/', as in 2/3.
    """

    NAME = "rconst"

    @staticmethod
    def add(
        args: list[Point | Ratio],
        dep_body: "DependencyBody",
        dep_graph: "DependencyGraph",
        symbols_graph: SymbolsGraph,
        disabled_intrinsic_rules: list[IntrinsicRules],
    ) -> tuple[list[Dependency], list[tuple[Statement, Dependency]]]:
        """Add new algebraic predicates of type eqratio-constant."""
        a, b, c, d, ratio = args

        num, den = ratio_to_num_den(ratio)
        nd, dn = symbols_graph.get_or_create_const_rat(num, den)

        if num == den:
            return preds.Cong.add(
                [a, b, c, d],
                dep_body,
                dep_graph,
                symbols_graph,
                disabled_intrinsic_rules,
            )

        ab = symbols_graph.get_or_create_segment(a, b, dep=None)
        cd = symbols_graph.get_or_create_segment(c, d, dep=None)

        symbols_graph.get_node_val(ab, dep=None)
        symbols_graph.get_node_val(cd, dep=None)

        if ab.val == cd.val:
            raise ValueError(f"{ab.name} and {cd.name} cannot be equal")

        args = [a, b, c, d, nd]
        i = 0
        for x, y, xy in [(a, b, ab), (c, d, cd)]:
            i += 1
            x_, y_ = list(xy._val._obj.points)
            if {x, y} == {x_, y_}:
                continue
            if (
                dep_body
                and IntrinsicRules.RCONST_FROM_CONG not in disabled_intrinsic_rules
            ):
                rconst = Statement(ConstantRatio, tuple(args))
                cong = Statement(preds.Cong, [x, y, x_, y_])
                dep_body = dep_body.extend(
                    dep_graph,
                    rconst,
                    cong,
                    extention_reason=Reason(IntrinsicRules.RCONST_FROM_CONG),
                )
            args[2 * i - 2] = x_
            args[2 * i - 1] = y_

        ab_cd, cd_ab, why = symbols_graph.get_or_create_ratio_from_segments(
            ab, cd, dep=None
        )

        rconst = Statement(ConstantRatio, [a, b, c, d, nd])
        if IntrinsicRules.RCONST_FROM_RATIO not in disabled_intrinsic_rules:
            dep_body = dep_body.extend_by_why(
                dep_graph,
                rconst,
                why=why,
                extention_reason=Reason(IntrinsicRules.RCONST_FROM_RATIO),
            )

        lab, lcd = ab_cd._l
        a, b = list(lab._obj.points)
        c, d = list(lcd._obj.points)

        add = []
        to_cache = []
        if not is_equal(ab_cd, nd):
            dep1 = dep_body.build(dep_graph, rconst)
            symbols_graph.make_equal(nd, ab_cd, dep=dep1)
            to_cache.append((rconst, dep1))
            add.append(dep1)

        if not is_equal(cd_ab, dn):
            rconst2 = Statement(ConstantRatio, [c, d, a, b, dn])
            dep2 = dep_body.build(dep_graph, rconst2)
            symbols_graph.make_equal(dn, cd_ab, dep=dep2)
            to_cache.append((rconst2, dep2))
            add.append(dep2)

        return add, to_cache

    @staticmethod
    def why(
        dep_graph: "DependencyGraph", statement: "Statement"
    ) -> tuple[Optional[Reason], list[Dependency]]:
        a, b, c, d, rat0 = statement.args
        symbols_graph = dep_graph.symbols_graph

        val: AngleValue = rat0._val
        for rat in val.neighbors(Ratio):
            if rat == rat0:
                continue
            l1, l2 = rat._l
            s1, s2 = l1._obj, l2._obj
            (a1, b1), (c1, d1) = list(s1.points), list(s2.points)

            cong_ab = preds.Cong.check([a, b, a1, b1], symbols_graph)
            cong_cd = preds.Cong.check([c, d, c1, d1], symbols_graph)
            if not cong_ab or not cong_cd:
                continue

            why_rconst = []
            for args in [(a, b, a1, b1), (c, d, c1, d1)]:
                if len(set(args)) > 2:
                    cong = Statement(preds.Cong, args)
                    why_rconst.append(
                        dep_graph.build_resolved_dependency(cong, use_cache=False)
                    )

            why_rconst += why_equal(rat, rat0)
            return None, why_rconst

    @staticmethod
    def check(
        args: tuple[Point, Point, Point, Point, Ratio], symbols_graph: SymbolsGraph
    ) -> bool:
        """Check whether a ratio is equal to some given constant."""
        a, b, c, d, ratio = args
        num, den = ratio_to_num_den(ratio)
        rat, _ = symbols_graph.get_or_create_const_rat(int(num), int(den))

        ab = symbols_graph.get_segment(a, b)
        cd = symbols_graph.get_segment(c, d)

        if not ab or not cd:
            return False

        if not (ab.val and cd.val):
            return False

        for rat1, _, _ in all_ratios(ab._val, cd._val):
            if is_equal(rat1, rat):
                return True
        return False

    @staticmethod
    def check_numerical(
        args: tuple[PointNum, PointNum, PointNum, PointNum, Ratio],
    ) -> bool:
        a, b, c, d, ratio = args
        m, n = ratio_to_num_den(ratio)
        ab = a.distance(b)
        cd = c.distance(d)
        return close_enough(ab * n, cd * m)

    @staticmethod
    def enumerate(
        symbols_graph: SymbolsGraph,
    ) -> Generator[tuple[Point, ...], None, None]:
        raise NotImplementedError

    @staticmethod
    def pretty(args: list[str]) -> str:
        a, b, c, d, y = args
        return f"{a}{b}:{c}{d} = {y}"

    @classmethod
    def hash(cls, args: list[Point | Ratio]) -> tuple[str | Point | Ratio]:
        return hash_ordered_two_lines_with_value(cls.NAME, args)
