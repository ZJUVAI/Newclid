"""Classical Breadth-First Search based agents."""

from __future__ import annotations
import logging
from typing import TYPE_CHECKING

from geosolver.agent.agents_interface import (
    DeductiveAgent,
)
from geosolver.proof import Proof

if TYPE_CHECKING:
    from geosolver.theorem import Theorem
    from geosolver.dependency.dependency import Dependency


class BFSDDAR(DeductiveAgent):
    """Apply Deductive Derivation to exhaustion by Breadth-First Search.

    BFSDD will match and apply all available rules level by level
    until reaching a fixpoint we call exaustion.

    """

    def __init__(self, proof: Proof, theorems: list["Theorem"]) -> None:
        self.proof = proof
        self.theorems = theorems
        self.theorem_buffer: list[Theorem] = []
        self.application_buffer: list[Dependency] = []
        self.hope = True

    def step(self) -> bool:
        if self.theorem_buffer:
            theorem = self.theorem_buffer.pop()
            logging.info("bfsddar matching" + str(theorem))
            deps = self.proof.match_theorem(theorem)
            logging.info("bfsddar matched " + str(len(deps)))
            self.application_buffer.extend(deps)
        elif self.application_buffer:
            # logging.info("bfsddar : apply")
            dep = self.application_buffer.pop()
            if self.proof.apply_theorem(dep):
                self.hope = True
        else:
            if not self.hope:
                return False
            self.hope = False
            self.theorem_buffer = list(self.theorems)
            logging.info("bfsddar : reload")
        return True
