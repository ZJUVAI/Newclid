from __future__ import annotations
from collections import defaultdict
from typing import TYPE_CHECKING, Optional, TypeVar


import geosolver.predicates as preds

from geosolver.statement import Statement

from geosolver.dependencies.dependency import Dependency
from geosolver.geometry import Line, Symbol, Point


if TYPE_CHECKING:
    from geosolver.dependencies.why_graph import DependencyGraph


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
    dep_graph: "DependencyGraph",
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
    eqpredicate = preds.Para if isinstance(ab, Line) else preds.Cong
    colls = [a, b, m, n]
    if len(set(colls)) > 2 and eqpredicate is preds.Para:
        collx = Statement(preds.Collx, colls)
        why.append(dep_graph.build_resolved_dependency(collx, use_cache=False))

    eq_statement = Statement(eqpredicate, [c, d, p, q])
    why.append(dep_graph.build_resolved_dependency(eq_statement, use_cache=False))
    return why
