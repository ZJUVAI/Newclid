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
from typing import Generator, Union
import logging


from geosolver.concepts import ConceptName
from geosolver.statement.adder import StatementAdder, ToCache
from geosolver.statement.checker import StatementChecker
from geosolver.symbols_graph import SymbolsGraph
from geosolver.algebraic.algebraic_manipulator import AlgebraicManipulator
from geosolver.geometry import Angle, Direction, Length, Ratio
from geosolver.geometry import Circle, Line, Point, Segment
from geosolver.geometry import Measure, Value
import geosolver.combinatorics as comb
import geosolver.numerical.geometries as num_geo

from geosolver.numerical.check import check_numerical
from geosolver.numerical.distances import (
    check_too_far_numerical,
    check_too_close_numerical,
)
from geosolver.numerical.sketch import sketch


from geosolver.problem import CONSTRUCTION_RULE, Clause, Definition, Problem

from geosolver.dependencies.empty_dependency import EmptyDependency
from geosolver.dependencies.caching import DependencyCache
from geosolver.dependencies.dependency import Dependency
from geosolver.dependencies.dependency_graph import DependencyGraph


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
        dependency_cache: DependencyCache,
        alegbraic_manipulator: AlgebraicManipulator,
        symbols_graph: SymbolsGraph,
        statements_checker: StatementChecker,
        statements_adder: StatementAdder,
    ):
        self.dependency_cache = dependency_cache
        self.symbols_graph = symbols_graph
        self.alegbraic_manipulator = alegbraic_manipulator
        self.statements_checker = statements_checker
        self.statements_adder = statements_adder
        self.dependency_graph = DependencyGraph()

    @classmethod
    def build_problem(
        cls,
        problem: Problem,
        definitions: dict[str, Definition],
        verbose: bool = True,
        init_copy: bool = True,
    ) -> tuple[Proof, list[Dependency]]:
        """Build a problem into a gr.Graph object."""
        check = False
        proof = None
        added = None
        if verbose:
            logging.info(problem.url)
            logging.info(problem.txt())
        while not check:
            # While loop to search for coordinates
            # that checks premises conditions numerically
            # will result in infinite loop if problem is impossible numerically.
            try:
                symbols_graph = SymbolsGraph()
                alegbraic_manipulator = AlgebraicManipulator(symbols_graph)
                statements_checker = StatementChecker(
                    symbols_graph, alegbraic_manipulator
                )

                dependency_cache = DependencyCache()
                statements_adder = StatementAdder(
                    symbols_graph,
                    alegbraic_manipulator,
                    statements_checker,
                    dependency_cache,
                )
                proof = Proof(
                    dependency_cache=dependency_cache,
                    alegbraic_manipulator=alegbraic_manipulator,
                    symbols_graph=symbols_graph,
                    statements_checker=statements_checker,
                    statements_adder=statements_adder,
                )
                added = []
                plevel = 0
                for clause in problem.clauses:
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

            if not problem.goal:
                break

            args = list(
                map(
                    lambda x: proof.symbols_graph.get_point(x, lambda: int(x)),
                    problem.goal.args,
                )
            )
            proof.dependency_graph.add_goal(problem.goal.name, args)
            check = check_numerical(problem.goal.name, args)

        proof.url = problem.url
        proof.build_def = (problem, definitions)
        for add in added:
            proof.add_algebra(add)

        return proof, added

    def add_piece(
        self, name: str, args: list[Point], deps: EmptyDependency
    ) -> list[Dependency]:
        new_deps, deps_to_cache = self.statements_adder.add_piece(name, args, deps)
        self.cache_deps(deps_to_cache)
        return new_deps

    def add_algebra(self, dep: Dependency) -> None:
        self.alegbraic_manipulator.add_algebra(dep)

    def do_algebra(self, name: str, args: list[Point]) -> list[Dependency]:
        """Derive (but not add) new algebraic predicates."""
        new_deps, to_cache = self.statements_adder.add_algebra(name, args)
        self.cache_deps(to_cache)
        self.dependency_graph.add_algebra_edges(new_deps, args[:-1])
        return new_deps

    def cache_deps(self, deps_to_cache: list[ToCache]):
        for to_cache in deps_to_cache:
            self.dependency_cache.add_dependency(*to_cache)

    def check(self, name: str, args: list[Point]) -> bool:
        """Symbolically check if a predicate is True."""
        if name in [
            ConceptName.FIX_L.value,
            ConceptName.FIX_C.value,
            ConceptName.FIX_B.value,
            ConceptName.FIX_T.value,
            ConceptName.FIX_P.value,
        ]:
            return self.dependency_cache.contains(name, args)
        if name in [ConceptName.IND.value]:
            return True
        return self.statements_checker.check(name, args)

    def additionally_draw(self, name: str, args: list[Point]) -> None:
        """Draw some extra line/circles for illustration purpose."""

        if name in [ConceptName.CIRCLE.value]:
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
            c_name = ConceptName.MIDPOINT.value if c.name == "midpoint" else c.name
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

        rely_on: set[Point] = set()
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
                    if b.name != ConceptName.CONSTANT_RATIO.value:
                        args = [mapping[a] for a in b.args]
                    else:
                        num, den = map(int, b.args[-2:])
                        rat, _ = self.alegbraic_manipulator.get_or_create_const_rat(
                            num, den
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
                            self.dependency_cache.add_dependency(
                                add.name, add.args, add
                            )

        assert len(plevel_done) == len(new_points)
        for p in new_points:
            p.basics = basics

        return added, plevel

    def all_eqangle_same_lines(self) -> Generator[tuple[Point, ...], None, None]:
        for l1, l2 in comb.permutations_pairs(self.symbols_graph.type2nodes[Line]):
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
                para_para = list(comb.cross_product(l1s, l2s))
                line_pairss.append(para_para)

            for pairs1, pairs2 in comb.arrangement_pairs(line_pairss):
                for pair1, pair2 in comb.cross_product(pairs1, pairs2):
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
                line_pairs.update(set(comb.cross_product(l1s, l2s)))
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
                line_pairss.append(set(comb.cross_product(l1s, l2s)))
                line_pairss.append(set(comb.cross_product(l2s, l1s)))

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
                line_pairss.append(set(comb.cross_product(l1s, l2s)))
                line_pairss.append(set(comb.cross_product(l2s, l1s)))

        record = set()
        for line_pairs in line_pairss:
            for pair1, pair2 in comb.permutations_pairs(list(line_pairs)):
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
            for l1, l2 in comb.permutations_pairs(d.neighbors(Line)):
                for a, b, c, d in comb.all_4points(l1, l2):
                    yield a, b, c, d

    def all_perps(self) -> Generator[tuple[Point, ...], None, None]:
        for ang in self.alegbraic_manipulator.vhalfpi.neighbors(Angle):
            d1, d2 = ang.directions
            if d1 is None or d2 is None:
                continue
            if d1 == d2:
                continue
            for l1, l2 in comb.cross_product(d1.neighbors(Line), d2.neighbors(Line)):
                for a, b, c, d in comb.all_4points(l1, l2):
                    yield a, b, c, d

    def all_congs(self) -> Generator[tuple[Point, ...], None, None]:
        for lenght in self.symbols_graph.type2nodes[Length]:
            for s1, s2 in comb.permutations_pairs(lenght.neighbors(Segment)):
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
                seg_pairs.update(comb.cross_product(s1s, s2s))
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
                seg_pairss.append(set(comb.cross_product(s1s, s2s)))
                seg_pairss.append(set(comb.cross_product(s2s, s1s)))

        # include Seg that does not have any Length.
        nolen_ss = [s for s in self.symbols_graph.type2nodes[Segment] if s.val is None]

        for seg in nolen_ss:
            for lenght in self.symbols_graph.type2nodes[Length]:
                s1s = lenght.neighbors(Segment)
                if len(s1s) == 1:
                    continue
                s2s = [seg]
                seg_pairss.append(set(comb.cross_product(s1s, s2s)))
                seg_pairss.append(set(comb.cross_product(s2s, s1s)))

        record = set()
        for seg_pairs in seg_pairss:
            for pair1, pair2 in comb.permutations_pairs(list(seg_pairs)):
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

        segs_pair = list(comb.permutations_pairs(list(segss)))
        segs_pair += list(zip(segss, segss))
        for segs1, segs2 in segs_pair:
            for s1, s2 in comb.permutations_pairs(list(segs1)):
                for s3, s4 in comb.permutations_pairs(list(segs2)):
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
            for x, y, z, t in comb.permutations_quadruplets(c.neighbors(Point)):
                yield x, y, z, t

    def all_colls(self) -> Generator[tuple[Point, ...], None, None]:
        for line in self.symbols_graph.type2nodes[Line]:
            for x, y, z in comb.permutations_triplets(line.neighbors(Point)):
                yield x, y, z

    def all_midps(self) -> Generator[tuple[Point, ...], None, None]:
        for line in self.symbols_graph.type2nodes[Line]:
            for a, b, c in comb.permutations_triplets(line.neighbors(Point)):
                if self.statements_checker.check_cong([a, b, a, c]):
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
                    for a, b, c in comb.permutations_triplets(ps):
                        yield p, a, b, c
