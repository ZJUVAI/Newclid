"""Implements Deductive Database (DD)."""

from __future__ import annotations
from typing import TYPE_CHECKING, NamedTuple, Optional, Union
from abc import abstractmethod


if TYPE_CHECKING:
    from geosolver.proof import Proof
    from geosolver.geometry import Point
    from geosolver.theorem import Theorem
    from geosolver.statements.adder import ToCache
    from geosolver.dependencies.dependency import Dependency
    from geosolver.match_theorems import MatchCache
    from geosolver.reasoning_engines.algebraic_reasoning.algebraic_manipulator import (
        Derivations,
    )
    from geosolver.problem import Problem
    from geosolver.statements.statement import Statement
    from geosolver.dependencies.empty_dependency import DependencyBuilder


Mapping = dict[str, Union["Point", str]]


class ResetAction(NamedTuple):
    pass


class StopAction(NamedTuple):
    pass


class ApplyTheoremAction(NamedTuple):
    theorem: "Theorem"
    mapping: Mapping


class MatchAction(NamedTuple):
    theorem: "Theorem"
    level: int
    cache: Optional["MatchCache"] = None


class ResolveEngineAction(NamedTuple):
    level: int


class ApplyDerivationAction(NamedTuple):
    statement: "Statement"
    reason: "DependencyBuilder"


class AuxAction(NamedTuple):
    aux_string: str


Action = Union[
    ResetAction,
    StopAction,
    ApplyTheoremAction,
    MatchAction,
    ResolveEngineAction,
    ApplyDerivationAction,
    AuxAction,
]


class ResetFeedback(NamedTuple):
    problem: "Problem"
    added: list["Dependency"]
    to_cache: list["ToCache"]


class StopFeedback(NamedTuple):
    success: bool


class ApplyTheoremFeedback(NamedTuple):
    success: bool
    added: list["Dependency"]
    to_cache: list["ToCache"]


class MatchFeedback(NamedTuple):
    theorem: "Theorem"
    mappings: list[Mapping]


class DeriveFeedback(NamedTuple):
    derives: "Derivations"
    eq4s: "Derivations"


class ApplyDerivationFeedback(NamedTuple):
    added: list["Dependency"]
    to_cache: list["ToCache"]


class AuxFeedback(NamedTuple):
    success: bool
    added: list["Dependency"]
    to_cache: list["ToCache"]


Feedback = Union[
    ResetFeedback,
    StopFeedback,
    ApplyTheoremFeedback,
    MatchFeedback,
    DeriveFeedback,
    ApplyDerivationFeedback,
    AuxFeedback,
]


class DeductiveAgent:
    """Common interface for deductive agents"""

    def __init__(self) -> None:
        self.level = None

    @abstractmethod
    def act(self, proof: "Proof", theorems: list["Theorem"]) -> Action:
        """Pict the next action to perform to update the proof state."""

    @abstractmethod
    def remember_effects(self, action: Action, feedback: Feedback):
        """Remember the action effects."""
        pass

    @abstractmethod
    def reset(self):
        """Resets the agent internal state."""
