"""Classical Breadth-First Search based agents."""

from __future__ import annotations
import logging
from typing import TYPE_CHECKING

from newclid.agent.agents_interface import (
    DeductiveAgent,
)
from newclid.proof import ProofState

if TYPE_CHECKING:
    from newclid.formulations.rule import Rule
    from newclid.dependencies.dependency import Dependency


class BFSDDAR(DeductiveAgent):
    """Apply Deductive Derivation to exhaustion by Breadth-First Search.

    BFSDD will match and apply all available rules level by level
    until reaching a fixpoint we call exhaustion.

    """

    def __init__(self, proof: ProofState, rules: list["Rule"]):
        self.proof = proof
        self.rules = rules
        self.rule_buffer: list[Rule] = []
        self.application_buffer: list[Dependency] = []
        self.hope = True

    def step(self) -> bool:
        if self.proof.check_goals():
            return False
        if self.rule_buffer:
            theorem = self.rule_buffer.pop()
            logging.info("bfsddar matching" + str(theorem))
            deps = self.proof.match_theorem(theorem)
            logging.info("bfsddar matched " + str(len(deps)))
            self.application_buffer.extend(deps)
        elif self.application_buffer:
            dep = self.application_buffer.pop()
            # logging.info(f"bfsddar : apply {dep}")
            if self.proof.apply_dep(dep):
                self.hope = True
        else:
            if not self.hope:
                return False
            self.hope = False
            self.rule_buffer = list(self.rules)
            logging.info("bfsddar : reload")
        return True
