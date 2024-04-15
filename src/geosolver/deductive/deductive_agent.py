from __future__ import annotations
from typing import TYPE_CHECKING, NamedTuple, Optional, Union
from abc import abstractmethod

from geosolver.algebraic.algebraic_manipulator import Derivations


if TYPE_CHECKING:
    from geosolver.proof import Proof
    from geosolver.geometry import Point
    from geosolver.problem import Problem, Theorem, Construction
    from geosolver.statement.adder import ToCache
    from geosolver.dependencies.dependency import Dependency
    from geosolver.deductive.match_theorems import MatchCache

Mapping = dict[str, "Point"]


class StopAction(NamedTuple):
    pass


class ApplyTheoremAction(NamedTuple):
    theorem: "Theorem"
    mapping: Mapping
    level: int


class MatchAction(NamedTuple):
    theorem: "Theorem"
    cache: Optional["MatchCache"] = None
    goal: Optional["Construction"] = None


class DeriveAlgebraAction(NamedTuple):
    level: int


Action = Union[StopAction, ApplyTheoremAction, MatchAction, DeriveAlgebraAction]


class StopFeedback(NamedTuple):
    pass


class ApplyTheoremFeedback(NamedTuple):
    success: bool
    added: list["Dependency"]
    to_cache: list["ToCache"]


class MatchFeedback(NamedTuple):
    theorem: "Theorem"
    mappings: list[Mapping]


class DeriveFeedback(NamedTuple):
    derives: Derivations
    eq4s: Derivations


Feedback = Union[StopFeedback, ApplyTheoremFeedback, MatchFeedback, DeriveFeedback]


class DeductiveAgent:
    """Common interface for deductive agents"""

    def __init__(self, problem: "Problem") -> None:
        self.problem = problem
        self.level = None

    @abstractmethod
    def act(self, proof: "Proof", theorems: list["Theorem"]) -> Action:
        """Pict the next action to perform to update the proof state."""

    @abstractmethod
    def remember_effects(self, action: Action, feedback: Feedback):
        """Remember the action effects."""
        pass
