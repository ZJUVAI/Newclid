"""Iterative level by level implementation of DD."""


from __future__ import annotations
import logging
from typing import TYPE_CHECKING, Optional
import time

from geosolver.deductive.deductive_agent import (
    DeductiveAgent,
    Action,
    Mapping,
    StopAction,
    ApplyTheoremAction,
)
from geosolver.deductive.match_theorems import match_all_theorems

if TYPE_CHECKING:
    from geosolver.statement.adder import ToCache
    from geosolver.problem import Problem, Theorem
    from geosolver.proof import Proof
    from geosolver.dependencies.dependency import Dependency


class BFSDeductor(DeductiveAgent):
    def __init__(self, problem: "Problem") -> None:
        super().__init__(problem)
        self.level = 0

        self._theorem_mappings: list[tuple["Theorem", list[Mapping]]] = {}
        self._actions_taken: set[tuple["Theorem", Mapping]] = set()
        self._current_mappings: tuple[Optional["Theorem"], list[Mapping]] = (None, [])
        self._level_start_time = time.time()

    def act(self, proof: "Proof", theorems: list["Theorem"]) -> Action:
        """Deduce new statements by applying
        breath-first search over all theorems one by one."""
        theorem, mapping = self._next_theorem_mapping(proof, theorems)
        if theorem is None:
            # Exausted all theorems
            return StopAction()
        return ApplyTheoremAction(theorem, mapping, self.level)

    def remember_effects(
        self,
        action: Action,
        success: bool,
        added: list[Dependency],
        to_cache: ToCache,
    ):
        if isinstance(action, StopAction):
            return
        elif isinstance(action, ApplyTheoremAction):
            if success:
                self._actions_taken.add(_action_str(action.theorem, action.mapping))
        else:
            raise NotImplementedError()

    def _next_theorem_mapping(
        self, proof: "Proof", theorems: list["Theorem"]
    ) -> tuple[Optional["Theorem"], Optional[Mapping]]:
        if not self._theorem_mappings:
            any_new_mapping = self._match_new_level(proof, theorems)
            if not any_new_mapping:
                return None, None

        theorem, mappings = self._current_mappings
        if not mappings:
            self._current_mappings = self._theorem_mappings.pop(0)

        theorem, mappings = self._current_mappings
        mapping = mappings.pop(0)
        return theorem, mapping

    def _match_new_level(self, proof: "Proof", theorems: list["Theorem"]) -> bool:
        self._update_level()
        theorem2mappings = match_all_theorems(proof, theorems, self.problem.goal)
        self._theorem_mappings = []

        any_new = False
        for theorem, mappings in theorem2mappings.items():
            new_mappings = [
                mapping
                for mapping in mappings
                if _action_str(theorem, mapping) not in self._actions_taken
            ]
            if new_mappings:
                any_new = True
                self._theorem_mappings.append((theorem, new_mappings))

        return any_new

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
