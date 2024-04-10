from __future__ import annotations
from typing import TYPE_CHECKING, NamedTuple, Union
from abc import abstractmethod

if TYPE_CHECKING:
    from geosolver.proof import Proof
    from geosolver.geometry import Point
    from geosolver.problem import Problem, Theorem
    from geosolver.statement.adder import ToCache
    from geosolver.dependencies.dependency import Dependency

Mapping = dict[str, "Point"]


class StopAction(NamedTuple):
    pass


class ApplyTheoremAction(NamedTuple):
    theorem: "Theorem"
    mapping: Mapping
    level: int


Action = Union[StopAction, ApplyTheoremAction]


class DeductiveAgent:
    """Common interface for deductive agents"""

    def __init__(self, problem: "Problem") -> None:
        self.problem = problem
        self.level = None

    @abstractmethod
    def act(self, proof: "Proof", theorems: list["Theorem"]) -> Action:
        """Pict the next action to perform to update the proof state."""

    @abstractmethod
    def remember_effects(
        self,
        action: Action,
        success: bool,
        added: list["Dependency"],
        to_cache: list[ToCache],
    ):
        """Remember the action effects."""
        pass
