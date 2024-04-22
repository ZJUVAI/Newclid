"""Implements Deductive Database (DD)."""
from __future__ import annotations
from typing import TYPE_CHECKING, NamedTuple, Optional, Union
from abc import abstractmethod


if TYPE_CHECKING:
    from geosolver.proof import Proof
    from geosolver.geometry import Point
    from geosolver.problem import Theorem
    from geosolver.statement.adder import ToCache
    from geosolver.dependencies.dependency import Dependency
    from geosolver.match_theorems import MatchCache
    from geosolver.algebraic.algebraic_manipulator import Derivations

Mapping = dict[str, "Point"]


class StopAction(NamedTuple):
    pass


class ApplyTheoremAction(NamedTuple):
    theorem: "Theorem"
    mapping: Mapping


class MatchAction(NamedTuple):
    theorem: "Theorem"
    level: int
    cache: Optional["MatchCache"] = None


class DeriveAlgebraAction(NamedTuple):
    level: int


class ApplyDerivationAction(NamedTuple):
    derivation_name: str
    derivation_arguments: tuple["Point", ...]


Action = Union[
    StopAction,
    ApplyTheoremAction,
    MatchAction,
    DeriveAlgebraAction,
    ApplyDerivationAction,
]


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


Feedback = Union[
    StopFeedback,
    ApplyTheoremFeedback,
    MatchFeedback,
    DeriveFeedback,
    ApplyDerivationFeedback,
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
