from __future__ import annotations
from collections import defaultdict
from typing import TYPE_CHECKING, Callable, Optional, TypeVar


import geosolver.predicates as preds

import geosolver.predicates.coll
from geosolver.statements.statement import Statement

from geosolver.dependencies.dependency import Dependency, Reason
from geosolver.geometry import Angle, AngleValue, Line, Symbol, Point, Ratio
from geosolver.predicate_name import PredicateName


if TYPE_CHECKING:
    from geosolver.dependencies.why_graph import WhyHyperGraph


def why_dependency(
    statements_graph: "WhyHyperGraph",
    statement: "Statement",
    use_cache: bool = True,
) -> tuple[Reason, list[Dependency]]:
    if use_cache:
        cached_me = statements_graph.dependency_cache.get(statement)
        if cached_me is not None:
            return cached_me.reason, cached_me.why

    predicate = PredicateName(statement.name)
    reason = Reason(f"why_{predicate.value}_resolution")

    if predicate is PredicateName.IND:
        return reason, []

    why_predicate = PREDICATE_TO_WHY[predicate]
    _reason, why = why_predicate(statements_graph, statement)
    if _reason is not None:
        reason = _reason
    return reason, why


def why_equal(x: Symbol, y: Symbol) -> list[Dependency]:
    if x == y:
        return []
    if not x._val or not y._val:
        return None
    if x._val == y._val:
        return []
    return x._val.why_equal([y._val])


def line_of_and_why(
    points: list[Point],
) -> tuple[Optional[Line], Optional[list[Dependency]]]:
    """Why points are collinear."""
    for l0 in _get_lines_thru_all(*points):
        for line in l0.equivs():
            if all([p in line.edge_graph for p in points]):
                x, y = line.points
                colls = list({x, y} | set(points))
                why = line.why_coll(colls)
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


def _why_aconst(
    statements_graph: "WhyHyperGraph", statement: "Statement"
) -> tuple[Optional[Reason], list[Dependency]]:
    a, b, c, d, ang0 = statement.args

    measure: AngleValue = ang0._val
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
                coll = Statement(preds.Coll.NAME, args)
                coll_dep = statements_graph.build_resolved_dependency(
                    coll, use_cache=False
                )
                why_aconst.append(coll_dep)
            else:
                para = Statement(preds.Para.NAME, args)
                para_dep = statements_graph.build_resolved_dependency(
                    para, use_cache=False
                )
                why_aconst.append(para_dep)

        why_aconst += why_equal(ang, ang0)
        return None, why_aconst


def _why_rconst(
    statements_graph: "WhyHyperGraph", statement: "Statement"
) -> tuple[Optional[Reason], list[Dependency]]:
    a, b, c, d, rat0 = statement.args

    val: AngleValue = rat0._val
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
                cong = Statement(preds.Cong.NAME, args)
                why_rconst.append(
                    statements_graph.build_resolved_dependency(cong, use_cache=False)
                )

        why_rconst += why_equal(rat, rat0)
        return None, why_rconst


def _why_numerical(
    statements_graph: "WhyHyperGraph", statement: "Statement"
) -> tuple[Optional[Reason], list[Dependency]]:
    return None, []


PREDICATE_TO_WHY: dict[
    PredicateName,
    Callable[
        ["WhyHyperGraph", "Statement", int],
        tuple[Optional[Reason], list[Dependency]],
    ],
] = {
    PredicateName.CONSTANT_ANGLE: _why_aconst,
    PredicateName.CONSTANT_RATIO: _why_rconst,
    PredicateName.DIFFERENT: _why_numerical,
    PredicateName.NON_PARALLEL: _why_numerical,
    PredicateName.NON_PERPENDICULAR: _why_numerical,
    PredicateName.NON_COLLINEAR: _why_numerical,
    PredicateName.SAMESIDE: _why_numerical,
}


P = TypeVar("P")
L = TypeVar("L")


def find_equal_pair(
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


def why_maybe_make_equal_pairs(
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
) -> list["Dependency"]:
    """Make a-b:c-d==m-n:p-q in case a-b==m-n or c-d==p-q."""
    if ab != mn:
        return
    why = []
    eqpredicate = preds.Para.NAME if isinstance(ab, Line) else preds.Cong.NAME
    colls = [a, b, m, n]
    if len(set(colls)) > 2 and eqpredicate is preds.Para.NAME:
        collx = Statement(geosolver.predicates.coll.Collx.NAME, colls)
        why.append(statements_graph.build_resolved_dependency(collx, use_cache=False))

    eq_statement = Statement(eqpredicate, [c, d, p, q])
    why.append(
        statements_graph.build_resolved_dependency(eq_statement, use_cache=False)
    )
    return why
