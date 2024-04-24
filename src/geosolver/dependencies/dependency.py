from __future__ import annotations
from typing import TYPE_CHECKING


from geosolver.concepts import ConceptName
from geosolver.dependencies.caching import DependencyCache, hashed
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
    is_equal,
    line_of_and_why,
    why_equal,
)
from geosolver.problem import CONSTRUCTION_RULE, Construction


if TYPE_CHECKING:
    from geosolver.symbols_graph import SymbolsGraph
    from geosolver.statement.checker import StatementChecker


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

    def why_me(
        self,
        symbols_graph: "SymbolsGraph",
        statements_checker: "StatementChecker",
        dependency_cache: "DependencyCache",
        level: int,
    ) -> None:
        """Figure out the dependencies predicates of self."""
        why_dependency(self, symbols_graph, statements_checker, dependency_cache, level)

    def why_me_or_cache(
        self,
        symbols_graph: "SymbolsGraph",
        statements_checker: "StatementChecker",
        dependency_cache: "DependencyCache",
        level: int,
    ) -> "Dependency":
        cached_dep = dependency_cache.get_cached(self)
        if cached_dep is not None:
            return cached_dep
        self.why_me(symbols_graph, statements_checker, dependency_cache, level)
        return self

    def hashed(self, rename: bool = False) -> tuple[str, ...]:
        return hashed(self.name, self.args, rename=rename)


def why_dependency(
    dep: "Dependency",
    symbols_graph: "SymbolsGraph",
    statements_checker: "StatementChecker",
    dependency_cache: "DependencyCache",
    level: int,
) -> None:
    cached_me = dependency_cache.get(dep.name, dep.args)
    if cached_me is not None:
        dep.why = cached_me.why
        dep.rule_name = cached_me.rule_name
        return

    if dep.name == ConceptName.PARALLEL.value:
        a, b, c, d = dep.args
        if {a, b} == {c, d}:
            dep.why = []
            return

        ab = symbols_graph.get_line(a, b)
        cd = symbols_graph.get_line(c, d)
        if ab == cd:
            if {a, b} == {c, d}:
                dep.why = []
                dep.rule_name = ""
                return
            dep = Dependency(
                ConceptName.COLLINEAR.value, list({a, b, c, d}), "t??", None
            )
            dep.why = [
                dep.why_me_or_cache(
                    symbols_graph, statements_checker, dependency_cache, level
                )
            ]
            return

        for (x, y), xy in zip([(a, b), (c, d)], [ab, cd]):
            x_, y_ = xy.points
            if {x, y} == {x_, y_}:
                continue
            d = Dependency(ConceptName.COLLINEAR_X.value, [x, y, x_, y_], None, level)
            dep.why += [
                d.why_me_or_cache(
                    symbols_graph, statements_checker, dependency_cache, level
                )
            ]

        whypara = why_equal(ab, cd)
        dep.why += whypara

    elif dep.name == ConceptName.MIDPOINT.value:
        m, a, b = dep.args
        ma = symbols_graph.get_segment(m, a)
        mb = symbols_graph.get_segment(m, b)
        dep = Dependency(
            ConceptName.COLLINEAR.value, [m, a, b], None, None
        ).why_me_or_cache(symbols_graph, statements_checker, dependency_cache, None)
        dep.why = [dep] + why_equal(ma, mb, level)

    elif dep.name == ConceptName.PERPENDICULAR.value:
        a, b, c, d = dep.args
        ab = symbols_graph.get_line(a, b)
        cd = symbols_graph.get_line(c, d)
        for (x, y), xy in zip([(a, b), (c, d)], [ab, cd]):
            x_, y_ = xy.points
            if {x, y} == {x_, y_}:
                continue
            d = Dependency(ConceptName.COLLINEAR_X.value, [x, y, x_, y_], None, level)
            dep.why += [
                d.why_me_or_cache(
                    symbols_graph, statements_checker, dependency_cache, level
                )
            ]

        _, why = why_eqangle(ab._val, cd._val, cd._val, ab._val, level)
        a, b = ab.points
        c, d = cd.points

        if hashed(dep.name, [a, b, c, d]) != dep.hashed():
            d = Dependency(dep.name, [a, b, c, d], None, level)
            d.why = why
            why = [d]

        dep.why += why

    elif dep.name == ConceptName.CONGRUENT.value:
        a, b, c, d = dep.args
        ab = symbols_graph.get_segment(a, b)
        cd = symbols_graph.get_segment(c, d)

        dep.why = why_equal(ab, cd, level)

    elif dep.name == ConceptName.COLLINEAR.value:
        _, why = line_of_and_why(dep.args, level)
        dep.why = why

    elif dep.name == ConceptName.COLLINEAR_X.value:
        if statements_checker.check_coll(dep.args):
            args = list(set(dep.args))
            cached_dep = dependency_cache.get(ConceptName.COLLINEAR.value, args)
            if cached_dep is not None:
                dep.why = [cached_dep]
                dep.rule_name = ""
                return
            _, dep.why = line_of_and_why(args, level)
        else:
            dep.name = ConceptName.PARALLEL.value
            dep.why_me(symbols_graph, statements_checker, dependency_cache, level)

    elif dep.name == ConceptName.CYCLIC.value:
        _, why = circle_of_and_why(dep.args, level)
        dep.why = why

    elif dep.name == ConceptName.CIRCLE.value:
        o, a, b, c = dep.args
        oa = symbols_graph.get_segment(o, a)
        ob = symbols_graph.get_segment(o, b)
        oc = symbols_graph.get_segment(o, c)
        dep.why = why_equal(oa, ob, level) + why_equal(oa, oc, level)

    elif dep.name in [ConceptName.EQANGLE.value, ConceptName.EQANGLE6.value]:
        a, b, c, d, m, n, p, q = dep.args

        ab, why1 = symbols_graph.get_line_thru_pair_why(a, b)
        cd, why2 = symbols_graph.get_line_thru_pair_why(c, d)
        mn, why3 = symbols_graph.get_line_thru_pair_why(m, n)
        pq, why4 = symbols_graph.get_line_thru_pair_why(p, q)

        if ab is None or cd is None or mn is None or pq is None:
            if {a, b} == {m, n}:
                d = Dependency(ConceptName.PARALLEL.value, [c, d, p, q], None, level)
                dep.why = [
                    d.why_me_or_cache(
                        symbols_graph, statements_checker, dependency_cache, level
                    )
                ]
            if {a, b} == {c, d}:
                d = Dependency(ConceptName.PARALLEL.value, [p, q, m, n], None, level)
                dep.why = [
                    d.why_me_or_cache(
                        symbols_graph, statements_checker, dependency_cache, level
                    )
                ]
            if {c, d} == {p, q}:
                d = Dependency(ConceptName.PARALLEL.value, [a, b, m, n], None, level)
                dep.why = [
                    d.why_me_or_cache(
                        symbols_graph, statements_checker, dependency_cache, level
                    )
                ]
            if {p, q} == {m, n}:
                d = Dependency(ConceptName.PARALLEL.value, [a, b, c, d], None, level)
                dep.why = [
                    d.why_me_or_cache(
                        symbols_graph, statements_checker, dependency_cache, level
                    )
                ]
            return

        for (x, y), xy, whyxy in zip(
            [(a, b), (c, d), (m, n), (p, q)],
            [ab, cd, mn, pq],
            [why1, why2, why3, why4],
        ):
            x_, y_ = xy.points
            if {x, y} == {x_, y_}:
                continue
            d = Dependency(ConceptName.COLLINEAR_X.value, [x, y, x_, y_], None, level)
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
                d = Dependency(
                    ConceptName.EQANGLE.value, [a, b, c, d, m, n, p, q], None, level
                )
                d.why = whyeqangle
                whyeqangle = [d]
            dep.why += whyeqangle

        else:
            if (ab == cd and mn == pq) or (ab == mn and cd == pq):
                dep.why += []
            elif ab == mn:
                dep.why += maybe_make_equal_pairs(
                    a,
                    b,
                    c,
                    d,
                    m,
                    n,
                    p,
                    q,
                    ab,
                    mn,
                    symbols_graph,
                    statements_checker,
                    dependency_cache,
                    level,
                )
            elif cd == pq:
                dep.why += maybe_make_equal_pairs(
                    c,
                    d,
                    a,
                    b,
                    p,
                    q,
                    m,
                    n,
                    cd,
                    pq,
                    symbols_graph,
                    statements_checker,
                    dependency_cache,
                    level,
                )
            elif ab == cd:
                dep.why += maybe_make_equal_pairs(
                    a,
                    b,
                    m,
                    n,
                    c,
                    d,
                    p,
                    q,
                    ab,
                    cd,
                    symbols_graph,
                    statements_checker,
                    dependency_cache,
                    level,
                )
            elif mn == pq:
                dep.why += maybe_make_equal_pairs(
                    m,
                    n,
                    a,
                    b,
                    p,
                    q,
                    c,
                    d,
                    mn,
                    pq,
                    symbols_graph,
                    statements_checker,
                    dependency_cache,
                    level,
                )
            elif is_equal(ab, mn) or is_equal(cd, pq):
                dep1 = Dependency(ConceptName.PARALLEL.value, [a, b, m, n], None, level)
                dep1.why_me(symbols_graph, statements_checker, dependency_cache, level)
                dep2 = Dependency(ConceptName.PARALLEL.value, [c, d, p, q], None, level)
                dep2.why_me(symbols_graph, statements_checker, dependency_cache, level)
                dep.why += [dep1, dep2]
            elif is_equal(ab, cd) or is_equal(mn, pq):
                dep1 = Dependency(ConceptName.PARALLEL.value, [a, b, c, d], None, level)
                dep1.why_me(symbols_graph, statements_checker, dependency_cache, level)
                dep2 = Dependency(ConceptName.PARALLEL.value, [m, n, p, q], None, level)
                dep2.why_me(symbols_graph, statements_checker, dependency_cache, level)
                dep.why += [dep1, dep2]
            elif ab._val and cd._val and mn._val and pq._val:
                dep.why = why_eqangle(ab._val, cd._val, mn._val, pq._val, level)

    elif dep.name in [ConceptName.EQRATIO.value, ConceptName.EQRATIO6.value]:
        why_me_eqratio(dep, symbols_graph, statements_checker, dependency_cache, level)
    elif dep.name == ConceptName.EQRATIO3.value:
        a, b, c, d, m, n = dep.args
        dep1 = Dependency(ConceptName.PARALLEL.value, [a, b, c, d], "", level)
        dep1.why_me(symbols_graph, statements_checker, dependency_cache, level)
        dep2 = Dependency(ConceptName.COLLINEAR.value, [m, a, c], "", level)
        dep2.why_me(symbols_graph, statements_checker, dependency_cache, level)
        dep3 = Dependency(ConceptName.COLLINEAR.value, [n, b, d], "", level)
        dep3.why_me(symbols_graph, statements_checker, dependency_cache, level)
        dep.rule_name = "r07"
        dep.why = [dep1, dep2, dep3]

    elif dep.name in [
        ConceptName.DIFFERENT.value,
        ConceptName.NON_PARALLEL.value,
        ConceptName.NON_PERPENDICULAR.value,
        ConceptName.NON_COLLINEAR.value,
        ConceptName.SAMESIDE.value,
    ]:
        dep.why = []

    elif dep.name == ConceptName.SIMILAR_TRIANGLE.value:
        a, b, c, x, y, z = dep.args
        dep1 = Dependency(
            ConceptName.EQANGLE.value, [a, b, a, c, x, y, x, z], "", level
        )
        dep1.why_me(symbols_graph, statements_checker, dependency_cache, level)
        dep2 = Dependency(
            ConceptName.EQANGLE.value, [b, a, b, c, y, x, y, z], "", level
        )
        dep2.why_me(symbols_graph, statements_checker, dependency_cache, level)
        dep.rule_name = "r34"
        dep.why = [dep1, dep2]

    elif dep.name in [
        ConceptName.CONTRI_TRIANGLE.value,
        ConceptName.CONTRI_TRIANGLE_REFLECTED.value,
        ConceptName.CONTRI_TRIANGLE_BOTH.value,
    ]:
        a, b, c, x, y, z = dep.args
        dep1 = Dependency(ConceptName.CONGRUENT.value, [a, b, x, y], "", level)
        dep1.why_me(symbols_graph, statements_checker, dependency_cache, level)
        dep2 = Dependency(ConceptName.CONGRUENT.value, [b, c, y, z], "", level)
        dep2.why_me(symbols_graph, statements_checker, dependency_cache, level)
        dep3 = Dependency(ConceptName.CONGRUENT.value, [c, a, z, x], "", level)
        dep3.why_me(symbols_graph, statements_checker, dependency_cache, level)
        dep.rule_name = "r32"
        dep.why = [dep1, dep2, dep3]

    elif dep.name == ConceptName.IND.value:
        pass

    elif dep.name == ConceptName.CONSTANT_ANGLE.value:
        a, b, c, d, ang0 = dep.args

        measure = ang0._val

        for ang in measure.neighbors(Angle):
            if ang == ang0:
                continue
            d1, d2 = ang._d
            l1, l2 = d1._obj, d2._obj
            (a1, b1), (c1, d1) = l1.points, l2.points

            if not statements_checker.check_para_or_coll(
                [a, b, a1, b1]
            ) or not statements_checker.check_para_or_coll([c, d, c1, d1]):
                continue

            dep.why = []
            for args in [(a, b, a1, b1), (c, d, c1, d1)]:
                if statements_checker.check_coll(args):
                    if len(set(args)) > 2:
                        dep = Dependency(ConceptName.COLLINEAR.value, args, None, None)
                        dep.why.append(
                            dep.why_me_or_cache(
                                symbols_graph,
                                statements_checker,
                                dependency_cache,
                                level,
                            )
                        )
                else:
                    dep = Dependency(ConceptName.PARALLEL.value, args, None, None)
                    dep.why.append(
                        dep.why_me_or_cache(
                            symbols_graph, statements_checker, dependency_cache, level
                        )
                    )

            dep.why += why_equal(ang, ang0)
            break

    elif dep.name == ConceptName.CONSTANT_RATIO.value:
        a, b, c, d, rat0 = dep.args

        val = rat0._val

        for rat in val.neighbors(Ratio):
            if rat == rat0:
                continue
            l1, l2 = rat._l
            s1, s2 = l1._obj, l2._obj
            (a1, b1), (c1, d1) = list(s1.points), list(s2.points)

            if not statements_checker.check_cong(
                [a, b, a1, b1]
            ) or not statements_checker.check_cong([c, d, c1, d1]):
                continue

            dep.why = []
            for args in [(a, b, a1, b1), (c, d, c1, d1)]:
                if len(set(args)) > 2:
                    dep = Dependency(ConceptName.CONGRUENT.value, args, None, None)
                    dep.why.append(
                        dep.why_me_or_cache(
                            symbols_graph, statements_checker, dependency_cache, level
                        )
                    )

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
        dep = Dependency(
            ConceptName.EQRATIO.value, [a_, b_, c_, d_, e_, f_, g_, h_], "", level
        )
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
            dep = Dependency(ConceptName.CONGRUENT.value, [x, y, x_, y_], "", level)
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
        dep = Dependency(
            ConceptName.EQANGLE.value, [a_, b_, c_, d_, e_, f_, g_, h_], "", None
        )
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
                name = ConceptName.COLLINEAR_X.value
            else:
                name = ConceptName.PARALLEL.value
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
    symbols_graph: "SymbolsGraph",
    statements_checker: "StatementChecker",
    dependency_cache: "DependencyCache",
    level: int,
) -> list["Dependency"]:
    """Make a-b:c-d==m-n:p-q in case a-b==m-n or c-d==p-q."""
    if ab != mn:
        return
    why = []
    eqname = (
        ConceptName.PARALLEL.value
        if isinstance(ab, Line)
        else ConceptName.CONGRUENT.value
    )
    colls = [a, b, m, n]
    if len(set(colls)) > 2 and eqname == ConceptName.PARALLEL.value:
        dep = Dependency(ConceptName.COLLINEAR_X.value, colls, None, level)
        dep.why_me(symbols_graph, statements_checker, dependency_cache, level)
        why += [dep]

    dep = Dependency(eqname, [c, d, p, q], None, level)
    dep.why_me(symbols_graph, statements_checker, dependency_cache, level)
    why += [dep]
    return why


def why_me_eqratio(
    dep: "Dependency",
    symbols_graph: "SymbolsGraph",
    statements_checker: "StatementChecker",
    dependency_cache: "DependencyCache",
    level: int,
):
    a, b, c, d, m, n, p, q = dep.args
    ab = symbols_graph.get_segment(a, b)
    cd = symbols_graph.get_segment(c, d)
    mn = symbols_graph.get_segment(m, n)
    pq = symbols_graph.get_segment(p, q)

    if ab is None or cd is None or mn is None or pq is None:
        if {a, b} == {m, n}:
            d = Dependency(ConceptName.CONGRUENT.value, [c, d, p, q], None, level)
            dep.why = [
                d.why_me_or_cache(
                    symbols_graph, statements_checker, dependency_cache, level
                )
            ]
        if {a, b} == {c, d}:
            d = Dependency(ConceptName.CONGRUENT.value, [p, q, m, n], None, level)
            dep.why = [
                d.why_me_or_cache(
                    symbols_graph, statements_checker, dependency_cache, level
                )
            ]
        if {c, d} == {p, q}:
            d = Dependency(ConceptName.CONGRUENT.value, [a, b, m, n], None, level)
            dep.why = [
                d.why_me_or_cache(
                    symbols_graph, statements_checker, dependency_cache, level
                )
            ]
        if {p, q} == {m, n}:
            d = Dependency(ConceptName.CONGRUENT.value, [a, b, c, d], None, level)
            dep.why = [
                d.why_me_or_cache(
                    symbols_graph, statements_checker, dependency_cache, level
                )
            ]
        return

    if ab._val and cd._val and mn._val and pq._val:
        dep.why = why_eqratio(ab._val, cd._val, mn._val, pq._val, level)

    if dep.why is None:
        dep.why = []
        if (ab == cd and mn == pq) or (ab == mn and cd == pq):
            dep.why = []
        elif ab == mn:
            points = [a, b, c, d, m, n, p, q]
            lines = [ab, mn]
            dep.why += maybe_make_equal_pairs(
                *points,
                *lines,
                symbols_graph,
                statements_checker,
                dependency_cache,
                level,
            )
        elif cd == pq:
            points = [c, d, a, b, p, q, m, n]
            lines = [cd, pq]
            dep.why += maybe_make_equal_pairs(
                *points,
                *lines,
                symbols_graph,
                statements_checker,
                dependency_cache,
                level,
            )
        elif ab == cd:
            points = [a, b, m, n, c, d, p, q]
            lines = [ab, cd]
            dep.why += maybe_make_equal_pairs(
                *points,
                *lines,
                symbols_graph,
                statements_checker,
                dependency_cache,
                level,
            )
        elif mn == pq:
            points = [m, n, a, b, p, q, c, d]
            lines = [mn, pq]
            dep.why += maybe_make_equal_pairs(
                *points,
                *lines,
                symbols_graph,
                statements_checker,
                dependency_cache,
                level,
            )
        elif is_equal(ab, mn) or is_equal(cd, pq):
            dep1 = Dependency(ConceptName.CONGRUENT.value, [a, b, m, n], None, level)
            dep1.why_me(symbols_graph, statements_checker, dependency_cache, level)
            dep2 = Dependency(ConceptName.CONGRUENT.value, [c, d, p, q], None, level)
            dep2.why_me(symbols_graph, statements_checker, dependency_cache, level)
            dep.why += [dep1, dep2]
        elif is_equal(ab, cd) or is_equal(mn, pq):
            dep1 = Dependency(ConceptName.CONGRUENT.value, [a, b, c, d], None, level)
            dep1.why_me(symbols_graph, statements_checker, dependency_cache, level)
            dep2 = Dependency(ConceptName.CONGRUENT.value, [m, n, p, q], None, level)
            dep2.why_me(symbols_graph, statements_checker, dependency_cache, level)
            dep.why += [dep1, dep2]
        elif ab._val and cd._val and mn._val and pq._val:
            dep.why = why_eqangle(ab._val, cd._val, mn._val, pq._val, level)
