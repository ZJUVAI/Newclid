from __future__ import annotations
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from geosolver.statements.statement import Statement


class Dependency:
    """Dependency is a directed hyper-edge of the StatementsHyperGraph.

    It links a statement to a list a statements that justify it
    and their own dependencies.

    """

    def __init__(self, statement: "Statement", rule_name: str, level: int):
        self.statement = statement
        self.rule_name = rule_name or ""
        self.level = level
        self.why: list[Dependency] = []
        self.algebra = None
