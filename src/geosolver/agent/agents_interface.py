"""Action / Feedback interface

Make all interactions explicit between DeductiveAgent and the Proof state to allow
for independent developpement of different kinds of DeductiveAgent.

"""

from __future__ import annotations
from typing import TYPE_CHECKING, NamedTuple, Union
from abc import abstractmethod


if TYPE_CHECKING:
    from geosolver.theorem import Theorem

    from geosolver.dependency.dependency import Dependency
    from geosolver.definition.definition import Definition


class ResetAction(NamedTuple):
    """Reset the proof state to its initial state."""


class StopAction(NamedTuple):
    """Stop the proof, often used when an agent is exausted."""


class ApplyTheoremAction(NamedTuple):
    """Apply a theorem with a given mapping of arguments."""

    dep: Dependency


class MatchAction(NamedTuple):
    """Match a theorem to fing available mapping of arguments."""

    theorem: "Theorem"


class ResolveEngineAction(NamedTuple):
    """Resolve new derivations using a specified reasoning engine."""

    engine_id: str


class EmptyAction(NamedTuple):
    """Do nothing"""


Action = Union[
    ResetAction,
    StopAction,
    ApplyTheoremAction,
    MatchAction,
    ResolveEngineAction,
    EmptyAction,
]


class ResetFeedback(NamedTuple):
    """Feedback from the initial proof state."""

    init_added: list["Dependency"]


class StopFeedback(NamedTuple):
    """Feedback from the proof stop."""

    success: bool


class ApplyTheoremFeedback(NamedTuple):
    """Feedback from an applied theorem to the proof."""

    added: list["Dependency"]


class MatchFeedback(NamedTuple):
    """Feedback from matching a theorem in the current proof state."""

    deps: list[Dependency]


class EmptyFeedback(NamedTuple):
    """No feedback"""


Feedback = Union[
    ResetFeedback, StopFeedback, ApplyTheoremFeedback, MatchFeedback, EmptyFeedback
]


class DeductiveAgent:
    """Common interface for deductive agents"""

    @abstractmethod
    def __init__(
        self, defs: dict[str, "Definition"], theorems: list["Theorem"]
    ) -> None:
        pass

    @abstractmethod
    def act(self) -> Action:
        """Pick the next action to perform to update the proof state."""

    @abstractmethod
    def remember_effects(self, action: Action, feedback: Feedback) -> None:
        """Remember the action effects."""

    @abstractmethod
    def reset(self) -> None:
        """Resets the agent internal state."""
