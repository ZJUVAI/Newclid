from __future__ import annotations
from enum import Enum
from typing import TYPE_CHECKING


from geosolver.agent.interface import DeriveFeedback
from geosolver.dependencies.dependency import Dependency, Reason
from geosolver.reasoning_engines.interface import Derivations, ReasoningEngine
from geosolver.predicates import Predicate
from geosolver.dependencies.empty_dependency import EmptyDependency
from geosolver.geometry import is_equiv
from geosolver.numerical.check import check_numerical


from geosolver.statements.statement import Statement, ratio_to_num_den, angle_to_num_den

from geosolver.reasoning_engines.algebraic_reasoning.geometric_tables import (
    AngleTable,
    DistanceTable,
    RatioTable,
)

if TYPE_CHECKING:
    from geosolver.symbols_graph import SymbolsGraph


class AlgebraicRules(Enum):
    Distance_Chase = "a00"
    Ratio_Chase = "a01"
    Angle_Chase = "a02"


class AlgebraicManipulator(ReasoningEngine):
    def __init__(self, symbols_graph: "SymbolsGraph") -> None:
        self.symbols_graph = symbols_graph

        self.atable = AngleTable()
        self.dtable = DistanceTable()
        self.rtable = RatioTable()

        self.PREDICATE_TO_ADDER = {
            Predicate.PARALLEL: self._add_para,
            Predicate.PERPENDICULAR: self._add_perp,
            Predicate.CONGRUENT: self._add_cong,
            Predicate.EQANGLE: self._add_eqangle,
            Predicate.EQRATIO: self._add_eqratio,
            Predicate.CONSTANT_ANGLE: self._add_aconst,
            Predicate.S_ANGLE: self._add_aconst,
            Predicate.CONSTANT_RATIO: self._add_rconst,
        }

    def ingest(self, dependency: "Dependency") -> None:
        """Add new algebraic predicates."""
        adder = self.PREDICATE_TO_ADDER.get(dependency.statement.predicate)
        if adder is not None:
            adder(dependency)

    def resolve(self, **kwargs) -> DeriveFeedback:
        """Derive new algebraic predicates."""
        level: int = kwargs.get("level")
        derives = []
        ang_derives = self.derive_angle_algebra(level)
        derives += ang_derives

        cong_derives = self.derive_cong_algebra(level)
        derives += cong_derives

        rat_derives = self.derive_ratio_algebra(level)
        derives += rat_derives

        return DeriveFeedback(derives)

    def derive_ratio_algebra(self, level: int) -> Derivations:
        """Derive new eqratio predicates."""
        added = []

        for x in self.rtable.get_all_eqs_and_why():
            x, why = x[:-1], x[-1]
            dep = EmptyDependency(
                level=level,
                reason=Reason(AlgebraicRules.Ratio_Chase),
            )
            dep.why = why

            if len(x) == 2:
                mn, pq = x
                if is_equiv(mn, pq):
                    continue

                (m, n), (p, q) = mn._obj.points, pq._obj.points
                cong = Statement(Predicate.CONGRUENT_2, (m, n, p, q))
                added.append((cong, dep))

            if len(x) == 4:
                ab, cd, mn, pq = x
                points = (
                    *ab._obj.points,
                    *cd._obj.points,
                    *mn._obj.points,
                    *pq._obj.points,
                )
                eqratio = Statement(Predicate.EQRATIO, points)
                added.append((eqratio, dep))

        return added

    def derive_angle_algebra(self, level: int) -> Derivations:
        """Derive new eqangles predicates."""
        added = []

        for x in self.atable.get_all_eqs_and_why():
            x, why = x[:-1], x[-1]
            dep = EmptyDependency(
                level=level,
                reason=Reason(AlgebraicRules.Angle_Chase),
            )
            dep.why = why

            if len(x) == 2:
                ab, cd = x
                if is_equiv(ab, cd):
                    continue

                points = (*ab._obj.points, *cd._obj.points)
                para = Statement(Predicate.PARALLEL, points)
                if not check_numerical(para):
                    continue

                added.append((para, dep))

            if len(x) == 3:
                ef, pq, (n, d) = x
                points = (*ef._obj.points, *pq._obj.points)
                angle, opposite_angle = self.symbols_graph.get_or_create_const_ang(n, d)
                angle.opposite = opposite_angle
                aconst = Statement(Predicate.CONSTANT_ANGLE, (*points, angle))
                if not check_numerical(aconst):
                    continue

                added.append((aconst, dep))

            if len(x) == 4:
                ab, cd, mn, pq = x
                points = (
                    *ab._obj.points,
                    *cd._obj.points,
                    *mn._obj.points,
                    *pq._obj.points,
                )
                eqangle = Statement(Predicate.EQANGLE, points)
                added.append((eqangle, dep))

        return added

    def derive_cong_algebra(self, level: int) -> Derivations:
        """Derive new cong predicates."""
        added = []
        for x in self.dtable.get_all_eqs_and_why():
            x, why = x[:-1], x[-1]
            dep = EmptyDependency(
                level=level,
                reason=Reason(AlgebraicRules.Distance_Chase),
            )
            dep.why = why

            if len(x) == 2:
                a, b = x
                if a == b:
                    continue

                inci = Statement(Predicate.INCI, (a, b))
                added.append((inci, dep))

            if len(x) == 4:
                a, b, c, d = x
                if not (a != b and c != d and (a != c or b != d)):
                    continue
                cong = Statement(Predicate.CONGRUENT, (a, b, c, d))
                added.append((cong, dep))

            if len(x) == 6:
                a, b, c, d, num, den = x
                if not (a != b and c != d and (a != c or b != d)):
                    continue
                ratio, _ = self.symbols_graph.get_or_create_const_rat(num, den)
                rconst = Statement(Predicate.CONSTANT_RATIO, (a, b, c, d, ratio))
                added.append((rconst, dep))

        return added

    def _add_para(self, dep: "Dependency"):
        a, b, c, d = dep.statement.args
        ab, _ = self.symbols_graph.get_line_thru_pair_why(a, b)
        cd, _ = self.symbols_graph.get_line_thru_pair_why(c, d)
        self.atable.add_para(ab._val, cd._val, dep)

    def _add_perp(self, dep: "Dependency"):
        a, b, c, d, _ = dep.statement.args
        ab = self.symbols_graph.get_line_thru_pair(a, b)
        cd = self.symbols_graph.get_line_thru_pair(c, d)
        self.atable.add_const_angle(ab, cd, 90, dep)

    def _add_eqangle(self, dep: "Dependency"):
        a, b, c, d, m, n, p, q = dep.statement.args
        ab, _ = self.symbols_graph.get_line_thru_pair_why(a, b)
        cd, _ = self.symbols_graph.get_line_thru_pair_why(c, d)
        mn, _ = self.symbols_graph.get_line_thru_pair_why(m, n)
        pq, _ = self.symbols_graph.get_line_thru_pair_why(p, q)
        ab_cd, _, _ = self.symbols_graph.get_or_create_angle_from_lines(
            ab, cd, deps=None
        )
        mn_pq, _, _ = self.symbols_graph.get_or_create_angle_from_lines(
            mn, pq, deps=None
        )
        ab, cd = ab_cd._d
        mn, pq = mn_pq._d
        if (ab, cd) == (pq, mn):
            self.atable.add_const_angle(ab, cd, 90, dep)
        else:
            self.atable.add_eqangle(ab, cd, mn, pq, dep)

    def _add_eqratio(self, dep: "Dependency"):
        a, b, c, d, m, n, p, q = dep.statement.args
        ab = self.symbols_graph.get_or_create_segment(a, b, deps=None)._val
        cd = self.symbols_graph.get_or_create_segment(c, d, deps=None)._val
        pq = self.symbols_graph.get_or_create_segment(p, q, deps=None)._val
        mn = self.symbols_graph.get_or_create_segment(m, n, deps=None)._val
        if (ab, cd) == (pq, mn):
            self.rtable.add_eq(ab, cd, dep)
        else:
            self.rtable.add_eqratio(ab, cd, mn, pq, dep)

    def _add_aconst(
        self, dep: "Dependency"
    ):  # not sure, in addr, add ab_cd as well as cd_ab
        a, b, c, d, ang = dep.statement.args
        ab, _ = self.symbols_graph.get_line_thru_pair_why(a, b)
        cd, _ = self.symbols_graph.get_line_thru_pair_why(c, d)
        ab_cd, _, _ = self.symbols_graph.get_or_create_angle_from_lines(
            ab, cd, deps=None
        )
        ab, cd = ab_cd._d
        num, den = angle_to_num_den(ang)
        self.atable.add_const_angle(ab, cd, num * 180 / den % 180, dep)

    def _add_rconst(
        self, dep: "Dependency"
    ):  # not sure, in addr, add ab_cd as well as cd_ab
        a, b, c, d, ratio = dep.statement.args
        num, den = ratio_to_num_den(ratio)
        ab = self.symbols_graph.get_or_create_segment(a, b, deps=None)
        cd = self.symbols_graph.get_or_create_segment(c, d, deps=None)
        self.rtable.add_const_ratio(ab, cd, num, den, dep)

    def _add_cong(self, dep: "Dependency"):
        a, b, c, d = dep.statement.args
        ab, _ = self.symbols_graph.get_line_thru_pair_why(a, b)
        cd, _ = self.symbols_graph.get_line_thru_pair_why(c, d)
        self.dtable.add_cong(ab, cd, a, b, c, d, dep)

        ab = self.symbols_graph.get_or_create_segment(a, b, deps=None)
        cd = self.symbols_graph.get_or_create_segment(c, d, deps=None)
        self.rtable.add_eq(ab._val, cd._val, dep)
