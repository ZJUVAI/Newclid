"""Classical Breadth-First Search based agents."""

from __future__ import annotations
from typing import TYPE_CHECKING

from geosolver.agent.agents_interface import (
    DeductiveAgent,
)

if TYPE_CHECKING:
    from geosolver.rule import Rule
    from geosolver.proof import Proof


class Flemmard(DeductiveAgent):
    """Apply Deductive Derivation to exhaustion by Breadth-First Search.

    BFSDD will match and apply all available rules level by level
    until reaching a fixpoint we call exaustion.

    """

    def __init__(self, proof: "Proof", rules: list["Rule"]) -> None:
        ...

    def step(self) -> bool:
        return False
