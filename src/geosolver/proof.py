"""Implements the proof state."""

from __future__ import annotations

from collections import defaultdict
from typing import Optional, Tuple, Union
from typing_extensions import Self
import logging


from geosolver.dependencies.why_predicates import why_dependency
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
from geosolver.statement.adder import IntrinsicRules, ToCache
from geosolver.statement import StatementsHandler
from geosolver.symbols_graph import SymbolsGraph
from geosolver.algebraic.algebraic_manipulator import AlgebraicManipulator
from geosolver.geometry import Angle, Ratio
from geosolver.geometry import Circle, Point
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
        statements_handler: StatementsHandler,
    ):
        self.dependency_cache = dependency_cache
        self.symbols_graph = symbols_graph
        self.alegbraic_manipulator = alegbraic_manipulator
        self.statements = statements_handler
        self.dependency_graph = DependencyGraph()

        self._goal = None
        self._resolved_mapping_deps: dict[str, tuple[EmptyDependency, ToCache]] = {}
        self._problem: Optional[Problem] = None
        self._definitions: Optional[dict[str, Definition]] = None
        self._init_added: list[Dependency] = []
        self._init_to_cache: list[ToCache] = []
        self._plevel: int = 0
        self._ACTION_TYPE_TO_STEP = {
            MatchAction: self._step_match_theorem,
            ApplyTheoremAction: self._step_apply_theorem,
            DeriveAlgebraAction: self._step_derive_algebra,
            ApplyDerivationAction: self._step_apply_derivation,
            AuxAction: self._step_auxiliary_construction,
            StopAction: self._step_stop,
        }

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
                dependency_cache = DependencyCache()
                alegbraic_manipulator = AlgebraicManipulator(symbols_graph)
                statements_handler = StatementsHandler(
                    symbols_graph,
                    alegbraic_manipulator,
                    dependency_cache,
                    disabled_intrinsic_rules,
                )

                proof = Proof(
                    dependency_cache=dependency_cache,
                    alegbraic_manipulator=alegbraic_manipulator,
                    symbols_graph=symbols_graph,
                    statements_handler=statements_handler,
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
        return self._ACTION_TYPE_TO_STEP[type(action)](action)

    def _step_match_theorem(self, action: MatchAction) -> MatchFeedback:
        theorem = action.theorem
        potential_mappings = match_one_theorem(
            self, theorem, cache=action.cache, goal=self._goal
        )
        mappings = []
        for mapping in potential_mappings:
            deps, to_cache = self._resolve_mapping_dependency(
                theorem, mapping, action.level
            )
            if deps is None:
                continue

            mappings.append(mapping)
            mapping_str = theorem_mapping_str(theorem, mapping)
            self._resolved_mapping_deps[mapping_str] = (deps, to_cache)

        return MatchFeedback(theorem, mappings)

    def _resolve_mapping_dependency(
        self, theorem: "Theorem", mapping: Mapping, dependency_level: int
    ) -> tuple[Optional[EmptyDependency], Optional[ToCache]]:
        deps = EmptyDependency(level=dependency_level, rule_name=theorem.rule_name)
        fail = False

        for premise in theorem.premise:
            p_args = [mapping[a] for a in premise.args]
            dep, fail = self._resolve_premise_dependency(
                theorem, premise, p_args, dependency_level
            )
            if fail:
                return None, None
            if dep is None:
                continue

            to_cache = (premise.name, p_args, dep)
            deps.why.append(dep)

        return deps, to_cache

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
        ] and premise.name in [
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
            dep.why = why_dependency(
                dep,
                self.symbols_graph,
                self.statements.checker,
                self.dependency_cache,
                dependency_level,
            )
            fail = False
        except Exception:
            fail = True

        if dep.why is None:
            fail = True

        return dep, fail

    def _step_apply_theorem(self, action: ApplyTheoremAction) -> ApplyTheoremFeedback:
        added, to_cache, success = self._apply_theorem(action.theorem, action.mapping)
        if self.alegbraic_manipulator and added:
            # Add algebra to AR, but do NOT derive nor add to the proof state (yet)
            for dep in added:
                self.alegbraic_manipulator.add_algebra(dep)
        self.cache_deps(to_cache)
        return ApplyTheoremFeedback(success, added, to_cache)

    def _apply_theorem(
        self, theorem: "Theorem", mapping: Mapping
    ) -> Tuple[list[Dependency], list[ToCache], bool]:
        mapping_str = theorem_mapping_str(theorem, mapping)
        deps, premise_to_cache = self._resolved_mapping_deps[mapping_str]
        args = self.map_construction_args_to_objects(
            theorem.conclusion, mapping_to_names(mapping)
        )
        add, to_cache = self.resolve_statement_dependencies(
            theorem.conclusion.name, args, deps=deps
        )
        self.dependency_graph.add_theorem_edges(to_cache, theorem, args)
        return add, [premise_to_cache] + to_cache, True

    def _step_derive_algebra(self, action: DeriveAlgebraAction) -> DeriveFeedback:
        derives, eq4s = self.alegbraic_manipulator.derive_algebra(action.level)
        return DeriveFeedback(derives, eq4s)

    def _step_apply_derivation(
        self, action: ApplyDerivationAction
    ) -> ApplyDerivationFeedback:
        added, to_cache = self.do_algebra(
            action.derivation_name, action.derivation_arguments
        )
        self.cache_deps(to_cache)
        return ApplyDerivationFeedback(added, to_cache)

    def _step_auxiliary_construction(self, action: AuxAction) -> AuxFeedback:
        aux_clause = Clause.from_txt(action.aux_string)
        added, to_cache = [], []
        try:
            added, to_cache, plevel = self.add_clause(
                aux_clause, self._plevel, self._definitions
            )
            self._plevel = plevel
            success = True
        except (num_geo.InvalidQuadSolveError, num_geo.InvalidLineIntersectError):
            success = False
        return AuxFeedback(success, added, to_cache)

    def _step_stop(self, action: StopAction) -> StopFeedback:
        success = False
        if self._goal is not None:
            success = self.check_goal(self._goal)
        return StopFeedback(success=success)

    def reset(self) -> ResetFeedback:
        self.cache_deps(self._init_to_cache)
        for add in self._init_added:
            self.alegbraic_manipulator.add_algebra(add)
        return ResetFeedback(self._problem, self._init_added, self._init_to_cache)

    def copy(self):
        """Make a blank copy of proof state."""
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
            disabled_intrinsic_rules=self.statements.adder.DISABLED_INTRINSIC_RULES,
        )
        return proof

    def resolve_statement_dependencies(
        self, name: str, args: list[Point], deps: EmptyDependency
    ) -> Tuple[list[Dependency], list[ToCache]]:
        return self.statements.adder.add_piece(name, args, deps)

    def do_algebra(
        self, name: str, args: list[Point]
    ) -> tuple[list[Dependency], list[ToCache]]:
        """Derive (but not add) new algebraic predicates."""
        new_deps, to_cache = self.statements.adder.add_algebra(name, args)
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
        return self.statements.checker.check(name, args)

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


def mapping_to_names(mapping: Mapping) -> dict[str, str]:
    mapping_names = {}
    for arg, point_or_str in mapping.items():
        if isinstance(point_or_str, Point):
            mapping_names[arg] = point_or_str.name
        else:
            mapping_names[arg] = point_or_str
    return mapping_names


def theorem_mapping_str(theorem: Theorem, mapping: Mapping) -> str:
    points_txt = " ".join(
        [point.name for _name, point in mapping.items() if isinstance(_name, str)]
    )
    return f"{theorem.rule_name} {points_txt}"
