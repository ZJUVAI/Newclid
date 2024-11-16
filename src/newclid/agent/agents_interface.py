"""Action / Feedback interface

Make all interactions explicit between DeductiveAgent and the Proof state to allow
for independent developpement of different kinds of DeductiveAgent.

"""

from __future__ import annotations
from abc import ABC, abstractmethod

from newclid.proof import ProofState
from newclid.formulations.rule import Rule


class DeductiveAgent(ABC):
    """Common interface for deductive agents"""

    @abstractmethod
    def __init__(self, proof: ProofState, rules: list[Rule]):
        pass

    @abstractmethod
    def step(self) -> bool:
        """Perform a single reasoning step on the given proof with given rules, and return if the agent is exausted.

        Returns:
            True if the agent is considered exausted, False otherwise.
        """
