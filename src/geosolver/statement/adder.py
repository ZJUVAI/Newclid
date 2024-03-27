from typing import Optional, Tuple


import geosolver.combinatorics as comb
import geosolver.numerical.check as nm
from geosolver.algebraic.algebraic_manipulator import AlgebraicManipulator
from geosolver.dependencies.caching import DependencyCache, hashed
from geosolver.dependencies.dependency import Dependency
from geosolver.dependencies.empty_dependency import EmptyDependency
from geosolver.geometry import Angle, Line, Node, Point, Segment, is_equal, is_equiv
from geosolver.ratios import simplify
from geosolver.statement.checker import StatementChecker
from geosolver.symbols_graph import SymbolsGraph

ToCache = Tuple[str, list[Point], Dependency]


class StatementAdder:
    def __init__(
        self,
        symbols_graph: SymbolsGraph,
        alegbraic_manipulator: AlgebraicManipulator,
        statements_checker: StatementChecker,
        dependency_cache: DependencyCache,
    ) -> None:
        self.symbols_graph = symbols_graph
        self.alegbraic_manipulator = alegbraic_manipulator

        self.statements_checker = statements_checker
        self.dependency_cache = dependency_cache

        self.NAME_TO_ADDER = {
            "coll": self._add_coll,
            "collx": self._add_coll,
            "para": self._add_para,
            "perp": self._add_perp,
            "midp": self._add_midp,
            "cong": self._add_cong,
            "circle": self._add_circle,
            "cyclic": self._add_cyclic,
            "eqangle": self._add_eqangle,
            "eqangle6": self._add_eqangle,
            "s_angle": self._add_s_angle,
            "cong2": self._add_cong2,
            "eqratio": self._add_eqratio,
            "eqratio6": self._add_eqratio,
            "eqratio3": self._add_eqratio3,
            "eqratio4": self._add_eqratio4,
            "simtri": self._add_simtri,
            "simtri2": self._add_simtri_reflect,
            "simtri*": self._add_simtri_check,
            "contri": self._add_contri,
            "contri2": self._add_contri_reflect,
            "contri*": self._add_contri_check,
        }

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
            merges = [self.alegbraic_manipulator.vhalfpi, vx, vy]

        self.symbols_graph.merge(merges, deps)

    def add_piece(
        self, name: str, args: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add a new predicate."""
        piece_adder = self.NAME_TO_ADDER.get(name)
        if piece_adder is not None:
            return piece_adder(args, deps)

        if name == "aconst":
            a, b, c, d, ang = args

            if isinstance(ang, str):
                name = ang
            else:
                name = ang.name

            num, den = name.split("pi/")
            num, den = int(num), int(den)
            return self._add_aconst([a, b, c, d, num, den], deps)

        elif name == "rconst":
            a, b, c, d, rat = args

            if isinstance(rat, str):
                name = rat
            else:
                name = rat.name

            num, den = name.split("/")
            num, den = int(num), int(den)
            return self._add_eqrat_const([a, b, c, d, num, den], deps)

        elif name == "s_angle":
            b, x, a, b, ang = args

            if isinstance(ang, str):
                name = ang
            else:
                name = ang.name

            n, d = name.split("pi/")
            ang = int(n) * 180 / int(d)
            return self._add_s_angle([a, b, x, ang], deps)

        deps_to_cache = []
        # Cached or compute piece
        if name in ["acompute", "rcompute"]:
            dep = deps.populate(name, args)
            deps_to_cache.append((name, args, dep))
            new_deps = [dep]
        elif name in ["fixl", "fixc", "fixb", "fixt", "fixp"]:
            dep = deps.populate(name, args)
            deps_to_cache.append((name, args, dep))
            new_deps = [dep]
        elif name in ["ind"]:
            new_deps = []
        else:
            raise ValueError(f"Not recognize {name}")

        return new_deps, deps_to_cache

    def add_algebra(
        self, name: str, args: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        new_deps, to_cache = [], []
        if name == "para":
            a, b, dep = args
            if is_equiv(a, b):
                return []
            else:
                (x, y), (m, n) = a._obj.points, b._obj.points
                new_deps, to_cache = self._add_para([x, y, m, n], dep)

        elif name == "aconst":
            a, b, n, d, dep = args
            ab, ba, why = self.symbols_graph.get_or_create_angle_from_directions(
                a, b, deps=None
            )
            nd, dn = self.alegbraic_manipulator.get_or_create_const_ang(n, d)

            (x, y), (m, n) = a._obj.points, b._obj.points

            if why:
                dep0 = dep.populate("aconst", [x, y, m, n, nd])
                dep = EmptyDependency(level=dep.level, rule_name=None)
                dep.why = [dep0] + why

            a, b = ab._d
            (x, y), (m, n) = a._obj.points, b._obj.points

            added = []
            to_cache = []
            if not is_equal(ab, nd):
                if nd == self.alegbraic_manipulator.halfpi:
                    _add, _to_cache = self._add_perp([x, y, m, n], dep)
                    added += _add
                    to_cache += _to_cache
                name = "aconst"
                args = [x, y, m, n, nd]
                dep1 = dep.populate(name, args)
                self.dependency_cache.add_dependency(name, args, dep1)
                self.make_equal(nd, ab, deps=dep1)
                added += [dep1]

            if not is_equal(ba, dn):
                if dn == self.alegbraic_manipulator.halfpi:
                    _add, _to_cache = self._add_perp([m, n, x, y], dep)
                    added += _add
                    to_cache += _to_cache
                name = "aconst"
                args = [m, n, x, y, dn]
                dep2 = dep.populate(name, args)
                self.dependency_cache.add_dependency(name, args, dep2)
                self.make_equal(dn, ba, deps=dep2)
                added += [dep2]
            new_deps = added

        elif name == "rconst":
            a, b, c, d, num, den, dep = args
            new_deps, to_cache = self._add_eqrat_const([a, b, c, d, num, den], dep)

        elif name == "eqangle":
            d1, d2, d3, d4, dep = args
            a, b = d1._obj.points
            c, d = d2._obj.points
            e, f = d3._obj.points
            g, h = d4._obj.points

            new_deps, to_cache = self._add_eqangle([a, b, c, d, e, f, g, h], dep)

        elif name == "eqratio":
            d1, d2, d3, d4, dep = args
            a, b = d1._obj.points
            c, d = d2._obj.points
            e, f = d3._obj.points
            g, h = d4._obj.points

            new_deps, to_cache = self._add_eqratio([a, b, c, d, e, f, g, h], dep)

        elif name in ["cong", "cong2"]:
            a, b, c, d, dep = args
            if not (a != b and c != d and (a != c or b != d)):
                new_deps = []
            else:
                new_deps, to_cache = self._add_cong([a, b, c, d], dep)

        return new_deps, to_cache

    def _add_coll(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add a predicate that `points` are collinear."""
        points = list(set(points))
        og_points = list(points)

        all_lines: list[Line] = []
        for p1, p2 in comb.comb2(points):
            all_lines.append(self.symbols_graph.get_line_thru_pair(p1, p2))
        points = sum([line.neighbors(Point) for line in all_lines], [])
        points = list(set(points))

        existed: set[Line] = set()
        new: set[Line] = set()
        for p1, p2 in comb.comb2(points):
            if p1.name > p2.name:
                p1, p2 = p2, p1
            if (p1, p2) in self.symbols_graph._pair2line:
                line = self.symbols_graph._pair2line[(p1, p2)]
                existed.add(line)
            else:
                line = self.symbols_graph.get_new_line_thru_pair(p1, p2)
                new.add(line)

        existed: list[Line] = list(sorted(existed, key=lambda node: node.name))
        new: list[Line] = list(sorted(new, key=lambda node: node.name))
        if not existed:
            line0, *lines = new
        else:
            line0, lines = existed[0], existed[1:] + new

        add = []
        to_cache = []
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
                    whys.append(self._coll_dep(og_points, x))

            abcd_deps = deps
            if whys + why0:
                dep0 = deps.populate("coll", og_points)
                abcd_deps = EmptyDependency(level=deps.level, rule_name=None)
                abcd_deps.why = [dep0] + whys

            is_coll = self.statements_checker.check_coll(args)
            dep = abcd_deps.populate("coll", args)
            to_cache.append(("coll", args, dep))
            self.symbols_graph.merge_into(line0, [line], dep)

            if not is_coll:
                add += [dep]

        return add, to_cache

    def _coll_dep(self, points: list[Point], p: Point) -> list[Dependency]:
        """Return the dep(.why) explaining why p is coll with points."""
        for p1, p2 in comb.comb2(points):
            if self.statements_checker.check_coll([p1, p2, p]):
                dep = Dependency("coll", [p1, p2, p], None, None)
                return dep.why_me_or_cache(
                    self.symbols_graph,
                    self.statements_checker,
                    self.dependency_cache,
                    None,
                )

    def _add_para(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add a new predicate that 4 points (2 lines) are parallel."""
        a, b, c, d = points
        ab, why1 = self.symbols_graph.get_line_thru_pair_why(a, b)
        cd, why2 = self.symbols_graph.get_line_thru_pair_why(c, d)

        (a, b), (c, d) = ab.points, cd.points

        dep0 = deps.populate("para", points)
        deps = EmptyDependency(level=deps.level, rule_name=None)

        deps = deps.populate("para", [a, b, c, d])
        deps.why = [dep0] + why1 + why2

        self.make_equal(ab, cd, deps)
        deps.algebra = ab._val, cd._val

        to_cache = [("para", [a, b, c, d], deps)]
        if not is_equal(ab, cd):
            return [deps], to_cache
        return [], to_cache

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
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add a new parallel or collinear predicate."""
        extends = [("perp", [x, y, m, n])]
        if {a, b} == {x, y}:
            pass
        elif self.statements_checker.check_para([a, b, x, y]):
            extends.append(("para", [a, b, x, y]))
        elif self.statements_checker.check_coll([a, b, x, y]):
            extends.append(("coll", set(list([a, b, x, y]))))
        else:
            return None

        if m in [c, d] or n in [c, d] or c in [m, n] or d in [m, n]:
            pass
        elif self.statements_checker.check_coll([c, d, m]):
            extends.append(("coll", [c, d, m]))
        elif self.statements_checker.check_coll([c, d, n]):
            extends.append(("coll", [c, d, n]))
        elif self.statements_checker.check_coll([c, m, n]):
            extends.append(("coll", [c, m, n]))
        elif self.statements_checker.check_coll([d, m, n]):
            extends.append(("coll", [d, m, n]))
        else:
            deps = deps.extend_many(self, "perp", [a, b, c, d], extends)
            return self._add_para([c, d, m, n], deps)

        deps = deps.extend_many(self, "perp", [a, b, c, d], extends)
        return self._add_coll(list(set([c, d, m, n])), deps)

    def _maybe_make_para_from_perp(
        self, points: list[Point], deps: EmptyDependency
    ) -> Optional[Tuple[list[Dependency], list[ToCache]]]:
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
                para_or_coll = self._add_para_or_coll(*args)
                if para_or_coll is not None:
                    return para_or_coll

        return None

    def _add_perp(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add a new perpendicular predicate from 4 points (2 lines)."""
        para_from_perp = self._maybe_make_para_from_perp(points, deps)
        if para_from_perp is not None:
            return para_from_perp

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

        dep = deps.populate("perp", [a, b, c, d])
        dep.algebra = [dab, dcd]
        self.make_equal(a12, a21, deps=dep)

        to_cache = [
            ("perp", [a, b, c, d], dep),
            ("eqangle", [a, b, c, d, c, d, a, b], dep),
        ]

        if not is_equal(a12, a21):
            return [dep], to_cache
        return [], to_cache

    def _add_cong(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add that two segments (4 points) are congruent."""
        a, b, c, d = points
        ab = self.symbols_graph.get_or_create_segment(a, b, deps=None)
        cd = self.symbols_graph.get_or_create_segment(c, d, deps=None)

        dep = deps.populate("cong", [a, b, c, d])
        self.make_equal(ab, cd, deps=dep)
        dep.algebra = ab._val, cd._val

        to_cache = [("cong", [a, b, c, d], dep)]
        deps = []

        if not is_equal(ab, cd):
            deps += [dep]

        if a not in [c, d] and b not in [c, d]:
            return deps, to_cache

        if b in [c, d]:
            a, b = b, a
        if a == d:
            c, d = d, c

        cyclic_deps, cyclic_cache = self._maybe_add_cyclic_from_cong(a, b, d, dep)
        deps += cyclic_deps
        to_cache += cyclic_cache
        return deps, to_cache

    def _add_cong2(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        m, n, a, b = points
        add, to_cache = self._add_cong([m, a, n, a], deps)
        _add, _to_cache = self._add_cong([m, b, n, b], deps)
        return add + _add, to_cache + _to_cache

    def _add_midp(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        m, a, b = points
        add_coll, to_cache_coll = self._add_coll(points, deps=deps)
        add_cong, to_cache_cong = self._add_cong([m, a, m, b], deps)
        return add_coll + add_cong, to_cache_coll + to_cache_cong

    def _add_circle(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        o, a, b, c = points
        add_ab, to_cache_ab = self._add_cong([o, a, o, b], deps=deps)
        add_ac, to_cache_ac = self._add_cong([o, a, o, c], deps=deps)
        return add_ab + add_ac, to_cache_ab + to_cache_ac

    def _add_cyclic(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
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
        to_cache = []
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

            is_cyclic = self.statements_checker.check_cyclic(args)

            dep = abcdef_deps.populate("cyclic", args)
            to_cache.append(("cyclic", args, dep))
            self.symbols_graph.merge_into(circle0, [circle], dep)
            if not is_cyclic:
                add += [dep]

        return add, to_cache

    def cyclic_dep(self, points: list[Point], p: Point) -> list[Dependency]:
        for p1, p2, p3 in comb.comb3(points):
            if self.statements_checker.check_cyclic([p1, p2, p3, p]):
                dep = Dependency("cyclic", [p1, p2, p3, p], None, None)
                return dep.why_me_or_cache(
                    self.symbols_graph,
                    self.statements_checker,
                    self.dependency_cache,
                    None,
                )

    def _maybe_add_cyclic_from_cong(
        self, a: Point, b: Point, c: Point, cong_ab_ac: Dependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
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
            return [], []

        x, y = points[:2]

        if self.statements_checker.check_cyclic([b, c, x, y]):
            return [], []

        ax = self.symbols_graph.get_or_create_segment(a, x, deps=None)
        ay = self.symbols_graph.get_or_create_segment(a, y, deps=None)
        why = ab._val.why_equal([ax._val, ay._val], level=None)
        why += [cong_ab_ac]

        deps = EmptyDependency(cong_ab_ac.level, "")
        deps.why = why

        return self._add_cyclic([b, c, x, y], deps)

    def _add_eqangle(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
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

        maybe_pairs = self._maybe_make_equal_pairs(
            a, b, c, d, m, n, p, q, ab, cd, mn, pq, deps
        )

        if maybe_pairs is not None:
            return maybe_pairs

        self.symbols_graph.get_node_val(ab, deps=None)
        self.symbols_graph.get_node_val(cd, deps=None)
        self.symbols_graph.get_node_val(mn, deps=None)
        self.symbols_graph.get_node_val(pq, deps=None)

        add, to_cache = [], []

        if (
            ab.val != cd.val
            and mn.val != pq.val
            and (ab.val != mn.val or cd.val != pq.val)
        ):
            _add, _to_cache = self._add_eqangle8(
                a, b, c, d, m, n, p, q, ab, cd, mn, pq, deps
            )
            add += _add
            to_cache += _to_cache

        if (
            ab.val != mn.val
            and cd.val != pq.val
            and (ab.val != cd.val or mn.val != pq.val)
        ):
            _add, _to_cache = self._add_eqangle8(
                a, b, m, n, c, d, p, q, ab, mn, cd, pq, deps
            )
            add += _add
            to_cache += _to_cache

        return add, to_cache

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
    ) -> Tuple[list[Dependency], list[ToCache]]:
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

        to_cache = []

        deps1 = None
        if deps:
            deps1 = deps.populate("eqangle", [a, b, c, d, m, n, p, q])
            deps1.algebra = [dab, dcd, dmn, dpq]
        if not is_equal(ab_cd, mn_pq):
            add += [deps1]
        to_cache.append(("eqangle", [a, b, c, d, m, n, p, q], deps1))
        self.make_equal(ab_cd, mn_pq, deps=deps1)

        deps2 = None
        if deps:
            deps2 = deps.populate("eqangle", [c, d, a, b, p, q, m, n])
            deps2.algebra = [dcd, dab, dpq, dmn]
        if not is_equal(cd_ab, pq_mn):
            add += [deps2]
        to_cache.append(("eqangle", [c, d, a, b, p, q, m, n], deps2))
        self.make_equal(cd_ab, pq_mn, deps=deps2)

        return add, to_cache

    def _add_eqratio3(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add three eqratios through a list of 6 points (due to parallel lines).

          a -- b
         m ---- n
        c ------ d

        """
        a, b, c, d, m, n = points

        add, to_cache = [], []

        ratios = [
            [m, a, m, c, n, b, n, d],
            [a, m, a, c, b, n, b, d],
            [c, m, c, a, d, n, d, b],
        ]
        if m == n:
            ratios.append([m, a, m, c, a, b, c, d])

        for ratio_points in ratios:
            _add, _to_cache = self._add_eqratio(ratio_points, deps)
            add += _add
            to_cache += _to_cache

        return add, to_cache

    def _add_eqratio4(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add four eqratios through a list of 5 points
        (due to parallel lines with common point).

           o
         a - b
        c --- d

        """
        o, a, b, c, d = points
        add, to_cache = self._add_eqratio3([a, b, c, d, o, o], deps)
        _add, _to_cache = self._add_eqratio([o, a, o, c, a, b, c, d], deps)
        return add + _add, to_cache + _to_cache

    def _add_eqratio(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
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
        to_cache = []
        if (
            ab.val != cd.val
            and mn.val != pq.val
            and (ab.val != mn.val or cd.val != pq.val)
        ):
            _add, _to_cache = self._add_eqratio8(
                a, b, c, d, m, n, p, q, ab, cd, mn, pq, deps
            )
            add += _add
            to_cache += _to_cache

        if (
            ab.val != mn.val
            and cd.val != pq.val
            and (ab.val != cd.val or mn.val != pq.val)
        ):
            _add, _to_cache = self._add_eqratio8(
                a, b, m, n, c, d, p, q, ab, mn, cd, pq, deps
            )
            add += _add
            to_cache += _to_cache
        return add, to_cache

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
    ) -> Tuple[list[Dependency], list[ToCache]]:
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

        to_cache = []

        deps1 = None
        if deps:
            deps1 = deps.populate("eqratio", [a, b, c, d, m, n, p, q])
            deps1.algebra = [ab._val, cd._val, mn._val, pq._val]
        if not is_equal(ab_cd, mn_pq):
            add += [deps1]
        to_cache.append(("eqratio", [a, b, c, d, m, n, p, q], deps1))
        self.make_equal(ab_cd, mn_pq, deps=deps1)

        deps2 = None
        if deps:
            deps2 = deps.populate("eqratio", [c, d, a, b, p, q, m, n])
            deps2.algebra = [cd._val, ab._val, pq._val, mn._val]
        if not is_equal(cd_ab, pq_mn):
            add += [deps2]
        to_cache.append(("eqratio", [c, d, a, b, p, q, m, n], deps2))
        self.make_equal(cd_ab, pq_mn, deps=deps2)
        return add, to_cache

    def _add_simtri_check(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        if nm.same_clock(*[p.num for p in points]):
            return self._add_simtri(points, deps)
        return self._add_simtri_reflect(points, deps)

    def _add_contri_check(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        if nm.same_clock(*[p.num for p in points]):
            return self._add_contri(points, deps)
        return self._add_contri_reflect(points, deps)

    def _add_simtri(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add two similar triangles."""
        add, to_cache = [], []
        hashs = [d.hashed() for d in deps.why]

        for args in comb.enum_triangle(points):
            if hashed("eqangle6", args) in hashs:
                continue
            _add, _to_cache = self._add_eqangle(args, deps=deps)
            add += _add
            to_cache += _to_cache

        for args in comb.enum_triangle(points):
            if hashed("eqratio6", args) in hashs:
                continue
            _add, _to_cache = self._add_eqratio(args, deps=deps)
            add += _add
            to_cache += _to_cache
        return add, to_cache

    def _add_simtri_reflect(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add two similar reflected triangles."""
        add, to_cache = [], []
        hashs = [d.hashed() for d in deps.why]
        for args in comb.enum_triangle_reflect(points):
            if hashed("eqangle6", args) in hashs:
                continue
            _add, _to_cache = self._add_eqangle(args, deps=deps)
            add += _add
            to_cache += _to_cache

        for args in comb.enum_triangle(points):
            if hashed("eqratio6", args) in hashs:
                continue
            _add, _to_cache = self._add_eqratio(args, deps=deps)
            add += _add
            to_cache += _to_cache

        return add, to_cache

    def _add_contri(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add two congruent triangles."""
        add, to_cache = [], []
        hashs = [d.hashed() for d in deps.why]
        for args in comb.enum_triangle(points):
            if hashed("eqangle6", args) in hashs:
                continue
            _add, _to_cache = self._add_eqangle(args, deps=deps)
            add += _add
            to_cache += _to_cache

        for args in comb.enum_sides(points):
            if hashed("cong", args) in hashs:
                continue
            _add, _to_cache = self._add_cong(args, deps=deps)
            add += _add
            to_cache += _to_cache
        return add, to_cache

    def _add_contri_reflect(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add two congruent reflected triangles."""
        add, to_cache = [], []
        hashs = [d.hashed() for d in deps.why]
        for args in comb.enum_triangle_reflect(points):
            if hashed("eqangle6", args) in hashs:
                continue
            _add, _to_cache = self._add_eqangle(args, deps=deps)
            add += _add
            to_cache += _to_cache

        for args in comb.enum_sides(points):
            if hashed("cong", args) in hashs:
                continue
            _add, _to_cache = self._add_cong(args, deps=deps)
            add += _add
            to_cache += _to_cache

        return add, to_cache

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
    ) -> Optional[Tuple[list[Dependency], list[ToCache]]]:
        """Add ab/cd = mn/pq in case maybe either two of (ab,cd,mn,pq) are equal."""
        level = deps.level
        if is_equal(ab, cd, level):
            return self._make_equal_pairs(a, b, c, d, m, n, p, q, ab, cd, mn, pq, deps)
        elif is_equal(mn, pq, level):
            return self._make_equal_pairs(m, n, p, q, a, b, c, d, mn, pq, ab, cd, deps)
        elif is_equal(ab, mn, level):
            return self._make_equal_pairs(a, b, m, n, c, d, p, q, ab, mn, cd, pq, deps)
        elif is_equal(cd, pq, level):
            return self._make_equal_pairs(c, d, p, q, a, b, m, n, cd, pq, ab, mn, deps)
        else:
            return None

    def _make_equal_pairs(
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
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add ab/cd = mn/pq in case either two of (ab,cd,mn,pq) are equal."""
        depname = "eqratio" if isinstance(ab, Segment) else "eqangle"
        eqname = "cong" if isinstance(ab, Segment) else "para"

        if ab != cd:
            dep0 = deps.populate(depname, [a, b, c, d, m, n, p, q])
            deps = EmptyDependency(level=deps.level, rule_name=None)

            dep = Dependency(eqname, [a, b, c, d], None, deps.level)
            deps.why = [
                dep0,
                dep.why_me_or_cache(
                    self.symbols_graph,
                    self.statements_checker,
                    self.dependency_cache,
                    None,
                ),
            ]

        elif eqname == "para":  # ab == cd.
            colls = [a, b, c, d]
            if len(set(colls)) > 2:
                dep0 = deps.populate(depname, [a, b, c, d, m, n, p, q])
                deps = EmptyDependency(level=deps.level, rule_name=None)

                dep = Dependency("collx", colls, None, deps.level)
                deps.why = [
                    dep0,
                    dep.why_me_or_cache(
                        self.symbols_graph,
                        self.statements_checker,
                        self.dependency_cache,
                        None,
                    ),
                ]

        deps = deps.populate(eqname, [m, n, p, q])
        self.make_equal(mn, pq, deps=deps)

        deps.algebra = mn._val, pq._val
        to_cache = [(eqname, [m, n, p, q], deps)]

        if is_equal(mn, pq):
            return [], to_cache
        return [deps], to_cache

    def _add_aconst(
        self, points: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add that an angle is equal to some constant."""
        a, b, c, d, num, den = points
        nd, dn = self.alegbraic_manipulator.get_or_create_const_ang(num, den)

        if nd == self.alegbraic_manipulator.halfpi:
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
        to_cache = []
        if not is_equal(ab_cd, nd):
            deps1 = deps.populate("aconst", [a, b, c, d, nd])
            deps1.algebra = dab, dcd, ang % 180
            self.make_equal(ab_cd, nd, deps=deps1)
            to_cache.append(("aconst", [a, b, c, d, nd], deps1))
            add += [deps1]

        if not is_equal(cd_ab, dn):
            deps2 = deps.populate("aconst", [c, d, a, b, dn])
            deps2.algebra = dcd, dab, 180 - ang % 180
            self.make_equal(cd_ab, dn, deps=deps2)
            to_cache.append(("aconst", [c, d, a, b, dn], deps2))
            add += [deps2]

        return add, to_cache

    def _add_s_angle(
        self, points: list[Point], deps: EmptyDependency
    ) -> list[Dependency]:
        """Add that an angle abx is equal to constant y."""
        a, b, x, y = points

        n, d = simplify(y % 180, 180)
        nd, dn = self.alegbraic_manipulator.get_or_create_const_ang(n, d)

        if nd == self.alegbraic_manipulator.halfpi:
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
            deps.why += [
                dep.why_me_or_cache(
                    self.symbols_graph,
                    self.statements_checker,
                    self.dependency_cache,
                    None,
                )
            ]

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

        to_cache = []
        if not is_equal(xba, nd):
            deps1 = deps.populate("aconst", [c, x, a, b, nd])
            deps1.algebra = dbx, dab, y % 180

            self.make_equal(xba, nd, deps=deps1)
            to_cache.append(("aconst", [c, x, a, b, nd], deps1))
            add += [deps1]

        if not is_equal(abx, dn):
            deps2 = deps.populate("aconst", [a, b, c, x, dn])
            deps2.algebra = dab, dbx, 180 - (y % 180)

            self.make_equal(abx, dn, deps=deps2)
            to_cache.append(("s_angle", [a, b, c, x, dn], deps2))
            add += [deps2]
        return add

    def _add_eqrat_const(
        self, args: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        """Add new algebraic predicates of type eqratio-constant."""
        a, b, c, d, num, den = args
        nd, dn = self.alegbraic_manipulator.get_or_create_const_rat(num, den)

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
        to_cache = []
        if not is_equal(ab_cd, nd):
            args = [a, b, c, d, nd]
            dep1 = deps.populate("rconst", args)
            dep1.algebra = ab._val, cd._val, num, den
            self.make_equal(nd, ab_cd, deps=dep1)
            to_cache.append(("rconst", [a, b, c, d, nd], dep1))
            add.append(dep1)

        if not is_equal(cd_ab, dn):
            args = [c, d, a, b, dn]
            dep2 = deps.populate("rconst", args)
            dep2.algebra = cd._val, ab._val, num, den
            self.make_equal(dn, cd_ab, deps=dep2)  # TODO FIX THAT
            to_cache.append(("rconst", [c, d, a, b, dn], dep2))
            add.append(dep2)

        return add, to_cache
