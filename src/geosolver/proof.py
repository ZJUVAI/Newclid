# Copyright 2023 DeepMind Technologies Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

"""Implements the graph representation of the proof state."""


from __future__ import annotations

from collections import defaultdict
from typing import Generator, Optional, Union
import logging

from geosolver.symbols_graph import SymbolsGraph
from geosolver.algebraic.algebraic_manipulator import AlgebraicManipulator
from geosolver.geometry import (
    Angle,
    Direction,
    Length,
    Node,
    Ratio,
    all_angles,
    all_ratios,
    is_equal,
    is_equiv,
    why_equal,
)
from geosolver.geometry import Circle, Line, Point, Segment
from geosolver.geometry import Measure, Value
import geosolver.combinatorics as comb
import geosolver.numerical.geometries as num_geo

from geosolver.numerical.check import (
    check_coll_numerical,
    check_numerical,
    check_para_numerical,
    check_perp_numerical,
    check_sameside_numerical,
)
from geosolver.numerical.distances import (
    check_too_far_numerical,
    check_too_close_numerical,
)
import geosolver.numerical.check as nm
from geosolver.numerical.sketch import sketch


from geosolver.problem import (
    CONSTRUCTION_RULE,
    Clause,
    Definition,
    Dependency,
    EmptyDependency,
    Problem,
    hashed,
)
from geosolver.dependency_graph import DependencyGraph
from geosolver.ratios import simplify


FREE = [
    "free",
    "segment",
    "r_triangle",
    "risos",
    "triangle",
    "triangle12",
    "ieq_triangle",
    "eq_quadrangle",
    "eq_trapezoid",
    "eqdia_quadrangle",
    "quadrangle",
    "r_trapezoid",
    "rectangle",
    "isquare",
    "trapezoid",
    "pentagon",
    "iso_triangle",
]

INTERSECT = [
    "angle_bisector",
    "angle_mirror",
    "eqdistance",
    "lc_tangent",
    "on_aline",
    "on_bline",
    "on_circle",
    "on_line",
    "on_pline",
    "on_tline",
    "on_dia",
    "s_angle",
    "on_opline",
    "eqangle3",
]


class DepCheckFailError(Exception):
    pass


class PointTooCloseError(Exception):
    pass


class PointTooFarError(Exception):
    pass


class Proof:
    """Object representing the proof state."""

    def __init__(
        self,
        alegbraic_manipulator: AlgebraicManipulator,
        symbols_graph: SymbolsGraph,
    ):
        self.cache = {}

        self.symbols_graph = symbols_graph
        self.alegbraic_manipulator = alegbraic_manipulator

        self._halfpi, _ = self.alegbraic_manipulator.get_or_create_const_ang(
            self.symbols_graph, 1, 2
        )
        self.vhalfpi = self._halfpi.val

        self.dependency_graph = DependencyGraph()

    def copy(self) -> Proof:
        """Make a copy of self."""
        p, definitions = self.build_def

        p = p.copy()
        for clause in p.clauses:
            clause.nums = []
            for pname in clause.points:
                clause.nums.append(self.symbols_graph._name2node[pname].num)

        proof, _ = Proof.build_problem(p, definitions, verbose=False, init_copy=False)

        proof.build_clauses = list(getattr(self, "build_clauses", []))
        return proof

    def do_algebra(self, name: str, args: list[Point]) -> list[Dependency]:
        """Derive (but not add) new algebraic predicates."""
        new_deps = []

        if name == "para":
            a, b, dep = args
            if is_equiv(a, b):
                return []
            else:
                (x, y), (m, n) = a._obj.points, b._obj.points
                new_deps = self._add_para([x, y, m, n], dep)

        elif name == "aconst":
            a, b, n, d, dep = args
            ab, ba, why = self.symbols_graph.get_or_create_angle_from_directions(
                a, b, deps=None
            )
            nd, dn = self.alegbraic_manipulator.get_or_create_const_ang(
                self.symbols_graph, n, d
            )

            (x, y), (m, n) = a._obj.points, b._obj.points

            if why:
                dep0 = dep.populate("aconst", [x, y, m, n, nd])
                dep = EmptyDependency(level=dep.level, rule_name=None)
                dep.why = [dep0] + why

            a, b = ab._d
            (x, y), (m, n) = a._obj.points, b._obj.points

            added = []
            if not self.is_equal(ab, nd):
                if nd == self._halfpi:
                    added += self._add_perp([x, y, m, n], dep)
                # else:
                name = "aconst"
                args = [x, y, m, n, nd]
                dep1 = dep.populate(name, args)
                self.cache_dep(name, args, dep1)
                self.make_equal(nd, ab, deps=dep1)
                added += [dep1]

            if not self.is_equal(ba, dn):
                if dn == self._halfpi:
                    added += self._add_perp([m, n, x, y], dep)
                name = "aconst"
                args = [m, n, x, y, dn]
                dep2 = dep.populate(name, args)
                self.cache_dep(name, args, dep2)
                self.make_equal(dn, ba, deps=dep2)
                added += [dep2]
            new_deps = added

        elif name == "rconst":
            a, b, c, d, num, den, dep = args
            new_deps = self._add_eqrat_const([a, b, c, d, num, den], dep)

        elif name == "eqangle":
            d1, d2, d3, d4, dep = args
            a, b = d1._obj.points
            c, d = d2._obj.points
            e, f = d3._obj.points
            g, h = d4._obj.points

            new_deps = self._add_eqangle([a, b, c, d, e, f, g, h], dep)

        elif name == "eqratio":
            d1, d2, d3, d4, dep = args
            a, b = d1._obj.points
            c, d = d2._obj.points
            e, f = d3._obj.points
            g, h = d4._obj.points

            new_deps = self._add_eqratio([a, b, c, d, e, f, g, h], dep)

        elif name in ["cong", "cong2"]:
            a, b, c, d, dep = args
            if not (a != b and c != d and (a != c or b != d)):
                new_deps = []
            else:
                new_deps = self._add_cong([a, b, c, d], dep)

        self.dependency_graph.add_algebra_edges(new_deps, args[:-1])
        return new_deps

    def add_algebra(self, dep: Dependency, level: int) -> None:
        self.alegbraic_manipulator.add_algebra(self.symbols_graph, dep, level)

    @classmethod
    def build_problem(
        cls,
        pr: Problem,
        definitions: dict[str, Definition],
        verbose: bool = True,
        init_copy: bool = True,
    ) -> tuple[Proof, list[Dependency]]:
        """Build a problem into a gr.Graph object."""
        check = False
        proof = None
        added = None
        if verbose:
            logging.info(pr.url)
            logging.info(pr.txt())
        while not check:
            # While loop to search for coordinates
            # that checks premises conditions numerically
            # will result in infinite loop if problem is impossible numerically.
            try:
                proof = Proof(
                    alegbraic_manipulator=AlgebraicManipulator(),
                    symbols_graph=SymbolsGraph(),
                )
                added = []
                plevel = 0
                for clause in pr.clauses:
                    adds, plevel = proof.add_clause(
                        clause, plevel, definitions, verbose=verbose
                    )
                    added += adds
                proof.plevel = plevel

            except (num_geo.InvalidLineIntersectError, num_geo.InvalidQuadSolveError):
                continue
            except DepCheckFailError:
                continue
            except (PointTooCloseError, PointTooFarError):
                continue

            if not pr.goal:
                break

            args = list(
                map(
                    lambda x: proof.symbols_graph.get_point(x, lambda: int(x)),
                    pr.goal.args,
                )
            )
            proof.dependency_graph.add_goal(pr.goal.name, args)
            check = check_numerical(pr.goal.name, args)

        proof.url = pr.url
        proof.build_def = (pr, definitions)
        for add in added:
            proof.add_algebra(add, level=0)

        return proof, added

    def add_piece(
        self, name: str, args: list[Point], deps: EmptyDependency
    ) -> list[Dependency]:
        """Add a new predicate."""
        if name in ["coll", "collx"]:
            new_deps = self._add_coll(args, deps)
        elif name == "para":
            new_deps = self._add_para(args, deps)
        elif name == "perp":
            new_deps = self._add_perp(args, deps)
        elif name == "midp":
            new_deps = self._add_midp(args, deps)
        elif name == "cong":
            new_deps = self._add_cong(args, deps)
        elif name == "circle":
            new_deps = self._add_circle(args, deps)
        elif name == "cyclic":
            new_deps = self._add_cyclic(args, deps)
        elif name in ["eqangle", "eqangle6"]:
            new_deps = self._add_eqangle(args, deps)
        elif name in ["eqratio", "eqratio6"]:
            new_deps = self._add_eqratio(args, deps)
        # numerical!
        elif name == "s_angle":
            new_deps = self._add_s_angle(args, deps)
        elif name == "aconst":
            a, b, c, d, ang = args

            if isinstance(ang, str):
                name = ang
            else:
                name = ang.name

            num, den = name.split("pi/")
            num, den = int(num), int(den)
            new_deps = self._add_aconst([a, b, c, d, num, den], deps)
        elif name == "s_angle":
            b, x, a, b, ang = args

            if isinstance(ang, str):
                name = ang
            else:
                name = ang.name

            n, d = name.split("pi/")
            ang = int(n) * 180 / int(d)
            new_deps = self._add_s_angle([a, b, x, ang], deps)
        elif name == "rconst":
            a, b, c, d, rat = args

            if isinstance(rat, str):
                name = rat
            else:
                name = rat.name

            num, den = name.split("/")
            num, den = int(num), int(den)
            new_deps = self._add_eqrat_const([a, b, c, d, num, den], deps)

        # composite pieces:
        elif name == "cong2":
            new_deps = self._add_cong2(args, deps)
        elif name == "eqratio3":
            new_deps = self._add_eqratio3(args, deps)
        elif name == "eqratio4":
            new_deps = self._add_eqratio4(args, deps)
        elif name == "simtri":
            new_deps = self._add_simtri(args, deps)
        elif name == "contri":
            new_deps = self._add_contri(args, deps)
        elif name == "simtri2":
            new_deps = self._add_simtri2(args, deps)
        elif name == "contri2":
            new_deps = self._add_contri2(args, deps)
        elif name == "simtri*":
            new_deps = self._add_simtri_check(args, deps)
        elif name == "contri*":
            new_deps = self._add_contri_check(args, deps)
        elif name in ["acompute", "rcompute"]:
            dep = deps.populate(name, args)
            self.cache_dep(name, args, dep)
            new_deps = [dep]
        elif name in ["fixl", "fixc", "fixb", "fixt", "fixp"]:
            dep = deps.populate(name, args)
            self.cache_dep(name, args, dep)
            new_deps = [dep]
        elif name in ["ind"]:
            new_deps = []
        else:
            raise ValueError(f"Not recognize {name}")

        return new_deps

    def check(self, name: str, args: list[Point]) -> bool:
        """Symbolically check if a predicate is True."""
        if name == "ncoll":
            return self.check_ncoll(args)
        if name == "npara":
            return self.check_npara(args)
        if name == "nperp":
            return self.check_nperp(args)
        if name == "midp":
            return self.check_midp(args)
        if name == "cong":
            return self.check_cong(args)
        if name == "perp":
            return self.check_perp(args)
        if name == "para":
            return self.check_para(args)
        if name == "coll":
            return self.check_coll(args)
        if name == "cyclic":
            return self.check_cyclic(args)
        if name == "circle":
            return self.check_circle(args)
        if name == "aconst":
            return self.check_aconst(args)
        if name == "rconst":
            return self.check_rconst(args)
        if name == "acompute":
            return self.check_acompute(args)
        if name == "rcompute":
            return self.check_rcompute(args)
        if name in ["eqangle", "eqangle6"]:
            if len(args) == 5:
                return self.check_aconst(args)
            return self.check_eqangle(args)
        if name in ["eqratio", "eqratio6"]:
            if len(args) == 5:
                return self.check_rconst(args)
            return self.check_eqratio(args)
        if name in ["simtri", "simtri2", "simtri*"]:
            return self.check_simtri(args)
        if name in ["contri", "contri2", "contri*"]:
            return self.check_contri(args)
        if name == "sameside":
            return self.check_sameside(args)
        if name in "diff":
            a, b = args
            return not a.num.close(b.num)
        if name in ["fixl", "fixc", "fixb", "fixt", "fixp"]:
            return self.in_cache(name, args)
        if name in ["ind"]:
            return True
        raise ValueError(f"Not recognize {name}")

    def coll_dep(self, points: list[Point], p: Point) -> list[Dependency]:
        """Return the dep(.why) explaining why p is coll with points."""
        for p1, p2 in comb.comb2(points):
            if self.check_coll([p1, p2, p]):
                dep = Dependency("coll", [p1, p2, p], None, None)
                return dep.why_me_or_cache(self, None)

    def _add_coll(self, points: list[Point], deps: EmptyDependency) -> list[Dependency]:
        """Add a predicate that `points` are collinear."""
        points = list(set(points))
        og_points = list(points)

        all_lines = []
        for p1, p2 in comb.comb2(points):
            all_lines.append(self.symbols_graph.get_line_thru_pair(p1, p2))
        points = sum([line.neighbors(Point) for line in all_lines], [])
        points = list(set(points))

        existed = set()
        new = set()
        for p1, p2 in comb.comb2(points):
            if p1.name > p2.name:
                p1, p2 = p2, p1
            if (p1, p2) in self.symbols_graph._pair2line:
                line = self.symbols_graph._pair2line[(p1, p2)]
                existed.add(line)
            else:
                line = self.symbols_graph.get_new_line_thru_pair(p1, p2)
                new.add(line)

        existed = sorted(existed, key=lambda node: node.name)
        new = sorted(new, key=lambda node: node.name)

        existed, new = list(existed), list(new)
        if not existed:
            line0, *lines = new
        else:
            line0, lines = existed[0], existed[1:] + new

        add = []
        line0, why0 = line0.rep_and_why()
        a, b = line0.points
        for line in lines:
            c, d = line.points
            args = list({a, b, c, d})
            if len(args) < 3:
                continue

            whys = []
            for x in args:
                if x not in og_points:
                    whys.append(self.coll_dep(og_points, x))

            abcd_deps = deps
            if whys + why0:
                dep0 = deps.populate("coll", og_points)
                abcd_deps = EmptyDependency(level=deps.level, rule_name=None)
                abcd_deps.why = [dep0] + whys

            is_coll = self.check_coll(args)
            dep = abcd_deps.populate("coll", args)
            self.cache_dep("coll", args, dep)
            self.symbols_graph.merge_into(line0, [line], dep)

            if not is_coll:
                add += [dep]

        return add

    def check_coll(self, points: list[Point]) -> bool:
        points = list(set(points))
        if len(points) < 3:
            return True
        line2count = defaultdict(lambda: 0)
        for p in points:
            for line in p.neighbors(Line):
                line2count[line] += 1
        return any([count == len(points) for _, count in line2count.items()])

    def why_coll(self, args: tuple[Line, list[Point]]) -> list[Dependency]:
        line, points = args
        return line.why_coll(points)

    def is_equal(self, x: Node, y: Node, level: int = None) -> bool:
        return is_equal(x, y, level)

    def _add_eqrat_const(
        self, args: list[Point], deps: EmptyDependency
    ) -> list[Dependency]:
        """Add new algebraic predicates of type eqratio-constant."""
        a, b, c, d, num, den = args
        nd, dn = self.alegbraic_manipulator.get_or_create_const_rat(
            self.symbols_graph, num, den
        )

        if num == den:
            return self._add_cong([a, b, c, d], deps)

        ab = self.symbols_graph.get_or_create_segment(a, b, deps=None)
        cd = self.symbols_graph.get_or_create_segment(c, d, deps=None)

        self.symbols_graph.get_node_val(ab, deps=None)
        self.symbols_graph.get_node_val(cd, deps=None)

        if ab.val == cd.val:
            raise ValueError(f"{ab.name} and {cd.name} cannot be equal")

        args = [a, b, c, d, nd]
        i = 0
        for x, y, xy in [(a, b, ab), (c, d, cd)]:
            i += 1
            x_, y_ = list(xy._val._obj.points)
            if {x, y} == {x_, y_}:
                continue
            if deps:
                deps = deps.extend(self, "rconst", list(args), "cong", [x, y, x_, y_])
            args[2 * i - 2] = x_
            args[2 * i - 1] = y_

        ab_cd, cd_ab, why = self.symbols_graph.get_or_create_ratio_from_segments(
            ab, cd, deps=None
        )
        if why:
            dep0 = deps.populate("rconst", [a, b, c, d, nd])
            deps = EmptyDependency(level=deps.level, rule_name=None)
            deps.why = [dep0] + why

        lab, lcd = ab_cd._l
        a, b = list(lab._obj.points)
        c, d = list(lcd._obj.points)

        add = []
        if not self.is_equal(ab_cd, nd):
            args = [a, b, c, d, nd]
            dep1 = deps.populate("rconst", args)
            dep1.algebra = ab._val, cd._val, num, den
            self.make_equal(nd, ab_cd, deps=dep1)
            self.cache_dep("rconst", [a, b, c, d, nd], dep1)
            add += [dep1]

        if not self.is_equal(cd_ab, dn):
            args = [c, d, a, b, dn]
            dep2 = deps.populate("rconst", args)
            dep2.algebra = cd._val, ab._val, num, den
            self.make_equal(dn, cd_ab, deps=dep2)
            self.cache_dep("rconst", [c, d, a, b, dn], dep2)
            add += [dep2]

        return add

    def check_ncoll(self, points: list[Point]) -> bool:
        if self.check_coll(points):
            return False
        return not check_coll_numerical([p.num for p in points])

    def check_sameside(self, points: list[Point]) -> bool:
        return check_sameside_numerical([p.num for p in points])

    def make_equal(self, x: Node, y: Node, deps: Dependency) -> None:
        """Make that two nodes x and y are equal, i.e. merge their value node."""
        if x.val is None:
            x, y = y, x

        self.symbols_graph.get_node_val(x, deps=None)
        self.symbols_graph.get_node_val(y, deps=None)
        vx = x._val
        vy = y._val

        if vx == vy:
            return

        merges = [vx, vy]

        if (
            isinstance(x, Angle)
            and x not in self.alegbraic_manipulator.aconst.values()
            and y not in self.alegbraic_manipulator.aconst.values()
            and x.directions == y.directions[::-1]
            and x.directions[0] != x.directions[1]
        ):
            merges = [self.vhalfpi, vx, vy]

        self.symbols_graph.merge(merges, deps)

    def merge_vals(self, vx: Node, vy: Node, deps: Dependency) -> None:
        if vx == vy:
            return
        merges = [vx, vy]
        self.symbols_graph.merge(merges, deps)

    def why_equal(self, x: Node, y: Node, level: int) -> list[Dependency]:
        return why_equal(x, y, level)

    def _why_coll4(
        self,
        a: Point,
        b: Point,
        ab: Line,
        c: Point,
        d: Point,
        cd: Line,
        level: int,
    ) -> list[Dependency]:
        return self._why_coll2(a, b, ab, level) + self._why_coll2(c, d, cd, level)

    def _why_coll8(
        self,
        a: Point,
        b: Point,
        ab: Line,
        c: Point,
        d: Point,
        cd: Line,
        m: Point,
        n: Point,
        mn: Line,
        p: Point,
        q: Point,
        pq: Line,
        level: int,
    ) -> list[Dependency]:
        """Dependency list of why 8 points are collinear."""
        why8 = self._why_coll4(a, b, ab, c, d, cd, level)
        why8 += self._why_coll4(m, n, mn, p, q, pq, level)
        return why8

    def _add_para(self, points: list[Point], deps: EmptyDependency) -> list[Dependency]:
        """Add a new predicate that 4 points (2 lines) are parallel."""
        a, b, c, d = points
        ab, why1 = self.symbols_graph.get_line_thru_pair_why(a, b)
        cd, why2 = self.symbols_graph.get_line_thru_pair_why(c, d)

        is_equal = self.is_equal(ab, cd)

        (a, b), (c, d) = ab.points, cd.points

        dep0 = deps.populate("para", points)
        deps = EmptyDependency(level=deps.level, rule_name=None)

        deps = deps.populate("para", [a, b, c, d])
        deps.why = [dep0] + why1 + why2

        self.make_equal(ab, cd, deps)
        deps.algebra = ab._val, cd._val

        self.cache_dep("para", [a, b, c, d], deps)
        if not is_equal:
            return [deps]
        return []

    def why_para(self, args: list[Point]) -> list[Dependency]:
        ab, cd, lvl = args
        return self.why_equal(ab, cd, lvl)

    def check_para_or_coll(self, points: list[Point]) -> bool:
        return self.check_para(points) or self.check_coll(points)

    def check_para(self, points: list[Point]) -> bool:
        a, b, c, d = points
        if (a == b) or (c == d):
            return False
        ab = self.symbols_graph.get_line(a, b)
        cd = self.symbols_graph.get_line(c, d)
        if not ab or not cd:
            return False

        return self.is_equal(ab, cd)

    def check_npara(self, points: list[Point]) -> bool:
        if self.check_para(points):
            return False
        return not check_para_numerical([p.num for p in points])

    def _add_para_or_coll(
        self,
        a: Point,
        b: Point,
        c: Point,
        d: Point,
        x: Point,
        y: Point,
        m: Point,
        n: Point,
        deps: EmptyDependency,
    ) -> list[Dependency]:
        """Add a new parallel or collinear predicate."""
        extends = [("perp", [x, y, m, n])]
        if {a, b} == {x, y}:
            pass
        elif self.check_para([a, b, x, y]):
            extends.append(("para", [a, b, x, y]))
        elif self.check_coll([a, b, x, y]):
            extends.append(("coll", set(list([a, b, x, y]))))
        else:
            return None

        if m in [c, d] or n in [c, d] or c in [m, n] or d in [m, n]:
            pass
        elif self.check_coll([c, d, m]):
            extends.append(("coll", [c, d, m]))
        elif self.check_coll([c, d, n]):
            extends.append(("coll", [c, d, n]))
        elif self.check_coll([c, m, n]):
            extends.append(("coll", [c, m, n]))
        elif self.check_coll([d, m, n]):
            extends.append(("coll", [d, m, n]))
        else:
            deps = deps.extend_many(self, "perp", [a, b, c, d], extends)
            return self._add_para([c, d, m, n], deps)

        deps = deps.extend_many(self, "perp", [a, b, c, d], extends)
        return self._add_coll(list(set([c, d, m, n])), deps)

    def _maybe_make_para_from_perp(
        self, points: list[Point], deps: EmptyDependency
    ) -> Optional[list[Dependency]]:
        """Maybe add a new parallel predicate from perp predicate."""
        a, b, c, d = points
        halfpi = self.alegbraic_manipulator.aconst[(1, 2)]
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
                args = args + (deps,)
                add = self._add_para_or_coll(*args)
                if add:
                    return add

        return None

    def _add_perp(self, points: list[Point], deps: EmptyDependency) -> list[Dependency]:
        """Add a new perpendicular predicate from 4 points (2 lines)."""
        add = self._maybe_make_para_from_perp(points, deps)
        if add is not None:
            return add

        a, b, c, d = points
        ab, why1 = self.symbols_graph.get_line_thru_pair_why(a, b)
        cd, why2 = self.symbols_graph.get_line_thru_pair_why(c, d)

        (a, b), (c, d) = ab.points, cd.points

        if why1 + why2:
            dep0 = deps.populate("perp", points)
            deps = EmptyDependency(level=deps.level, rule_name=None)
            deps.why = [dep0] + why1 + why2

        self.symbols_graph.get_node_val(ab, deps=None)
        self.symbols_graph.get_node_val(cd, deps=None)

        if ab.val == cd.val:
            raise ValueError(f"{ab.name} and {cd.name} Cannot be perp.")

        args = [a, b, c, d]
        i = 0
        for x, y, xy in [(a, b, ab), (c, d, cd)]:
            i += 1
            x_, y_ = xy._val._obj.points
            if {x, y} == {x_, y_}:
                continue
            if deps:
                deps = deps.extend(self, "perp", list(args), "para", [x, y, x_, y_])
            args[2 * i - 2] = x_
            args[2 * i - 1] = y_

        a12, a21, why = self.symbols_graph.get_or_create_angle_from_lines(
            ab, cd, deps=None
        )

        if why:
            dep0 = deps.populate("perp", [a, b, c, d])
            deps = EmptyDependency(level=deps.level, rule_name=None)
            deps.why = [dep0] + why

        dab, dcd = a12._d
        a, b = dab._obj.points
        c, d = dcd._obj.points

        is_equal = self.is_equal(a12, a21)
        deps = deps.populate("perp", [a, b, c, d])
        deps.algebra = [dab, dcd]
        self.make_equal(a12, a21, deps=deps)

        self.cache_dep("perp", [a, b, c, d], deps)
        self.cache_dep("eqangle", [a, b, c, d, c, d, a, b], deps)

        if not is_equal:
            return [deps]
        return []

    def why_perp(self, args: list[Union[Point, list[Dependency]]]) -> list[Dependency]:
        a, b, deps = args
        return deps + self.why_equal(a, b, None)

    def check_perpl(self, ab: Line, cd: Line) -> bool:
        if ab.val is None or cd.val is None:
            return False
        if ab.val == cd.val:
            return False
        a12, a21 = self.symbols_graph.get_angle(ab.val, cd.val)
        if a12 is None or a21 is None:
            return False
        return self.is_equal(a12, a21)

    def check_perp(self, points: list[Point]) -> bool:
        a, b, c, d = points
        ab = self.symbols_graph.get_line(a, b)
        cd = self.symbols_graph.get_line(c, d)
        if not ab or not cd:
            return False
        return self.check_perpl(ab, cd)

    def check_nperp(self, points: list[Point]) -> bool:
        if self.check_perp(points):
            return False
        return not check_perp_numerical([p.num for p in points])

    def _add_cong(self, points: list[Point], deps: EmptyDependency) -> list[Dependency]:
        """Add that two segments (4 points) are congruent."""
        a, b, c, d = points
        ab = self.symbols_graph.get_or_create_segment(a, b, deps=None)
        cd = self.symbols_graph.get_or_create_segment(c, d, deps=None)

        is_equal = self.is_equal(ab, cd)

        dep = deps.populate("cong", [a, b, c, d])
        self.make_equal(ab, cd, deps=dep)
        dep.algebra = ab._val, cd._val

        self.cache_dep("cong", [a, b, c, d], dep)

        result = []

        if not is_equal:
            result += [dep]

        if a not in [c, d] and b not in [c, d]:
            return result

        if b in [c, d]:
            a, b = b, a
        if a == d:
            c, d = d, c

        result += self._maybe_add_cyclic_from_cong(a, b, d, dep)
        return result

    def _maybe_add_cyclic_from_cong(
        self, a: Point, b: Point, c: Point, cong_ab_ac: Dependency
    ) -> list[Dependency]:
        """Maybe add a new cyclic predicate from given congruent segments."""
        ab = self.symbols_graph.get_or_create_segment(a, b, deps=None)

        # all eq segs with one end being a.
        segs = [s for s in ab.val.neighbors(Segment) if a in s.points]

        # all points on circle (a, b)
        points = []
        for s in segs:
            x, y = list(s.points)
            points.append(x if y == a else y)

        # for sure both b and c are in points
        points = [p for p in points if p not in [b, c]]

        if len(points) < 2:
            return []

        x, y = points[:2]

        if self.check_cyclic([b, c, x, y]):
            return []

        ax = self.symbols_graph.get_or_create_segment(a, x, deps=None)
        ay = self.symbols_graph.get_or_create_segment(a, y, deps=None)
        why = ab._val.why_equal([ax._val, ay._val], level=None)
        why += [cong_ab_ac]

        deps = EmptyDependency(cong_ab_ac.level, "")
        deps.why = why

        return self._add_cyclic([b, c, x, y], deps)

    def check_cong(self, points: list[Point]) -> bool:
        a, b, c, d = points
        if {a, b} == {c, d}:
            return True

        ab = self.symbols_graph.get_segment(a, b)
        cd = self.symbols_graph.get_segment(c, d)
        if ab is None or cd is None:
            return False
        return self.is_equal(ab, cd)

    def why_cong(self, args: tuple[Segment, Segment]) -> list[Dependency]:
        ab, cd = args
        return self.why_equal(ab, cd, None)

    def _add_midp(self, points: list[Point], deps: EmptyDependency) -> list[Dependency]:
        m, a, b = points
        add = self._add_coll(points, deps=deps)
        add += self._add_cong([m, a, m, b], deps)
        return add

    def why_midp(
        self, args: tuple[Line, list[Point], Segment, Segment]
    ) -> list[Dependency]:
        line, points, ma, mb = args
        return self.why_coll([line, points]) + self.why_cong([ma, mb])

    def check_midp(self, points: list[Point]) -> bool:
        if not self.check_coll(points):
            return False
        m, a, b = points
        return self.check_cong([m, a, m, b])

    def _add_circle(
        self, points: list[Point], deps: EmptyDependency
    ) -> list[Dependency]:
        o, a, b, c = points
        add = self._add_cong([o, a, o, b], deps=deps)
        add += self._add_cong([o, a, o, c], deps=deps)
        return add

    def why_circle(self, args: tuple[Segment, Segment, Segment]) -> list[Dependency]:
        oa, ob, oc = args
        return self.why_equal(oa, ob, None) and self.why_equal(oa, oc, None)

    def check_circle(self, points: list[Point]) -> bool:
        o, a, b, c = points
        return self.check_cong([o, a, o, b]) and self.check_cong([o, a, o, c])

    def cyclic_dep(self, points: list[Point], p: Point) -> list[Dependency]:
        for p1, p2, p3 in comb.comb3(points):
            if self.check_cyclic([p1, p2, p3, p]):
                dep = Dependency("cyclic", [p1, p2, p3, p], None, None)
                return dep.why_me_or_cache(self, None)

    def _add_cyclic(
        self, points: list[Point], deps: EmptyDependency
    ) -> list[Dependency]:
        """Add a new cyclic predicate that 4 points are concyclic."""
        points = list(set(points))
        og_points = list(points)

        all_circles = []
        for p1, p2, p3 in comb.comb3(points):
            all_circles.append(self.symbols_graph.get_circle_thru_triplet(p1, p2, p3))
        points = sum([c.neighbors(Point) for c in all_circles], [])
        points = list(set(points))

        existed = set()
        new = set()
        for p1, p2, p3 in comb.comb3(points):
            p1, p2, p3 = sorted([p1, p2, p3], key=lambda x: x.name)

            if (p1, p2, p3) in self.symbols_graph._triplet2circle:
                circle = self.symbols_graph._triplet2circle[(p1, p2, p3)]
                existed.add(circle)
            else:
                circle = self.symbols_graph.get_new_circle_thru_triplet(p1, p2, p3)
                new.add(circle)

        existed = sorted(existed, key=lambda node: node.name)
        new = sorted(new, key=lambda node: node.name)

        existed, new = list(existed), list(new)
        if not existed:
            circle0, *circles = new
        else:
            circle0, circles = existed[0], existed[1:] + new

        add = []
        circle0, why0 = circle0.rep_and_why()
        a, b, c = circle0.points
        for circle in circles:
            d, e, f = circle.points
            args = list({a, b, c, d, e, f})
            if len(args) < 4:
                continue
            whys = []
            for x in [a, b, c, d, e, f]:
                if x not in og_points:
                    whys.append(self.cyclic_dep(og_points, x))
            abcdef_deps = deps
            if whys + why0:
                dep0 = deps.populate("cyclic", og_points)
                abcdef_deps = EmptyDependency(level=deps.level, rule_name=None)
                abcdef_deps.why = [dep0] + whys

            is_cyclic = self.check_cyclic(args)

            dep = abcdef_deps.populate("cyclic", args)
            self.cache_dep("cyclic", args, dep)
            self.symbols_graph.merge_into(circle0, [circle], dep)
            if not is_cyclic:
                add += [dep]

        return add

    def check_cyclic(self, points: list[Point]) -> bool:
        points = list(set(points))
        if len(points) < 4:
            return True
        circle2count = defaultdict(lambda: 0)
        for p in points:
            for c in p.neighbors(Circle):
                circle2count[c] += 1
        return any([count == len(points) for _, count in circle2count.items()])

    def make_equal_pairs(
        self,
        a: Point,
        b: Point,
        c: Point,
        d: Point,
        m: Point,
        n: Point,
        p: Point,
        q: Point,
        ab: Line,
        cd: Line,
        mn: Line,
        pq: Line,
        deps: EmptyDependency,
    ) -> list[Dependency]:
        """Add ab/cd = mn/pq in case either two of (ab,cd,mn,pq) are equal."""
        depname = "eqratio" if isinstance(ab, Segment) else "eqangle"
        eqname = "cong" if isinstance(ab, Segment) else "para"

        is_equal = self.is_equal(mn, pq)

        if ab != cd:
            dep0 = deps.populate(depname, [a, b, c, d, m, n, p, q])
            deps = EmptyDependency(level=deps.level, rule_name=None)

            dep = Dependency(eqname, [a, b, c, d], None, deps.level)
            deps.why = [dep0, dep.why_me_or_cache(self, None)]

        elif eqname == "para":  # ab == cd.
            colls = [a, b, c, d]
            if len(set(colls)) > 2:
                dep0 = deps.populate(depname, [a, b, c, d, m, n, p, q])
                deps = EmptyDependency(level=deps.level, rule_name=None)

                dep = Dependency("collx", colls, None, deps.level)
                deps.why = [dep0, dep.why_me_or_cache(self, None)]

        deps = deps.populate(eqname, [m, n, p, q])
        self.make_equal(mn, pq, deps=deps)

        deps.algebra = mn._val, pq._val
        self.cache_dep(eqname, [m, n, p, q], deps)

        if is_equal:
            return []
        return [deps]

    def _maybe_make_equal_pairs(
        self,
        a: Point,
        b: Point,
        c: Point,
        d: Point,
        m: Point,
        n: Point,
        p: Point,
        q: Point,
        ab: Line,
        cd: Line,
        mn: Line,
        pq: Line,
        deps: EmptyDependency,
    ) -> Optional[list[Dependency]]:
        """Add ab/cd = mn/pq in case maybe either two of (ab,cd,mn,pq) are equal."""
        level = deps.level
        if self.is_equal(ab, cd, level):
            return self.make_equal_pairs(a, b, c, d, m, n, p, q, ab, cd, mn, pq, deps)
        elif self.is_equal(mn, pq, level):
            return self.make_equal_pairs(
                m,
                n,
                p,
                q,
                a,
                b,
                c,
                d,
                mn,
                pq,
                ab,
                cd,
                deps,
            )
        elif self.is_equal(ab, mn, level):
            return self.make_equal_pairs(
                a,
                b,
                m,
                n,
                c,
                d,
                p,
                q,
                ab,
                mn,
                cd,
                pq,
                deps,
            )
        elif self.is_equal(cd, pq, level):
            return self.make_equal_pairs(
                c,
                d,
                p,
                q,
                a,
                b,
                m,
                n,
                cd,
                pq,
                ab,
                mn,
                deps,
            )
        else:
            return None

    def _add_eqangle8(
        self,
        a: Point,
        b: Point,
        c: Point,
        d: Point,
        m: Point,
        n: Point,
        p: Point,
        q: Point,
        ab: Line,
        cd: Line,
        mn: Line,
        pq: Line,
        deps: EmptyDependency,
    ) -> list[Dependency]:
        """Add eqangle core."""
        if deps:
            deps = deps.copy()

        args = [a, b, c, d, m, n, p, q]
        i = 0
        for x, y, xy in [(a, b, ab), (c, d, cd), (m, n, mn), (p, q, pq)]:
            i += 1
            x_, y_ = xy._val._obj.points
            if {x, y} == {x_, y_}:
                continue
            if deps:
                deps = deps.extend(self, "eqangle", list(args), "para", [x, y, x_, y_])

                args[2 * i - 2] = x_
                args[2 * i - 1] = y_

        add = []
        ab_cd, cd_ab, why1 = self.symbols_graph.get_or_create_angle_from_lines(
            ab, cd, deps=None
        )
        mn_pq, pq_mn, why2 = self.symbols_graph.get_or_create_angle_from_lines(
            mn, pq, deps=None
        )

        why = why1 + why2
        if why:
            dep0 = deps.populate("eqangle", args)
            deps = EmptyDependency(level=deps.level, rule_name=None)
            deps.why = [dep0] + why

        dab, dcd = ab_cd._d
        dmn, dpq = mn_pq._d

        a, b = dab._obj.points
        c, d = dcd._obj.points
        m, n = dmn._obj.points
        p, q = dpq._obj.points

        is_eq1 = self.is_equal(ab_cd, mn_pq)
        deps1 = None
        if deps:
            deps1 = deps.populate("eqangle", [a, b, c, d, m, n, p, q])
            deps1.algebra = [dab, dcd, dmn, dpq]
        if not is_eq1:
            add += [deps1]
        self.cache_dep("eqangle", [a, b, c, d, m, n, p, q], deps1)
        self.make_equal(ab_cd, mn_pq, deps=deps1)

        is_eq2 = self.is_equal(cd_ab, pq_mn)
        deps2 = None
        if deps:
            deps2 = deps.populate("eqangle", [c, d, a, b, p, q, m, n])
            deps2.algebra = [dcd, dab, dpq, dmn]
        if not is_eq2:
            add += [deps2]
        self.cache_dep("eqangle", [c, d, a, b, p, q, m, n], deps2)
        self.make_equal(cd_ab, pq_mn, deps=deps2)

        return add

    def _add_eqangle(
        self, points: list[Point], deps: EmptyDependency
    ) -> list[Dependency]:
        """Add eqangle made by 8 points in `points`."""
        if deps:
            deps = deps.copy()
        a, b, c, d, m, n, p, q = points
        ab, why1 = self.symbols_graph.get_line_thru_pair_why(a, b)
        cd, why2 = self.symbols_graph.get_line_thru_pair_why(c, d)
        mn, why3 = self.symbols_graph.get_line_thru_pair_why(m, n)
        pq, why4 = self.symbols_graph.get_line_thru_pair_why(p, q)

        a, b = ab.points
        c, d = cd.points
        m, n = mn.points
        p, q = pq.points

        if deps and why1 + why2 + why3 + why4:
            dep0 = deps.populate("eqangle", points)
            deps = EmptyDependency(level=deps.level, rule_name=None)
            deps.why = [dep0] + why1 + why2 + why3 + why4

        add = self._maybe_make_equal_pairs(a, b, c, d, m, n, p, q, ab, cd, mn, pq, deps)

        if add is not None:
            return add

        self.symbols_graph.get_node_val(ab, deps=None)
        self.symbols_graph.get_node_val(cd, deps=None)
        self.symbols_graph.get_node_val(mn, deps=None)
        self.symbols_graph.get_node_val(pq, deps=None)

        add = []
        if (
            ab.val != cd.val
            and mn.val != pq.val
            and (ab.val != mn.val or cd.val != pq.val)
        ):
            add += self._add_eqangle8(a, b, c, d, m, n, p, q, ab, cd, mn, pq, deps)

        if (
            ab.val != mn.val
            and cd.val != pq.val
            and (ab.val != cd.val or mn.val != pq.val)
        ):
            add += self._add_eqangle8(
                a,
                b,
                m,
                n,
                c,
                d,
                p,
                q,
                ab,
                mn,
                cd,
                pq,
                deps,
            )

        return add

    def _add_aconst(
        self, points: list[Point], deps: EmptyDependency
    ) -> list[Dependency]:
        """Add that an angle is equal to some constant."""
        a, b, c, d, num, den = points
        nd, dn = self.alegbraic_manipulator.get_or_create_const_ang(
            self.symbols_graph, num, den
        )

        if nd == self._halfpi:
            return self._add_perp([a, b, c, d], deps)

        ab, why1 = self.symbols_graph.get_line_thru_pair_why(a, b)
        cd, why2 = self.symbols_graph.get_line_thru_pair_why(c, d)

        (a, b), (c, d) = ab.points, cd.points
        if why1 + why2:
            args = points[:-2] + [nd]
            dep0 = deps.populate("aconst", args)
            deps = EmptyDependency(level=deps.level, rule_name=None)
            deps.why = [dep0] + why1 + why2

        self.symbols_graph.get_node_val(ab, deps=None)
        self.symbols_graph.get_node_val(cd, deps=None)

        if ab.val == cd.val:
            raise ValueError(f"{ab.name} - {cd.name} cannot be {nd.name}")

        args = [a, b, c, d, nd]
        i = 0
        for x, y, xy in [(a, b, ab), (c, d, cd)]:
            i += 1
            x_, y_ = xy._val._obj.points
            if {x, y} == {x_, y_}:
                continue
            if deps:
                deps = deps.extend(self, "aconst", list(args), "para", [x, y, x_, y_])
            args[2 * i - 2] = x_
            args[2 * i - 1] = y_

        ab_cd, cd_ab, why = self.symbols_graph.get_or_create_angle_from_lines(
            ab, cd, deps=None
        )
        if why:
            dep0 = deps.populate("aconst", [a, b, c, d, nd])
            deps = EmptyDependency(level=deps.level, rule_name=None)
            deps.why = [dep0] + why

        dab, dcd = ab_cd._d
        a, b = dab._obj.points
        c, d = dcd._obj.points

        ang = int(num) * 180 / int(den)
        add = []
        if not self.is_equal(ab_cd, nd):
            deps1 = deps.populate("aconst", [a, b, c, d, nd])
            deps1.algebra = dab, dcd, ang % 180
            self.make_equal(ab_cd, nd, deps=deps1)
            self.cache_dep("aconst", [a, b, c, d, nd], deps1)
            add += [deps1]

        if not self.is_equal(cd_ab, dn):
            deps2 = deps.populate("aconst", [c, d, a, b, dn])
            deps2.algebra = dcd, dab, 180 - ang % 180
            self.make_equal(cd_ab, dn, deps=deps2)
            self.cache_dep("aconst", [c, d, a, b, dn], deps2)
            add += [deps2]
        return add

    def _add_s_angle(
        self, points: list[Point], deps: EmptyDependency
    ) -> list[Dependency]:
        """Add that an angle abx is equal to constant y."""
        a, b, x, y = points

        n, d = simplify(y % 180, 180)
        nd, dn = self.alegbraic_manipulator.get_or_create_const_ang(
            self.symbols_graph, n, d
        )

        if nd == self._halfpi:
            return self._add_perp([a, b, b, x], deps)

        ab, why1 = self.symbols_graph.get_line_thru_pair_why(a, b)
        bx, why2 = self.symbols_graph.get_line_thru_pair_why(b, x)

        self.symbols_graph.get_node_val(ab, deps=None)
        self.symbols_graph.get_node_val(bx, deps=None)
        add = []

        if ab.val == bx.val:
            return add

        deps.why += why1 + why2

        for p, q, pq in [(a, b, ab), (b, x, bx)]:
            p_, q_ = pq.val._obj.points
            if {p, q} == {p_, q_}:
                continue
            dep = Dependency("para", [p, q, p_, q_], None, deps.level)
            deps.why += [dep.why_me_or_cache(self, None)]

        xba, abx, why = self.symbols_graph.get_or_create_angle_from_lines(
            bx, ab, deps=None
        )
        if why:
            dep0 = deps.populate("aconst", [b, x, a, b, nd])
            deps = EmptyDependency(level=deps.level, rule_name=None)
            deps.why = [dep0] + why

        dab, dbx = abx._d
        a, b = dab._obj.points
        c, x = dbx._obj.points

        if not self.is_equal(xba, nd):
            deps1 = deps.populate("aconst", [c, x, a, b, nd])
            deps1.algebra = dbx, dab, y % 180

            self.make_equal(xba, nd, deps=deps1)
            self.cache_dep("aconst", [c, x, a, b, nd], deps1)
            add += [deps1]

        if not self.is_equal(abx, dn):
            deps2 = deps.populate("aconst", [a, b, c, x, dn])
            deps2.algebra = dab, dbx, 180 - (y % 180)

            self.make_equal(abx, dn, deps=deps2)
            self.cache_dep("s_angle", [a, b, c, x, dn], deps2)
            add += [deps2]
        return add

    def check_aconst(self, points: list[Point], verbose: bool = False) -> bool:
        """Check if the angle is equal to a certain constant."""
        a, b, c, d, nd = points
        _ = verbose
        if isinstance(nd, str):
            name = nd
        else:
            name = nd.name
        num, den = name.split("pi/")
        ang, _ = self.alegbraic_manipulator.get_or_create_const_ang(
            self.symbols_graph, int(num), int(den)
        )

        ab = self.symbols_graph.get_line(a, b)
        cd = self.symbols_graph.get_line(c, d)
        if not ab or not cd:
            return False

        if not (ab.val and cd.val):
            return False

        for ang1, _, _ in all_angles(ab._val, cd._val):
            if self.is_equal(ang1, ang):
                return True
        return False

    def check_acompute(self, points: list[Point]) -> bool:
        """Check if an angle has a constant value."""
        a, b, c, d = points
        ab = self.symbols_graph.get_line(a, b)
        cd = self.symbols_graph.get_line(c, d)
        if not ab or not cd:
            return False

        if not (ab.val and cd.val):
            return False

        for ang0 in self.alegbraic_manipulator.aconst.values():
            for ang in ang0.val.neighbors(Angle):
                d1, d2 = ang.directions
                if ab.val == d1 and cd.val == d2:
                    return True
        return False

    def check_eqangle(self, points: list[Point]) -> bool:
        """Check if two angles are equal."""
        a, b, c, d, m, n, p, q = points

        if {a, b} == {c, d} and {m, n} == {p, q}:
            return True
        if {a, b} == {m, n} and {c, d} == {p, q}:
            return True

        if (a == b) or (c == d) or (m == n) or (p == q):
            return False
        ab = self.symbols_graph.get_line(a, b)
        cd = self.symbols_graph.get_line(c, d)
        mn = self.symbols_graph.get_line(m, n)
        pq = self.symbols_graph.get_line(p, q)

        if {a, b} == {c, d} and mn and pq and self.is_equal(mn, pq):
            return True
        if {a, b} == {m, n} and cd and pq and self.is_equal(cd, pq):
            return True
        if {p, q} == {m, n} and ab and cd and self.is_equal(ab, cd):
            return True
        if {p, q} == {c, d} and ab and mn and self.is_equal(ab, mn):
            return True

        if not ab or not cd or not mn or not pq:
            return False

        if self.is_equal(ab, cd) and self.is_equal(mn, pq):
            return True
        if self.is_equal(ab, mn) and self.is_equal(cd, pq):
            return True

        if not (ab.val and cd.val and mn.val and pq.val):
            return False

        if (ab.val, cd.val) == (mn.val, pq.val) or (ab.val, mn.val) == (
            cd.val,
            pq.val,
        ):
            return True

        for ang1, _, _ in all_angles(ab._val, cd._val):
            for ang2, _, _ in all_angles(mn._val, pq._val):
                if self.is_equal(ang1, ang2):
                    return True

        if self.check_perp([a, b, m, n]) and self.check_perp([c, d, p, q]):
            return True
        if self.check_perp([a, b, p, q]) and self.check_perp([c, d, m, n]):
            return True

        return False

    def _add_cong2(
        self, points: list[Point], deps: EmptyDependency
    ) -> list[Dependency]:
        m, n, a, b = points
        add = []
        add += self._add_cong([m, a, n, a], deps)
        add += self._add_cong([m, b, n, b], deps)
        return add

    def _add_eqratio3(
        self, points: list[Point], deps: EmptyDependency
    ) -> list[Dependency]:
        """Add three eqratios through a list of 6 points (due to parallel lines)."""
        a, b, c, d, m, n = points
        #   a -- b
        #  m  --  n
        # c   --   d
        add = []
        add += self._add_eqratio([m, a, m, c, n, b, n, d], deps)
        add += self._add_eqratio([a, m, a, c, b, n, b, d], deps)
        add += self._add_eqratio([c, m, c, a, d, n, d, b], deps)
        if m == n:
            add += self._add_eqratio([m, a, m, c, a, b, c, d], deps)
        return add

    def _add_eqratio4(
        self, points: list[Point], deps: EmptyDependency
    ) -> list[Dependency]:
        o, a, b, c, d = points
        #   o
        #  a b
        # c   d
        add = self._add_eqratio3([a, b, c, d, o, o], deps)
        add += self._add_eqratio([o, a, o, c, a, b, c, d], deps)
        return add

    def _add_eqratio8(
        self,
        a: Point,
        b: Point,
        c: Point,
        d: Point,
        m: Point,
        n: Point,
        p: Point,
        q: Point,
        ab: Segment,
        cd: Segment,
        mn: Segment,
        pq: Segment,
        deps: EmptyDependency,
    ) -> list[Dependency]:
        """Add a new eqratio from 8 points (core)."""
        if deps:
            deps = deps.copy()

        args = [a, b, c, d, m, n, p, q]
        i = 0
        for x, y, xy in [(a, b, ab), (c, d, cd), (m, n, mn), (p, q, pq)]:
            if {x, y} == set(xy.points):
                continue
            x_, y_ = list(xy.points)
            if deps:
                deps = deps.extend(self, "eqratio", list(args), "cong", [x, y, x_, y_])
            args[2 * i - 2] = x_
            args[2 * i - 1] = y_

        add = []
        ab_cd, cd_ab, why1 = self.symbols_graph.get_or_create_ratio_from_segments(
            ab, cd, deps=None
        )
        mn_pq, pq_mn, why2 = self.symbols_graph.get_or_create_ratio_from_segments(
            mn, pq, deps=None
        )

        why = why1 + why2
        if why:
            dep0 = deps.populate("eqratio", args)
            deps = EmptyDependency(level=deps.level, rule_name=None)
            deps.why = [dep0] + why

        lab, lcd = ab_cd._l
        lmn, lpq = mn_pq._l

        a, b = lab._obj.points
        c, d = lcd._obj.points
        m, n = lmn._obj.points
        p, q = lpq._obj.points

        is_eq1 = self.is_equal(ab_cd, mn_pq)
        deps1 = None
        if deps:
            deps1 = deps.populate("eqratio", [a, b, c, d, m, n, p, q])
            deps1.algebra = [ab._val, cd._val, mn._val, pq._val]
        if not is_eq1:
            add += [deps1]
        self.cache_dep("eqratio", [a, b, c, d, m, n, p, q], deps1)
        self.make_equal(ab_cd, mn_pq, deps=deps1)

        is_eq2 = self.is_equal(cd_ab, pq_mn)
        deps2 = None
        if deps:
            deps2 = deps.populate("eqratio", [c, d, a, b, p, q, m, n])
            deps2.algebra = [cd._val, ab._val, pq._val, mn._val]
        if not is_eq2:
            add += [deps2]
        self.cache_dep("eqratio", [c, d, a, b, p, q, m, n], deps2)
        self.make_equal(cd_ab, pq_mn, deps=deps2)
        return add

    def _add_eqratio(
        self, points: list[Point], deps: EmptyDependency
    ) -> list[Dependency]:
        """Add a new eqratio from 8 points."""
        if deps:
            deps = deps.copy()
        a, b, c, d, m, n, p, q = points
        ab = self.symbols_graph.get_or_create_segment(a, b, deps=None)
        cd = self.symbols_graph.get_or_create_segment(c, d, deps=None)
        mn = self.symbols_graph.get_or_create_segment(m, n, deps=None)
        pq = self.symbols_graph.get_or_create_segment(p, q, deps=None)

        add = self._maybe_make_equal_pairs(a, b, c, d, m, n, p, q, ab, cd, mn, pq, deps)

        if add is not None:
            return add

        self.symbols_graph.get_node_val(ab, deps=None)
        self.symbols_graph.get_node_val(cd, deps=None)
        self.symbols_graph.get_node_val(mn, deps=None)
        self.symbols_graph.get_node_val(pq, deps=None)

        add = []
        if (
            ab.val != cd.val
            and mn.val != pq.val
            and (ab.val != mn.val or cd.val != pq.val)
        ):
            add += self._add_eqratio8(a, b, c, d, m, n, p, q, ab, cd, mn, pq, deps)

        if (
            ab.val != mn.val
            and cd.val != pq.val
            and (ab.val != cd.val or mn.val != pq.val)
        ):
            add += self._add_eqratio8(
                a,
                b,
                m,
                n,
                c,
                d,
                p,
                q,
                ab,
                mn,
                cd,
                pq,
                deps,
            )
        return add

    def check_rconst(self, points: list[Point], verbose: bool = False) -> bool:
        """Check whether a ratio is equal to some given constant."""
        _ = verbose
        a, b, c, d, nd = points
        if isinstance(nd, str):
            name = nd
        else:
            name = nd.name
        num, den = name.split("/")
        rat, _ = self.alegbraic_manipulator.get_or_create_const_rat(
            self.symbols_graph, int(num), int(den)
        )

        ab = self.symbols_graph.get_segment(a, b)
        cd = self.symbols_graph.get_segment(c, d)

        if not ab or not cd:
            return False

        if not (ab.val and cd.val):
            return False

        for rat1, _, _ in all_ratios(ab._val, cd._val):
            if self.is_equal(rat1, rat):
                return True
        return False

    def check_rcompute(self, points: list[Point]) -> bool:
        """Check whether a ratio is equal to some constant."""
        a, b, c, d = points
        ab = self.symbols_graph.get_segment(a, b)
        cd = self.symbols_graph.get_segment(c, d)

        if not ab or not cd:
            return False

        if not (ab.val and cd.val):
            return False

        for rat0 in self.alegbraic_manipulator.rconst.values():
            for rat in rat0.val.neighbors(Ratio):
                l1, l2 = rat.lengths
                if ab.val == l1 and cd.val == l2:
                    return True
        return False

    def check_eqratio(self, points: list[Point]) -> bool:
        """Check if 8 points make an eqratio predicate."""
        a, b, c, d, m, n, p, q = points

        if {a, b} == {c, d} and {m, n} == {p, q}:
            return True
        if {a, b} == {m, n} and {c, d} == {p, q}:
            return True

        ab = self.symbols_graph.get_segment(a, b)
        cd = self.symbols_graph.get_segment(c, d)
        mn = self.symbols_graph.get_segment(m, n)
        pq = self.symbols_graph.get_segment(p, q)

        if {a, b} == {c, d} and mn and pq and self.is_equal(mn, pq):
            return True
        if {a, b} == {m, n} and cd and pq and self.is_equal(cd, pq):
            return True
        if {p, q} == {m, n} and ab and cd and self.is_equal(ab, cd):
            return True
        if {p, q} == {c, d} and ab and mn and self.is_equal(ab, mn):
            return True

        if not ab or not cd or not mn or not pq:
            return False

        if self.is_equal(ab, cd) and self.is_equal(mn, pq):
            return True
        if self.is_equal(ab, mn) and self.is_equal(cd, pq):
            return True

        if not (ab.val and cd.val and mn.val and pq.val):
            return False

        if (ab.val, cd.val) == (mn.val, pq.val) or (ab.val, mn.val) == (
            cd.val,
            pq.val,
        ):
            return True

        for rat1, _, _ in all_ratios(ab._val, cd._val):
            for rat2, _, _ in all_ratios(mn._val, pq._val):
                if self.is_equal(rat1, rat2):
                    return True
        return False

    def _add_simtri_check(
        self, points: list[Point], deps: EmptyDependency
    ) -> list[Dependency]:
        if nm.same_clock(*[p.num for p in points]):
            return self._add_simtri(points, deps)
        return self._add_simtri2(points, deps)

    def _add_contri_check(
        self, points: list[Point], deps: EmptyDependency
    ) -> list[Dependency]:
        if nm.same_clock(*[p.num for p in points]):
            return self._add_contri(points, deps)
        return self._add_contri2(points, deps)

    def _add_simtri(
        self, points: list[Point], deps: EmptyDependency
    ) -> list[Dependency]:
        """Add two similar triangles."""
        add = []
        hashs = [d.hashed() for d in deps.why]

        for args in comb.enum_triangle(points):
            if hashed("eqangle6", args) in hashs:
                continue
            add += self._add_eqangle(args, deps=deps)

        for args in comb.enum_triangle(points):
            if hashed("eqratio6", args) in hashs:
                continue
            add += self._add_eqratio(args, deps=deps)

        return add

    def check_simtri(self, points: list[Point]) -> bool:
        a, b, c, x, y, z = points
        return self.check_eqangle([a, b, a, c, x, y, x, z]) and self.check_eqangle(
            [b, a, b, c, y, x, y, z]
        )

    def _add_simtri2(
        self, points: list[Point], deps: EmptyDependency
    ) -> list[Dependency]:
        """Add two similar reflected triangles."""
        add = []
        hashs = [d.hashed() for d in deps.why]
        for args in comb.enum_triangle2(points):
            if hashed("eqangle6", args) in hashs:
                continue
            add += self._add_eqangle(args, deps=deps)

        for args in comb.enum_triangle(points):
            if hashed("eqratio6", args) in hashs:
                continue
            add += self._add_eqratio(args, deps=deps)

        return add

    def _add_contri(
        self, points: list[Point], deps: EmptyDependency
    ) -> list[Dependency]:
        """Add two congruent triangles."""
        add = []
        hashs = [d.hashed() for d in deps.why]
        for args in comb.enum_triangle(points):
            if hashed("eqangle6", args) in hashs:
                continue
            add += self._add_eqangle(args, deps=deps)

        for args in comb.enum_sides(points):
            if hashed("cong", args) in hashs:
                continue
            add += self._add_cong(args, deps=deps)
        return add

    def check_contri(self, points: list[Point]) -> bool:
        a, b, c, x, y, z = points
        return (
            self.check_cong([a, b, x, y])
            and self.check_cong([b, c, y, z])
            and self.check_cong([c, a, z, x])
        )

    def _add_contri2(
        self, points: list[Point], deps: EmptyDependency
    ) -> list[Dependency]:
        """Add two congruent reflected triangles."""
        add = []
        hashs = [d.hashed() for d in deps.why]
        for args in comb.enum_triangle2(points):
            if hashed("eqangle6", args) in hashs:
                continue
            add += self._add_eqangle(args, deps=deps)

        for args in comb.enum_sides(points):
            if hashed("cong", args) in hashs:
                continue
            add += self._add_cong(args, deps=deps)

        return add

    def in_cache(self, name: str, args: list[Point]) -> bool:
        return hashed(name, args) in self.cache

    def cache_dep(
        self,
        name: str,
        args: list[Point],
        premises: Union[Dependency, list[Dependency]],
    ) -> None:
        _hashed = hashed(name, args)
        if _hashed in self.cache:
            return
        self.cache[_hashed] = premises

    def all_same_line(
        self, a: Point, b: Point
    ) -> Generator[tuple[Point, Point], None, None]:
        ab = self.symbols_graph.get_line(a, b)
        if ab is None:
            return
        for p1, p2 in comb.comb2(ab.neighbors(Point)):
            if {p1, p2} != {a, b}:
                yield p1, p2

    def all_same_angle(
        self, a: Point, b: Point, c: Point, d: Point
    ) -> Generator[tuple[Point, Point, Point, Point], None, None]:
        for x, y in self.all_same_line(a, b):
            for m, n in self.all_same_line(c, d):
                yield x, y, m, n

    def additionally_draw(self, name: str, args: list[Point]) -> None:
        """Draw some extra line/circles for illustration purpose."""

        if name in ["circle"]:
            center, point = args[:2]
            circle = self.symbols_graph.new_node(
                Circle, f"({center.name},{point.name})"
            )
            circle.num = num_geo.Circle(center.num, p1=point.num)
            circle.points = center, point

        if name in ["on_circle", "tangent"]:
            center, point = args[-2:]
            circle = self.symbols_graph.new_node(
                Circle, f"({center.name},{point.name})"
            )
            circle.num = num_geo.Circle(center.num, p1=point.num)
            circle.points = center, point

        if name in ["incenter", "excenter", "incenter2", "excenter2"]:
            d, a, b, c = [x for x in args[-4:]]
            a, b, c = sorted([a, b, c], key=lambda x: x.name.lower())
            circle = self.symbols_graph.new_node(
                Circle, f"({d.name},h.{a.name}{b.name})"
            )
            p = d.num.foot(num_geo.Line(a.num, b.num))
            circle.num = num_geo.Circle(d.num, p1=p)
            circle.points = d, a, b, c

        if name in ["cc_tangent"]:
            o, a, w, b = args[-4:]
            c1 = self.symbols_graph.new_node(Circle, f"({o.name},{a.name})")
            c1.num = num_geo.Circle(o.num, p1=a.num)
            c1.points = o, a

            c2 = self.symbols_graph.new_node(Circle, f"({w.name},{b.name})")
            c2.num = num_geo.Circle(w.num, p1=b.num)
            c2.points = w, b

        if name in ["ninepoints"]:
            a, b, c = args[-3:]
            a, b, c = sorted([a, b, c], key=lambda x: x.name.lower())
            circle = self.symbols_graph.new_node(
                Circle, f"(,m.{a.name}{b.name}{c.name})"
            )
            p1 = (b.num + c.num) * 0.5
            p2 = (c.num + a.num) * 0.5
            p3 = (a.num + b.num) * 0.5
            circle.num = num_geo.Circle(p1=p1, p2=p2, p3=p3)
            circle.points = (None, None, a, b, c)

        if name in ["2l1c"]:
            a, b, c, o = args[:4]
            a, b, c = sorted([a, b, c], key=lambda x: x.name.lower())
            circle = self.symbols_graph.new_node(
                Circle, f"({o.name},{a.name}{b.name}{c.name})"
            )
            circle.num = num_geo.Circle(p1=a.num, p2=b.num, p3=c.num)
            circle.points = (a, b, c)

    def add_clause(
        self,
        clause: Clause,
        plevel: int,
        definitions: dict[str, Definition],
        verbose: int = False,
    ) -> tuple[list[Dependency], int]:
        """Add a new clause of construction, e.g. a new excenter."""
        existing_points = self.symbols_graph.all_points()
        new_points = [Point(name) for name in clause.points]

        new_points_dep_points = set()
        new_points_dep = []

        # Step 1: check for all deps.
        for c in clause.constructions:
            cdef = definitions[c.name]

            if len(cdef.construction.args) != len(c.args):
                if len(cdef.construction.args) - len(c.args) == len(clause.points):
                    c.args = clause.points + c.args
                else:
                    correct_form = " ".join(cdef.points + ["=", c.name] + cdef.args)
                    raise ValueError("Argument mismatch. " + correct_form)

            mapping = dict(zip(cdef.construction.args, c.args))
            c_name = "midp" if c.name == "midpoint" else c.name
            deps = EmptyDependency(level=0, rule_name=CONSTRUCTION_RULE)
            deps.construction = Dependency(c_name, c.args, rule_name=None, level=0)

            for d in cdef.deps.constructions:
                args = self.symbols_graph.names2points([mapping[a] for a in d.args])
                new_points_dep_points.update(args)
                if not self.check(d.name, args):
                    raise DepCheckFailError(
                        d.name + " " + " ".join([x.name for x in args])
                    )
                construction = Dependency(
                    d.name, args, rule_name=CONSTRUCTION_RULE, level=0
                )
                self.dependency_graph.add_dependency(construction)
                deps.why += [construction]

            new_points_dep += [deps]

        # Step 2: draw.
        def range_fn() -> (
            list[
                Union[
                    num_geo.Point,
                    num_geo.Line,
                    num_geo.Circle,
                    num_geo.HalfLine,
                    num_geo.HoleCircle,
                ]
            ]
        ):
            to_be_intersected = []
            for c in clause.constructions:
                cdef = definitions[c.name]
                mapping = dict(zip(cdef.construction.args, c.args))
                for n in cdef.numerics:
                    args = [mapping[a] for a in n.args]
                    args = list(
                        map(
                            lambda x: self.symbols_graph.get_point(x, lambda: int(x)),
                            args,
                        )
                    )
                    to_be_intersected += sketch(n.name, args)

            return to_be_intersected

        is_total_free = (
            len(clause.constructions) == 1 and clause.constructions[0].name in FREE
        )
        is_semi_free = (
            len(clause.constructions) == 1 and clause.constructions[0].name in INTERSECT
        )

        existing_points = [p.num for p in existing_points]

        def draw_fn() -> list[num_geo.Point]:
            to_be_intersected = range_fn()
            return num_geo.reduce(to_be_intersected, existing_points)

        rely_on = set()
        for c in clause.constructions:
            cdef = definitions[c.name]
            mapping = dict(zip(cdef.construction.args, c.args))
            for n in cdef.numerics:
                args = [mapping[a] for a in n.args]
                args = list(
                    map(lambda x: self.symbols_graph.get_point(x, lambda: int(x)), args)
                )
                rely_on.update([a for a in args if isinstance(a, Point)])

        for p in rely_on:
            p.change.update(new_points)

        nums = draw_fn()
        for p, num, num0 in zip(new_points, nums, clause.nums):
            p.co_change = new_points
            if isinstance(num0, num_geo.Point):
                num = num0
            elif isinstance(num0, (tuple, list)):
                x, y = num0
                num = num_geo.Point(x, y)

            p.num = num

        # check two things.
        if check_too_close_numerical(nums, existing_points):
            raise PointTooCloseError()
        if check_too_far_numerical(nums, existing_points):
            raise PointTooFarError()

        # Commit: now that all conditions are passed.
        # add these points to current graph.
        for p in new_points:
            self.symbols_graph.add_node(p)

        for p in new_points:
            p.why = sum([d.why for d in new_points_dep], [])  # to generate txt logs.
            p.group = new_points
            p.dep_points = new_points_dep_points
            p.dep_points.update(new_points)
            p.plevel = plevel

        # movement dependency:
        rely_dict_0 = defaultdict(lambda: [])

        for c in clause.constructions:
            cdef = definitions[c.name]
            mapping = dict(zip(cdef.construction.args, c.args))
            for p, ps in cdef.rely.items():
                p = mapping[p]
                ps = [mapping[x] for x in ps]
                rely_dict_0[p].append(ps)

        rely_dict = {}
        for p, pss in rely_dict_0.items():
            ps = sum(pss, [])
            if len(pss) > 1:
                ps = [x for x in ps if x != p]

            p = self.symbols_graph._name2point[p]
            ps = self.symbols_graph.names2nodes(ps)
            rely_dict[p] = ps

        for p in new_points:
            p.rely_on = set(rely_dict.get(p, []))
            for x in p.rely_on:
                if not hasattr(x, "base_rely_on"):
                    x.base_rely_on = set()
            p.base_rely_on = set.union(*[x.base_rely_on for x in p.rely_on] + [set()])
            if is_total_free or is_semi_free:
                p.rely_on.add(p)
                p.base_rely_on.add(p)

        plevel_done = set()
        added = []
        basics = []
        # Step 3: build the basics.
        for c, deps in zip(clause.constructions, new_points_dep):
            cdef = definitions[c.name]
            mapping = dict(zip(cdef.construction.args, c.args))

            # not necessary for proofing, but for visualization.
            c_args = list(
                map(lambda x: self.symbols_graph.get_point(x, lambda: int(x)), c.args)
            )
            self.additionally_draw(c.name, c_args)

            for points, bs in cdef.basics:
                if points:
                    points = self.symbols_graph.names2nodes(
                        [mapping[p] for p in points]
                    )
                    points = [p for p in points if p not in plevel_done]
                    for p in points:
                        p.plevel = plevel
                    plevel_done.update(points)
                    plevel += 1
                else:
                    continue

                for b in bs:
                    if b.name != "rconst":
                        args = [mapping[a] for a in b.args]
                    else:
                        num, den = map(int, b.args[-2:])
                        rat, _ = self.alegbraic_manipulator.get_or_create_const_rat(
                            self.symbols_graph, num, den
                        )
                        args = [mapping[a] for a in b.args[:-2]] + [rat.name]

                    args = list(
                        map(
                            lambda x: self.symbols_graph.get_point(x, lambda: int(x)),
                            args,
                        )
                    )

                    adds = self.add_piece(name=b.name, args=args, deps=deps)
                    self.dependency_graph.add_construction_edges(adds, args)
                    basics.append((b.name, args, deps))
                    if adds:
                        added += adds
                        for add in adds:
                            self.cache_dep(add.name, add.args, add)

        assert len(plevel_done) == len(new_points)
        for p in new_points:
            p.basics = basics

        return added, plevel

    def all_eqangle_same_lines(self) -> Generator[tuple[Point, ...], None, None]:
        for l1, l2 in comb.perm2(self.symbols_graph.type2nodes[Line]):
            for a, b, c, d, e, f, g, h in comb.all_8points(l1, l2, l1, l2):
                if (a, b, c, d) != (e, f, g, h):
                    yield a, b, c, d, e, f, g, h

    def all_eqangles_distinct_linepairss(
        self,
    ) -> Generator[tuple[Line, ...], None, None]:
        """No eqangles betcause para-para, or para-corresponding, or same."""

        for measure in self.symbols_graph.type2nodes[Measure]:
            angs = measure.neighbors(Angle)
            line_pairss = []
            for ang in angs:
                d1, d2 = ang.directions
                if d1 is None or d2 is None:
                    continue
                l1s = d1.neighbors(Line)
                l2s = d2.neighbors(Line)
                # Any pair in this is para-para.
                para_para = list(comb.cross(l1s, l2s))
                line_pairss.append(para_para)

            for pairs1, pairs2 in comb.comb2(line_pairss):
                for pair1, pair2 in comb.cross(pairs1, pairs2):
                    (l1, l2), (l3, l4) = pair1, pair2
                    yield l1, l2, l3, l4

    def all_eqangles_8points(self) -> Generator[tuple[Point, ...], None, None]:
        """List all sets of 8 points that make two equal angles."""
        # Case 1: (l1-l2) = (l3-l4), including because l1//l3, l2//l4 (para-para)
        angss = []
        for measure in self.symbols_graph.type2nodes[Measure]:
            angs = measure.neighbors(Angle)
            angss.append(angs)

        # include the angs that do not have any measure.
        angss.extend(
            [[ang] for ang in self.symbols_graph.type2nodes[Angle] if ang.val is None]
        )

        line_pairss = []
        for angs in angss:
            line_pairs = set()
            for ang in angs:
                d1, d2 = ang.directions
                if d1 is None or d2 is None:
                    continue
                l1s = d1.neighbors(Line)
                l2s = d2.neighbors(Line)
                line_pairs.update(set(comb.cross(l1s, l2s)))
            line_pairss.append(line_pairs)

        # include (d1, d2) in which d1 does not have any angles.
        noang_ds = [
            d
            for d in self.symbols_graph.type2nodes[Direction]
            if not d.neighbors(Angle)
        ]

        for d1 in noang_ds:
            for d2 in self.symbols_graph.type2nodes[Direction]:
                if d1 == d2:
                    continue
                l1s = d1.neighbors(Line)
                l2s = d2.neighbors(Line)
                if len(l1s) < 2 and len(l2s) < 2:
                    continue
                line_pairss.append(set(comb.cross(l1s, l2s)))
                line_pairss.append(set(comb.cross(l2s, l1s)))

        # Case 2: d1 // d2 => (d1-d3) = (d2-d3)
        # include lines that does not have any direction.
        nodir_ls = [
            line for line in self.symbols_graph.type2nodes[Line] if line.val is None
        ]

        for line in nodir_ls:
            for d in self.symbols_graph.type2nodes[Direction]:
                l1s = d.neighbors(Line)
                if len(l1s) < 2:
                    continue
                l2s = [line]
                line_pairss.append(set(comb.cross(l1s, l2s)))
                line_pairss.append(set(comb.cross(l2s, l1s)))

        record = set()
        for line_pairs in line_pairss:
            for pair1, pair2 in comb.perm2(list(line_pairs)):
                (l1, l2), (l3, l4) = pair1, pair2
                if l1 == l2 or l3 == l4:
                    continue
                if (l1, l2) == (l3, l4):
                    continue
                if (l1, l2, l3, l4) in record:
                    continue
                record.add((l1, l2, l3, l4))
                for a, b, c, d, e, f, g, h in comb.all_8points(l1, l2, l3, l4):
                    yield (a, b, c, d, e, f, g, h)

        for a, b, c, d, e, f, g, h in self.all_eqangle_same_lines():
            yield a, b, c, d, e, f, g, h

    def all_eqangles_6points(self) -> Generator[tuple[Point, ...], None, None]:
        """List all sets of 6 points that make two equal angles."""
        record = set()
        for a, b, c, d, e, f, g, h in self.all_eqangles_8points():
            if (
                a not in (c, d)
                and b not in (c, d)
                or e not in (g, h)
                and f not in (g, h)
            ):
                continue

            if b in (c, d):
                a, b = b, a  # now a in c, d
            if f in (g, h):
                e, f = f, e  # now e in g, h
            if a == d:
                c, d = d, c  # now a == c
            if e == h:
                g, h = h, g  # now e == g
            if (a, b, c, d, e, f, g, h) in record:
                continue
            record.add((a, b, c, d, e, f, g, h))
            yield a, b, c, d, e, f, g, h  # where a==c, e==g

    def all_paras(self) -> Generator[tuple[Point, ...], None, None]:
        for d in self.symbols_graph.type2nodes[Direction]:
            for l1, l2 in comb.perm2(d.neighbors(Line)):
                for a, b, c, d in comb.all_4points(l1, l2):
                    yield a, b, c, d

    def all_perps(self) -> Generator[tuple[Point, ...], None, None]:
        for ang in self.vhalfpi.neighbors(Angle):
            d1, d2 = ang.directions
            if d1 is None or d2 is None:
                continue
            if d1 == d2:
                continue
            for l1, l2 in comb.cross(d1.neighbors(Line), d2.neighbors(Line)):
                for a, b, c, d in comb.all_4points(l1, l2):
                    yield a, b, c, d

    def all_congs(self) -> Generator[tuple[Point, ...], None, None]:
        for lenght in self.symbols_graph.type2nodes[Length]:
            for s1, s2 in comb.perm2(lenght.neighbors(Segment)):
                (a, b), (c, d) = s1.points, s2.points
                for x, y in [(a, b), (b, a)]:
                    for m, n in [(c, d), (d, c)]:
                        yield x, y, m, n

    def all_eqratios_8points(self) -> Generator[tuple[Point, ...], None, None]:
        """List all sets of 8 points that make two equal ratios."""
        ratss = []
        for value in self.symbols_graph.type2nodes[Value]:
            rats = value.neighbors(Ratio)
            ratss.append(rats)

        # include the rats that do not have any val.
        ratss.extend(
            [[rat] for rat in self.symbols_graph.type2nodes[Ratio] if rat.val is None]
        )

        seg_pairss = []
        for rats in ratss:
            seg_pairs = set()
            for rat in rats:
                l1, l2 = rat.lengths
                if l1 is None or l2 is None:
                    continue
                s1s = l1.neighbors(Segment)
                s2s = l2.neighbors(Segment)
                seg_pairs.update(comb.cross(s1s, s2s))
            seg_pairss.append(seg_pairs)

        # include (l1, l2) in which l1 does not have any ratio.
        norat_ls = [
            lenght
            for lenght in self.symbols_graph.type2nodes[Length]
            if not lenght.neighbors(Ratio)
        ]

        for l1 in norat_ls:
            for l2 in self.symbols_graph.type2nodes[Length]:
                if l1 == l2:
                    continue
                s1s = l1.neighbors(Segment)
                s2s = l2.neighbors(Segment)
                if len(s1s) < 2 and len(s2s) < 2:
                    continue
                seg_pairss.append(set(comb.cross(s1s, s2s)))
                seg_pairss.append(set(comb.cross(s2s, s1s)))

        # include Seg that does not have any Length.
        nolen_ss = [s for s in self.symbols_graph.type2nodes[Segment] if s.val is None]

        for seg in nolen_ss:
            for lenght in self.symbols_graph.type2nodes[Length]:
                s1s = lenght.neighbors(Segment)
                if len(s1s) == 1:
                    continue
                s2s = [seg]
                seg_pairss.append(set(comb.cross(s1s, s2s)))
                seg_pairss.append(set(comb.cross(s2s, s1s)))

        record = set()
        for seg_pairs in seg_pairss:
            for pair1, pair2 in comb.perm2(list(seg_pairs)):
                (s1, s2), (s3, s4) = pair1, pair2
                if s1 == s2 or s3 == s4:
                    continue
                if (s1, s2) == (s3, s4):
                    continue
                if (s1, s2, s3, s4) in record:
                    continue
                record.add((s1, s2, s3, s4))
                a, b = s1.points
                c, d = s2.points
                e, f = s3.points
                g, h = s4.points

                for x, y in [(a, b), (b, a)]:
                    for z, t in [(c, d), (d, c)]:
                        for m, n in [(e, f), (f, e)]:
                            for p, q in [(g, h), (h, g)]:
                                yield (x, y, z, t, m, n, p, q)

        segss = []
        # finally the list of ratios that is equal to 1.0
        for length in self.symbols_graph.type2nodes[Length]:
            segs = length.neighbors(Segment)
            segss.append(segs)

        segs_pair = list(comb.perm2(list(segss)))
        segs_pair += list(zip(segss, segss))
        for segs1, segs2 in segs_pair:
            for s1, s2 in comb.perm2(list(segs1)):
                for s3, s4 in comb.perm2(list(segs2)):
                    if (s1, s2) == (s3, s4) or (s1, s3) == (s2, s4):
                        continue
                    if (s1, s2, s3, s4) in record:
                        continue
                    record.add((s1, s2, s3, s4))
                    a, b = s1.points
                    c, d = s2.points
                    e, f = s3.points
                    g, h = s4.points

                    for x, y in [(a, b), (b, a)]:
                        for z, t in [(c, d), (d, c)]:
                            for m, n in [(e, f), (f, e)]:
                                for p, q in [(g, h), (h, g)]:
                                    yield (x, y, z, t, m, n, p, q)

    def all_eqratios_6points(self) -> Generator[tuple[Point, ...], None, None]:
        """List all sets of 6 points that make two equal angles."""
        record = set()
        for a, b, c, d, e, f, g, h in self.all_eqratios_8points():
            if (
                a not in (c, d)
                and b not in (c, d)
                or e not in (g, h)
                and f not in (g, h)
            ):
                continue
            if b in (c, d):
                a, b = b, a
            if f in (g, h):
                e, f = f, e
            if a == d:
                c, d = d, c
            if e == h:
                g, h = h, g
            if (a, b, c, d, e, f, g, h) in record:
                continue
            record.add((a, b, c, d, e, f, g, h))
            yield a, b, c, d, e, f, g, h  # now a==c, e==g

    def all_cyclics(self) -> Generator[tuple[Point, ...], None, None]:
        for c in self.symbols_graph.type2nodes[Circle]:
            for x, y, z, t in comb.perm4(c.neighbors(Point)):
                yield x, y, z, t

    def all_colls(self) -> Generator[tuple[Point, ...], None, None]:
        for line in self.symbols_graph.type2nodes[Line]:
            for x, y, z in comb.perm3(line.neighbors(Point)):
                yield x, y, z

    def all_midps(self) -> Generator[tuple[Point, ...], None, None]:
        for line in self.symbols_graph.type2nodes[Line]:
            for a, b, c in comb.perm3(line.neighbors(Point)):
                if self.check_cong([a, b, a, c]):
                    yield a, b, c

    def all_circles(self) -> Generator[tuple[Point, ...], None, None]:
        for lenght in self.symbols_graph.type2nodes[Length]:
            p2p = defaultdict(list)
            for s in lenght.neighbors(Segment):
                a, b = s.points
                p2p[a].append(b)
                p2p[b].append(a)
            for p, ps in p2p.items():
                if len(ps) >= 3:
                    for a, b, c in comb.perm3(ps):
                        yield p, a, b, c

    def two_points_on_direction(self, d: Direction) -> tuple[Point, Point]:
        line_neighbor = d.neighbors(Line)[0]
        p1, p2 = line_neighbor.neighbors(Point)[:2]
        return p1, p2

    def two_points_of_length(self, lenght: Length) -> tuple[Point, Point]:
        s = lenght.neighbors(Segment)[0]
        p1, p2 = s.points
        return p1, p2
