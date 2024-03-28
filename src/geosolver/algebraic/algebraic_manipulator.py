from typing import TYPE_CHECKING, Dict, Tuple


from geosolver.algebraic import AlgebraicRules
from geosolver.algebraic.geometric_tables import AngleTable, DistanceTable, RatioTable
from geosolver.concepts import ConceptName
from geosolver.dependencies.empty_dependency import EmptyDependency
from geosolver.geometry import Angle, Point, Ratio, is_equiv
from geosolver.numerical.check import check_numerical


import geosolver.ratios

if TYPE_CHECKING:
    from geosolver.symbols_graph import SymbolsGraph
    from geosolver.dependencies.dependency import Dependency


class AlgebraicManipulator:
    def __init__(self, symbols_graph: "SymbolsGraph") -> None:
        self.symbols_graph = symbols_graph

        self.atable = AngleTable()
        self.dtable = DistanceTable()
        self.rtable = RatioTable()

        self.rconst: Dict[Tuple[int, int], Ratio] = {}  # contains all constant ratios
        self.aconst: Dict[Tuple[int, int], Angle] = {}  # contains all constant angles.

        # Half pi constant is always added by default.
        self.halfpi, _ = self.get_or_create_const_ang(1, 2)
        self.vhalfpi = self.halfpi.val

        self.NAME_TO_ADDER = {
            ConceptName.PARALLEL.value: self._add_para,
            ConceptName.PERPENDICULAR.value: self._add_perp,
            ConceptName.CONGRUENT.value: self._add_cong,
            ConceptName.EQANGLE.value: self._add_eqangle,
            ConceptName.EQRATIO.value: self._add_eqratio,
            ConceptName.CONSTANT_ANGLE.value: self._add_aconst,
            ConceptName.CONSTANT_RATIO.value: self._add_rconst,
        }

    def add_algebra(self, dep: "Dependency") -> None:
        """Add new algebraic predicates."""
        adder = self.NAME_TO_ADDER.get(dep.name)
        if adder is not None:
            adder(dep)

    def derive_algebra(
        self, level: int, verbose: bool = False
    ) -> tuple[dict[str, list[tuple[Point, ...]]], dict[str, list[tuple[Point, ...]]]]:
        """Derive new algebraic predicates."""
        derives = {}
        ang_derives = self.derive_angle_algebra(level, verbose=verbose)
        dist_derives = self.derive_distance_algebra(level, verbose=verbose)
        rat_derives = self.derive_ratio_algebra(level, verbose=verbose)

        derives.update(ang_derives)
        derives.update(dist_derives)
        derives.update(rat_derives)

        # Separate eqangle and eqratio derivations
        # As they are too numerous => slow down DD+AR.
        # & reserve them only for last effort.
        eqs = {
            ConceptName.EQANGLE.value: derives.pop(ConceptName.EQANGLE.value),
            ConceptName.EQRATIO.value: derives.pop(ConceptName.EQRATIO.value),
        }
        return derives, eqs

    def derive_ratio_algebra(
        self, level: int, verbose: bool = False
    ) -> dict[str, list[tuple[Point, ...]]]:
        """Derive new eqratio predicates."""
        added = {ConceptName.CONGRUENT_2.value: [], ConceptName.EQRATIO.value: []}

        for x in self.rtable.get_all_eqs_and_why():
            x, why = x[:-1], x[-1]
            dep = EmptyDependency(
                level=level,
                rule_name=AlgebraicRules.Ratio_Chase.value,
            )
            dep.why = why

            if len(x) == 2:
                a, b = x
                if is_equiv(a, b):
                    continue

                (m, n), (p, q) = a._obj.points, b._obj.points
                added[ConceptName.CONGRUENT_2.value].append((m, n, p, q, dep))

            if len(x) == 4:
                a, b, c, d = x
                added[ConceptName.EQRATIO.value].append((a, b, c, d, dep))

        return added

    def derive_angle_algebra(
        self, level: int, verbose: bool = False
    ) -> dict[str, list[tuple[Point, ...]]]:
        """Derive new eqangles predicates."""
        added = {
            ConceptName.EQANGLE.value: [],
            ConceptName.CONSTANT_ANGLE.value: [],
            ConceptName.PARALLEL.value: [],
        }

        for x in self.atable.get_all_eqs_and_why():
            x, why = x[:-1], x[-1]
            dep = EmptyDependency(
                level=level,
                rule_name=AlgebraicRules.Angle_Chase.value,
            )
            dep.why = why

            if len(x) == 2:
                a, b = x
                if is_equiv(a, b):
                    continue

                (e, f), (p, q) = a._obj.points, b._obj.points
                if not check_numerical(ConceptName.PARALLEL.value, [e, f, p, q]):
                    continue

                added[ConceptName.PARALLEL.value].append((a, b, dep))

            if len(x) == 3:
                a, b, (n, d) = x

                (e, f), (p, q) = a._obj.points, b._obj.points
                if not check_numerical(
                    ConceptName.CONSTANT_ANGLE.value, [e, f, p, q, n, d]
                ):
                    continue

                added[ConceptName.CONSTANT_ANGLE.value].append((a, b, n, d, dep))

            if len(x) == 4:
                a, b, c, d = x
                added[ConceptName.EQANGLE.value].append((a, b, c, d, dep))

        return added

    def derive_distance_algebra(
        self, level: int, verbose: bool = False
    ) -> dict[str, list[tuple[Point, ...]]]:
        """Derive new cong predicates."""
        added = {
            ConceptName.INCI.value: [],
            ConceptName.CONGRUENT.value: [],
            ConceptName.CONSTANT_RATIO.value: [],
        }
        for x in self.dtable.get_all_eqs_and_why():
            x, why = x[:-1], x[-1]
            dep = EmptyDependency(
                level=level,
                rule_name=AlgebraicRules.Distance_Chase.value,
            )
            dep.why = why

            if len(x) == 2:
                a, b = x
                if a == b:
                    continue

                dep.name = f"inci {a.name} {b.name}"
                added[ConceptName.INCI.value].append((x, dep))

            if len(x) == 4:
                a, b, c, d = x
                if not (a != b and c != d and (a != c or b != d)):
                    continue
                added[ConceptName.CONGRUENT.value].append((a, b, c, d, dep))

            if len(x) == 6:
                a, b, c, d, num, den = x
                if not (a != b and c != d and (a != c or b != d)):
                    continue
                added[ConceptName.CONSTANT_RATIO.value].append(
                    (a, b, c, d, num, den, dep)
                )

        return added

    def _add_para(self, dep: "Dependency"):
        ab, cd = dep.algebra
        self.atable.add_para(ab, cd, dep)

    def _add_perp(self, dep: "Dependency"):
        ab, cd = dep.algebra
        self.atable.add_const_angle(ab, cd, 90, dep)

    def _add_eqangle(self, dep: "Dependency"):
        ab, cd, mn, pq = dep.algebra
        if (ab, cd) == (pq, mn):
            self.atable.add_const_angle(ab, cd, 90, dep)
        else:
            self.atable.add_eqangle(ab, cd, mn, pq, dep)

    def _add_eqratio(self, dep: "Dependency"):
        ab, cd, mn, pq = dep.algebra
        if (ab, cd) == (pq, mn):
            self.rtable.add_eq(ab, cd, dep)
        else:
            self.rtable.add_eqratio(ab, cd, mn, pq, dep)

    def _add_aconst(self, dep: "Dependency"):
        bx, ab, y = dep.algebra
        self.atable.add_const_angle(bx, ab, y, dep)

    def _add_rconst(self, dep: "Dependency"):
        l1, l2, m, n = dep.algebra
        self.rtable.add_const_ratio(l1, l2, m, n, dep)

    def _add_cong(self, dep: "Dependency"):
        a, b, c, d = dep.args
        ab, _ = self.symbols_graph.get_line_thru_pair_why(a, b)
        cd, _ = self.symbols_graph.get_line_thru_pair_why(c, d)
        self.dtable.add_cong(ab, cd, a, b, c, d, dep)

        ab, cd = dep.algebra
        self.rtable.add_eq(ab, cd, dep)

    def _create_const_ang(self, n: int, d: int) -> None:
        n, d = geosolver.ratios.simplify(n, d)
        ang = self.aconst[(n, d)] = self.symbols_graph.new_node(Angle, f"{n}pi/{d}")
        ang.set_directions(None, None)
        self.symbols_graph.get_node_val(ang, deps=None)

    def _create_const_rat(self, n: int, d: int) -> None:
        n, d = geosolver.ratios.simplify(n, d)
        rat = self.rconst[(n, d)] = self.symbols_graph.new_node(Ratio, f"{n}/{d}")
        rat.set_lengths(None, None)
        self.symbols_graph.get_node_val(rat, deps=None)

    def get_or_create_const_ang(self, n: int, d: int) -> None:
        n, d = geosolver.ratios.simplify(n, d)
        if (n, d) not in self.aconst:
            self._create_const_ang(n, d)
        ang1 = self.aconst[(n, d)]

        n, d = geosolver.ratios.simplify(d - n, d)
        if (n, d) not in self.aconst:
            self._create_const_ang(n, d)
        ang2 = self.aconst[(n, d)]
        return ang1, ang2

    def get_or_create_const_rat(self, n: int, d: int) -> None:
        n, d = geosolver.ratios.simplify(n, d)
        if (n, d) not in self.rconst:
            self._create_const_rat(n, d)
        rat1 = self.rconst[(n, d)]

        if (d, n) not in self.rconst:
            self._create_const_rat(d, n)
        rat2 = self.rconst[(d, n)]
        return rat1, rat2
