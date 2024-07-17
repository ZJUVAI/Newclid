from __future__ import annotations
from typing import Any

from geosolver.reasoning_engines.algebraic_reasoning.tables import Table
from geosolver.reasoning_engines.engines_interface import ReasoningEngine

config: dict[Any, Any] = dict()


class AlgebraicManipulator(ReasoningEngine):
    def __init__(self) -> None:
        self.verbose = config.get("verbose", "")
        self.atable = Table(verbose=("a" in self.verbose))
        self.rtable = Table(verbose=("r" in self.verbose))
