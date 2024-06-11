from __future__ import annotations
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Callable, Optional, TypeVar


from geosolver.statements.statement import Statement
from geosolver.dependencies.caching import DependencyCache

from geosolver.dependencies.dependency import Dependency, Reason
from geosolver.geometry import (
    Angle,
    Circle,
    Direction,
    Line,
    Node,
    Point,
    Ratio,
    all_angles,
    all_ratios,
    bfs_backtrack,
    is_equal,
)
from geosolver.predicates import Predicate


if TYPE_CHECKING:
    from geosolver.statements.checker import StatementChecker
    from geosolver.symbols_graph import SymbolsGraph
    from geosolver.dependencies.why_graph import WhyHyperGraph


def why_dependency(
    statements_graph: "WhyHyperGraph", dependency: "Dependency", level: int
) -> list[Dependency]:
    cached_me = statements_graph.dependency_cache.get(dependency.statement)
    if cached_me is not None:
        dependency.reason = cached_me.reason
        return cached_me.why

    predicate = Predicate(dependency.statement.name)
    if predicate is Predicate.IND:
        return []

    why_predicate = PREDICATE_TO_WHY[predicate]
    return why_predicate(statements_graph, dependency, level)


def _why_equal(x: Node, y: Node, level: int = None) -> list[Any]:
    if x == y:
        return []
    if not x._val or not y._val:
        return None
    if x._val == y._val:
        return []
    return x._val.why_equal([y._val], level)


def _why_para(
    statements_graph: "WhyHyperGraph", dep: "Dependency", level: int
) -> list[Dependency]:
    a, b, c, d = dep.statement.args

    if {a, b} == {c, d}:
        return []

    ab = statements_graph.symbols_graph.get_line(a, b)
    cd = statements_graph.symbols_graph.get_line(c, d)
    if ab == cd:
        if {a, b} == {c, d}:
            return []

        coll = Statement(Predicate.COLLINEAR, list({a, b, c, d}))
        coll_dep = Dependency(coll, Reason("t??"), None)
        coll_dep.why = _why_coll(statements_graph, coll_dep, level)
        return [coll_dep]

    whypara = []
    for (x, y), xy in zip([(a, b), (c, d)], [ab, cd]):
        x_, y_ = xy.points
        if {x, y} == {x_, y_}:
            continue
        collx = Statement(Predicate.COLLINEAR_X, [x, y, x_, y_])
        collx_dep = Dependency(collx, None, level)
        collx_dep.why = _why_collx(statements_graph, collx_dep, level)
        whypara.append(collx_dep)

    whypara += _why_equal(ab, cd)
    return whypara


def _why_midpoint(
    statements_graph: "WhyHyperGraph", dep: "Dependency", level: int
) -> list[Dependency]:
    m, a, b = dep.statement.args
    ma = statements_graph.symbols_graph.get_segment(m, a)
    mb = statements_graph.symbols_graph.get_segment(m, b)
    coll = Statement(Predicate.COLLINEAR, [m, a, b])
    coll_dep = Dependency(coll, None, None)
    coll_dep.why = _why_coll(statements_graph, coll_dep, None)
    return [coll_dep] + _why_equal(ma, mb, level)


def _why_perp(
    statements_graph: "WhyHyperGraph", dep: "Dependency", level: int
) -> list[Dependency]:
    a, b, c, d = dep.statement.args
    ab = statements_graph.symbols_graph.get_line(a, b)
    cd = statements_graph.symbols_graph.get_line(c, d)

    why_perp = []
    for (x, y), xy in zip([(a, b), (c, d)], [ab, cd]):
        x_, y_ = xy.points
        if {x, y} == {x_, y_}:
            continue
        collx = Statement(Predicate.COLLINEAR_X, [x, y, x_, y_])
        collx_dep = Dependency(collx, None, level)
        collx_dep.why = _why_collx(statements_graph, collx_dep, level)
        why_perp.append(collx_dep)

    _, why_eqangle = _why_eqangle_directions(ab._val, cd._val, cd._val, ab._val, level)
    a, b = ab.points
    c, d = cd.points

    perp_repr = Statement(dep.statement.name, [a, b, c, d])
    if perp_repr.hash_tuple != dep.statement.hash_tuple:
        repr_dep = Dependency(perp_repr, None, level)
        repr_dep.why = why_eqangle
        why_eqangle = [repr_dep]

    why_perp += why_eqangle
    return why_perp


def _why_cong(
    statements_graph: "WhyHyperGraph", dep: "Dependency", level: int
) -> list[Dependency]:
    a, b, c, d = dep.statement.args
    ab = statements_graph.symbols_graph.get_segment(a, b)
    cd = statements_graph.symbols_graph.get_segment(c, d)
    return _why_equal(ab, cd, level)


def _why_coll(
    statements_graph: "WhyHyperGraph", dep: "Dependency", level: int
) -> list[Dependency]:
    _, why = _line_of_and_why(dep.statement.args, level)
    return why


def _why_collx(
    statements_graph: "WhyHyperGraph", dep: "Dependency", level: int
) -> list[Dependency]:
    if statements_graph.statements_checker.check_coll(dep.statement.args):
        args = list(set(dep.statement.args))
        coll = Statement(Predicate.COLLINEAR, args)
        cached_dep = statements_graph.dependency_cache.get(coll)
        if cached_dep is not None:
            return [cached_dep]
        _, why = _line_of_and_why(args, level)
        return why

    para = Statement(Predicate.PARALLEL, dep.statement.args)
    para_dep = Dependency(para, dep.reason, dep.level)
    return _why_para(statements_graph, para_dep, statements_graph, level)


def _line_of_and_why(
    points: list[Point], level: Optional[int] = None
) -> tuple[Optional[Line], Optional[list[Dependency]]]:
    """Why points are collinear."""
    for l0 in _get_lines_thru_all(*points):
        for line in l0.equivs():
            if all([p in line.edge_graph for p in points]):
                x, y = line.points
                colls = list({x, y} | set(points))
                # if len(colls) < 3:
                #   return l, []
                why = line.why_coll(colls, level)
                if why is not None:
                    return line, why

    return None, None


def _get_lines_thru_all(*points: Point) -> list[Line]:
    line2count = defaultdict(lambda: 0)
    points = set(points)
    for p in points:
        for line_neighbor in p.neighbors(Line):
            line2count[line_neighbor] += 1
    return [line for line, count in line2count.items() if count == len(points)]


def _why_cyclic(
    statements_graph: "WhyHyperGraph", dep: "Dependency", level: int
) -> list[Dependency]:
    _, why = _circle_of_and_why(dep.statement.args, level)
    return why


def _circle_of_and_why(
    points: list[Point], level: int = None
) -> tuple[Optional[Circle], Optional[list[Dependency]]]:
    """Why points are concyclic."""
    for c0 in _get_circles_thru_all(*points):
        for c in c0.equivs():
            if all([p in c.edge_graph for p in points]):
                cycls = list(set(points))
                why = c.why_cyclic(cycls, level)
                if why is not None:
                    return c, why

    return None, None


def _get_circles_thru_all(*points: list[Point]) -> list[Circle]:
    circle2count = defaultdict(lambda: 0)
    points = set(points)
    for p in points:
        for c in p.neighbors(Circle):
            circle2count[c] += 1
    return [c for c, count in circle2count.items() if count == len(points)]


def _why_circle(
    statements_graph: "WhyHyperGraph", dep: "Dependency", level: int
) -> list[Dependency]:
    o, a, b, c = dep.statement.args
    oa = statements_graph.symbols_graph.get_segment(o, a)
    ob = statements_graph.symbols_graph.get_segment(o, b)
    oc = statements_graph.symbols_graph.get_segment(o, c)
    return _why_equal(oa, ob, level) + _why_equal(oa, oc, level)


def _why_eqangle(
    statements_graph: "WhyHyperGraph", dep: "Dependency", level: int
) -> list[Dependency]:
    a, b, c, d, m, n, p, q = dep.statement.args

    ab, why1 = statements_graph.symbols_graph.get_line_thru_pair_why(a, b)
    cd, why2 = statements_graph.symbols_graph.get_line_thru_pair_why(c, d)
    mn, why3 = statements_graph.symbols_graph.get_line_thru_pair_why(m, n)
    pq, why4 = statements_graph.symbols_graph.get_line_thru_pair_why(p, q)

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
        para = Statement(Predicate.PARALLEL, para_points)
        para_dep = Dependency(para, None, level)
        para_dep.why = _why_para(para_dep, statements_graph, level)
        return [para_dep]

    why_eqangle = []
    for (x, y), xy, whyxy in zip(
        [(a, b), (c, d), (m, n), (p, q)],
        [ab, cd, mn, pq],
        [why1, why2, why3, why4],
    ):
        x_, y_ = xy.points
        if {x, y} == {x_, y_}:
            continue
        collx = Statement(Predicate.COLLINEAR_X, [x, y, x_, y_])
        collx_dep = Dependency(collx, None, level)
        collx_dep.why = whyxy
        why_eqangle.append(collx_dep)

    a, b = ab.points
    c, d = cd.points
    m, n = mn.points
    p, q = pq.points

    representent_statement = Statement(dep.statement.name, [a, b, c, d, m, n, p, q])
    different_from_repr = representent_statement.hash_tuple != dep.statement.hash_tuple

    why_eqangle_values = None
    if ab._val and cd._val and mn._val and pq._val:
        why_eqangle_values = _why_eqangle_directions(
            ab._val, cd._val, mn._val, pq._val, level
        )

    if why_eqangle_values:
        (dab, dcd, dmn, dpq), why_eqangle_values = why_eqangle_values
        if different_from_repr:
            eqangle = Statement(Predicate.EQANGLE, [a, b, c, d, m, n, p, q])
            eqangle_dep = Dependency(eqangle, None, level)
            eqangle_dep.why = why_eqangle_values
            why_eqangle_values = [eqangle_dep]
        return why_eqangle + why_eqangle_values

    if (ab == cd and mn == pq) or (ab == mn and cd == pq):
        return why_eqangle

    equal_pair_points, equal_pair_lines = _find_equal_pair(
        a, b, c, d, m, n, p, q, ab, cd, mn, pq
    )
    if equal_pair_points is not None and equal_pair_lines is not None:
        why_eqangle += _maybe_make_equal_pairs(
            statements_graph, *equal_pair_points, *equal_pair_lines, level
        )
        return why_eqangle

    if is_equal(ab, mn) or is_equal(cd, pq):
        para1 = Statement(Predicate.PARALLEL, [a, b, m, n])
        dep1 = Dependency(para1, None, level)
        dep1.why = _why_para(dep1, statements_graph, level)
        para2 = Statement(Predicate.PARALLEL, [c, d, p, q])
        dep2 = Dependency(para2, None, level)
        dep2.why = _why_para(dep2, statements_graph, level)
        why_eqangle += [dep1, dep2]

    elif is_equal(ab, cd) or is_equal(mn, pq):
        para1 = Statement(Predicate.PARALLEL, [a, b, c, d])
        dep1 = Dependency(para1, None, level)
        dep1.why = _why_para(dep1, statements_graph, level)
        para2 = Statement(Predicate.PARALLEL, [m, n, p, q])
        dep2 = Dependency(para2, None, level)
        dep2.why = _why_para(dep2, statements_graph, level)
        why_eqangle += [dep1, dep2]
    elif ab._val and cd._val and mn._val and pq._val:
        why_eqangle = _why_eqangle_directions(ab._val, cd._val, mn._val, pq._val, level)

    return why_eqangle


def _why_eqratio(
    statements_graph: "WhyHyperGraph", dep: "Dependency", level: int
) -> list[Dependency]:
    a, b, c, d, m, n, p, q = dep.statement.args
    ab = statements_graph.symbols_graph.get_segment(a, b)
    cd = statements_graph.symbols_graph.get_segment(c, d)
    mn = statements_graph.symbols_graph.get_segment(m, n)
    pq = statements_graph.symbols_graph.get_segment(p, q)

    why_eqratio = []
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
            cong = Statement(Predicate.CONGRUENT, congruent_points)
            cong_dep = Dependency(cong, None, level)
            cong_dep.why = _why_cong(statements_graph, cong_dep, level)
            why_eqratio = [cong_dep]
        return why_eqratio

    if ab._val and cd._val and mn._val and pq._val:
        why_eqratio = _why_eqratio_directions(ab._val, cd._val, mn._val, pq._val, level)

    if dep.why is not None:
        return why_eqratio

    if (ab == cd and mn == pq) or (ab == mn and cd == pq):
        return []

    equal_pair_points, equal_pair_lines = _find_equal_pair(
        a, b, c, d, m, n, p, q, ab, cd, mn, pq
    )
    if equal_pair_points is not None:
        why_eqratio += _maybe_make_equal_pairs(
            statements_graph, *equal_pair_points, *equal_pair_lines, level
        )
        return why_eqratio

    if is_equal(ab, mn) or is_equal(cd, pq):
        cong1 = Statement(Predicate.CONGRUENT, [a, b, m, n])
        dep1 = Dependency(cong1, None, level)
        dep1.why = _why_cong(statements_graph, dep1, level)
        cong2 = Statement(Predicate.CONGRUENT, [c, d, p, q])
        dep2 = Dependency(cong2, None, level)
        dep2.why = _why_cong(statements_graph, dep2, level)
        why_eqratio += [dep1, dep2]
    elif is_equal(ab, cd) or is_equal(mn, pq):
        cong1 = Statement(Predicate.CONGRUENT, [a, b, c, d])
        dep1 = Dependency(cong1, None, level)
        dep1.why = _why_cong(statements_graph, dep1, level)
        cong2 = Statement(Predicate.CONGRUENT, [m, n, p, q])
        dep2 = Dependency(cong2, None, level)
        dep2.why = _why_cong(statements_graph, dep2, level)
        why_eqratio += [dep1, dep2]
    elif ab._val and cd._val and mn._val and pq._val:
        why_eqratio = _why_eqangle_directions(ab._val, cd._val, mn._val, pq._val, level)

    return why_eqratio


def _why_eqratio3(
    statements_graph: "WhyHyperGraph", dep: "Dependency", level: int
) -> list[Dependency]:
    a, b, c, d, m, n = dep.statement.args
    para = Statement(Predicate.PARALLEL, [a, b, c, d])
    dep1 = Dependency(para, "", level)
    dep1.why = _why_para(statements_graph, dep1, level)
    coll_mac = Statement(Predicate.COLLINEAR, [m, a, c])
    dep2 = Dependency(coll_mac, "", level)
    dep2.why = _why_coll(statements_graph, dep2, level)
    coll_nbd = Statement(Predicate.COLLINEAR, [n, b, d])
    dep3 = Dependency(coll_nbd, "", level)
    dep3.why = _why_coll(statements_graph, dep3, level)
    dep.reason = Reason("br07")
    return [dep1, dep2, dep3]


def _why_simtri(
    statements_graph: "WhyHyperGraph", dep: "Dependency", level: int
) -> list[Dependency]:
    a, b, c, x, y, z = dep.statement.args
    eqangle1 = Statement(Predicate.EQANGLE, [a, b, a, c, x, y, x, z])
    dep1 = Dependency(eqangle1, "", level)
    dep1.why = _why_eqangle(statements_graph, dep1, level)
    eqangle2 = Statement(Predicate.EQANGLE, [b, a, b, c, y, x, y, z])
    dep2 = Dependency(eqangle2, "", level)
    dep2.why = _why_eqangle(statements_graph, dep2, level)
    dep.reason = Reason("br34")
    return [dep1, dep2]


def _why_simtri_both(
    statements_graph: "WhyHyperGraph", dep: "Dependency", level: int
) -> list[Dependency]:
    a, b, c, p, q, r = dep.statement.args
    eqratio1 = Statement(Predicate.EQRATIO, [b, a, b, c, q, p, q, r])
    dep1 = Dependency(eqratio1, "", level)
    dep1.why = _why_eqratio(statements_graph, dep1, level)
    eqratio2 = Statement(Predicate.EQRATIO, [c, a, c, b, r, p, r, q])
    dep2 = Dependency(eqratio2, "", level)
    dep2.why = _why_eqratio(statements_graph, dep2, level)
    dep.reason = Reason("br38")
    return [dep1, dep2]


def _why_contri(
    statements_graph: "WhyHyperGraph", dep: "Dependency", level: int
) -> list[Dependency]:
    a, b, c, x, y, z = dep.statement.args
    eqangle1 = Statement(Predicate.EQANGLE, [b, a, b, c, y, x, y, z])
    dep1 = Dependency(eqangle1, "", level)
    dep1.why = _why_eqangle(statements_graph, dep1, level)
    eqangle2 = Statement(Predicate.EQANGLE, [c, a, c, b, z, x, z, y])
    dep2 = Dependency(eqangle2, "", level)
    dep2.why = _why_eqangle(statements_graph, dep2, level)
    cong = Statement(Predicate.CONGRUENT, [a, b, x, y])
    dep3 = Dependency(cong, "", level)
    dep3.why = _why_cong(statements_graph, dep3, level)
    dep.reason = Reason("br36")
    return [dep1, dep2, dep3]


def why_contri_2(
    statements_graph: "WhyHyperGraph", dep: "Dependency", level: int
) -> list[Dependency]:
    a, b, c, x, y, z = dep.statement.args
    eqangle1 = Statement(Predicate.EQANGLE, [b, a, b, c, y, z, y, x])
    dep1 = Dependency(eqangle1, "", level)
    dep1.why = _why_eqangle(statements_graph, dep1, level)
    eqangle2 = Statement(Predicate.EQANGLE, [c, a, c, b, z, y, z, x])
    dep2 = Dependency(eqangle2, "", level)
    dep2.why = _why_eqangle(statements_graph, dep2, level)
    cong = Statement(Predicate.CONGRUENT, [a, b, x, y])
    dep3 = Dependency(cong, "", level)
    dep3.why = _why_cong(statements_graph, dep3, level)
    dep.reason = Reason("br37")
    return [dep1, dep2, dep3]


def _why_contri_both(
    statements_graph: "WhyHyperGraph", dep: "Dependency", level: int
) -> list[Dependency]:
    a, b, c, x, y, z = dep.statement.args
    cong1 = Statement(Predicate.CONGRUENT, [a, b, x, y])
    dep1 = Dependency(cong1, "", level)
    dep1.why = _why_cong(statements_graph, dep1, level)
    cong2 = Statement(Predicate.CONGRUENT, [b, c, y, z])
    dep2 = Dependency(cong2, "", level)
    dep2.why = _why_cong(statements_graph, dep2, level)
    cong3 = Statement(Predicate.CONGRUENT, [c, a, z, x])
    dep3 = Dependency(cong3, "", level)
    dep3.why = _why_cong(statements_graph, dep3, level)
    dep.reason = Reason("br32")
    return [dep1, dep2, dep3]


def _why_aconst(
    statements_graph: "WhyHyperGraph", dep: "Dependency", level: int
) -> list[Dependency]:
    a, b, c, d, ang0 = dep.statement.args

    measure = ang0._val
    for ang in measure.neighbors(Angle):
        if ang == ang0:
            continue
        d1, d2 = ang._d
        l1, l2 = d1._obj, d2._obj
        (a1, b1), (c1, d1) = l1.points, l2.points

        if not statements_graph.statements_checker.check_para_or_coll(
            [a, b, a1, b1]
        ) or not statements_graph.statements_checker.check_para_or_coll([c, d, c1, d1]):
            continue

        why_aconst = []
        for args in [(a, b, a1, b1), (c, d, c1, d1)]:
            if statements_graph.statements_checker.check_coll(args):
                if len(set(args)) <= 2:
                    continue
                coll = Statement(Predicate.COLLINEAR, args)
                coll_dep = Dependency(coll, None, None)
                coll_dep.why = _why_coll(statements_graph, coll_dep, level)
                why_aconst.append(coll_dep)
            else:
                para = Statement(Predicate.PARALLEL, args)
                para_dep = Dependency(para, None, None)
                para_dep.why = _why_para(statements_graph, para_dep, level)
                why_aconst.append(para_dep)

        why_aconst += _why_equal(ang, ang0)
        return why_aconst


def _why_rconst(statements_graph: "WhyHyperGraph", dep: "Dependency", level: int):
    a, b, c, d, rat0 = dep.statement.args
    val = rat0._val

    for rat in val.neighbors(Ratio):
        if rat == rat0:
            continue
        l1, l2 = rat._l
        s1, s2 = l1._obj, l2._obj
        (a1, b1), (c1, d1) = list(s1.points), list(s2.points)

        if not statements_graph.statements_checker.check_cong(
            [a, b, a1, b1]
        ) or not statements_graph.statements_checker.check_cong([c, d, c1, d1]):
            continue

        why_rconst = []
        for args in [(a, b, a1, b1), (c, d, c1, d1)]:
            if len(set(args)) > 2:
                cong = Statement(Predicate.CONGRUENT, args)
                cong_dep = Dependency(cong, None, None)
                cong_dep.why = _why_cong(statements_graph, cong_dep, level)
                why_rconst.append(cong_dep)

        why_rconst += _why_equal(rat, rat0)
        return why_rconst


def _why_numerical(
    statements_graph: "WhyHyperGraph", dep: "Dependency", level: int
) -> list[Dependency]:
    return []


PREDICATE_TO_WHY: dict[
    Predicate,
    Callable[
        [
            "Dependency",
            "SymbolsGraph",
            "StatementChecker",
            "DependencyCache",
            int,
        ],
        list[Dependency],
    ],
] = {
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
    statements_graph: "WhyHyperGraph",
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
    level: int,
) -> list["Dependency"]:
    """Make a-b:c-d==m-n:p-q in case a-b==m-n or c-d==p-q."""
    if ab != mn:
        return
    why = []
    eqpredicate = Predicate.PARALLEL if isinstance(ab, Line) else Predicate.CONGRUENT
    colls = [a, b, m, n]
    if len(set(colls)) > 2 and eqpredicate is Predicate.PARALLEL:
        collx = Statement(Predicate.COLLINEAR_X, colls)
        collx_dep = Dependency(collx, None, level)
        collx_dep.why = _why_collx(statements_graph, collx_dep, level)
        why += [collx_dep]

    eq_statement = Statement(eqpredicate, [c, d, p, q])
    eqdep = Dependency(eq_statement, None, level)
    if eqpredicate is Predicate.PARALLEL:
        eqdep.why = _why_para(statements_graph, eqdep, level)
    elif eqpredicate is Predicate.CONGRUENT:
        eqdep.why = _why_cong(statements_graph, eqdep, level)
    why += [eqdep]
    return why


def _why_eqangle_directions(
    d1: Direction,
    d2: Direction,
    d3: Direction,
    d4: Direction,
    level: int,
) -> Optional[
    tuple[
        tuple[Direction, Direction, Direction, Direction],
        list[Dependency],
    ]
]:
    """Why two angles are equal, returns a Dependency objects."""
    all12 = list(all_angles(d1, d2, level))
    all34 = list(all_angles(d3, d4, level))

    min_why = None
    for ang12, d1s, d2s in all12:
        for ang34, d3s, d4s in all34:
            why0 = _why_equal(ang12, ang34, level)
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
    why0 = _why_equal(ang12, ang34, level)
    d1_, d2_ = ang12._d
    d3_, d4_ = ang34._d

    if d1 == d1_ and d2 == d2_ and d3 == d3_ and d4 == d4_:
        return (d1_, d2_, d3_, d4_), why0

    (a_, b_), (c_, d_) = d1_._obj.points, d2_._obj.points
    (e_, f_), (g_, h_) = d3_._obj.points, d4_._obj.points
    deps = []
    if why0:
        eqangle = Statement(Predicate.EQANGLE, [a_, b_, c_, d_, e_, f_, g_, h_])
        dep = Dependency(eqangle, "", None)
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
                predicate = Predicate.COLLINEAR_X
            else:
                predicate = Predicate.PARALLEL
            because_statement = Statement(predicate, [x_, y_, x, y])
            dep = Dependency(because_statement, "", None)
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
            why0 = _why_equal(ang12, ang34, level)
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
        eqratio = Statement(Predicate.EQRATIO, [a_, b_, c_, d_, e_, f_, g_, h_])
        dep = Dependency(eqratio, "", level)
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
            cong = Statement(Predicate.CONGRUENT, [x, y, x_, y_])
            dep = Dependency(cong, "", level)
            dep.why = why
            deps.append(dep)

    return deps
