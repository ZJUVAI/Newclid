from __future__ import annotations
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from geosolver.statement import Statement

BY_CONSTRUCTION = "Construction"


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
        if not self.statement.check_numerical():
            raise Exception("Adding a statement that is numerically false")
        dep_graph = self.statement.dep_graph
        s = dep_graph.hyper_graph.get(self.statement)
        if s is not None and self in s:
            return
        if s is None:
            dep_graph.hyper_graph[self.statement] = {self}
        else:
            s.add(self)
        self.statement.predicate.add(self)

    def with_new(self, statement: Statement) -> Dependency:
        return Dependency(statement, self.reason, self.why)

    @classmethod
    def mk(
        cls, statement: Statement, reason: str, why: tuple[Statement, ...]
    ) -> Dependency:
        why = tuple(sorted(set(why), key=lambda x: hash(x)))
        return Dependency(statement, reason, why)

    def pretty(self):
        return f"{self.statement.pretty()} <={self.reason} {', '.join(s.pretty() for s in self.why)}"
