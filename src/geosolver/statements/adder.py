from __future__ import annotations
from typing import TYPE_CHECKING, Optional


import geosolver.combinatorics as comb
import geosolver.predicates as preds

from geosolver.intrinsic_rules import IntrinsicRules
from geosolver.statements.statement import Statement, angle_to_num_den, ratio_to_num_den

from geosolver.predicate_name import PredicateName
import geosolver.numerical.check as nm


from geosolver.dependencies.dependency import Reason, Dependency
from geosolver.dependencies.dependency_building import DependencyBody
from geosolver.geometry import Length, Line, Point, Segment
from geosolver.listing import list_eqratio3
from geosolver.symbols_graph import is_equal


ToCache = tuple[Statement, Dependency]

if TYPE_CHECKING:
    from geosolver.symbols_graph import SymbolsGraph
    from geosolver.statements.checker import StatementChecker
    from geosolver.dependencies.caching import DependencyCache
    from geosolver.dependencies.why_graph import WhyHyperGraph


ALL_INTRINSIC_RULES = [rule for rule in IntrinsicRules]


class StatementAdder:
    def __init__(
        self,
        symbols_graph: "SymbolsGraph",
        statements_graph: "WhyHyperGraph",
        statements_checker: "StatementChecker",
        dependency_cache: "DependencyCache",
        disabled_intrinsic_rules: Optional[list[IntrinsicRules | str]] = None,
    ) -> None:
        self.symbols_graph = symbols_graph

        self.statements_checker = statements_checker
        self.dependency_cache = dependency_cache
        self.statements_graph = statements_graph

        if disabled_intrinsic_rules is None:
            disabled_intrinsic_rules = []
        self.DISABLED_INTRINSIC_RULES = [
            IntrinsicRules(r) for r in disabled_intrinsic_rules
        ]

        self.PREDICATE_TO_ADDER = {
            PredicateName.MIDPOINT: self._add_midp,
            PredicateName.CONGRUENT: self._add_cong,
            PredicateName.CONGRUENT_2: self._add_cong2,
            PredicateName.CIRCLE: self._add_circle,
            PredicateName.CYCLIC: self._add_cyclic,
            PredicateName.S_ANGLE: self._add_s_angle,
            PredicateName.EQRATIO: self._add_eqratio,
            PredicateName.EQRATIO6: self._add_eqratio,
            PredicateName.EQRATIO3: self._add_eqratio3,
            # Predicate.EQRATIO4: self._add_eqratio4,
            PredicateName.SIMILAR_TRIANGLE: self._add_simtri,
            PredicateName.SIMILAR_TRIANGLE_REFLECTED: self._add_simtri_reflect,
            PredicateName.SIMILAR_TRIANGLE_BOTH: self._add_simtri_check,
            PredicateName.CONTRI_TRIANGLE: self._add_contri,
            PredicateName.CONTRI_TRIANGLE_REFLECTED: self._add_contri_reflect,
            PredicateName.CONTRI_TRIANGLE_BOTH: self._add_contri_check,
            PredicateName.CONSTANT_ANGLE: self._add_aconst,
            PredicateName.CONSTANT_RATIO: self._add_rconst,
            PredicateName.CONSTANT_LENGTH: self._add_lconst,
        }

    def add(
        self, statement: Statement, dep_body: DependencyBody
    ) -> tuple[list[Dependency], list[ToCache]]:
        """Add a new predicate."""
        piece_adder = self.PREDICATE_TO_ADDER.get(statement.predicate)
        if piece_adder is not None:
            return piece_adder(statement.args, dep_body)

        deps_to_cache = []
        # Cached or compute piece
        if statement.predicate in [
            PredicateName.COMPUTE_ANGLE,
            PredicateName.COMPUTE_RATIO,
            PredicateName.FIX_L,
            PredicateName.FIX_C,
            PredicateName.FIX_B,
            PredicateName.FIX_T,
            PredicateName.FIX_P,
        ]:
            dep = dep_body.build(self.statements_graph, statement)
            deps_to_cache.append((statement, dep))
            new_deps = [dep]
        elif statement.predicate is PredicateName.IND:
            new_deps = []
        else:
            raise ValueError(f"Not recognize predicate {statement.predicate}")

        return new_deps, deps_to_cache

    def _add_cong(
        self, points: list[Point], dep_body: DependencyBody
    ) -> tuple[list[Dependency], list[ToCache]]:
        """Add that two segments (4 points) are congruent."""
        a, b, c, d = points
        ab = self.symbols_graph.get_or_create_segment(a, b, None)
        cd = self.symbols_graph.get_or_create_segment(c, d, None)

        cong = Statement(PredicateName.CONGRUENT, [a, b, c, d])
        dep = dep_body.build(self.statements_graph, cong)
        self._make_equal(ab, cd, dep=dep)

        to_cache = [(cong, dep)]
        dep_body = []

        if not is_equal(ab, cd):
            dep_body += [dep]

        if IntrinsicRules.CYCLIC_FROM_CONG in self.DISABLED_INTRINSIC_RULES or (
            a not in [c, d] and b not in [c, d]
        ):
            return dep_body, to_cache

        # Make a=c if possible
        if b in [c, d]:
            a, b = b, a
        if a == d:
            c, d = d, c

        cyclic_deps, cyclic_cache = self._maybe_add_cyclic_from_cong(a, b, d, dep)
        dep_body += cyclic_deps
        to_cache += cyclic_cache
        return dep_body, to_cache

    def _add_cong2(
        self, points: list[Point], dep_body: DependencyBody
    ) -> tuple[list[Dependency], list[ToCache]]:
        m, n, a, b = points
        add, to_cache = self._add_cong([m, a, n, a], dep_body)
        _add, _to_cache = self._add_cong([m, b, n, b], dep_body)
        return add + _add, to_cache + _to_cache

    def _add_midp(
        self, points: list[Point], dep_body: DependencyBody
    ) -> tuple[list[Dependency], list[ToCache]]:
        m, a, b = points
        add_coll, to_cache_coll = preds.Coll.add(points, dep_body)
        add_cong, to_cache_cong = self._add_cong([m, a, m, b], dep_body)
        return add_coll + add_cong, to_cache_coll + to_cache_cong

    def _add_circle(
        self, points: list[Point], dep_body: DependencyBody
    ) -> tuple[list[Dependency], list[ToCache]]:
        o, a, b, c = points
        add_ab, to_cache_ab = self._add_cong([o, a, o, b], dep_body)
        add_ac, to_cache_ac = self._add_cong([o, a, o, c], dep_body)
        return add_ab + add_ac, to_cache_ab + to_cache_ac

    def _add_cyclic(
        self, points: list[Point], dep_body: DependencyBody
    ) -> tuple[list[Dependency], list[ToCache]]:
        """Add a new cyclic predicate that 4 points are concyclic."""
        points = list(set(points))
        og_points = list(points)

        all_circles = []
        for p1, p2, p3 in comb.arrangement_triplets(points):
            all_circles.append(self.symbols_graph.get_circle_thru_triplet(p1, p2, p3))
        points = sum([c.neighbors(Point) for c in all_circles], [])
        points = list(set(points))

        existed = set()
        new = set()
        for p1, p2, p3 in comb.arrangement_triplets(points):
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
                    whys.append(self._cyclic_dep(og_points, x))

            abcdef_deps = dep_body
            if IntrinsicRules.CYCLIC_FROM_CIRCLE:
                cyclic = Statement(PredicateName.CYCLIC, og_points)
                abcdef_deps = abcdef_deps.extend_by_why(
                    self.statements_graph,
                    cyclic,
                    why=whys + why0,
                    extention_reason=Reason(IntrinsicRules.CYCLIC_FROM_CIRCLE),
                )

            is_cyclic = self.statements_checker.check_cyclic(args)

            cyclic = Statement(PredicateName.CYCLIC, args)
            dep = abcdef_deps.build(self.statements_graph, cyclic)
            to_cache.append((cyclic, dep))
            self.symbols_graph.merge_into(circle0, [circle], dep)
            if not is_cyclic:
                add += [dep]

        return add, to_cache

    def _cyclic_dep(self, points: list[Point], p: Point) -> list[Dependency]:
        for p1, p2, p3 in comb.arrangement_triplets(points):
            if self.statements_checker.check_cyclic([p1, p2, p3, p]):
                cyclic = Statement(PredicateName.CYCLIC, (p1, p2, p3, p))
                return self.statements_graph.build_resolved_dependency(cyclic)

    def _maybe_add_cyclic_from_cong(
        self, a: Point, b: Point, c: Point, cong_ab_ac: Dependency
    ) -> tuple[list[Dependency], list[ToCache]]:
        """Maybe add a new cyclic predicate from given congruent segments."""
        ab = self.symbols_graph.get_or_create_segment(a, b, None)

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

        ax = self.symbols_graph.get_or_create_segment(a, x, dep=None)
        ay = self.symbols_graph.get_or_create_segment(a, y, dep=None)
        why = ab._val.why_equal([ax._val, ay._val])
        why += [cong_ab_ac]

        dep_body = DependencyBody(Reason(IntrinsicRules.CYCLIC_FROM_CONG), why=why)
        return self._add_cyclic([b, c, x, y], dep_body)

    def _add_eqratio3(
        self, points: list[Point], dep_body: DependencyBody
    ) -> tuple[list[Dependency], list[ToCache]]:
        """Add three eqratios through a list of 6 points (due to parallel lines).

          a -- b
         m ---- n
        c ------ d

        """
        add, to_cache = [], []
        ratios = list_eqratio3(points)
        for ratio_points in ratios:
            _add, _to_cache = self._add_eqratio(ratio_points, dep_body)
            add += _add
            to_cache += _to_cache

        self._simple_add(PredicateName.EQRATIO3, tuple(points), dep_body, add, to_cache)
        return add, to_cache

    def _add_eqratio4(
        self, points: list[Point], dep_body: DependencyBody
    ) -> tuple[list[Dependency], list[ToCache]]:
        """Add four eqratios through a list of 5 points
            (due to parallel lines with common point).

           o
         a - b
        c --- d

        """
        o, a, b, c, d = points
        add, to_cache = self._add_eqratio3([a, b, c, d, o, o], dep_body)
        _add, _to_cache = self._add_eqratio([o, a, o, c, a, b, c, d], dep_body)
        return add + _add, to_cache + _to_cache

    def _add_eqratio(
        self, points: list[Point], dep_body: DependencyBody
    ) -> tuple[list[Dependency], list[ToCache]]:
        """Add a new eqratio from 8 points."""
        if dep_body:
            dep_body = dep_body.copy()
        a, b, c, d, m, n, p, q = points
        ab = self.symbols_graph.get_or_create_segment(a, b, dep=None)
        cd = self.symbols_graph.get_or_create_segment(c, d, dep=None)
        mn = self.symbols_graph.get_or_create_segment(m, n, dep=None)
        pq = self.symbols_graph.get_or_create_segment(p, q, dep=None)

        if IntrinsicRules.CONG_FROM_EQRATIO not in self.DISABLED_INTRINSIC_RULES:
            add = self._maybe_make_equal_pairs(
                a, b, c, d, m, n, p, q, ab, cd, mn, pq, dep_body
            )
            if add is not None:
                return add

        self.symbols_graph.get_node_val(ab, dep=None)
        self.symbols_graph.get_node_val(cd, dep=None)
        self.symbols_graph.get_node_val(mn, dep=None)
        self.symbols_graph.get_node_val(pq, dep=None)

        add = []
        to_cache = []
        if (
            ab.val != cd.val
            and mn.val != pq.val
            and (ab.val != mn.val or cd.val != pq.val)
        ):
            _add, _to_cache = self._add_eqratio8(
                a, b, c, d, m, n, p, q, ab, cd, mn, pq, dep_body
            )
            add += _add
            to_cache += _to_cache

        if (
            ab.val != mn.val
            and cd.val != pq.val
            and (ab.val != cd.val or mn.val != pq.val)
        ):
            _add, _to_cache = self._add_eqratio8(
                a, b, m, n, c, d, p, q, ab, mn, cd, pq, dep_body
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
        dep_body: DependencyBody,
    ) -> tuple[list[Dependency], list[ToCache]]:
        """Add a new eqratio from 8 points (core)."""
        if dep_body:
            dep_body = dep_body.copy()

        args = [a, b, c, d, m, n, p, q]
        i = 0
        for x, y, xy in [(a, b, ab), (c, d, cd), (m, n, mn), (p, q, pq)]:
            if {x, y} == set(xy.points):
                continue
            x_, y_ = list(xy.points)
            if (
                dep_body
                and IntrinsicRules.EQRATIO_FROM_CONG
                not in self.DISABLED_INTRINSIC_RULES
            ):
                eqratio = Statement(PredicateName.EQRATIO, tuple(args))
                cong = Statement(PredicateName.CONGRUENT, [x, y, x_, y_])
                dep_body = dep_body.extend(
                    self.statements_graph,
                    eqratio,
                    cong,
                    extention_reason=Reason(IntrinsicRules.EQRATIO_FROM_CONG),
                )
            args[2 * i - 2] = x_
            args[2 * i - 1] = y_

        add = []
        ab_cd, cd_ab, why1 = self.symbols_graph.get_or_create_ratio_from_segments(
            ab, cd, dep=None
        )
        mn_pq, pq_mn, why2 = self.symbols_graph.get_or_create_ratio_from_segments(
            mn, pq, dep=None
        )

        if (
            IntrinsicRules.EQRATIO_FROM_PROPORTIONAL_SEGMENTS
            not in self.DISABLED_INTRINSIC_RULES
        ):
            dep_body = dep_body.extend_by_why(
                self.statements_graph,
                Statement(PredicateName.EQRATIO, tuple(args)),
                why=why1 + why2,
                extention_reason=Reason(
                    IntrinsicRules.EQRATIO_FROM_PROPORTIONAL_SEGMENTS
                ),
            )

        lab, lcd = ab_cd._l
        lmn, lpq = mn_pq._l

        a, b = lab._obj.points
        c, d = lcd._obj.points
        m, n = lmn._obj.points
        p, q = lpq._obj.points

        to_cache = []

        dep1 = None
        eqratio = Statement(PredicateName.EQRATIO, [a, b, c, d, m, n, p, q])
        dep1 = dep_body.build(self.statements_graph, eqratio)
        if not is_equal(ab_cd, mn_pq):
            add += [dep1]
        to_cache.append((eqratio, dep1))
        self._make_equal(ab_cd, mn_pq, dep=dep1)

        dep2 = None
        eqratio_sym = Statement(PredicateName.EQRATIO, [c, d, a, b, p, q, m, n])
        dep2 = dep_body.build(self.statements_graph, eqratio_sym)
        if not is_equal(cd_ab, pq_mn):
            add += [dep2]
        to_cache.append((eqratio_sym, dep2))
        self._make_equal(cd_ab, pq_mn, dep=dep2)
        return add, to_cache

    def _simple_add(
        self,
        predicate: PredicateName,
        points: tuple[Point, ...],
        dep_body: DependencyBody,
        added: list[Dependency],
        to_cache: list[ToCache],
    ):
        statement = Statement(predicate, points)
        dep = self.statements_graph.build_dependency(statement, dep_body)
        added.append(dep)
        to_cache.append((statement, dep))

    def _add_simtri_check(
        self, points: list[Point], dep_body: DependencyBody
    ) -> tuple[list[Dependency], list[ToCache]]:
        if nm.same_clock(*[p.num for p in points]):
            added, to_cache = self._add_simtri(points, dep_body)
        else:
            added, to_cache = self._add_simtri_reflect(points, dep_body)
        self._simple_add(
            PredicateName.SIMILAR_TRIANGLE_BOTH,
            tuple(points),
            dep_body,
            added,
            to_cache,
        )
        return added, to_cache

    def _add_contri_check(
        self, points: list[Point], dep_body: DependencyBody
    ) -> tuple[list[Dependency], list[ToCache]]:
        if nm.same_clock(*[p.num for p in points]):
            added, to_cache = self._add_contri(points, dep_body)
        else:
            added, to_cache = self._add_contri_reflect(points, dep_body)
        self._simple_add(
            PredicateName.CONTRI_TRIANGLE_BOTH, points, dep_body, added, to_cache
        )
        return added, to_cache

    def _add_simtri(
        self, points: list[Point], dep_body: DependencyBody
    ) -> tuple[list[Dependency], list[ToCache]]:
        """Add two similar triangles."""
        add, to_cache = [], []
        hashs = [dep.statement.hash_tuple for dep in dep_body.why]

        for args in comb.enum_triangle(points):
            eqangle6 = Statement(PredicateName.EQANGLE6, args)
            if eqangle6.hash_tuple in hashs:
                continue
            _add, _to_cache = self._add_eqangle(args, dep_body=dep_body)
            add += _add
            to_cache += _to_cache

        for args in comb.enum_triangle(points):
            eqratio6 = Statement(PredicateName.EQRATIO6, args)
            if eqratio6.hash_tuple in hashs:
                continue
            _add, _to_cache = self._add_eqratio(args, dep_body=dep_body)
            add += _add
            to_cache += _to_cache

        self._simple_add(
            PredicateName.SIMILAR_TRIANGLE, tuple(points), dep_body, add, to_cache
        )
        return add, to_cache

    def _add_simtri_reflect(
        self, points: list[Point], dep_body: DependencyBody
    ) -> tuple[list[Dependency], list[ToCache]]:
        """Add two similar reflected triangles."""
        add, to_cache = [], []
        hashs = [dep.statement.hash_tuple for dep in dep_body.why]
        for args in comb.enum_triangle_reflect(points):
            eqangle6 = Statement(PredicateName.EQANGLE6, args)
            if eqangle6.hash_tuple in hashs:
                continue
            _add, _to_cache = self._add_eqangle(args, dep_body=dep_body)
            add += _add
            to_cache += _to_cache

        for args in comb.enum_triangle(points):
            eqratio6 = Statement(PredicateName.EQRATIO6, args)
            if eqratio6.hash_tuple in hashs:
                continue
            _add, _to_cache = self._add_eqratio(args, dep_body=dep_body)
            add += _add
            to_cache += _to_cache

        self._simple_add(
            PredicateName.SIMILAR_TRIANGLE_REFLECTED,
            tuple(points),
            dep_body,
            add,
            to_cache,
        )
        return add, to_cache

    def _add_contri(
        self, points: list[Point], dep_body: DependencyBody
    ) -> tuple[list[Dependency], list[ToCache]]:
        """Add two congruent triangles."""
        add, to_cache = [], []
        hashs = [dep.statement.hash_tuple for dep in dep_body.why]
        for args in comb.enum_triangle(points):
            eqangle6 = Statement(PredicateName.EQANGLE6, args)
            if eqangle6.hash_tuple in hashs:
                continue
            _add, _to_cache = self._add_eqangle(args, dep_body=dep_body)
            add += _add
            to_cache += _to_cache

        for args in comb.enum_sides(points):
            cong = Statement(PredicateName.CONGRUENT, args)
            if cong.hash_tuple in hashs:
                continue
            _add, _to_cache = self._add_cong(args, dep_body)
            add += _add
            to_cache += _to_cache

        self._simple_add(
            PredicateName.CONTRI_TRIANGLE, tuple(points), dep_body, add, to_cache
        )
        return add, to_cache

    def _add_contri_reflect(
        self, points: list[Point], dep_body: DependencyBody
    ) -> tuple[list[Dependency], list[ToCache]]:
        """Add two congruent reflected triangles."""
        add, to_cache = [], []
        hashs = [dep.statement.hash_tuple for dep in dep_body.why]
        for args in comb.enum_triangle_reflect(points):
            eqangle6 = Statement(PredicateName.EQANGLE6, args)
            if eqangle6.hash_tuple in hashs:
                continue
            _add, _to_cache = self._add_eqangle(args, dep_body)
            add += _add
            to_cache += _to_cache

        for args in comb.enum_sides(points):
            cong = Statement(PredicateName.CONGRUENT, args)
            if cong.hash_tuple in hashs:
                continue
            _add, _to_cache = self._add_cong(args, dep_body)
            add += _add
            to_cache += _to_cache

        self._simple_add(
            PredicateName.CONTRI_TRIANGLE_REFLECTED,
            tuple(points),
            dep_body,
            add,
            to_cache,
        )
        return add, to_cache

    def _add_aconst(
        self, points: list[Point], dep_body: DependencyBody
    ) -> tuple[list[Dependency], list[ToCache]]:
        """Add that an angle is equal to some constant."""
        points = list(points)
        a, b, c, d, ang = points

        num, den = angle_to_num_den(ang)
        nd, dn = self.symbols_graph.get_or_create_const_ang(num, den)

        if nd == self.symbols_graph.halfpi:
            return self._add_perp([a, b, c, d], dep_body)

        ab, why1 = self.symbols_graph.get_line_thru_pair_why(a, b)
        cd, why2 = self.symbols_graph.get_line_thru_pair_why(c, d)

        (a, b), (c, d) = ab.points, cd.points
        if IntrinsicRules.ACONST_FROM_LINES not in self.DISABLED_INTRINSIC_RULES:
            args = points[:-1] + [nd]
            aconst = Statement(PredicateName.CONSTANT_ANGLE, tuple(args))
            dep_body = dep_body.extend_by_why(
                self.statements_graph,
                aconst,
                why=why1 + why2,
                extention_reason=Reason(IntrinsicRules.ACONST_FROM_LINES),
            )

        self.symbols_graph.get_node_val(ab, dep=None)
        self.symbols_graph.get_node_val(cd, dep=None)

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
                and IntrinsicRules.ACONST_FROM_PARA not in self.DISABLED_INTRINSIC_RULES
            ):
                aconst = Statement(PredicateName.CONSTANT_ANGLE, tuple(args))
                para = Statement(preds.Para.NAME, [x, y, x_, y_])
                dep_body = dep_body.extend(
                    self.statements_graph,
                    aconst,
                    para,
                    Reason(IntrinsicRules.ACONST_FROM_PARA),
                )
            args[2 * i - 2] = x_
            args[2 * i - 1] = y_

        ab_cd, cd_ab, why = self.symbols_graph.get_or_create_angle_from_lines(
            ab, cd, dep=None
        )

        aconst = Statement(PredicateName.CONSTANT_ANGLE, [a, b, c, d, nd])
        if IntrinsicRules.ACONST_FROM_ANGLE not in self.DISABLED_INTRINSIC_RULES:
            dep_body = dep_body.extend_by_why(
                self.statements_graph,
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
            dep1 = dep_body.build(self.statements_graph, aconst)
            self._make_equal(ab_cd, nd, dep=dep1)
            to_cache.append((aconst, dep1))
            add += [dep1]

        aconst2 = Statement(PredicateName.CONSTANT_ANGLE, [a, b, c, d, nd])
        if not is_equal(cd_ab, dn):
            dep2 = dep_body.build(self.statements_graph, aconst2)
            self._make_equal(cd_ab, dn, dep=dep2)
            to_cache.append((aconst2, dep2))
            add += [dep2]

        return add, to_cache

    def _add_s_angle(
        self, points: list[Point], dep_body: DependencyBody
    ) -> tuple[list[Dependency], list[ToCache]]:
        """Add that an angle abx is equal to constant y."""
        a, b, x, angle = points
        num, den = angle_to_num_den(angle)
        nd, dn = self.symbols_graph.get_or_create_const_ang(num, den)

        if nd == self.symbols_graph.halfpi:
            return self._add_perp([a, b, b, x], dep_body)

        ab, why1 = self.symbols_graph.get_line_thru_pair_why(a, b)
        bx, why2 = self.symbols_graph.get_line_thru_pair_why(b, x)

        self.symbols_graph.get_node_val(ab, dep=None)
        self.symbols_graph.get_node_val(bx, dep=None)

        add, to_cache = [], []

        if ab.val == bx.val:
            return add, to_cache

        sangle = Statement(PredicateName.S_ANGLE, (a, b, x))
        if IntrinsicRules.SANGLE_FROM_LINES not in self.DISABLED_INTRINSIC_RULES:
            dep_body = dep_body.extend_by_why(
                self.statements_graph,
                sangle,
                why=why1 + why2,
                extention_reason=Reason(IntrinsicRules.SANGLE_FROM_LINES),
            )

        if IntrinsicRules.SANGLE_FROM_PARA not in self.DISABLED_INTRINSIC_RULES:
            paras = []
            for p, q, pq in [(a, b, ab), (b, x, bx)]:
                p_, q_ = pq.val._obj.points
                if {p, q} == {p_, q_}:
                    continue
                paras.append(Statement(preds.Para.NAME, (p, q, p_, q_)))
            if paras:
                dep_body = dep_body.extend_many(
                    self.statements_graph,
                    sangle,
                    paras,
                    Reason(IntrinsicRules.SANGLE_FROM_PARA),
                )

        xba, abx, why = self.symbols_graph.get_or_create_angle_from_lines(
            bx, ab, dep=None
        )
        if IntrinsicRules.SANGLE_FROM_ANGLE not in self.DISABLED_INTRINSIC_RULES:
            aconst = Statement(PredicateName.CONSTANT_ANGLE, [b, x, a, b, nd])
            dep_body = dep_body.extend_by_why(
                self.statements_graph,
                aconst,
                why=why,
                extention_reason=Reason(IntrinsicRules.SANGLE_FROM_ANGLE),
            )

        dab, dbx = abx._d
        a, b = dab._obj.points
        c, x = dbx._obj.points

        if not is_equal(xba, nd):
            aconst = Statement(PredicateName.S_ANGLE, [c, x, a, b, nd])
            dep1 = dep_body.build(self.statements_graph, aconst)
            self._make_equal(xba, nd, dep=dep1)
            to_cache.append((aconst, dep1))
            add += [dep1]

        if not is_equal(abx, dn):
            aconst2 = Statement(PredicateName.S_ANGLE, [a, b, c, x, dn])
            dep2 = dep_body.build(self.statements_graph, aconst2)
            self._make_equal(abx, dn, dep=dep2)
            to_cache.append((aconst2, dep2))
            add += [dep2]

        return add, to_cache

    def _add_rconst(
        self, args: list[Point], dep_body: DependencyBody
    ) -> tuple[list[Dependency], list[ToCache]]:
        """Add new algebraic predicates of type eqratio-constant."""
        a, b, c, d, ratio = args

        num, den = ratio_to_num_den(ratio)
        nd, dn = self.symbols_graph.get_or_create_const_rat(num, den)

        if num == den:
            return self._add_cong([a, b, c, d], dep_body)

        ab = self.symbols_graph.get_or_create_segment(a, b, dep=None)
        cd = self.symbols_graph.get_or_create_segment(c, d, dep=None)

        self.symbols_graph.get_node_val(ab, dep=None)
        self.symbols_graph.get_node_val(cd, dep=None)

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
                and IntrinsicRules.RCONST_FROM_CONG not in self.DISABLED_INTRINSIC_RULES
            ):
                rconst = Statement(PredicateName.CONSTANT_RATIO, tuple(args))
                cong = Statement(PredicateName.CONGRUENT, [x, y, x_, y_])
                dep_body = dep_body.extend(
                    self.statements_graph,
                    rconst,
                    cong,
                    extention_reason=Reason(IntrinsicRules.RCONST_FROM_CONG),
                )
            args[2 * i - 2] = x_
            args[2 * i - 1] = y_

        ab_cd, cd_ab, why = self.symbols_graph.get_or_create_ratio_from_segments(
            ab, cd, dep=None
        )

        rconst = Statement(PredicateName.CONSTANT_RATIO, [a, b, c, d, nd])
        if IntrinsicRules.RCONST_FROM_RATIO not in self.DISABLED_INTRINSIC_RULES:
            dep_body = dep_body.extend_by_why(
                self.statements_graph,
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
            dep1 = dep_body.build(self.statements_graph, rconst)
            self._make_equal(nd, ab_cd, dep=dep1)
            to_cache.append((rconst, dep1))
            add.append(dep1)

        if not is_equal(cd_ab, dn):
            rconst2 = Statement(PredicateName.CONSTANT_RATIO, [c, d, a, b, dn])
            dep2 = dep_body.build(self.statements_graph, rconst2)
            self._make_equal(dn, cd_ab, dep=dep2)
            to_cache.append((rconst2, dep2))
            add.append(dep2)

        return add, to_cache

    def _add_lconst(
        self, args: tuple[Point, Point, Length], dep_body: DependencyBody
    ) -> tuple[list[Dependency], list[ToCache]]:
        """Add new algebraic predicates of type eqratio-constant."""
        a, b, length = args

        ab = self.symbols_graph.get_or_create_segment(a, b, dep=None)
        l_ab = self.symbols_graph.get_node_val(ab, dep=None)

        lconst = Statement(PredicateName.CONSTANT_LENGTH, args)

        lconst_dep = dep_body.build(self.statements_graph, lconst)
        self._make_equal(length, l_ab, dep=lconst_dep)

        add = [lconst_dep]
        to_cache = [(lconst, lconst_dep)]
        return add, to_cache


def maybe_make_equal_pairs(
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
    dep_body: DependencyBody,
    dep_graph: WhyHyperGraph,
    symbols_graph: SymbolsGraph,
) -> Optional[tuple[list[Dependency], list[ToCache]]]:
    """Add ab/cd = mn/pq in case maybe either two of (ab,cd,mn,pq) are equal."""
    points = None
    lines = None
    if is_equal(ab, cd):
        points = (a, b, c, d, m, n, p, q)
        lines = (ab, cd, mn, pq)
    elif is_equal(mn, pq):
        points = (m, n, p, q, a, b, c, d)
        lines = (mn, pq, ab, cd)
    elif is_equal(ab, mn):
        points = (a, b, m, n, c, d, p, q)
        lines = (ab, mn, cd, pq)
    elif is_equal(cd, pq):
        points = (c, d, p, q, a, b, m, n)
        lines = (cd, pq, ab, mn)

    if points is None:
        return None

    return _make_equal_pairs(*points, *lines, dep_body, dep_graph, symbols_graph)


def _make_equal_pairs(
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
    dep_body: DependencyBody,
    dep_graph: WhyHyperGraph,
    symbols_graph: SymbolsGraph,
) -> tuple[list[Dependency], list[ToCache]]:
    """Add ab/cd = mn/pq in case either two of (ab,cd,mn,pq) are equal."""
    if isinstance(ab, Segment):
        dep_pred = PredicateName.EQRATIO
        eq_pred = PredicateName.CONGRUENT
        intrinsic_rule = IntrinsicRules.CONG_FROM_EQRATIO
    else:
        dep_pred = preds.EqAngle.NAME
        eq_pred = preds.Para.NAME
        intrinsic_rule = IntrinsicRules.PARA_FROM_EQANGLE

    reason = Reason(intrinsic_rule)
    eq = Statement(dep_pred, [a, b, c, d, m, n, p, q])
    if ab != cd:
        because_eq = Statement(eq_pred, [a, b, c, d])
        dep_body = dep_body.extend(dep_graph, eq, because_eq, reason)

    elif eq_pred is preds.Para.NAME:  # ab == cd.
        colls = [a, b, c, d]
        if len(set(colls)) > 2:
            because_collx = Statement(preds.Collx.NAME, colls)
            dep_body = dep_body.extend(dep_graph, eq, because_collx, reason)

    because_eq = Statement(eq_pred, [m, n, p, q])
    dep = dep_body.build(dep_graph, because_eq)
    symbols_graph.make_equal(mn, pq, dep=dep)

    to_cache = [(because_eq, dep)]

    if is_equal(mn, pq):
        return [], to_cache
    return [dep], to_cache
