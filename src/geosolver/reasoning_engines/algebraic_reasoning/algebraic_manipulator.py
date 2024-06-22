from __future__ import annotations
from enum import Enum
from typing import TYPE_CHECKING


from geosolver.numerical.check import check_numerical
import geosolver.predicates as preds
from geosolver.dependencies.dependency import Dependency, Reason
from geosolver.reasoning_engines.engines_interface import Derivation, ReasoningEngine
from geosolver.predicate_name import PredicateName
from geosolver.dependencies.dependency_building import DependencyBody
from geosolver.symbols_graph import is_equiv


from geosolver.statements.statement import Statement, ratio_to_num_den, angle_to_num_den

from geosolver.reasoning_engines.algebraic_reasoning.geometric_tables import (
    AngleTable,
    DistanceTable,
    RatioTable,
    report,
)

if TYPE_CHECKING:
    from geosolver.symbols_graph import SymbolsGraph

config = dict()


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
        self.verbose = config.get("verbose", "")

        self.PREDICATE_TO_ADDER = {
            preds.Para.NAME: self._add_para,
            preds.Perp.NAME: self._add_perp,
            preds.Cong.NAME: self._add_cong,
            preds.EqAngle.NAME: self._add_eqangle,
            preds.EqRatio.NAME: self._add_eqratio,
            preds.ConstantAngle.NAME: self._add_aconst,
            preds.SAngle.NAME: self._add_aconst,
            preds.ConstantRatio.NAME: self._add_rconst,
        }

    def ingest(self, dependency: "Dependency") -> None:
        """Add new algebraic predicates."""
        adder = self.PREDICATE_TO_ADDER.get(dependency.statement.predicate)
        if adder is not None:
            adder(dependency)

    def resolve(self, **kwargs) -> list[Derivation]:
        """Derive new algebraic predicates."""
        derives = []
        ang_derives = self.derive_angle_algebra()
        derives += ang_derives

        cong_derives = self.derive_cong_algebra()
        derives += cong_derives

        rat_derives = self.derive_ratio_algebra()
        derives += rat_derives

        if "a" in self.verbose:
            report(self.atable.v2e)
        if "d" in self.verbose:
            report(self.dtable.v2e)
        if "r" in self.verbose:
            report(self.rtable.v2e)

        return derives

    def derive_ratio_algebra(self) -> list[Derivation]:
        """Derive new eqratio predicates."""
        added = []

        for x in self.rtable.get_all_eqs_and_why():
            x, why = x[:-1], x[-1]
            dep = DependencyBody(reason=Reason(AlgebraicRules.Ratio_Chase), why=why)

            if len(x) == 2:
                mn, pq = x
                if is_equiv(mn, pq):
                    continue

                (m, n), (p, q) = mn._obj.points, pq._obj.points
                cong = Statement(preds.Cong.NAME_2, (m, n, p, q))
                added.append(Derivation(cong, dep))

            if len(x) == 4:
                ab, cd, mn, pq = x
                points = (
                    *ab._obj.points,
                    *cd._obj.points,
                    *mn._obj.points,
                    *pq._obj.points,
                )
                eqratio = Statement(preds.EqRatio.NAME, points)
                added.append(Derivation(eqratio, dep))

        return added

    def derive_angle_algebra(self) -> list[Derivation]:
        """Derive new eqangles predicates."""
        added = []

        for x in self.atable.get_all_eqs_and_why():
            x, why = x[:-1], x[-1]
            dep = DependencyBody(reason=Reason(AlgebraicRules.Angle_Chase), why=why)

            if len(x) == 2:
                ab, cd = x
                if is_equiv(ab, cd):
                    continue

                points = (*ab._obj.points, *cd._obj.points)
                para = Statement(preds.Para.NAME, points)
                if not check_numerical(para):
                    continue

                added.append(Derivation(para, dep))

            if len(x) == 3:
                ef, pq, (n, d) = x
                points = (*ef._obj.points, *pq._obj.points)
                angle, opposite_angle = self.symbols_graph.get_or_create_const_ang(n, d)
                angle.opposite = opposite_angle
                aconst = Statement(preds.ConstantAngle.NAME, (*points, angle))
                if not check_numerical(aconst):
                    continue

                added.append(Derivation(aconst, dep))

            if len(x) == 4:
                ab, cd, mn, pq = x
                points = (
                    *ab._obj.points,
                    *cd._obj.points,
                    *mn._obj.points,
                    *pq._obj.points,
                )
                eqangle = Statement(preds.EqAngle.NAME, points)
                added.append(Derivation(eqangle, dep))

        return added

    def derive_cong_algebra(self) -> list[Derivation]:
        """Derive new cong predicates."""
        added = []
        for x in self.dtable.get_all_eqs_and_why():
            x, why = x[:-1], x[-1]
            dep = DependencyBody(reason=Reason(AlgebraicRules.Distance_Chase), why=why)

            if len(x) == 2:
                a, b = x
                if a == b:
                    continue

                inci = Statement(PredicateName.INCI, (a, b))
                added.append(Derivation(inci, dep))

            if len(x) == 4:
                a, b, c, d = x
                if not (a != b and c != d and (a != c or b != d)):
                    continue
                cong = Statement(preds.Cong.NAME, (a, b, c, d))
                added.append(Derivation(cong, dep))

            if len(x) == 6:
                a, b, c, d, num, den = x
                if not (a != b and c != d and (a != c or b != d)):
                    continue
                ratio, _ = self.symbols_graph.get_or_create_const_rat(num, den)
                rconst = Statement(preds.ConstantRatio.NAME, (a, b, c, d, ratio))
                added.append(Derivation(rconst, dep))

        return added

    def _add_para(self, dep: "Dependency"):
        a, b, c, d = dep.statement.args
        ab, _ = self.symbols_graph.get_line_thru_pair_why(a, b)
        cd, _ = self.symbols_graph.get_line_thru_pair_why(c, d)
        self.atable.add_para(ab._val, cd._val, dep)

    def _add_perp(self, dep: "Dependency"):
        a, b, c, d = dep.statement.args
        ab = self.symbols_graph.get_line_thru_pair(a, b)
        cd = self.symbols_graph.get_line_thru_pair(c, d)
        self.atable.add_const_angle(ab.val, cd.val, 90, dep)

    def _add_eqangle(self, dep: "Dependency"):
        a, b, c, d, m, n, p, q = dep.statement.args
        ab, _ = self.symbols_graph.get_line_thru_pair_why(a, b)
        cd, _ = self.symbols_graph.get_line_thru_pair_why(c, d)
        mn, _ = self.symbols_graph.get_line_thru_pair_why(m, n)
        pq, _ = self.symbols_graph.get_line_thru_pair_why(p, q)
        ab_cd, _, _ = self.symbols_graph.get_or_create_angle_from_lines(
            ab, cd, dep=None
        )
        mn_pq, _, _ = self.symbols_graph.get_or_create_angle_from_lines(
            mn, pq, dep=None
        )
        ab, cd = ab_cd._d
        mn, pq = mn_pq._d
        if (ab, cd) == (pq, mn):
            self.atable.add_const_angle(ab, cd, 90, dep)
        else:
            self.atable.add_eqangle(ab, cd, mn, pq, dep)

    def _add_eqratio(self, dep: "Dependency"):
        a, b, c, d, m, n, p, q = dep.statement.args
        ab = self.symbols_graph.get_or_create_segment(a, b, dep=None)._val
        cd = self.symbols_graph.get_or_create_segment(c, d, dep=None)._val
        pq = self.symbols_graph.get_or_create_segment(p, q, dep=None)._val
        mn = self.symbols_graph.get_or_create_segment(m, n, dep=None)._val
        if (ab, cd) == (pq, mn):
            self.rtable.add_eq(ab, cd, dep)
        else:
            self.rtable.add_eqratio(ab, cd, mn, pq, dep)

    def _add_aconst(
        self, dep: "Dependency"
    ):  # not sure, in addr, add ab_cd as well as cd_ab
        if len(dep.statement.args) == 3:
            a, b, c, ang = dep.statement.args
            d = b
        else:
            a, b, c, d, ang = dep.statement.args
        ab, _ = self.symbols_graph.get_line_thru_pair_why(a, b)
        cd, _ = self.symbols_graph.get_line_thru_pair_why(c, d)
        ab_cd, _, _ = self.symbols_graph.get_or_create_angle_from_lines(
            ab, cd, dep=None
        )
        ab, cd = ab_cd._d
        num, den = angle_to_num_den(ang)
        self.atable.add_const_angle(ab, cd, num * 180 / den % 180, dep)

    def _add_rconst(
        self, dep: "Dependency"
    ):  # not sure, in addr, add ab_cd as well as cd_ab
        a, b, c, d, ratio = dep.statement.args
        num, den = ratio_to_num_den(ratio)
        ab = self.symbols_graph.get_or_create_segment(a, b, dep=None)
        cd = self.symbols_graph.get_or_create_segment(c, d, dep=None)
        self.rtable.add_const_ratio(ab, cd, num, den, dep)

    def _add_cong(self, dep: "Dependency"):
        a, b, c, d = dep.statement.args
        ab, _ = self.symbols_graph.get_line_thru_pair_why(a, b)
        cd, _ = self.symbols_graph.get_line_thru_pair_why(c, d)
        self.dtable.add_cong(ab, cd, a, b, c, d, dep)

        ab = self.symbols_graph.get_or_create_segment(a, b, dep=None)
        cd = self.symbols_graph.get_or_create_segment(c, d, dep=None)
        self.rtable.add_eq(ab._val, cd._val, dep)
