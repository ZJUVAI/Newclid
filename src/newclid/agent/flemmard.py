"""Classical Breadth-First Search based agents."""

from __future__ import annotations
from typing import TYPE_CHECKING

from newclid.agent.agents_interface import (
    DeductiveAgent,
)

if TYPE_CHECKING:
    from newclid.formulations.rule import Rule
    from newclid.proof import ProofState


class Flemmard(DeductiveAgent):
    """Apply Deductive Derivation to exhaustion by Breadth-First Search.

    BFSDD will match and apply all available rules level by level
    until reaching a fixpoint we call exhaustion.

    """

    def __init__(self, proof: "ProofState", rules: list["Rule"]) -> None:
        ...

    def step(self) -> bool:
        return False
