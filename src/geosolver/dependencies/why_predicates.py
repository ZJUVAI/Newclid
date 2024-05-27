from typing import TYPE_CHECKING, Optional, TypeVar
from geosolver.dependencies.caching import DependencyCache, hashed

from geosolver.dependencies.dependency import Dependency
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
from geosolver.predicates import Predicate


if TYPE_CHECKING:
    from geosolver.statement.checker import StatementChecker
    from geosolver.symbols_graph import SymbolsGraph


def why_dependency(
    dependency: "Dependency",
    symbols_graph: "SymbolsGraph",
    statements_checker: "StatementChecker",
    dependency_cache: "DependencyCache",
    level: int,
) -> Dependency:
    cached_me = dependency_cache.get(dependency.name, dependency.args)
    if cached_me is not None:
        dependency.why = cached_me.why
        dependency.rule_name = cached_me.rule_name
        return dependency

    if dependency.name == Predicate.IND.value:
        return dependency

    predicate = Predicate(dependency.name)
    why_predicate = PREDICATE_TO_WHY[predicate]
    why_predicate(
        dependency, symbols_graph, statements_checker, dependency_cache, level
    )
    return dependency


def _why_para(
    dep: "Dependency",
    symbols_graph: "SymbolsGraph",
    statements_checker: "StatementChecker",
    dependency_cache: "DependencyCache",
    level: int,
):
    a, b, c, d = dep.args
    if {a, b} == {c, d}:
        return []

    ab = symbols_graph.get_line(a, b)
    cd = symbols_graph.get_line(c, d)
    if ab == cd:
        if {a, b} == {c, d}:
            dep.why = []
            dep.rule_name = ""
            return
        dep = Dependency(Predicate.COLLINEAR.value, list({a, b, c, d}), "t??", None)
        dep.why = [
            why_dependency(
                dep, symbols_graph, statements_checker, dependency_cache, level
            )
        ]
        return

    for (x, y), xy in zip([(a, b), (c, d)], [ab, cd]):
        x_, y_ = xy.points
        if {x, y} == {x_, y_}:
            continue
        d = Dependency(Predicate.COLLINEAR_X.value, [x, y, x_, y_], None, level)
        dep.why += [
            why_dependency(
                d, symbols_graph, statements_checker, dependency_cache, level
            )
        ]

    whypara = why_equal(ab, cd)
    dep.why += whypara


def _why_midpoint(
    dep: "Dependency",
    symbols_graph: "SymbolsGraph",
    statements_checker: "StatementChecker",
    dependency_cache: "DependencyCache",
    level: int,
):
    m, a, b = dep.args
    ma = symbols_graph.get_segment(m, a)
    mb = symbols_graph.get_segment(m, b)
    dep = Dependency(Predicate.COLLINEAR.value, [m, a, b], None, None)
    dep = why_dependency(dep, symbols_graph, statements_checker, dependency_cache, None)
    dep.why = [dep] + why_equal(ma, mb, level)


def _why_perp(
    dep: "Dependency",
    symbols_graph: "SymbolsGraph",
    statements_checker: "StatementChecker",
    dependency_cache: "DependencyCache",
    level: int,
):
    a, b, c, d = dep.args
    ab = symbols_graph.get_line(a, b)
    cd = symbols_graph.get_line(c, d)
    for (x, y), xy in zip([(a, b), (c, d)], [ab, cd]):
        x_, y_ = xy.points
        if {x, y} == {x_, y_}:
            continue
        d = Dependency(Predicate.COLLINEAR_X.value, [x, y, x_, y_], None, level)
        dep.why += [
            why_dependency(
                d, symbols_graph, statements_checker, dependency_cache, level
            )
        ]

    _, why = _why_eqangle_directions(ab._val, cd._val, cd._val, ab._val, level)
    a, b = ab.points
    c, d = cd.points

    if hashed(dep.name, [a, b, c, d]) != dep.hashed():
        d = Dependency(dep.name, [a, b, c, d], None, level)
        d.why = why
        why = [d]

    dep.why += why


def _why_cong(
    dep: "Dependency",
    symbols_graph: "SymbolsGraph",
    statements_checker: "StatementChecker",
    dependency_cache: "DependencyCache",
    level: int,
):
    a, b, c, d = dep.args
    ab = symbols_graph.get_segment(a, b)
    cd = symbols_graph.get_segment(c, d)

    dep.why = why_equal(ab, cd, level)


def _why_coll(
    dep: "Dependency",
    symbols_graph: "SymbolsGraph",
    statements_checker: "StatementChecker",
    dependency_cache: "DependencyCache",
    level: int,
):
    _, why = line_of_and_why(dep.args, level)
    dep.why = why


def _why_collx(
    dep: "Dependency",
    symbols_graph: "SymbolsGraph",
    statements_checker: "StatementChecker",
    dependency_cache: "DependencyCache",
    level: int,
):
    if statements_checker.check_coll(dep.args):
        args = list(set(dep.args))
        cached_dep = dependency_cache.get(Predicate.COLLINEAR.value, args)
        if cached_dep is not None:
            dep.why = [cached_dep]
            dep.rule_name = ""
            return
        _, dep.why = line_of_and_why(args, level)
        return

    dep.name = Predicate.PARALLEL.value
    why_dependency(dep, symbols_graph, statements_checker, dependency_cache, level)


def _why_cyclic(
    dep: "Dependency",
    symbols_graph: "SymbolsGraph",
    statements_checker: "StatementChecker",
    dependency_cache: "DependencyCache",
    level: int,
):
    _, why = circle_of_and_why(dep.args, level)
    dep.why = why


def _why_circle(
    dep: "Dependency",
    symbols_graph: "SymbolsGraph",
    statements_checker: "StatementChecker",
    dependency_cache: "DependencyCache",
    level: int,
):
    o, a, b, c = dep.args
    oa = symbols_graph.get_segment(o, a)
    ob = symbols_graph.get_segment(o, b)
    oc = symbols_graph.get_segment(o, c)
    dep.why = why_equal(oa, ob, level) + why_equal(oa, oc, level)


def _why_eqangle(
    dep: "Dependency",
    symbols_graph: "SymbolsGraph",
    statements_checker: "StatementChecker",
    dependency_cache: "DependencyCache",
    level: int,
):
    a, b, c, d, m, n, p, q = dep.args

    ab, why1 = symbols_graph.get_line_thru_pair_why(a, b)
    cd, why2 = symbols_graph.get_line_thru_pair_why(c, d)
    mn, why3 = symbols_graph.get_line_thru_pair_why(m, n)
    pq, why4 = symbols_graph.get_line_thru_pair_why(p, q)

    if ab is None or cd is None or mn is None or pq is None:
        para_points = None
        if {a, b} == {m, n}:
            para_points = [c, d, p, q]
        elif {a, b} == {c, d}:
            para_points = [p, q, m, n]
        elif {c, d} == {p, q}:
            para_points = [a, b, m, n]
        elif {p, q} == {m, n}:
            para_points = [a, b, c, d]
        d = Dependency(Predicate.PARALLEL.value, para_points, None, level)
        dep.why = [
            why_dependency(
                d, symbols_graph, statements_checker, dependency_cache, level
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
        d = Dependency(Predicate.COLLINEAR_X.value, [x, y, x_, y_], None, level)
        d.why = whyxy
        dep.why += [d]

    a, b = ab.points
    c, d = cd.points
    m, n = mn.points
    p, q = pq.points
    diff = hashed(dep.name, [a, b, c, d, m, n, p, q]) != dep.hashed()

    whyeqangle = None
    if ab._val and cd._val and mn._val and pq._val:
        whyeqangle = _why_eqangle_directions(ab._val, cd._val, mn._val, pq._val, level)

    if whyeqangle:
        (dab, dcd, dmn, dpq), whyeqangle = whyeqangle
        if diff:
            d = Dependency(
                Predicate.EQANGLE.value, [a, b, c, d, m, n, p, q], None, level
            )
            d.why = whyeqangle
            whyeqangle = [d]
        dep.why += whyeqangle
        return

    if (ab == cd and mn == pq) or (ab == mn and cd == pq):
        dep.why += []
        return

    equal_pair_points, equal_pair_lines = _find_equal_pair(
        a, b, c, d, m, n, p, q, ab, cd, mn, pq
    )
    if equal_pair_points is not None and equal_pair_lines is not None:
        dep.why += _maybe_make_equal_pairs(
            *equal_pair_points,
            *equal_pair_lines,
            symbols_graph,
            statements_checker,
            dependency_cache,
            level,
        )
        return

    if is_equal(ab, mn) or is_equal(cd, pq):
        dep1 = Dependency(Predicate.PARALLEL.value, [a, b, m, n], None, level)
        why_dependency(dep1, symbols_graph, statements_checker, dependency_cache, level)
        dep2 = Dependency(Predicate.PARALLEL.value, [c, d, p, q], None, level)
        why_dependency(dep2, symbols_graph, statements_checker, dependency_cache, level)
        dep.why += [dep1, dep2]
    elif is_equal(ab, cd) or is_equal(mn, pq):
        dep1 = Dependency(Predicate.PARALLEL.value, [a, b, c, d], None, level)
        why_dependency(dep1, symbols_graph, statements_checker, dependency_cache, level)
        dep2 = Dependency(Predicate.PARALLEL.value, [m, n, p, q], None, level)
        why_dependency(dep2, symbols_graph, statements_checker, dependency_cache, level)
        dep.why += [dep1, dep2]
    elif ab._val and cd._val and mn._val and pq._val:
        dep.why = _why_eqangle_directions(ab._val, cd._val, mn._val, pq._val, level)


def _why_eqratio(
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
        congruent_points = None
        if {a, b} == {m, n}:
            congruent_points = [c, d, p, q]
        elif {a, b} == {c, d}:
            congruent_points = [p, q, m, n]
        elif {c, d} == {p, q}:
            congruent_points = [a, b, m, n]
        elif {p, q} == {m, n}:
            congruent_points = [a, b, c, d]

        if congruent_points is not None:
            d = Dependency(Predicate.CONGRUENT.value, congruent_points, None, level)
            dep.why = [
                why_dependency(
                    d, symbols_graph, statements_checker, dependency_cache, level
                )
            ]
        return

    if ab._val and cd._val and mn._val and pq._val:
        dep.why = _why_eqratio_directions(ab._val, cd._val, mn._val, pq._val, level)

    if dep.why is None:
        dep.why = []
        if (ab == cd and mn == pq) or (ab == mn and cd == pq):
            dep.why = []
            return

        equal_pair_points, equal_pair_lines = _find_equal_pair(
            a, b, c, d, m, n, p, q, ab, cd, mn, pq
        )
        if equal_pair_points is not None:
            dep.why += _maybe_make_equal_pairs(
                *equal_pair_points,
                *equal_pair_lines,
                symbols_graph,
                statements_checker,
                dependency_cache,
                level,
            )
            return

        if is_equal(ab, mn) or is_equal(cd, pq):
            dep1 = Dependency(Predicate.CONGRUENT.value, [a, b, m, n], None, level)
            why_dependency(
                dep1, symbols_graph, statements_checker, dependency_cache, level
            )
            dep2 = Dependency(Predicate.CONGRUENT.value, [c, d, p, q], None, level)
            why_dependency(
                dep2, symbols_graph, statements_checker, dependency_cache, level
            )
            dep.why += [dep1, dep2]
        elif is_equal(ab, cd) or is_equal(mn, pq):
            dep1 = Dependency(Predicate.CONGRUENT.value, [a, b, c, d], None, level)
            why_dependency(
                dep1, symbols_graph, statements_checker, dependency_cache, level
            )
            dep2 = Dependency(Predicate.CONGRUENT.value, [m, n, p, q], None, level)
            why_dependency(
                dep2, symbols_graph, statements_checker, dependency_cache, level
            )
            dep.why += [dep1, dep2]
        elif ab._val and cd._val and mn._val and pq._val:
            dep.why = _why_eqangle_directions(ab._val, cd._val, mn._val, pq._val, level)


def _why_eqratio3(
    dep: "Dependency",
    symbols_graph: "SymbolsGraph",
    statements_checker: "StatementChecker",
    dependency_cache: "DependencyCache",
    level: int,
):
    a, b, c, d, m, n = dep.args
    dep1 = Dependency(Predicate.PARALLEL.value, [a, b, c, d], "", level)
    why_dependency(dep1, symbols_graph, statements_checker, dependency_cache, level)
    dep2 = Dependency(Predicate.COLLINEAR.value, [m, a, c], "", level)
    why_dependency(dep2, symbols_graph, statements_checker, dependency_cache, level)
    dep3 = Dependency(Predicate.COLLINEAR.value, [n, b, d], "", level)
    why_dependency(dep3, symbols_graph, statements_checker, dependency_cache, level)
    dep.rule_name = "r07"
    dep.why = [dep1, dep2, dep3]


def _why_simtri(
    dep: "Dependency",
    symbols_graph: "SymbolsGraph",
    statements_checker: "StatementChecker",
    dependency_cache: "DependencyCache",
    level: int,
):
    a, b, c, x, y, z = dep.args
    dep1 = Dependency(Predicate.EQANGLE.value, [a, b, a, c, x, y, x, z], "", level)
    why_dependency(dep1, symbols_graph, statements_checker, dependency_cache, level)
    dep2 = Dependency(Predicate.EQANGLE.value, [b, a, b, c, y, x, y, z], "", level)
    why_dependency(dep2, symbols_graph, statements_checker, dependency_cache, level)
    dep.rule_name = "r34"
    dep.why = [dep1, dep2]


def _why_simtri_both(
    dep: "Dependency",
    symbols_graph: "SymbolsGraph",
    statements_checker: "StatementChecker",
    dependency_cache: "DependencyCache",
    level: int,
):
    a, b, c, p, q, r = dep.args
    dep1 = Dependency(Predicate.EQRATIO.value, [b, a, b, c, q, p, q, r], "", level)
    why_dependency(dep1, symbols_graph, statements_checker, dependency_cache, level)
    dep2 = Dependency(Predicate.EQRATIO.value, [c, a, c, b, r, p, r, q], "", level)
    why_dependency(dep2, symbols_graph, statements_checker, dependency_cache, level)
    dep.rule_name = "r38"
    dep.why = [dep1, dep2]


def _why_contri(
    dep: "Dependency",
    symbols_graph: "SymbolsGraph",
    statements_checker: "StatementChecker",
    dependency_cache: "DependencyCache",
    level: int,
):
    a, b, c, x, y, z = dep.args
    dep1 = Dependency(Predicate.EQANGLE.value, [b, a, b, c, y, x, y, z], "", level)
    why_dependency(dep1, symbols_graph, statements_checker, dependency_cache, level)
    dep2 = Dependency(Predicate.EQANGLE.value, [c, a, c, b, z, x, z, y], "", level)
    why_dependency(dep2, symbols_graph, statements_checker, dependency_cache, level)
    dep3 = Dependency(Predicate.CONGRUENT.value, [a, b, x, y], "", level)
    why_dependency(dep3, symbols_graph, statements_checker, dependency_cache, level)
    dep.rule_name = "r36"
    dep.why = [dep1, dep2, dep3]


def why_contri_2(
    dep: "Dependency",
    symbols_graph: "SymbolsGraph",
    statements_checker: "StatementChecker",
    dependency_cache: "DependencyCache",
    level: int,
):
    a, b, c, x, y, z = dep.args
    dep1 = Dependency(Predicate.EQANGLE.value, [b, a, b, c, y, z, y, x], "", level)
    why_dependency(dep1, symbols_graph, statements_checker, dependency_cache, level)
    dep2 = Dependency(Predicate.EQANGLE.value, [c, a, c, b, z, y, z, x], "", level)
    why_dependency(dep2, symbols_graph, statements_checker, dependency_cache, level)
    dep3 = Dependency(Predicate.CONGRUENT.value, [a, b, x, y], "", level)
    why_dependency(dep3, symbols_graph, statements_checker, dependency_cache, level)
    dep.rule_name = "r37"
    dep.why = [dep1, dep2, dep3]


def _why_contri_both(
    dep: "Dependency",
    symbols_graph: "SymbolsGraph",
    statements_checker: "StatementChecker",
    dependency_cache: "DependencyCache",
    level: int,
):
    a, b, c, x, y, z = dep.args
    dep1 = Dependency(Predicate.CONGRUENT.value, [a, b, x, y], "", level)
    why_dependency(dep1, symbols_graph, statements_checker, dependency_cache, level)
    dep2 = Dependency(Predicate.CONGRUENT.value, [b, c, y, z], "", level)
    why_dependency(dep2, symbols_graph, statements_checker, dependency_cache, level)
    dep3 = Dependency(Predicate.CONGRUENT.value, [c, a, z, x], "", level)
    why_dependency(dep3, symbols_graph, statements_checker, dependency_cache, level)
    dep.rule_name = "r32"
    dep.why = [dep1, dep2, dep3]


def _why_aconst(
    dep: "Dependency",
    symbols_graph: "SymbolsGraph",
    statements_checker: "StatementChecker",
    dependency_cache: "DependencyCache",
    level: int,
):
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
                    dep = Dependency(Predicate.COLLINEAR.value, args, None, None)
                    dep.why.append(
                        why_dependency(
                            dep,
                            symbols_graph,
                            statements_checker,
                            dependency_cache,
                            level,
                        )
                    )
            else:
                dep = Dependency(Predicate.PARALLEL.value, args, None, None)
                dep.why.append(
                    why_dependency(
                        dep, symbols_graph, statements_checker, dependency_cache, level
                    )
                )

        dep.why += why_equal(ang, ang0)
        return


def _why_rconst(
    dep: "Dependency",
    symbols_graph: "SymbolsGraph",
    statements_checker: "StatementChecker",
    dependency_cache: "DependencyCache",
    level: int,
):
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
                dep = Dependency(Predicate.CONGRUENT.value, args, None, None)
                dep.why.append(
                    why_dependency(
                        dep, symbols_graph, statements_checker, dependency_cache, level
                    )
                )

        dep.why += why_equal(rat, rat0)
        return


def _why_numerical(
    dep: "Dependency",
    symbols_graph: "SymbolsGraph",
    statements_checker: "StatementChecker",
    dependency_cache: "DependencyCache",
    level: int,
):
    dep.why = []


PREDICATE_TO_WHY = {
    Predicate.PARALLEL: _why_para,
    Predicate.MIDPOINT: _why_midpoint,
    Predicate.PERPENDICULAR: _why_perp,
    Predicate.CONGRUENT: _why_cong,
    Predicate.COLLINEAR: _why_coll,
    Predicate.COLLINEAR_X: _why_collx,
    Predicate.CYCLIC: _why_cyclic,
    Predicate.CIRCLE: _why_circle,
    Predicate.EQANGLE: _why_eqangle,
    Predicate.EQANGLE6: _why_eqangle,
    Predicate.EQRATIO: _why_eqratio,
    Predicate.EQRATIO6: _why_eqratio,
    Predicate.EQRATIO3: _why_eqratio3,
    Predicate.SIMILAR_TRIANGLE: _why_simtri,
    Predicate.SIMILAR_TRIANGLE_BOTH: _why_simtri_both,
    Predicate.CONTRI_TRIANGLE: _why_contri,
    Predicate.CONTRI_TRIANGLE_REFLECTED: why_contri_2,
    Predicate.CONTRI_TRIANGLE_BOTH: _why_contri_both,
    Predicate.CONSTANT_ANGLE: _why_aconst,
    Predicate.CONSTANT_RATIO: _why_rconst,
    Predicate.DIFFERENT: _why_numerical,
    Predicate.NON_PARALLEL: _why_numerical,
    Predicate.NON_PERPENDICULAR: _why_numerical,
    Predicate.NON_COLLINEAR: _why_numerical,
    Predicate.SAMESIDE: _why_numerical,
}


P = TypeVar("P")
L = TypeVar("L")


def _find_equal_pair(
    a: P, b: P, c: P, d: P, m: P, n: P, p: P, q: P, ab: L, cd: L, mn: L, pq: L
) -> tuple[Optional[list[P]], Optional[list[L]]]:
    points = None
    lines = None
    if ab == mn:
        points = [a, b, c, d, m, n, p, q]
        lines = [ab, mn]
    elif cd == pq:
        points = [c, d, a, b, p, q, m, n]
        lines = [cd, pq]
    elif ab == cd:
        points = [a, b, m, n, c, d, p, q]
        lines = [ab, cd]
    elif mn == pq:
        points = [m, n, a, b, p, q, c, d]
        lines = [mn, pq]

    return points, lines


def _maybe_make_equal_pairs(
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
        Predicate.PARALLEL.value if isinstance(ab, Line) else Predicate.CONGRUENT.value
    )
    colls = [a, b, m, n]
    if len(set(colls)) > 2 and eqname == Predicate.PARALLEL.value:
        dep = Dependency(Predicate.COLLINEAR_X.value, colls, None, level)
        why_dependency(dep, symbols_graph, statements_checker, dependency_cache, level)
        why += [dep]

    dep = Dependency(eqname, [c, d, p, q], None, level)
    why_dependency(dep, symbols_graph, statements_checker, dependency_cache, level)
    why += [dep]
    return why


def _why_eqangle_directions(
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
            Predicate.EQANGLE.value, [a_, b_, c_, d_, e_, f_, g_, h_], "", None
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
                name = Predicate.COLLINEAR_X.value
            else:
                name = Predicate.PARALLEL.value
            dep = Dependency(name, [x_, y_, x, y], "", None)
            dep.why = why
            deps.append(dep)

    return (d1_, d2_, d3_, d4_), deps


def _why_eqratio_directions(
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
            Predicate.EQRATIO.value, [a_, b_, c_, d_, e_, f_, g_, h_], "", level
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
            dep = Dependency(Predicate.CONGRUENT.value, [x, y, x_, y_], "", level)
            dep.why = why
            deps.append(dep)

    return deps
