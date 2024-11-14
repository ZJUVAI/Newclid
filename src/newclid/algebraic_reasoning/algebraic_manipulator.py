from __future__ import annotations
from typing import Any

from newclid.algebraic_reasoning.tables import Table

config: dict[Any, Any] = dict()


class AlgebraicManipulator:
    def __init__(self) -> None:
        self.verbose = config.get("verbose", "")
        self.atable = Table(verbose=("a" in self.verbose))
        self.rtable = Table(verbose=("r" in self.verbose))
