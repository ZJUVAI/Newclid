from __future__ import annotations
from typing import TYPE_CHECKING, Any

from geosolver.reasoning_engines.algebraic_reasoning.tables import (
    AngleTable,
    RatioTable,
    report,
)
from geosolver.reasoning_engines.engines_interface import ReasoningEngine

if TYPE_CHECKING:
    from geosolver.dependency.dependency import Dependency

config: dict[Any, Any] = dict()


class AlgebraicManipulator(ReasoningEngine):
    def __init__(self) -> None:
        self.atable = AngleTable()
        self.rtable = RatioTable()
        self.verbose = config.get("verbose", "")

    def resolve(self, **kwargs: Any) -> list[Dependency]:
        """Derive new algebraic predicates."""
        if "a" in self.verbose:
            report(self.atable.v2e)
        if "r" in self.verbose:
            report(self.rtable.v2e)
        return []
