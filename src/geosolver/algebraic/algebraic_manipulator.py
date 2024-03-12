from typing import TYPE_CHECKING


from geosolver.algebraic import AlgebraicRules
from geosolver.algebraic.geometric_tables import AngleTable, DistanceTable, RatioTable
from geosolver.geometry import Angle, Point, Ratio, is_equiv
from geosolver.numericals import check

from geosolver.problem import Dependency, EmptyDependency
import geosolver.ratios

if TYPE_CHECKING:
    from geosolver.graph import ProofGraph


class AlgebraicManipulator:
    def __init__(self) -> None:
        self.atable = AngleTable()
        self.dtable = DistanceTable()
        self.rtable = RatioTable()

        self.rconst = {}  # contains all constant ratios
        self.aconst = {}  # contains all constant angles.

    def add_algebra(self, graph: "ProofGraph", dep: Dependency, level: int) -> None:
        """Add new algebraic predicates."""
        _ = level
        if dep.name not in [
            "para",
            "perp",
            "eqangle",
            "eqratio",
            "aconst",
            "rconst",
            "cong",
        ]:
            return

        name, args = dep.name, dep.args

        if name == "para":
            ab, cd = dep.algebra
            self.atable.add_para(ab, cd, dep)

        if name == "perp":
            ab, cd = dep.algebra
            self.atable.add_const_angle(ab, cd, 90, dep)

        if name == "eqangle":
            ab, cd, mn, pq = dep.algebra
            if (ab, cd) == (pq, mn):
                self.atable.add_const_angle(ab, cd, 90, dep)
            else:
                self.atable.add_eqangle(ab, cd, mn, pq, dep)

        if name == "eqratio":
            ab, cd, mn, pq = dep.algebra
            if (ab, cd) == (pq, mn):
                self.rtable.add_eq(ab, cd, dep)
            else:
                self.rtable.add_eqratio(ab, cd, mn, pq, dep)

        if name == "aconst":
            bx, ab, y = dep.algebra
            self.atable.add_const_angle(bx, ab, y, dep)

        if name == "rconst":
            l1, l2, m, n = dep.algebra
            self.rtable.add_const_ratio(l1, l2, m, n, dep)

        if name == "cong":
            a, b, c, d = args
            ab, _ = graph.get_line_thru_pair_why(a, b)
            cd, _ = graph.get_line_thru_pair_why(c, d)
            self.dtable.add_cong(ab, cd, a, b, c, d, dep)

            ab, cd = dep.algebra
            self.rtable.add_eq(ab, cd, dep)

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
        eqs = {"eqangle": derives.pop("eqangle"), "eqratio": derives.pop("eqratio")}
        return derives, eqs

    def derive_ratio_algebra(
        self, level: int, verbose: bool = False
    ) -> dict[str, list[tuple[Point, ...]]]:
        """Derive new eqratio predicates."""
        added = {"cong2": [], "eqratio": []}

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
                added["cong2"].append((m, n, p, q, dep))

            if len(x) == 4:
                a, b, c, d = x
                added["eqratio"].append((a, b, c, d, dep))

        return added

    def derive_angle_algebra(
        self, level: int, verbose: bool = False
    ) -> dict[str, list[tuple[Point, ...]]]:
        """Derive new eqangles predicates."""
        added = {"eqangle": [], "aconst": [], "para": []}

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
                if not check("para", [e, f, p, q]):
                    continue

                added["para"].append((a, b, dep))

            if len(x) == 3:
                a, b, (n, d) = x

                (e, f), (p, q) = a._obj.points, b._obj.points
                if not check("aconst", [e, f, p, q, n, d]):
                    continue

                added["aconst"].append((a, b, n, d, dep))

            if len(x) == 4:
                a, b, c, d = x
                added["eqangle"].append((a, b, c, d, dep))

        return added

    def derive_distance_algebra(
        self, level: int, verbose: bool = False
    ) -> dict[str, list[tuple[Point, ...]]]:
        """Derive new cong predicates."""
        added = {"inci": [], "cong": [], "rconst": []}
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
                added["inci"].append((x, dep))

            if len(x) == 4:
                a, b, c, d = x
                if not (a != b and c != d and (a != c or b != d)):
                    continue
                added["cong"].append((a, b, c, d, dep))

            if len(x) == 6:
                a, b, c, d, num, den = x
                if not (a != b and c != d and (a != c or b != d)):
                    continue
                added["rconst"].append((a, b, c, d, num, den, dep))

        return added

    def _create_const_ang(self, graph: "ProofGraph", n: int, d: int) -> None:
        n, d = geosolver.ratios.simplify(n, d)
        ang = self.aconst[(n, d)] = graph.new_node(Angle, f"{n}pi/{d}")
        ang.set_directions(None, None)
        graph.connect_val(ang, deps=None)

    def _create_const_rat(self, graph: "ProofGraph", n: int, d: int) -> None:
        n, d = geosolver.ratios.simplify(n, d)
        rat = self.rconst[(n, d)] = graph.new_node(Ratio, f"{n}/{d}")
        rat.set_lengths(None, None)
        graph.connect_val(rat, deps=None)

    def get_or_create_const_ang(self, graph: "ProofGraph", n: int, d: int) -> None:
        n, d = geosolver.ratios.simplify(n, d)
        if (n, d) not in self.aconst:
            self._create_const_ang(graph, n, d)
        ang1 = self.aconst[(n, d)]

        n, d = geosolver.ratios.simplify(d - n, d)
        if (n, d) not in self.aconst:
            self._create_const_ang(graph, n, d)
        ang2 = self.aconst[(n, d)]
        return ang1, ang2

    def get_or_create_const_rat(self, graph: "ProofGraph", n: int, d: int) -> None:
        n, d = geosolver.ratios.simplify(n, d)
        if (n, d) not in self.rconst:
            self._create_const_rat(graph, n, d)
        rat1 = self.rconst[(n, d)]

        if (d, n) not in self.rconst:
            self._create_const_rat(graph, d, n)
        rat2 = self.rconst[(d, n)]
        return rat1, rat2
