"""Action / Feedback interface

Make all interactions explicit between DeductiveAgent and the Proof state to allow
for independent developpement of different kinds of DeductiveAgent.

"""

from __future__ import annotations
from typing import TYPE_CHECKING
from abc import ABC, abstractmethod

from geosolver.proof import Proof
from geosolver.rule import Rule


if TYPE_CHECKING:
    ...


class DeductiveAgent(ABC):
    """Common interface for deductive agents"""

    @abstractmethod
    def __init__(self, proof: Proof, rules: list[Rule]) -> None:
        pass

    @abstractmethod
    def step(self) -> bool:
        ...
