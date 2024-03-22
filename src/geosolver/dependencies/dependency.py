from __future__ import annotations
from typing import TYPE_CHECKING


from geosolver.dependencies.caching import hashed
from geosolver.geometry import (
    Angle,
    Direction,
    Line,
    Point,
    Ratio,
    all_angles,
    all_ratios,
    bfs_backtrack,
    circle_of_and_why,
    line_of_and_why,
    why_equal,
)
from geosolver.problem import CONSTRUCTION_RULE, Construction

if TYPE_CHECKING:
    from geosolver.proof import Proof


class Dependency(Construction):
    """Dependency is a predicate that other predicates depend on."""

    def __init__(self, name: str, args: list["Point"], rule_name: str, level: int):
        super().__init__(name, args)
        self.rule_name = rule_name or ""
        self.level = level
        self.why = []

        self._stat = None
        self.trace = None

    def _find(self, dep_hashed: tuple[str, ...]) -> "Dependency":
        for w in self.why:
            f = w._find(dep_hashed)
            if f:
                return f
            if w.hashed() == dep_hashed:
                return w

    def remove_loop(self) -> "Dependency":
        f = self._find(self.hashed())
        if f:
            return f
        return self

    def copy(self) -> "Dependency":
        dep = Dependency(self.name, self.args, self.rule_name, self.level)
        dep.trace = self.trace
        dep.why = list(self.why)
        return dep

    def populate(self, name: str, args: list["Point"]) -> "Dependency":
        assert self.rule_name == CONSTRUCTION_RULE, self.rule_name
        dep = Dependency(self.name, self.args, self.rule_name, self.level)
        dep.why = list(self.why)
        return dep

    def why_me(self, proof: "Proof", level: int) -> None:
        """Figure out the dependencies predicates of self."""
        why_dependency(self, proof, level)

    def why_me_or_cache(self, proof: "Proof", level: int) -> "Dependency":
        cached_dep = proof.dependency_cache.get_cached(self)
        if cached_dep is not None:
            return cached_dep
        self.why_me(proof, level)
        return self

    def hashed(self, rename: bool = False) -> tuple[str, ...]:
        return hashed(self.name, self.args, rename=rename)


def why_dependency(dep: "Dependency", proof: "Proof", level: int) -> None:
    cached_me = proof.dependency_cache.get(dep.name, dep.args)
    if cached_me is not None:
        dep.why = cached_me.why
        dep.rule_name = cached_me.rule_name
        return

    if dep.name == "para":
        a, b, c, d = dep.args
        if {a, b} == {c, d}:
            dep.why = []
            return

        ab = proof.symbols_graph.get_line(a, b)
        cd = proof.symbols_graph.get_line(c, d)
        if ab == cd:
            if {a, b} == {c, d}:
                dep.why = []
                dep.rule_name = ""
                return
            dep = Dependency("coll", list({a, b, c, d}), "t??", None)
            dep.why = [dep.why_me_or_cache(proof, level)]
            return

        for (x, y), xy in zip([(a, b), (c, d)], [ab, cd]):
            x_, y_ = xy.points
            if {x, y} == {x_, y_}:
                continue
            d = Dependency("collx", [x, y, x_, y_], None, level)
            dep.why += [d.why_me_or_cache(proof, level)]

        whypara = proof.why_equal(ab, cd, None)
        dep.why += whypara

    elif dep.name == "midp":
        m, a, b = dep.args
        ma = proof.symbols_graph.get_segment(m, a)
        mb = proof.symbols_graph.get_segment(m, b)
        dep = Dependency("coll", [m, a, b], None, None).why_me_or_cache(proof, None)
        dep.why = [dep] + proof.why_equal(ma, mb, level)

    elif dep.name == "perp":
        a, b, c, d = dep.args
        ab = proof.symbols_graph.get_line(a, b)
        cd = proof.symbols_graph.get_line(c, d)
        for (x, y), xy in zip([(a, b), (c, d)], [ab, cd]):
            x_, y_ = xy.points
            if {x, y} == {x_, y_}:
                continue
            d = Dependency("collx", [x, y, x_, y_], None, level)
            dep.why += [d.why_me_or_cache(proof, level)]

        _, why = why_eqangle(ab._val, cd._val, cd._val, ab._val, level)
        a, b = ab.points
        c, d = cd.points

        if hashed(dep.name, [a, b, c, d]) != dep.hashed():
            d = Dependency(dep.name, [a, b, c, d], None, level)
            d.why = why
            why = [d]

        dep.why += why

    elif dep.name == "cong":
        a, b, c, d = dep.args
        ab = proof.symbols_graph.get_segment(a, b)
        cd = proof.symbols_graph.get_segment(c, d)

        dep.why = proof.why_equal(ab, cd, level)

    elif dep.name == "coll":
        _, why = line_of_and_why(dep.args, level)
        dep.why = why

    elif dep.name == "collx":
        if proof.check_coll(dep.args):
            args = list(set(dep.args))
            cached_dep = proof.dependency_cache.get("coll", args)
            if cached_dep is not None:
                dep.why = [cached_dep]
                dep.rule_name = ""
                return
            _, dep.why = line_of_and_why(args, level)
        else:
            dep.name = "para"
            dep.why_me(proof, level)

    elif dep.name == "cyclic":
        _, why = circle_of_and_why(dep.args, level)
        dep.why = why

    elif dep.name == "circle":
        o, a, b, c = dep.args
        oa = proof.symbols_graph.get_segment(o, a)
        ob = proof.symbols_graph.get_segment(o, b)
        oc = proof.symbols_graph.get_segment(o, c)
        dep.why = proof.why_equal(oa, ob, level) + proof.why_equal(oa, oc, level)

    elif dep.name in ["eqangle", "eqangle6"]:
        a, b, c, d, m, n, p, q = dep.args

        ab, why1 = proof.symbols_graph.get_line_thru_pair_why(a, b)
        cd, why2 = proof.symbols_graph.get_line_thru_pair_why(c, d)
        mn, why3 = proof.symbols_graph.get_line_thru_pair_why(m, n)
        pq, why4 = proof.symbols_graph.get_line_thru_pair_why(p, q)

        if ab is None or cd is None or mn is None or pq is None:
            if {a, b} == {m, n}:
                d = Dependency("para", [c, d, p, q], None, level)
                dep.why = [d.why_me_or_cache(proof, level)]
            if {a, b} == {c, d}:
                d = Dependency("para", [p, q, m, n], None, level)
                dep.why = [d.why_me_or_cache(proof, level)]
            if {c, d} == {p, q}:
                d = Dependency("para", [a, b, m, n], None, level)
                dep.why = [d.why_me_or_cache(proof, level)]
            if {p, q} == {m, n}:
                d = Dependency("para", [a, b, c, d], None, level)
                dep.why = [d.why_me_or_cache(proof, level)]
            return

        for (x, y), xy, whyxy in zip(
            [(a, b), (c, d), (m, n), (p, q)],
            [ab, cd, mn, pq],
            [why1, why2, why3, why4],
        ):
            x_, y_ = xy.points
            if {x, y} == {x_, y_}:
                continue
            d = Dependency("collx", [x, y, x_, y_], None, level)
            d.why = whyxy
            dep.why += [d]

        a, b = ab.points
        c, d = cd.points
        m, n = mn.points
        p, q = pq.points
        diff = hashed(dep.name, [a, b, c, d, m, n, p, q]) != dep.hashed()

        whyeqangle = None
        if ab._val and cd._val and mn._val and pq._val:
            whyeqangle = why_eqangle(ab._val, cd._val, mn._val, pq._val, level)

        if whyeqangle:
            (dab, dcd, dmn, dpq), whyeqangle = whyeqangle
            if diff:
                d = Dependency("eqangle", [a, b, c, d, m, n, p, q], None, level)
                d.why = whyeqangle
                whyeqangle = [d]
            dep.why += whyeqangle

        else:
            if (ab == cd and mn == pq) or (ab == mn and cd == pq):
                dep.why += []
            elif ab == mn:
                dep.why += maybe_make_equal_pairs(
                    a, b, c, d, m, n, p, q, ab, mn, proof, level
                )
            elif cd == pq:
                dep.why += maybe_make_equal_pairs(
                    c, d, a, b, p, q, m, n, cd, pq, proof, level
                )
            elif ab == cd:
                dep.why += maybe_make_equal_pairs(
                    a, b, m, n, c, d, p, q, ab, cd, proof, level
                )
            elif mn == pq:
                dep.why += maybe_make_equal_pairs(
                    m, n, a, b, p, q, c, d, mn, pq, proof, level
                )
            elif proof.is_equal(ab, mn) or proof.is_equal(cd, pq):
                dep1 = Dependency("para", [a, b, m, n], None, level)
                dep1.why_me(proof, level)
                dep2 = Dependency("para", [c, d, p, q], None, level)
                dep2.why_me(proof, level)
                dep.why += [dep1, dep2]
            elif proof.is_equal(ab, cd) or proof.is_equal(mn, pq):
                dep1 = Dependency("para", [a, b, c, d], None, level)
                dep1.why_me(proof, level)
                dep2 = Dependency("para", [m, n, p, q], None, level)
                dep2.why_me(proof, level)
                dep.why += [dep1, dep2]
            elif ab._val and cd._val and mn._val and pq._val:
                dep.why = why_eqangle(ab._val, cd._val, mn._val, pq._val, level)

    elif dep.name in ["eqratio", "eqratio6"]:
        a, b, c, d, m, n, p, q = dep.args
        ab = proof.symbols_graph.get_segment(a, b)
        cd = proof.symbols_graph.get_segment(c, d)
        mn = proof.symbols_graph.get_segment(m, n)
        pq = proof.symbols_graph.get_segment(p, q)

        if ab is None or cd is None or mn is None or pq is None:
            if {a, b} == {m, n}:
                d = Dependency("cong", [c, d, p, q], None, level)
                dep.why = [d.why_me_or_cache(proof, level)]
            if {a, b} == {c, d}:
                d = Dependency("cong", [p, q, m, n], None, level)
                dep.why = [d.why_me_or_cache(proof, level)]
            if {c, d} == {p, q}:
                d = Dependency("cong", [a, b, m, n], None, level)
                dep.why = [d.why_me_or_cache(proof, level)]
            if {p, q} == {m, n}:
                d = Dependency("cong", [a, b, c, d], None, level)
                dep.why = [d.why_me_or_cache(proof, level)]
            return

        if ab._val and cd._val and mn._val and pq._val:
            dep.why = why_eqratio(ab._val, cd._val, mn._val, pq._val, level)

        if dep.why is None:
            dep.why = []
            if (ab == cd and mn == pq) or (ab == mn and cd == pq):
                dep.why = []
            elif ab == mn:
                dep.why += maybe_make_equal_pairs(
                    a, b, c, d, m, n, p, q, ab, mn, proof, level
                )
            elif cd == pq:
                dep.why += maybe_make_equal_pairs(
                    c, d, a, b, p, q, m, n, cd, pq, proof, level
                )
            elif ab == cd:
                dep.why += maybe_make_equal_pairs(
                    a, b, m, n, c, d, p, q, ab, cd, proof, level
                )
            elif mn == pq:
                dep.why += maybe_make_equal_pairs(
                    m, n, a, b, p, q, c, d, mn, pq, proof, level
                )
            elif proof.is_equal(ab, mn) or proof.is_equal(cd, pq):
                dep1 = Dependency("cong", [a, b, m, n], None, level)
                dep1.why_me(proof, level)
                dep2 = Dependency("cong", [c, d, p, q], None, level)
                dep2.why_me(proof, level)
                dep.why += [dep1, dep2]
            elif proof.is_equal(ab, cd) or proof.is_equal(mn, pq):
                dep1 = Dependency("cong", [a, b, c, d], None, level)
                dep1.why_me(proof, level)
                dep2 = Dependency("cong", [m, n, p, q], None, level)
                dep2.why_me(proof, level)
                dep.why += [dep1, dep2]
            elif ab._val and cd._val and mn._val and pq._val:
                dep.why = why_eqangle(ab._val, cd._val, mn._val, pq._val, level)

    elif dep.name in ["diff", "npara", "nperp", "ncoll", "sameside"]:
        dep.why = []

    elif dep.name == "simtri":
        a, b, c, x, y, z = dep.args
        dep1 = Dependency("eqangle", [a, b, a, c, x, y, x, z], "", level)
        dep1.why_me(proof, level)
        dep2 = Dependency("eqangle", [b, a, b, c, y, x, y, z], "", level)
        dep2.why_me(proof, level)
        dep.rule_name = "r34"
        dep.why = [dep1, dep2]

    elif dep.name == "contri":
        a, b, c, x, y, z = dep.args
        dep1 = Dependency("cong", [a, b, x, y], "", level)
        dep1.why_me(proof, level)
        dep2 = Dependency("cong", [b, c, y, z], "", level)
        dep2.why_me(proof, level)
        dep3 = Dependency("cong", [c, a, z, x], "", level)
        dep3.why_me(proof, level)
        dep.rule_name = "r32"
        dep.why = [dep1, dep2, dep3]

    elif dep.name == "ind":
        pass

    elif dep.name == "aconst":
        a, b, c, d, ang0 = dep.args

        measure = ang0._val

        for ang in measure.neighbors(Angle):
            if ang == ang0:
                continue
            d1, d2 = ang._d
            l1, l2 = d1._obj, d2._obj
            (a1, b1), (c1, d1) = l1.points, l2.points

            if not proof.check_para_or_coll(
                [a, b, a1, b1]
            ) or not proof.check_para_or_coll([c, d, c1, d1]):
                continue

            dep.why = []
            for args in [(a, b, a1, b1), (c, d, c1, d1)]:
                if proof.check_coll(args):
                    if len(set(args)) > 2:
                        dep = Dependency("coll", args, None, None)
                        dep.why.append(dep.why_me_or_cache(proof, level))
                else:
                    dep = Dependency("para", args, None, None)
                    dep.why.append(dep.why_me_or_cache(proof, level))

            dep.why += why_equal(ang, ang0)
            break

    elif dep.name == "rconst":
        a, b, c, d, rat0 = dep.args

        val = rat0._val

        for rat in val.neighbors(Ratio):
            if rat == rat0:
                continue
            l1, l2 = rat._l
            s1, s2 = l1._obj, l2._obj
            (a1, b1), (c1, d1) = list(s1.points), list(s2.points)

            if not proof.check_cong([a, b, a1, b1]) or not proof.check_cong(
                [c, d, c1, d1]
            ):
                continue

            dep.why = []
            for args in [(a, b, a1, b1), (c, d, c1, d1)]:
                if len(set(args)) > 2:
                    dep = Dependency("cong", args, None, None)
                    dep.why.append(dep.why_me_or_cache(proof, level))

            dep.why += why_equal(rat, rat0)
            break

    else:
        raise ValueError("Not recognize", dep.name)


def why_eqratio(
    d1: Direction,
    d2: Direction,
    d3: Direction,
    d4: Direction,
    level: int,
) -> list[Dependency]:
    """Why two ratios are equal, returns a Dependency objects."""
    all12 = list(all_ratios(d1, d2, level))
    all34 = list(all_ratios(d3, d4, level))

    min_why = None
    for ang12, d1s, d2s in all12:
        for ang34, d3s, d4s in all34:
            why0 = why_equal(ang12, ang34, level)
            if why0 is None:
                continue
            d1_, d2_ = ang12._l
            d3_, d4_ = ang34._l
            why1 = bfs_backtrack(d1, [d1_], d1s)
            why2 = bfs_backtrack(d2, [d2_], d2s)
            why3 = bfs_backtrack(d3, [d3_], d3s)
            why4 = bfs_backtrack(d4, [d4_], d4s)
            why = why0 + why1 + why2 + why3 + why4
            if min_why is None or len(why) < len(min_why[0]):
                min_why = why, ang12, ang34, why0, why1, why2, why3, why4

    if min_why is None:
        return None

    _, ang12, ang34, why0, why1, why2, why3, why4 = min_why
    d1_, d2_ = ang12._l
    d3_, d4_ = ang34._l

    if d1 == d1_ and d2 == d2_ and d3 == d3_ and d4 == d4_:
        return why0

    (a_, b_), (c_, d_) = d1_._obj.points, d2_._obj.points
    (e_, f_), (g_, h_) = d3_._obj.points, d4_._obj.points
    deps = []
    if why0:
        dep = Dependency("eqratio", [a_, b_, c_, d_, e_, f_, g_, h_], "", level)
        dep.why = why0
        deps.append(dep)

    (a, b), (c, d) = d1._obj.points, d2._obj.points
    (e, f), (g, h) = d3._obj.points, d4._obj.points
    for why, (x, y), (x_, y_) in zip(
        [why1, why2, why3, why4],
        [(a, b), (c, d), (e, f), (g, h)],
        [(a_, b_), (c_, d_), (e_, f_), (g_, h_)],
    ):
        if why:
            dep = Dependency("cong", [x, y, x_, y_], "", level)
            dep.why = why
            deps.append(dep)

    return deps


def why_eqangle(
    d1: Direction,
    d2: Direction,
    d3: Direction,
    d4: Direction,
    level: int,
    verbose: bool = False,
) -> list[Dependency]:
    """Why two angles are equal, returns a Dependency objects."""
    all12 = list(all_angles(d1, d2, level))
    all34 = list(all_angles(d3, d4, level))

    min_why = None
    for ang12, d1s, d2s in all12:
        for ang34, d3s, d4s in all34:
            why0 = why_equal(ang12, ang34, level)
            if why0 is None:
                continue
            d1_, d2_ = ang12._d
            d3_, d4_ = ang34._d
            why1 = bfs_backtrack(d1, [d1_], d1s)
            why2 = bfs_backtrack(d2, [d2_], d2s)
            why3 = bfs_backtrack(d3, [d3_], d3s)
            why4 = bfs_backtrack(d4, [d4_], d4s)
            why = why0 + why1 + why2 + why3 + why4
            if min_why is None or len(why) < len(min_why[0]):
                min_why = why, ang12, ang34, why0, why1, why2, why3, why4

    if min_why is None:
        return None

    _, ang12, ang34, why0, why1, why2, why3, why4 = min_why
    why0 = why_equal(ang12, ang34, level)
    d1_, d2_ = ang12._d
    d3_, d4_ = ang34._d

    if d1 == d1_ and d2 == d2_ and d3 == d3_ and d4 == d4_:
        return (d1_, d2_, d3_, d4_), why0

    (a_, b_), (c_, d_) = d1_._obj.points, d2_._obj.points
    (e_, f_), (g_, h_) = d3_._obj.points, d4_._obj.points
    deps = []
    if why0:
        dep = Dependency("eqangle", [a_, b_, c_, d_, e_, f_, g_, h_], "", None)
        dep.why = why0
        deps.append(dep)

    (a, b), (c, d) = d1._obj.points, d2._obj.points
    (e, f), (g, h) = d3._obj.points, d4._obj.points
    for why, d_xy, (x, y), d_xy_, (x_, y_) in zip(
        [why1, why2, why3, why4],
        [d1, d2, d3, d4],
        [(a, b), (c, d), (e, f), (g, h)],
        [d1_, d2_, d3_, d4_],
        [(a_, b_), (c_, d_), (e_, f_), (g_, h_)],
    ):
        xy, xy_ = d_xy._obj, d_xy_._obj
        if why:
            if xy == xy_:
                name = "collx"
            else:
                name = "para"
            dep = Dependency(name, [x_, y_, x, y], "", None)
            dep.why = why
            deps.append(dep)

    return (d1_, d2_, d3_, d4_), deps


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
    mn: Line,
    proof: "Proof",
    level: int,
) -> list["Dependency"]:
    """Make a-b:c-d==m-n:p-q in case a-b==m-n or c-d==p-q."""
    if ab != mn:
        return
    why = []
    eqname = "para" if isinstance(ab, Line) else "cong"
    colls = [a, b, m, n]
    if len(set(colls)) > 2 and eqname == "para":
        dep = Dependency("collx", colls, None, level)
        dep.why_me(proof, level)
        why += [dep]

    dep = Dependency(eqname, [c, d, p, q], None, level)
    dep.why_me(proof, level)
    why += [dep]
    return why
