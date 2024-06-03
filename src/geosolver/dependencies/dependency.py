from __future__ import annotations
from typing import TYPE_CHECKING


from geosolver.problem import CONSTRUCTION_RULE


if TYPE_CHECKING:
    from geosolver.statements.statement import Statement


class Dependency:
    """Dependency is a predicate that other predicates depend on."""

    def __init__(self, statement: "Statement", rule_name: str, level: int):
        self.statement = statement
        self.rule_name = rule_name or ""
        self.level = level
        self.why: list[Dependency] = []

        self._stat = None
        self.trace = None
        self.trace2 = None
        self.algebra = None

    def _find(self, dep_hashed: tuple[str, ...]) -> "Dependency":
        for w in self.why:
            f = w._find(dep_hashed)
            if f:
                return f
            if w.statement.hash_tuple == dep_hashed:
                return w

    def remove_loop(self) -> "Dependency":
        f = self._find(self.statement.hash_tuple)
        if f:
            return f
        return self

    def copy(self) -> "Dependency":
        dep = Dependency(self.statement, self.rule_name, self.level)
        dep.trace = self.trace
        dep.why = list(self.why)
        return dep

    def populate(self, statement: Statement) -> "Dependency":
        assert self.rule_name == CONSTRUCTION_RULE, self.rule_name
        dep = Dependency(statement, self.rule_name, self.level)
        dep.why = list(self.why)
        return dep
