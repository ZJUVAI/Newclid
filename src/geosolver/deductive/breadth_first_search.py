"""Iterative level by level implementation of DD."""


from __future__ import annotations
from enum import Enum, auto
import logging
from typing import TYPE_CHECKING, Optional, Union

from abc import abstractmethod

import time


from geosolver.dependencies.dependency import Dependency
from geosolver.geometry import Angle, Point, Ratio
from geosolver.deductive.match_theorems import match_all_theorems


if TYPE_CHECKING:
    from geosolver.statement.adder import ToCache
    from geosolver.problem import Problem, Theorem
    from geosolver.proof import Proof
    from geosolver.algebraic.algebraic_manipulator import AlgebraicManipulator


class DeductiveAgent:
    def __init__(self, problem: "Problem") -> None:
        self.problem = problem
        self.level = None

    @abstractmethod
    def choose_one_theorem(
        self, proof: "Proof", theorems: list["Theorem"]
    ) -> tuple[list[Dependency], list["ToCache"]]:
        """Deduce new statements in the given proof state using ONE theorem on ONE mapping."""


Mapping = dict[str, Point]


class BFSDeductor(DeductiveAgent):
    class State(Enum):
        EXAUSTED = auto()
        DEDUCTING_ON_LEVEL = auto()
        AR_DEDUCTION = auto()

    def __init__(self, problem: "Problem") -> None:
        super().__init__(problem)
        self.theorem_mappings: list[tuple["Theorem", list[Mapping]]] = {}
        self.actions_taken: set[tuple["Theorem", Mapping]] = set()
        self.current_mappings: tuple[Optional["Theorem"], list[Mapping]] = (None, [])
        self.level = 0
        self._level_start_time = time.time()
        self._state = self.State.EXAUSTED

    def choose_one_theorem(
        self, proof: "Proof", theorems: list["Theorem"]
    ) -> tuple[list[Dependency], list["ToCache"]]:
        """Deduce new statements by applying
        breath-first search over all theorems one by one."""
        add = []
        while not add:
            theorem, mapping = self._next_theorem_mapping(proof, theorems)
            if theorem is None:
                # Exausted all theorems
                return [], []

            add, to_cache, success = proof.apply_theorem(theorem, mapping, self.level)
            if success:
                self.actions_taken.add(_action_str(theorem, mapping))

            conclusion_name, args = theorem.conclusion_name_args(mapping)
            cached_conclusion = proof.dependency_cache.get(conclusion_name, args)
            if cached_conclusion is not None:
                # Skip theorem if already have the conclusion
                add, to_cache = [], []
                continue

        return add, to_cache

    def _next_theorem_mapping(
        self, proof: "Proof", theorems: list["Theorem"]
    ) -> tuple["Theorem", Mapping]:
        if not self.theorem_mappings:
            any_new_mapping = self._match_new_level(proof, theorems)
            if not any_new_mapping:
                return None, None

        theorem, mappings = self.current_mappings
        if not mappings:
            self.current_mappings = self.theorem_mappings.pop(0)

        theorem, mappings = self.current_mappings
        mapping = mappings.pop(0)
        return theorem, mapping

    def _match_new_level(self, proof: "Proof", theorems: list["Theorem"]) -> bool:
        self._update_level()
        theorem2mappings = match_all_theorems(proof, theorems, self.problem.goal)
        self.theorem_mappings = []

        any_new = False
        for theorem, mappings in theorem2mappings.items():
            new_mappings = [
                mapping
                for mapping in mappings
                if _action_str(theorem, mapping) not in self.actions_taken
            ]
            if new_mappings:
                any_new = True
                self.theorem_mappings.append((theorem, new_mappings))

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


def do_deduction(
    deductive_agent: DeductiveAgent,
    proof: "Proof",
    theorems: list["Theorem"],
) -> tuple[
    list[Dependency],
    dict[str, list[tuple[Point, ...]]],
    dict[str, list[tuple[Point, ...]]],
    int,
]:
    """Forward deduce one breadth-first level."""

    added, to_cache = deductive_agent.choose_one_theorem(proof, theorems)
    proof.cache_deps(to_cache)

    branching = len(added)

    # Run AR, but do NOT apply to the proof state (yet).
    for dep in added:
        proof.alegbraic_manipulator.add_algebra(dep)
    derives, eq4s = proof.alegbraic_manipulator.derive_algebra(deductive_agent.level)

    branching += sum([len(x) for x in derives.values()])
    branching += sum([len(x) for x in eq4s.values()])

    return added, derives, eq4s, branching


def create_consts_str(
    alegbraic_manipulator: "AlgebraicManipulator", s: str
) -> Union[Ratio, Angle]:
    if "pi/" in s:
        n, d = s.split("pi/")
        n, d = int(n), int(d)
        p0, _ = alegbraic_manipulator.get_or_create_const_ang(n, d)
    else:
        n, d = s.split("/")
        n, d = int(n), int(d)
        p0, _ = alegbraic_manipulator.get_or_create_const_rat(n, d)
    return p0


def _action_str(theorem: "Theorem", mapping: Mapping) -> str:
    arg_names = [point.name for arg, point in mapping.items() if isinstance(arg, str)]
    return ".".join([theorem.name] + arg_names)
