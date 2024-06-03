from __future__ import annotations
from typing import TYPE_CHECKING

from geosolver.dependencies.dependency import Dependency
from geosolver.dependencies.why_predicates import why_dependency

if TYPE_CHECKING:
    from geosolver.proof import Proof
    from geosolver.dependencies.caching import DependencyCache
    from geosolver.symbols_graph import SymbolsGraph
    from geosolver.statements.checker import StatementChecker
    from geosolver.statements.statement import Statement


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
        proof: "Proof",
        statement0: "Statement",
        statement: "Statement",
    ) -> "EmptyDependency":
        """Extend the dependency list by (name, args)."""
        dep0 = self.populate(statement0)
        deps = EmptyDependency(level=self.level, rule_name=None)
        dep = Dependency(statement, None, deps.level)
        dep.why = why_dependency(
            dep,
            proof.symbols_graph,
            proof.statements.checker,
            proof.dependency_cache,
            None,
        )
        deps.why = [dep0, dep]
        return deps

    def extend_many(
        self,
        symbols_graph: "SymbolsGraph",
        statements_checker: "StatementChecker",
        dependency_cache: "DependencyCache",
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
            dep.why = why_dependency(
                dep,
                symbols_graph,
                statements_checker,
                dependency_cache,
                None,
            )
            deps.why += [dep]
        return deps
