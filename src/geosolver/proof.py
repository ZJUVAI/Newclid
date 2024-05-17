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
from typing import Generator, Optional, Tuple, Union
from typing_extensions import Self
import logging


from geosolver.predicates import Predicate
from geosolver.agent.breadth_first_search import Action, Mapping
from geosolver.agent.interface import (
    ApplyDerivationAction,
    ApplyDerivationFeedback,
    ApplyTheoremAction,
    ApplyTheoremFeedback,
    AuxAction,
    AuxFeedback,
    DeriveAlgebraAction,
    DeriveFeedback,
    Feedback,
    MatchAction,
    MatchFeedback,
    ResetFeedback,
    StopAction,
    StopFeedback,
)
from geosolver.match_theorems import match_one_theorem
from geosolver.statement.adder import IntrinsicRules, StatementAdder, ToCache
from geosolver.statement.checker import StatementChecker
from geosolver.symbols_graph import SymbolsGraph
from geosolver.algebraic.algebraic_manipulator import AlgebraicManipulator
from geosolver.geometry import Angle, Direction, Length, Ratio
from geosolver.geometry import Circle, Line, Point, Segment
from geosolver.geometry import Measure, Value
import geosolver.combinatorics as comb
import geosolver.numerical.geometries as num_geo

from geosolver.numerical.check import check_numerical, same_clock
from geosolver.numerical.distances import (
    PointTooCloseError,
    PointTooFarError,
    check_too_far_numerical,
    check_too_close_numerical,
)
from geosolver.numerical.sketch import sketch


from geosolver.problem import (
    CONSTRUCTION_RULE,
    Clause,
    Construction,
    Definition,
    Problem,
    Theorem,
)

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
    "iso_trapezoid",
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

        self._goal = None
        self._resolved_mapping_deps: dict[
            tuple["Theorem", "Mapping"], EmptyDependency
        ] = {}
        self._problem: Optional[Problem] = None
        self._definitions: Optional[dict[str, Definition]] = None
        self._init_added: list[Dependency] = []
        self._init_to_cache: list[ToCache] = []
        self._plevel: int = 0

    @classmethod
    def build_problem(
        cls,
        problem: Problem,
        definitions: dict[str, Definition],
        disabled_intrinsic_rules: Optional[list[IntrinsicRules]] = None,
        max_attempts=100,
    ) -> Self:
        """Build a problem into a Proof state object."""
        proof = None
        added = None
        logging.info(f"Building proof from problem '{problem.url}': {problem.txt()}")

        if disabled_intrinsic_rules is None:
            disabled_intrinsic_rules = []

        err = DepCheckFailError(f"Numerical check failed {max_attempts} times")
        for _ in range(max_attempts):
            # Search for coordinates that checks premises conditions numerically.
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
                    disabled_intrinsic_rules=disabled_intrinsic_rules,
                )
                proof = Proof(
                    dependency_cache=dependency_cache,
                    alegbraic_manipulator=alegbraic_manipulator,
                    symbols_graph=symbols_graph,
                    statements_checker=statements_checker,
                    statements_adder=statements_adder,
                )
                added = []
                to_cache = []
                plevel = 0
                for clause in problem.clauses:
                    adds, clause_to_cache, plevel = proof.add_clause(
                        clause, plevel, definitions
                    )
                    added += adds
                    to_cache += clause_to_cache
                proof._plevel = plevel

            except (
                num_geo.InvalidLineIntersectError,
                num_geo.InvalidQuadSolveError,
                DepCheckFailError,
                PointTooCloseError,
                PointTooFarError,
            ) as e:
                err = e
                continue

            if not problem.goal:
                break

            goal_args = proof.map_construction_args_to_objects(problem.goal)
            proof.dependency_graph.add_goal(problem.goal.name, goal_args)
            if check_numerical(problem.goal.name, goal_args):
                break
        else:
            raise err

        proof._goal = problem.goal
        proof._problem = problem
        proof._definitions = definitions
        proof._init_added = added
        proof._init_to_cache = to_cache

        return proof

    def step(self, action: Action) -> Feedback:
        if isinstance(action, StopAction):
            success = False
            if self._goal is not None:
                success = self.check_goal(self._goal)
            return StopFeedback(success=success)
        elif isinstance(action, ApplyTheoremAction):
            added, to_cache, success = self._apply_theorem(
                action.theorem, action.mapping
            )
            if self.alegbraic_manipulator and added:
                # Add algebra to AR, but do NOT derive nor add to the proof state (yet)
                for dep in added:
                    self.alegbraic_manipulator.add_algebra(dep)
            self.cache_deps(to_cache)
            return ApplyTheoremFeedback(success, added, to_cache)
        elif isinstance(action, DeriveAlgebraAction):
            derives, eq4s = self.alegbraic_manipulator.derive_algebra(action.level)
            return DeriveFeedback(derives, eq4s)
        elif isinstance(action, MatchAction):
            theorem = action.theorem
            potential_mappings = match_one_theorem(
                self, theorem, cache=action.cache, goal=self._goal
            )
            mappings = []
            for mapping in potential_mappings:
                deps = self._resolve_mapping_dependency(theorem, mapping, action.level)
                if deps is not None:
                    mappings.append(mapping)
                    mapping_str = theorem_mapping_str(theorem, mapping)
                    self._resolved_mapping_deps[mapping_str] = deps

            return MatchFeedback(theorem, mappings)
        elif isinstance(action, ApplyDerivationAction):
            added, to_cache = self.do_algebra(
                action.derivation_name, action.derivation_arguments
            )
            self.cache_deps(to_cache)
            return ApplyDerivationFeedback(added, to_cache)

        elif isinstance(action, AuxAction):
            aux_clause = Clause.from_txt(action.aux_string)
            success = False
            added, to_cache = [], []
            try:
                added, to_cache, plevel = self.add_clause(
                    aux_clause, self._plevel, self._definitions
                )
                self._plevel = plevel
                success = True
            except (num_geo.InvalidQuadSolveError, num_geo.InvalidLineIntersectError):
                pass
            return AuxFeedback(success, added, to_cache)

        raise NotImplementedError()

    def reset(self) -> ResetFeedback:
        self.cache_deps(self._init_to_cache)
        for add in self._init_added:
            self.alegbraic_manipulator.add_algebra(add)
        return ResetFeedback(self._problem, self._init_added, self._init_to_cache)

    def copy(self):
        """Make a copy of proof state."""
        if self._problem is None:
            raise TypeError("Could not find problem when trying to copy.")
        if self._definitions is None:
            raise TypeError("Could not find definitions when trying to copy.")

        problem = self._problem.copy()
        for clause in problem.clauses:
            clause.nums = [
                self.symbols_graph._name2node[pname].num for pname in clause.points
            ]

        proof = Proof.build_problem(
            problem,
            self._definitions,
            disabled_intrinsic_rules=self.statements_adder.DISABLED_INTRINSIC_RULES,
        )
        return proof

    def _apply_theorem(
        self, theorem: "Theorem", mapping: Mapping
    ) -> Tuple[list[Dependency], list[ToCache], bool]:
        mapping_str = theorem_mapping_str(theorem, mapping)
        deps = self._resolved_mapping_deps.get(mapping_str)
        if deps is None:
            return [], [], False
        conclusion_name, args = theorem.conclusion_name_args(mapping)
        add, to_cache = self.resolve_statement_dependencies(
            conclusion_name, args, deps=deps
        )
        self.dependency_graph.add_theorem_edges(to_cache, theorem, args)
        return add, to_cache, True

    def _resolve_mapping_dependency(
        self, theorem: "Theorem", mapping: Mapping, dependency_level: int
    ) -> Optional[EmptyDependency]:
        deps = EmptyDependency(level=dependency_level, rule_name=theorem.rule_name)
        fail = False

        for premise in theorem.premise:
            p_args = [mapping[a] for a in premise.args]
            dep, fail = self._resolve_premise_dependency(
                theorem, premise, p_args, dependency_level
            )
            if fail:
                return None
            if dep is None:
                continue

            self.dependency_cache.add_dependency(premise.name, p_args, dep)
            deps.why.append(dep)

        return deps

    def _resolve_premise_dependency(
        self,
        theorem: "Theorem",
        premise: "Construction",
        p_args: list["Point"],
        dependency_level: int,
    ) -> Tuple[Optional[Dependency], bool]:
        # Trivial deps.
        if premise.name in [Predicate.PARALLEL.value, Predicate.CONGRUENT.value]:
            a, b, c, d = p_args
            if {a, b} == {c, d}:
                return None, False

        if theorem.name in [
            "cong_cong_eqangle6_ncoll_contri*",
            "eqratio6_eqangle6_ncoll_simtri*",
        ]:
            if premise.name in [
                Predicate.EQANGLE.value,
                Predicate.EQANGLE6.value,
            ]:  # SAS or RAR
                b, a, b, c, y, x, y, z = p_args
                if not same_clock(a.num, b.num, c.num, x.num, y.num, z.num):
                    p_args = b, a, b, c, y, z, y, x

        dep = Dependency(
            premise.name, p_args, rule_name="Premise", level=dependency_level
        )
        try:
            dep = dep.why_me_or_cache(
                self.symbols_graph,
                self.statements_checker,
                self.dependency_cache,
                dependency_level,
            )
            fail = False
        except Exception:
            fail = True

        if dep.why is None:
            fail = True

        return dep, fail

    def resolve_statement_dependencies(
        self, name: str, args: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        return self.statements_adder.add_piece(name, args, deps)

    def do_algebra(
        self, name: str, args: list[Point]
    ) -> tuple[list[Dependency], list[ToCache]]:
        """Derive (but not add) new algebraic predicates."""
        new_deps, to_cache = self.statements_adder.add_algebra(name, args)
        self.dependency_graph.add_algebra_edges(to_cache, args[:-1])
        return new_deps, to_cache

    def cache_deps(self, deps_to_cache: list[ToCache]):
        for to_cache in deps_to_cache:
            self.dependency_cache.add_dependency(*to_cache)

    def check(self, name: str, args: list[Point]) -> bool:
        """Symbolically check if a predicate is True."""
        if name in [
            Predicate.FIX_L.value,
            Predicate.FIX_C.value,
            Predicate.FIX_B.value,
            Predicate.FIX_T.value,
            Predicate.FIX_P.value,
        ]:
            return self.dependency_cache.contains(name, args)
        if name in [Predicate.IND.value]:
            return True
        return self.statements_checker.check(name, args)

    def check_goal(self, goal: Optional["Construction"]):
        success = False
        if goal is not None:
            goal_args = self.map_construction_args_to_objects(goal)
            if self.check(goal.name, goal_args):
                success = True
        return success

    def additionally_draw(self, name: str, args: list[Point]) -> None:
        """Draw some extra line/circles for illustration purpose."""

        if name in [Predicate.CIRCLE.value]:
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
    ) -> tuple[list[Dependency], list[ToCache], int]:
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
            c_name = Predicate.MIDPOINT.value if c.name == "midpoint" else c.name
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
                    args = self.map_construction_args_to_objects(n, mapping)
                    to_be_intersected += sketch(n.name, args)

            return to_be_intersected

        is_total_free = (
            len(clause.constructions) == 1 and clause.constructions[0].name in FREE
        )
        is_semi_free = (
            len(clause.constructions) == 1 and clause.constructions[0].name in INTERSECT
        )

        existing_numerical_points = [p.num for p in existing_points]

        def draw_fn() -> list[num_geo.Point]:
            to_be_intersected = range_fn()
            return num_geo.reduce(to_be_intersected, existing_numerical_points)

        rely_on: set[Point] = set()
        for c in clause.constructions:
            cdef = definitions[c.name]
            mapping = dict(zip(cdef.construction.args, c.args))
            for n in cdef.numerics:
                args = self.map_construction_args_to_objects(n, mapping)
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

        # check two things
        new_points_nums = [p.num for p in new_points]
        if check_too_close_numerical(new_points_nums, existing_numerical_points):
            raise PointTooCloseError()
        if check_too_far_numerical(new_points_nums, existing_numerical_points):
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
        to_cache = []
        basics = []
        # Step 3: build the basics.
        for c, deps in zip(clause.constructions, new_points_dep):
            cdef = definitions[c.name]
            mapping = dict(zip(cdef.construction.args, c.args))

            # not necessary for proofing, but for visualization.
            c_args = [self.symbols_graph.get_point(a, lambda a: a) for a in c.args]
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
                    args = self.map_construction_args_to_objects(b, mapping)
                    adds, basic_to_cache = self.resolve_statement_dependencies(
                        name=b.name, args=args, deps=deps
                    )
                    self.dependency_graph.add_construction_edges(basic_to_cache, args)
                    to_cache += basic_to_cache

                    basics.append((b.name, args, deps))
                    if adds:
                        added += adds

        assert len(plevel_done) == len(new_points)
        for p in new_points:
            p.basics = basics

        return added, to_cache, plevel

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
            segss.append(tuple(segs))

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

    def map_construction_args_to_objects(
        self, construction: Construction, mapping: Optional[dict[str, str]] = None
    ) -> list[Point | Angle | Ratio]:
        def make_const(x):
            arg_obj, _ = self.alegbraic_manipulator.get_or_create_const(
                x, construction.name
            )
            return arg_obj

        args_objs = []
        for arg in construction.args:
            if mapping and arg in mapping:
                arg = mapping[arg]
            args_objs.append(self.symbols_graph.get_point(arg, make_const))
        return args_objs


def theorem_mapping_str(theorem: Theorem, mapping: Mapping) -> str:
    points_txt = " ".join(
        [point.name for _name, point in mapping.items() if isinstance(_name, str)]
    )
    return f"{theorem.rule_name} {points_txt}"
