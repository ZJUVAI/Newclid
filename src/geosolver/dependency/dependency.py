from __future__ import annotations
from typing import TYPE_CHECKING, NamedTuple


if TYPE_CHECKING:
    from geosolver.statement import Statement

CONSTRUCTION = "cstr"


class Dependency(NamedTuple):
    """Dependency is a directed hyper-edge of the StatementsHyperGraph.

    It links a statement to a list of statements that justify it
    and their own dependencies.

    .. image:: ../_static/Images/dependency_building/dependency_structure.svg

    """

    statement: Statement
    reason: str
    why: tuple[Statement, ...]

    def add(self):
        dep_graph = self.statement.dep_graph
        dep_graph.add_edge_to_hyper_graph(self)
        self.statement.predicate.add(self)

    def with_new(self, statement: Statement) -> Dependency:
        return Dependency(statement, self.reason, self.why)

    @classmethod
    def mk(
        cls, statement: Statement, reason: str, why: tuple[Statement, ...]
    ) -> Dependency:
        why = tuple(sorted(why, key=lambda x: hash(x)))
        return Dependency(statement, reason, why)
