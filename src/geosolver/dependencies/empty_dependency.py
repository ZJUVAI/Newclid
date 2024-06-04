from __future__ import annotations
from typing import TYPE_CHECKING

from geosolver.dependencies.dependency import Dependency


if TYPE_CHECKING:
    from geosolver.statements.statement import Statement
    from geosolver.dependencies.why_predicates import StatementsHyperGraph


class EmptyDependency:
    """Empty dependency predicate ready to get filled up."""

    def __init__(self, level: int, rule_name: str):
        self.level = level
        self.rule_name = rule_name or ""
        self.empty = True
        self.why: list[Dependency] = []
        self.trace = None
        self.construction = None

    def populate(self, statement: "Statement") -> Dependency:
        dep = Dependency(statement, self.rule_name, self.level)
        dep.trace2 = self.trace
        dep.why = list(self.why)
        return dep

    def copy(self) -> "EmptyDependency":
        other = EmptyDependency(self.level, self.rule_name)
        other.why = list(self.why)
        return other

    def extend(
        self,
        statements_graph: "StatementsHyperGraph",
        statement_to_extend: "Statement",
        extention_statement: "Statement",
    ) -> "EmptyDependency":
        """Extend the dependency list by (name, args)."""
        dep0 = self.populate(statement_to_extend)
        deps = EmptyDependency(level=self.level, rule_name=None)
        dep = Dependency(extention_statement, None, deps.level)
        dep.why = statements_graph.resolve(dep, None)
        deps.why = [dep0, dep]
        return deps

    def extend_many(
        self,
        statements_graph: "StatementsHyperGraph",
        statement0: "Statement",
        statements: list["Statement"],
    ) -> "EmptyDependency":
        """Extend the dependency list by many name_args."""
        if not statements:
            return self
        dep0 = self.populate(statement0)
        deps = EmptyDependency(level=self.level, rule_name=None)
        deps.why = [dep0]
        for statement in statements:
            dep = Dependency(statement, None, deps.level)
            dep.why = statements_graph.resolve(dep, None)
            deps.why += [dep]
        return deps
