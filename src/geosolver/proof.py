"""Implements the proof state."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional, Union
import logging

from geosolver.definition.clause import Clause
from geosolver.dependency.dependency_graph import DependencyGraph
from geosolver.dependency.symbols import Point
from geosolver.numerical.geometries import (
    InvalidIntersectError,
    InvalidQuadSolveError,
    ObjNum,
    PointNum,
    reduce,
)
from geosolver.reasoning_engines.algebraic_reasoning.algebraic_manipulator import (
    AlgebraicManipulator,
)
from geosolver.statement import Statement
from geosolver.definition.definition import Definition
from geosolver.agent.agents_interface import (
    Action,
    EmptyAction,
    EmptyFeedback,
    Feedback,
    ApplyTheoremAction,
    ApplyTheoremFeedback,
    MatchAction,
    MatchFeedback,
    ResetFeedback,
    StopAction,
    StopFeedback,
)
from geosolver.match_theorems import Matcher, translate_sentence

from geosolver.numerical.distances import (
    PointTooCloseError,
    PointTooFarError,
    check_too_far_numerical,
    check_too_close_numerical,
)
from geosolver.numerical.sketch import sketch

from geosolver.problem import Problem
from geosolver.dependency.dependency import BY_CONSTRUCTION, Dependency
from geosolver.tools import atomize

if TYPE_CHECKING:
    from numpy.random import Generator


class ConstructionError(Exception):
    pass


class Proof:
    """Object representing the proof state."""

    def __init__(
        self,
        problem: Problem,
        defs: dict[str, Definition],
        runtime_cache_path: Optional[Path],
        rng: "Generator",
    ):
        self.dep_graph = DependencyGraph(AlgebraicManipulator())
        self.symbols_graph = self.dep_graph.symbols_graph
        self.goals: list[Statement] = []
        self.problem: Problem = problem
        self.defs: dict[str, Definition] = defs
        self._init_added: list[Dependency] = []
        self._ACTION_TYPE_TO_STEP: dict[type[Action], Callable[..., Feedback]] = {
            MatchAction: self._step_match_theorem,
            ApplyTheoremAction: self._step_apply_theorem,
            StopAction: self._step_stop,
            EmptyAction: self._idle,
        }
        self.runtime_cache_path = runtime_cache_path
        self.rng = rng
        self.matcher = Matcher(self.dep_graph, self.runtime_cache_path, self.rng)

    @classmethod
    def build_problem(
        cls,
        problem: Problem,
        defs: dict[str, Definition],
        runtime_cache_path: Optional[Path],
        max_attempts: int = 10000,
        *,
        rng: "Generator",
    ) -> Proof:
        """Build a problem into a Proof state object."""
        logging.info(f"Building proof from problem '{problem.name}': {problem}")

        err = ConstructionError(f"Construction failed {max_attempts} times")
        for _ in range(max_attempts):
            # Search for coordinates that checks premises conditions numerically.
            try:
                proof = Proof(
                    problem=problem,
                    defs=defs,
                    runtime_cache_path=runtime_cache_path,
                    rng=rng,
                )
                added: list[Dependency] = []
                for construction in problem.constructions:
                    adds = proof.add_construction(construction)
                    for add in adds:
                        if not add.statement.check_numerical():
                            raise ConstructionError(
                                "This is probably because the construction itself is wrong"
                            )
                        add.add()
                    added += adds

            except (
                InvalidIntersectError,
                InvalidQuadSolveError,
                ConstructionError,
                PointTooCloseError,
                PointTooFarError,
            ) as e:
                err = e
                continue

            if not problem.goals:
                break

            all_check = True
            proof.goals = [
                Statement.from_tokens(goal, proof.dep_graph) for goal in problem.goals
            ]
            for goal in proof.goals:
                if not goal.check_numerical():
                    all_check = False
                    break
            if all_check:
                break

        else:
            raise err

        proof._init_added = added

        return proof

    def step(self, action: Action) -> Feedback:
        return self._ACTION_TYPE_TO_STEP[type(action)](action)

    def _step_match_theorem(self, action: MatchAction) -> MatchFeedback:
        return MatchFeedback(deps=list(self.matcher.match_theorem(action.theorem)))

    def _step_apply_theorem(self, action: ApplyTheoremAction) -> ApplyTheoremFeedback:
        added = self._apply_theorem(action.dep)
        return ApplyTheoremFeedback(added)

    def _apply_theorem(self, dep: Dependency) -> list[Dependency]:
        if dep.statement in dep.statement.dep_graph.hyper_graph:
            return []
        dep.add()
        return [dep]

    def _step_stop(self, action: StopAction) -> StopFeedback:
        return StopFeedback(success=self.check_goals())

    def _idle(self, action: EmptyAction) -> EmptyFeedback:
        return EmptyFeedback()

    def init(self) -> ResetFeedback:
        return ResetFeedback(self._init_added)

    def check_goals(self) -> bool:
        if not self.goals:
            return False
        for goal in self.goals:
            if not goal.check():
                return False
        return True

    def add_construction(self, construction: Clause) -> list[Dependency]:
        """Add a new clause of construction, e.g. a new excenter."""
        adds: list[Dependency] = []
        numerics: list[tuple[str, ...]] = []
        existing_points = self.symbols_graph.nodes_of_type(Point)

        for constr_sentence in construction.sentences:
            cdef = self.defs[constr_sentence[0]]
            if len(constr_sentence) == len(cdef.declare):
                mapping = dict(zip(cdef.declare[1:], constr_sentence[1:]))
            else:
                assert len(constr_sentence) + len(construction.points) == len(
                    cdef.declare
                )
                mapping = dict(
                    zip(cdef.declare[1:], construction.points + constr_sentence[1:])
                )

            for premise in cdef.require.sentences:
                if len(premise) == 0:
                    continue
                statement = Statement.from_tokens(
                    translate_sentence(mapping, premise), self.dep_graph
                )
                if not statement.check_numerical():
                    raise ConstructionError(construction)

            for bs in cdef.basics:
                for t in bs.sentences:
                    if len(t) == 0:
                        continue
                    statement = Statement.from_tokens(
                        translate_sentence(mapping, t), self.dep_graph
                    )
                    adds.append(Dependency.mk(statement, BY_CONSTRUCTION, ()))
            for n in cdef.numerics:
                numerics.append(tuple(mapping[a] if a in mapping else a for a in n))

        point_names: list[str] = []
        fix_point_postions: list[Optional[PointNum]] = []
        for s in construction.points:
            if "@" in s:
                name, pos = atomize(s, "@")
                point_names.append(name)
                x, y = atomize(pos, "_")
                fix_point_postions.append(PointNum(x, y))
            else:
                point_names.append(s)
                fix_point_postions.append(None)
        new_points = self.symbols_graph.names2points(point_names)
        for p in new_points:
            if p in existing_points:
                raise Exception("The construction is illegal")

        # Step 2: draw.

        def draw_fn() -> list[PointNum]:
            to_be_intersected: list[ObjNum] = []
            for n in numerics:
                args: list[Union[PointNum, str]] = []
                for t in n[1:]:
                    if str.isalpha(t[0]):
                        args.append(self.symbols_graph.names2points([t])[0].num)
                    else:
                        args.append(t)
                to_be_intersected += sketch(n[0], tuple(args), self.rng)

            return reduce(
                to_be_intersected, [p.num for p in existing_points], rng=self.rng
            )

        new_numerical_points = draw_fn()
        for p, num, num0 in zip(new_points, new_numerical_points, fix_point_postions):
            p.num = num0 or num

        # check two things
        existing_numerical_points = [p.num for p in existing_points]
        if check_too_close_numerical(
            new_numerical_points, existing_numerical_points, 0.01
        ):
            raise PointTooCloseError()
        if check_too_far_numerical(
            new_numerical_points, existing_numerical_points, 100
        ):
            raise PointTooFarError()

        return adds
