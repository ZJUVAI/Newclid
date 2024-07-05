"""Classical Breadth-First Search based agents.

"""

from __future__ import annotations
import logging
from typing import TYPE_CHECKING

from geosolver.agent.agents_interface import (
    ApplyTheoremAction,
    DeductiveAgent,
    Action,
    EmptyAction,
    Feedback,
    MatchAction,
    MatchFeedback,
    StopAction,
)

if TYPE_CHECKING:
    from geosolver.theorem import Theorem
    from geosolver.definition.definition import Definition
    from geosolver.dependency.dependency import Dependency


class BFSDDAR(DeductiveAgent):
    """Apply Deductive Derivation to exhaustion by Breadth-First Search.

    BFSDD will match and apply all available rules level by level
    until reaching a fixpoint we call exaustion.

    """

    def __init__(
        self, defs: dict[str, "Definition"], theorems: list["Theorem"]
    ) -> None:
        self.defs = defs
        self.theorems = theorems
        self.theorem_buffer: list[Theorem] = []
        self.application_buffer: list[Dependency] = []
        self.applied_any = 10000

    def act(self) -> Action:
        if self.application_buffer:
            self.applied_any = 10000
            return ApplyTheoremAction(self.application_buffer.pop())
        if self.theorem_buffer:
            return MatchAction(self.theorem_buffer.pop())
        else:
            if not self.applied_any:
                return StopAction()
            self.theorem_buffer = list(self.theorems)
            logging.info("bfsddar : reload")
            self.applied_any = False
            return EmptyAction()

    def remember_effects(self, action: Action, feedback: Feedback) -> None:
        if isinstance(feedback, MatchFeedback):
            self.application_buffer.extend(feedback.deps)

    def reset(self):
        self.theorem_buffer = []
        self.application_buffer = []
        self.applied_any = True
