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
        original_statement: "Statement",
        extention_statement: "Statement",
        extention_reason: Reason,
    ) -> "EmptyDependency":
        """Extend the dependency list by (name, args)."""
        original_dep = self.populate(original_statement)
        deps = EmptyDependency(reason=extention_reason, level=self.level)
        dep = Dependency(extention_statement, reason=extention_reason, level=deps.level)
        dep.why = statements_graph.resolve(dep, None)
        deps.why = [original_dep, dep]
        return deps

    def extend_by_why(
        self,
        original_statement: "Statement",
        why: list[Dependency],
        extention_reason: Reason,
    ) -> "EmptyDependency":
        if not why:
            return self
        original_dep = self.populate(original_statement)
        deps = EmptyDependency(reason=extention_reason, level=self.level)
        deps.why = [original_dep] + why
        return deps

    def extend_many(
        self,
        statements_graph: "WhyHyperGraph",
        original_statement: "Statement",
        extention_statements: list["Statement"],
        extention_reason: Reason,
    ) -> "EmptyDependency":
        """Extend the dependency list by many name_args."""
        if not extention_statements:
            return self
        original_dep = self.populate(original_statement)
        deps = EmptyDependency(reason=extention_reason, level=self.level)
        deps.why = [original_dep]
        for extention_statement in extention_statements:
            dep = Dependency(
                extention_statement, reason=extention_reason, level=deps.level
            )
            dep.why = statements_graph.resolve(dep, None)
            deps.why.append(dep)
        return deps
