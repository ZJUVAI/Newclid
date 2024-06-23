"""Action / Feedback interface

Make all interactions explicit between DeductiveAgent and the Proof state to allow
for independent developpement of different kinds of DeductiveAgent.

"""

from __future__ import annotations
from typing import TYPE_CHECKING, NamedTuple, Optional, Union
from abc import abstractmethod


if TYPE_CHECKING:
    from geosolver.proof import Proof
    from geosolver.geometry import Point
    from geosolver.theorem import Theorem

    from geosolver.dependencies.dependency import Dependency
    from geosolver.match_theorems import MatchCache

    from geosolver.reasoning_engines.engines_interface import Derivation
    from geosolver.problem import Problem

    from geosolver.statement import Statement


Mapping = dict[str, Union["Point", str]]


class ResetAction(NamedTuple):
    """Reset the proof state to its initial state."""


class StopAction(NamedTuple):
    """Stop the proof, often used when an agent is exausted."""


class ApplyTheoremAction(NamedTuple):
    """Apply a theorem with a given mapping of arguments."""

    theorem: "Theorem"
    mapping: Mapping


class MatchAction(NamedTuple):
    """Match a theorem to fing available mapping of arguments."""

    theorem: "Theorem"
    cache: Optional["MatchCache"] = None


class ResolveEngineAction(NamedTuple):
    """Resolve new derivations using a specified reasoning engine."""

    engine_id: str


class ImportDerivationAction(NamedTuple):
    """Import new dependencies from a given derivation."""

    derivation: "Derivation"


class AuxAction(NamedTuple):
    """Add an auxiliary construction."""

    aux_string: str


Action = Union[
    ResetAction,
    StopAction,
    ApplyTheoremAction,
    MatchAction,
    ResolveEngineAction,
    ImportDerivationAction,
    AuxAction,
]


class ResetFeedback(NamedTuple):
    """Feedback from the initial proof state."""

    problem: "Problem"
    available_engines: list[str]
    added: list["Dependency"]
    to_cache: list[tuple["Statement", "Dependency"]]


class StopFeedback(NamedTuple):
    """Feedback from the proof stop."""

    success: bool


class ApplyTheoremFeedback(NamedTuple):
    """Feedback from an applied theorem to the proof."""

    success: bool
    added: list["Dependency"]
    to_cache: list[tuple["Statement", "Dependency"]]


class MatchFeedback(NamedTuple):
    """Feedback from matching a theorem in the current proof state."""

    theorem: "Theorem"
    mappings: list[Mapping]


class DeriveFeedback(NamedTuple):
    """Feedback from resolving a reasoning engine."""

    derivations: list["Derivation"]


class ImportDerivationFeedback(NamedTuple):
    """Feedback from importing a derivation."""

    added: list["Dependency"]
    to_cache: list[tuple["Statement", "Dependency"]]


class AuxFeedback(NamedTuple):
    """Feedback from adding an auxiliary construction."""

    success: bool
    added: list["Dependency"]
    to_cache: list[tuple["Statement", "Dependency"]]


Feedback = Union[
    ResetFeedback,
    StopFeedback,
    ApplyTheoremFeedback,
    MatchFeedback,
    DeriveFeedback,
    ImportDerivationFeedback,
    AuxFeedback,
]


class DeductiveAgent:
    """Common interface for deductive agents"""

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
