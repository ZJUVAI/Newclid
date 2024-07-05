from __future__ import annotations
from typing import TYPE_CHECKING, NamedTuple, Optional


if TYPE_CHECKING:
    from geosolver.statement import Statement


class Dependency(NamedTuple):
    """Dependency is a directed hyper-edge of the StatementsHyperGraph.

    It links a statement to a list of statements that justify it
    and their own dependencies.

    .. image:: ../_static/Images/dependency_building/dependency_structure.svg

    """

    statement: Statement
    reason: Optional[str] = None
    why: Optional[tuple[Statement, ...]] = None

    def add(self):
        dep_graph = self.statement.dep_graph
        dep_graph.ar.ingest(self)
        self.statement.predicate.add(self)
        dep_graph.add_edge_to_hyper_graph(self)
