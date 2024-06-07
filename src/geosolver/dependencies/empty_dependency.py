from __future__ import annotations
from typing import TYPE_CHECKING


from geosolver.dependencies.dependency import Reason, Dependency

if TYPE_CHECKING:
    from geosolver.statements.statement import Statement
    from geosolver.dependencies.why_graph import WhyHyperGraph


class EmptyDependency:
    """Empty dependency predicate ready to get filled up."""

    def __init__(self, reason: Reason, level: int):
        assert isinstance(reason, Reason)
        self.reason = reason
        self.level = level
        self.why: list[Dependency] = []

    def populate(self, statement: "Statement") -> Dependency:
        dep = Dependency(statement, self.reason, level=self.level)
        dep.why = self.why.copy()
        return dep

    def copy(self) -> "EmptyDependency":
        other = EmptyDependency(reason=self.reason, level=self.level)
        other.why = self.why.copy()
        return other

    def extend(
        self,
        statements_graph: "WhyHyperGraph",
        statement_to_extend: "Statement",
        extention_statement: "Statement",
        reason: Reason,
    ) -> "EmptyDependency":
        """Extend the dependency list by (name, args)."""
        dep0 = self.populate(statement_to_extend)
        deps = EmptyDependency(reason=reason, level=self.level)
        dep = Dependency(extention_statement, reason=reason, level=deps.level)
        dep.why = statements_graph.resolve(dep, None)
        deps.why = [dep0, dep]
        return deps

    def extend_by_why(
        self,
        statement_to_extend: "Statement",
        why: list[Dependency],
        reason: Reason,
    ) -> "EmptyDependency":
        if not why:
            return self
        dep0 = self.populate(statement_to_extend)
        deps = EmptyDependency(reason=reason, level=self.level)
        deps.why = [dep0] + why
        return deps

    def extend_many(
        self,
        statements_graph: "WhyHyperGraph",
        statement0: "Statement",
        statements: list["Statement"],
        reason: Reason,
    ) -> "EmptyDependency":
        """Extend the dependency list by many name_args."""
        if not statements:
            return self
        dep0 = self.populate(statement0)
        deps = EmptyDependency(reason=reason, level=self.level)
        deps.why = [dep0]
        for statement in statements:
            dep = Dependency(statement, reason=None, level=deps.level)
            dep.why = statements_graph.resolve(dep, None)
            deps.why += [dep]
        return deps
