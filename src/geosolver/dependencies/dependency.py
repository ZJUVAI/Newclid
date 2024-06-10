from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from geosolver.theorem import Theorem


if TYPE_CHECKING:
    from geosolver.statements.statement import Statement
    from geosolver.statements.adder import IntrinsicRules
    from geosolver.reasoning_engines.algebraic_reasoning import AlgebraicRules


@dataclass
class Reason:
    object: Theorem | "AlgebraicRules" | "IntrinsicRules" | str

    def __post_init__(self):
        if isinstance(self.object, Theorem):
            self.name = self.object.rule_name
        elif isinstance(self.object, str):
            self.name = self.object
        else:
            self.name = self.object.value


class Dependency:
    """Dependency is a directed hyper-edge of the StatementsHyperGraph.

    It links a statement to a list a statements that justify it
    and their own dependencies.

    """

    def __init__(self, statement: "Statement", reason: Optional[Reason], level: int):
        self.statement = statement
        self.reason = reason
        self.level = level

        self.why: list[Dependency] = []
        self.algebra = None
