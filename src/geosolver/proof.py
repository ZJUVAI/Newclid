"""Implements the proof state."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Optional, Tuple, Type, Union
from typing_extensions import Self
import logging

from geosolver.defs.clause import ArgType, Clause, Construction
from geosolver.numerical.geometries import (
    CircleNum,
    HalfLine,
    HoleCircle,
    InvalidLineIntersectError,
    InvalidQuadSolveError,
    LineNum,
    PointNum,
    reduce,
)
from geosolver.intrinsic_rules import IntrinsicRules
import geosolver.predicates as preds
from geosolver.ratios import simplify
from geosolver.reasoning_engines.engines_interface import ReasoningEngine
from geosolver.statements.statement import Statement, angle_to_num_den, ratio_to_num_den
from geosolver.defs.definition import Definition
from geosolver.theorem import Theorem
from geosolver.predicate_name import PredicateName
from geosolver.agent.agents_interface import (
    Action,
    Feedback,
    Mapping,
    ImportDerivationAction,
    ImportDerivationFeedback,
    ApplyTheoremAction,
    ApplyTheoremFeedback,
    AuxAction,
    AuxFeedback,
    ResolveEngineAction,
    DeriveFeedback,
    MatchAction,
    MatchFeedback,
    ResetFeedback,
    StopAction,
    StopFeedback,
)
from geosolver.match_theorems import match_one_theorem
from geosolver.statements.adder import ToCache
from geosolver.statements.handler import StatementsHandler
from geosolver.symbols_graph import SymbolsGraph
from geosolver.geometry import Angle, Ratio, Circle, Point

from geosolver.numerical.check import check_numerical, same_clock
from geosolver.numerical.distances import (
    PointTooCloseError,
    PointTooFarError,
    check_too_far_numerical,
    check_too_close_numerical,
)
from geosolver.numerical.sketch import sketch

from geosolver.problem import CONSTRUCTION_RULE, Problem
from geosolver.dependencies.dependency_building import DependencyBody
from geosolver.dependencies.caching import DependencyCache
from geosolver.dependencies.dependency import Reason, Dependency
from geosolver._lazy_loading import lazy_import


if TYPE_CHECKING:
    import numpy.random


np_random: "numpy.random" = lazy_import("numpy.random")


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
        external_reasoning_engines: dict[str, ReasoningEngine],
        symbols_graph: SymbolsGraph,
        statements_handler: StatementsHandler,
        rnd_generator: "numpy.random.Generator" = None,
    ):
        self.dependency_cache = dependency_cache
        self.symbols_graph = symbols_graph
        self.reasoning_engines = external_reasoning_engines
        self.statements = statements_handler

        self._goal: Optional[Construction] = None
        self._resolved_mapping_deps: dict[str, tuple[DependencyBody, ToCache]] = {}
        self._problem: Optional[Problem] = None
        self._definitions: Optional[dict[str, Definition]] = None
        self._init_added: list[Dependency] = []
        self._init_to_cache: list[ToCache] = []
        self._plevel: int = 0
        self._ACTION_TYPE_TO_STEP = {
            MatchAction: self._step_match_theorem,
            ApplyTheoremAction: self._step_apply_theorem,
            ResolveEngineAction: self._step_derive,
            ImportDerivationAction: self._step_apply_derivation,
            AuxAction: self._step_auxiliary_construction,
            StopAction: self._step_stop,
        }
        self.rnd_gen = (
            rnd_generator if rnd_generator is not None else np_random.default_rng()
        )

    @classmethod
    def build_problem(
        cls,
        problem: Problem,
        definitions: dict[str, Definition],
        disabled_intrinsic_rules: Optional[list[IntrinsicRules]] = None,
        additional_reasoning_engine: Optional[dict[str, Type[ReasoningEngine]]] = None,
        max_attempts: int = 10000,
        rnd_generator: "numpy.random.Generator" = None,
    ) -> Self:
        """Build a problem into a Proof state object."""
        proof = None
        added = None
        logging.info(f"Building proof from problem '{problem.url}': {problem}")

        if disabled_intrinsic_rules is None:
            disabled_intrinsic_rules = []

        err = DepCheckFailError(f"Numerical check failed {max_attempts} times")
        for _ in range(max_attempts):
            # Search for coordinates that checks premises conditions numerically.
            try:
                symbols_graph = SymbolsGraph()
                dependency_cache = DependencyCache()
                statements_handler = StatementsHandler(
                    symbols_graph,
                    dependency_cache,
                    disabled_intrinsic_rules,
                )
                reasoning_engines = {}

                for engine_name, engine_type in additional_reasoning_engine.items():
                    if engine_name in reasoning_engines:
                        raise ValueError(f"Conflicting engine names for {engine_name}")
                    reasoning_engines[engine_name] = engine_type(symbols_graph)

                proof = Proof(
                    dependency_cache=dependency_cache,
                    external_reasoning_engines=reasoning_engines,
                    symbols_graph=symbols_graph,
                    statements_handler=statements_handler,
                    rnd_generator=rnd_generator,
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
                InvalidLineIntersectError,
                InvalidQuadSolveError,
                DepCheckFailError,
                PointTooCloseError,
                PointTooFarError,
            ) as e:
                err = e
                continue

            if not problem.goal:
                break

            goal_args = proof.map_construction_args_to_objects(problem.goal)
            goal = Statement(problem.goal.name, goal_args)
            if check_numerical(goal):
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
            dep_body, to_cache = self._resolve_mapping_dependency(theorem, mapping)
            if dep_body is None:
                continue

            mappings.append(mapping)
            mapping_str = theorem_mapping_str(theorem, mapping)
            self._resolved_mapping_deps[mapping_str] = (dep_body, to_cache)

        return MatchFeedback(theorem, mappings)

    def _resolve_mapping_dependency(
        self, theorem: "Theorem", mapping: Mapping
    ) -> tuple[Optional[DependencyBody], Optional[ToCache]]:
        fail = False

        deps: list["Dependency"] = []
        for premise in theorem.premises:
            p_args = [mapping[a] for a in premise.args]
            dep, fail = self._resolve_premise_dependency(theorem, premise, p_args)
            if fail:
                return None, None
            if dep is None:
                continue

            to_cache = (dep.statement, dep)
            deps.append(dep)

        dep_body = DependencyBody(reason=Reason(theorem), why=deps)
        return dep_body, to_cache

    def _resolve_premise_dependency(
        self,
        theorem: "Theorem",
        premise: "Construction",
        p_args: list["Point"],
    ) -> Tuple[Optional[Dependency], bool]:
        if premise.name in [preds.Para.NAME, preds.Cong.NAME]:
            a, b, c, d = p_args
            if {a, b} == {c, d}:
                return None, False

        if theorem.name in [
            "cong_cong_eqangle6_ncoll_contri*",
            "eqratio6_eqangle6_ncoll_simtri*",
        ] and premise.name in [preds.EqAngle.NAME, preds.EqAngle6.NAME]:  # SAS or RAR
            b, a, b, c, y, x, y, z = p_args
            if not same_clock(a.num, b.num, c.num, x.num, y.num, z.num):
                p_args = b, a, b, c, y, z, y, x

        premise_statement = Statement(premise.name, tuple(p_args))

        dep = None
        fail = False
        dep = self.statements.graph.build_resolved_dependency(premise_statement)
        if dep.why is None:
            fail = True

        return dep, fail

    def _step_apply_theorem(self, action: ApplyTheoremAction) -> ApplyTheoremFeedback:
        added, to_cache, success = self._apply_theorem(action.theorem, action.mapping)
        for dep in added:
            for _, external_reasoning_engine in self.reasoning_engines.items():
                external_reasoning_engine.ingest(dep)
        self.cache_deps(to_cache)
        return ApplyTheoremFeedback(success, added, to_cache)

    def _apply_theorem(
        self, theorem: "Theorem", mapping: Mapping
    ) -> Tuple[list[Dependency], list[ToCache], bool]:
        mapping_str = theorem_mapping_str(theorem, mapping)
        dep_body, premise_to_cache = self._resolved_mapping_deps[mapping_str]
        args = self.map_construction_args_to_objects(
            theorem.conclusion, mapping_to_names(mapping)
        )

        conclusion_statement = Statement(theorem.conclusion.name, tuple(args))
        add, to_cache = self.resolve_statement_dependencies(
            conclusion_statement, dep_body=dep_body
        )
        return add, [premise_to_cache] + to_cache, True

    def _step_derive(self, action: ResolveEngineAction) -> DeriveFeedback:
        choosen_engine = self.reasoning_engines[action.engine_id]
        derivations = choosen_engine.resolve()
        return DeriveFeedback(derivations)

    def _step_apply_derivation(
        self, action: ImportDerivationAction
    ) -> ImportDerivationFeedback:
        added, to_cache = self.resolve_statement_dependencies(
            action.derivation.statement, action.derivation.dep_body
        )
        self.cache_deps(to_cache)
        return ImportDerivationFeedback(added, to_cache)

    def _step_auxiliary_construction(self, action: AuxAction) -> AuxFeedback:
        aux_clause = Clause.from_txt(action.aux_string)
        added, to_cache = [], []
        try:
            added, to_cache, plevel = self.add_clause(
                aux_clause, self._plevel, self._definitions
            )
            self._plevel = plevel
            success = True
        except (InvalidQuadSolveError, InvalidLineIntersectError):
            success = False
        return AuxFeedback(success, added, to_cache)

    def _step_stop(self, action: StopAction) -> StopFeedback:
        return StopFeedback(success=self.check_goal())

    def reset(self) -> ResetFeedback:
        self.cache_deps(self._init_to_cache)
        for _, ext in self.reasoning_engines.items():
            for add in self._init_added:
                ext.ingest(add)
        return ResetFeedback(
            problem=self._problem,
            added=self._init_added,
            to_cache=self._init_to_cache,
            available_engines=list(self.reasoning_engines.keys()),
        )

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
            rnd_generator=self.rnd_gen,
        )
        return proof

    def get_rnd_generator(self):
        return self.rnd_gen

    def set_rnd_generator(self, rnd_gen: "numpy.random.Generator"):
        del self.rnd_gen
        self.rnd_gen = rnd_gen

    def resolve_statement_dependencies(
        self, statement: Statement, dep_body: DependencyBody
    ) -> Tuple[list[Dependency], list[ToCache]]:
        return self.statements.adder.add(statement, dep_body)

    def cache_deps(self, deps_to_cache: list[ToCache]):
        for to_cache in deps_to_cache:
            self.dependency_cache.add_dependency(*to_cache)

    def check(self, statement: Statement) -> bool:
        """Symbolically check if a statement is currently considered True."""
        if statement.predicate in [
            PredicateName.FIX_L,
            PredicateName.FIX_C,
            PredicateName.FIX_B,
            PredicateName.FIX_T,
            PredicateName.FIX_P,
        ]:
            return self.dependency_cache.contains(statement)
        if statement.predicate is PredicateName.IND:
            return True
        return self.statements.checker.check(statement)

    def check_goal(self):
        success = False
        if self._goal is not None:
            goal_args = self.map_construction_args_to_objects(self._goal)
            goal_statement = Statement(self._goal.name, goal_args)
            if self.check(goal_statement):
                success = True
        return success

    def additionally_draw(self, name: str, args: list[Point]) -> None:
        """Draw some extra line/circles for illustration purpose."""

        if name in [preds.Circumcenter.NAME]:
            center, point = args[:2]
            circle = self.symbols_graph.new_node(
                Circle, f"({center.name},{point.name})"
            )
            circle.num = CircleNum(center.num, p1=point.num)
            circle.points = center, point

        if name in ["on_circle", "tangent"]:
            center, point = args[-2:]
            circle = self.symbols_graph.new_node(
                Circle, f"({center.name},{point.name})"
            )
            circle.num = CircleNum(center.num, p1=point.num)
            circle.points = center, point

        if name in ["incenter", "excenter", "incenter2", "excenter2"]:
            d, a, b, c = [x for x in args[-4:]]
            a, b, c = sorted([a, b, c], key=lambda x: x.name.lower())
            circle = self.symbols_graph.new_node(
                Circle, f"({d.name},h.{a.name}{b.name})"
            )
            p = d.num.foot(LineNum(a.num, b.num))
            circle.num = CircleNum(d.num, p1=p)
            circle.points = d, a, b, c

        if name in ["cc_tangent"]:
            o, a, w, b = args[-4:]
            c1 = self.symbols_graph.new_node(Circle, f"({o.name},{a.name})")
            c1.num = CircleNum(o.num, p1=a.num)
            c1.points = o, a

            c2 = self.symbols_graph.new_node(Circle, f"({w.name},{b.name})")
            c2.num = CircleNum(w.num, p1=b.num)
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
            circle.num = CircleNum(p1=p1, p2=p2, p3=p3)
            circle.points = (None, None, a, b, c)

        if name in ["2l1c"]:
            a, b, c, o = args[:4]
            a, b, c = sorted([a, b, c], key=lambda x: x.name.lower())
            circle = self.symbols_graph.new_node(
                Circle, f"({o.name},{a.name}{b.name}{c.name})"
            )
            circle.num = CircleNum(p1=a.num, p2=b.num, p3=c.num)
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
        new_points_dep: list[DependencyBody] = []

        # Step 1: check for all dependencies.
        reason = Reason(CONSTRUCTION_RULE)
        for clause_construction in clause.constructions:
            cdef = definitions[clause_construction.name]

            if len(cdef.construction.args) != len(clause_construction.args):
                if len(cdef.construction.args) - len(clause_construction.args) == len(
                    clause.points
                ):
                    clause_construction.args = (
                        tuple(clause.points) + clause_construction.args
                    )
                else:
                    correct_form = " ".join(
                        cdef.points + ["=", clause_construction.name] + cdef.args
                    )
                    raise ValueError("Argument mismatch. " + correct_form)

            mapping = dict(zip(cdef.construction.args, clause_construction.args))
            c_name = (
                preds.MidPoint.NAME
                if clause_construction.name == "midpoint"
                else clause_construction.name
            )
            construction = Construction(
                c_name, clause_construction.args, clause_construction.args_types
            )

            deps: list[Dependency] = []
            for construction in cdef.clause.constructions:
                args = self.symbols_graph.names2points(
                    [mapping[a] for a in construction.args]
                )
                new_points_dep_points.update(args)

                statement = Statement(construction.name, args)
                if not self.check(statement):
                    raise DepCheckFailError(
                        construction.name + " " + " ".join([x.name for x in args])
                    )

                construction_body = DependencyBody(reason=reason, why=[])
                construction_dep = construction_body.build(
                    self.statements.graph, statement
                )
                deps.append(construction_dep)

            dep_body = DependencyBody(reason=reason, why=deps)
            new_points_dep.append(dep_body)

        # Step 2: draw.

        is_total_free = (
            len(clause.constructions) == 1 and clause.constructions[0].name in FREE
        )
        is_semi_free = (
            len(clause.constructions) == 1 and clause.constructions[0].name in INTERSECT
        )

        existing_numerical_points = [p.num for p in existing_points]

        rely_on: set[Point] = set()
        for construction in clause.constructions:
            cdef = definitions[construction.name]
            mapping = dict(zip(cdef.construction.args, construction.args))
            for n in cdef.numerics:
                args = self.map_construction_args_to_objects(n, mapping)
                rely_on.update([a for a in args if isinstance(a, Point)])

        for p in rely_on:
            p.change.update(new_points)

        def range_fn() -> (
            list[Union[PointNum, LineNum, CircleNum, HalfLine, HoleCircle]]
        ):
            to_be_intersected = []
            for c in clause.constructions:
                cdef = definitions[c.name]
                mapping = dict(zip(cdef.construction.args, c.args))
                for n in cdef.numerics:
                    args = self.map_construction_args_to_objects(n, mapping)
                    to_be_intersected += sketch(
                        n.name, args, rnd_generator=self.get_rnd_generator()
                    )

            return to_be_intersected

        def draw_fn() -> list[PointNum]:
            to_be_intersected = range_fn()
            return reduce(
                to_be_intersected,
                existing_numerical_points,
                rnd_generator=self.get_rnd_generator(),
            )

        nums = draw_fn()
        for p, num, num0 in zip(new_points, nums, clause.nums):
            p.co_change = new_points
            if isinstance(num0, PointNum):
                num = num0
            elif isinstance(num0, (tuple, list)):
                x, y = num0
                num = PointNum(x, y)

            p.num = num

        # check two things
        new_points_nums = [p.num for p in new_points]
        if len(existing_numerical_points) > 0:
            if check_too_close_numerical(
                new_points_nums, existing_numerical_points, 0.01
            ):
                raise PointTooCloseError()
            if check_too_far_numerical(new_points_nums, existing_numerical_points, 100):
                raise PointTooFarError()

        # Commit: now that all conditions are passed.
        # add these points to current graph.
        for p in new_points:
            self.symbols_graph.add_node(p)

        for p in new_points:
            why_point: list["Dependency"] = []
            for d in new_points_dep:
                why_point.extend(d.why)
            p.why = why_point  # to generate txt logs.
            p.group = new_points
            p.dep_points = new_points_dep_points
            p.dep_points.update(new_points)
            p.plevel = plevel

        # movement dependency:
        rely_dict_0 = defaultdict(lambda: [])

        for construction in clause.constructions:
            cdef = definitions[construction.name]
            mapping = dict(zip(cdef.construction.args, construction.args))
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
        for construction, dep_body in zip(clause.constructions, new_points_dep):
            cdef = definitions[construction.name]
            mapping = dict(zip(cdef.construction.args, construction.args))

            # not necessary for proofing, but for visualization.
            c_args = self.map_construction_args_to_objects(construction)
            self.additionally_draw(construction, c_args)

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
                    basic_statement = Statement(b.name, args)
                    adds, basic_to_cache = self.resolve_statement_dependencies(
                        basic_statement, dep_body=dep_body
                    )
                    to_cache += basic_to_cache

                    basics.append((basic_statement, dep_body))
                    if adds:
                        added += adds

        assert len(plevel_done) == len(new_points)
        for p in new_points:
            p.basics = basics

        return added, to_cache, plevel

    def map_construction_args_to_objects(
        self, construction: Construction, mapping: Optional[dict[str, str]] = None
    ) -> list[Point | Angle | Ratio]:
        args_objs = []
        for arg, arg_type in zip(construction.args, construction.args_types):
            if mapping and arg in mapping:
                arg = mapping[arg]
            args_objs.append(arg_to_object(arg, arg_type, self.symbols_graph))
        return args_objs


def arg_to_object(arg: str, arg_type: ArgType, symbols_graph: "SymbolsGraph"):
    if arg_type is ArgType.POINT:
        return symbols_graph.get_point(arg)
    elif arg_type is ArgType.ANGLE:
        if "pi/" in arg:
            # pi fraction
            num, den = angle_to_num_den(arg)
        elif arg.endswith("o"):
            # degrees
            num, den = simplify(int(arg[:-1]), 180)
        else:
            raise ValueError("Could not interpret constant angle: %s", arg)
        ang, _ = symbols_graph.get_or_create_const_ang(num, den)
        return ang
    elif arg_type is ArgType.RATIO:
        if "/" not in arg:
            raise ValueError("Cannot interpret %s as a ratio", arg)
        num, den = ratio_to_num_den(arg)
        rat, _ = symbols_graph.get_or_create_const_rat(num, den)
        return rat
    elif arg_type is ArgType.LENGTH:
        return symbols_graph.get_or_create_const_length(float(arg))


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
