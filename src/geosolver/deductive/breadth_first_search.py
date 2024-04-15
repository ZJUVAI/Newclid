"""Iterative level by level implementation of DD."""


from __future__ import annotations
import logging
from typing import TYPE_CHECKING, Optional
import time

from geosolver.algebraic.algebraic_manipulator import Derivations
from geosolver.deductive.deductive_agent import (
    ApplyTheoremFeedback,
    DeductiveAgent,
    Action,
    DeriveAlgebraAction,
    DeriveFeedback,
    Feedback,
    Mapping,
    MatchAction,
    MatchFeedback,
    StopAction,
    ApplyTheoremAction,
    StopFeedback,
)
from geosolver.deductive.match_theorems import MatchCache


if TYPE_CHECKING:
    from geosolver.problem import Problem, Theorem
    from geosolver.proof import Proof


class BFSDeductor(DeductiveAgent):
    def __init__(self, problem: "Problem") -> None:
        super().__init__(problem)
        self.level = 0

        self._theorem_mappings: list[tuple["Theorem", list[Mapping]]] = []
        self._actions_taken: set[str] = set()
        self._actions_failed: set[str] = set()

        self._current_mappings: list[Mapping] = []
        self._current_theorem: Optional["Theorem"] = None
        self._level_start_time: float = time.time()

        self._unmatched_theorems: list["Theorem"] = []
        self._match_cache: Optional[MatchCache] = None
        self._any_success_or_new_match_per_level: dict[int, bool] = {}

        self._derivations: Derivations = {}
        self._eq4s: Derivations = {}

    def act(self, proof: "Proof", theorems: list["Theorem"]) -> Action:
        """Deduce new statements by applying
        breath-first search over all theorems one by one."""

        if self._unmatched_theorems:
            # We first match all unmatch theorems of the level
            return self._match_next_theorem(proof)

        if self._current_mappings or self._theorem_mappings:
            # Then we apply all gathered mappings of the level
            theorem, mapping = self._next_theorem_mapping()
            return ApplyTheoremAction(theorem, mapping, self.level)

        if self.level > 0 and not self._any_success_or_new_match_per_level[self.level]:
            # If one full level without new success we have saturated
            return StopAction()

        # Else we derive the algebra of this level and go to the next level
        action = DeriveAlgebraAction(self.level)
        self._next_level(theorems)
        return action

    def remember_effects(self, action: Action, feedback: Feedback):
        if isinstance(feedback, StopFeedback):
            return
        elif isinstance(feedback, ApplyTheoremFeedback):
            assert isinstance(action, ApplyTheoremAction)
            action_hash = _action_str(action.theorem, action.mapping)
            if feedback.success:
                self._any_success_or_new_match_per_level[self.level] = True
                self._actions_taken.add(action_hash)
                if action_hash in self._actions_failed:
                    self._actions_failed.remove(action_hash)
            else:
                self._actions_failed.add(action_hash)

        elif isinstance(feedback, MatchFeedback):
            new_mappings = self._filter_new_mappings(
                feedback.theorem, feedback.mappings
            )
            if len(new_mappings) > 0:
                self._theorem_mappings.append((feedback.theorem, new_mappings))
            for mapping in new_mappings:
                action_hash = _action_str(feedback.theorem, mapping)
                if action_hash not in self._actions_failed:
                    self._any_success_or_new_match_per_level[self.level] = True
        elif isinstance(feedback, DeriveFeedback):
            concat_derivations(self._derivations, feedback.derives)
            concat_derivations(self._eq4s, feedback.eq4s)
        else:
            raise NotImplementedError()

    def _next_theorem_mapping(self) -> tuple[Optional["Theorem"], Optional[Mapping]]:
        if not self._current_mappings:
            new_mapping = self._theorem_mappings.pop(0)
            self._current_theorem, self._current_mappings = new_mapping
        return self._current_theorem, self._current_mappings.pop(0)

    def _filter_new_mappings(self, theorem: "Theorem", mappings: list[Mapping]):
        return [
            mapping
            for mapping in mappings
            if _action_str(theorem, mapping) not in self._actions_taken
        ]

    def _match_next_theorem(self, proof: "Proof"):
        if self._match_cache is None:
            self._match_cache = MatchCache(proof)
        next_theorem = self._unmatched_theorems.pop(0)
        return MatchAction(
            next_theorem,
            cache=self._match_cache,
            goal=self.problem.goal,
        )

    def _next_level(self, theorems: list["Theorem"]):
        self._update_level()
        self._any_success_or_new_match_per_level[self.level] = False
        if self._match_cache is not None:
            self._match_cache.reset()
        self._unmatched_theorems = theorems.copy()

    def _update_level(self):
        if self.level == 0:
            self.level = 1
            self._level_start_time = time.time()
            return

        logging.info(
            f"Level {self.level} exausted"
            f" | Time={ time.time() - self._level_start_time:.1f}s"
        )
        self._level_start_time = time.time()
        self.level += 1


def _action_str(theorem: "Theorem", mapping: Mapping) -> str:
    arg_names = [point.name for arg, point in mapping.items() if isinstance(arg, str)]
    return ".".join([theorem.name] + arg_names)


def concat_derivations(derivations: Derivations, new: Derivations):
    for new_key, new_vals in new.items():
        if new_key not in derivations:
            derivations[new_key] = []
        derivations[new_key] += new_vals
