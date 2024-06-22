from __future__ import annotations
from typing import TYPE_CHECKING, Optional


import geosolver.combinatorics as comb
import geosolver.predicates as preds

from geosolver.intrinsic_rules import IntrinsicRules
import geosolver.predicates.coll
from geosolver.statements.statement import Statement

from geosolver.predicate_name import PredicateName
import geosolver.numerical.check as nm


from geosolver.dependencies.dependency import Reason, Dependency
from geosolver.dependencies.dependency_building import DependencyBody
from geosolver.geometry import Line, Point, Segment
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
            PredicateName.SIMILAR_TRIANGLE: self._add_simtri,
            PredicateName.SIMILAR_TRIANGLE_REFLECTED: self._add_simtri_reflect,
            PredicateName.SIMILAR_TRIANGLE_BOTH: self._add_simtri_check,
            PredicateName.CONTRI_TRIANGLE: self._add_contri,
            PredicateName.CONTRI_TRIANGLE_REFLECTED: self._add_contri_reflect,
            PredicateName.CONTRI_TRIANGLE_BOTH: self._add_contri_check,
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
            eqangle6 = Statement(preds.EqAngle6.NAME, args)
            if eqangle6.hash_tuple in hashs:
                continue
            _add, _to_cache = self._add_eqangle(args, dep_body=dep_body)
            add += _add
            to_cache += _to_cache

        for args in comb.enum_triangle(points):
            eqratio6 = Statement(preds.EqRatio6.NAME, args)
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
            eqangle6 = Statement(preds.EqAngle6.NAME, args)
            if eqangle6.hash_tuple in hashs:
                continue
            _add, _to_cache = self._add_eqangle(args, dep_body=dep_body)
            add += _add
            to_cache += _to_cache

        for args in comb.enum_triangle(points):
            eqratio6 = Statement(preds.EqRatio6.NAME, args)
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
            eqangle6 = Statement(preds.EqAngle6.NAME, args)
            if eqangle6.hash_tuple in hashs:
                continue
            _add, _to_cache = self._add_eqangle(args, dep_body=dep_body)
            add += _add
            to_cache += _to_cache

        for args in comb.enum_sides(points):
            cong = Statement(preds.Cong.NAME, args)
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
            eqangle6 = Statement(preds.EqAngle6.NAME, args)
            if eqangle6.hash_tuple in hashs:
                continue
            _add, _to_cache = self._add_eqangle(args, dep_body)
            add += _add
            to_cache += _to_cache

        for args in comb.enum_sides(points):
            cong = Statement(preds.Cong.NAME, args)
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
        dep_pred = preds.EqRatio.NAME
        eq_pred = preds.Cong.NAME
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
            because_collx = Statement(geosolver.predicates.coll.Collx.NAME, colls)
            dep_body = dep_body.extend(dep_graph, eq, because_collx, reason)

    because_eq = Statement(eq_pred, [m, n, p, q])
    dep = dep_body.build(dep_graph, because_eq)
    symbols_graph.make_equal(mn, pq, dep=dep)

    to_cache = [(because_eq, dep)]

    if is_equal(mn, pq):
        return [], to_cache
    return [dep], to_cache
