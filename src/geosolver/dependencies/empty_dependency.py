from __future__ import annotations
from typing import TYPE_CHECKING


from geosolver.dependencies.dependency import Reason, Dependency

if TYPE_CHECKING:
    from geosolver.statements.statement import Statement
    from geosolver.dependencies.why_graph import WhyHyperGraph


class DependencyBuilder:
    """A builder to construct a subgraph of reasoning."""

    def __init__(self, reason: Reason, level: int):
        assert isinstance(reason, Reason)
        self.reason = reason
        self.level = level
        self.why: list[Dependency] = []

    def add_head(self, statement: "Statement") -> Dependency:
        dep = Dependency(statement, self.reason, level=self.level)
        dep.why = self.why.copy()
        return dep

    def extend(
        self,
        statements_graph: "WhyHyperGraph",
        original_statement: "Statement",
        extention_statement: "Statement",
        extention_reason: Reason,
    ) -> "DependencyBuilder":
        """Extend the dependency list by (name, args)."""
        original_dep = self.add_head(original_statement)
        dep_builder = DependencyBuilder(reason=extention_reason, level=self.level)
        dep = Dependency(
            extention_statement, reason=extention_reason, level=dep_builder.level
        )
        dep.why = statements_graph.resolve(dep, None)
        dep_builder.why = [original_dep, dep]
        return dep_builder

    def extend_by_why(
        self,
        original_statement: "Statement",
        why: list[Dependency],
        extention_reason: Reason,
    ) -> "DependencyBuilder":
        if not why:
            return self
        original_dep = self.add_head(original_statement)
        dep_builder = DependencyBuilder(reason=extention_reason, level=self.level)
        dep_builder.why = [original_dep] + why
        return dep_builder

    def extend_many(
        self,
        statements_graph: "WhyHyperGraph",
        original_statement: "Statement",
        extention_statements: list["Statement"],
        extention_reason: Reason,
    ) -> "DependencyBuilder":
        """Extend the dependency list by many name_args."""
        if not extention_statements:
            return self
        original_dep = self.add_head(original_statement)
        dep_builder = DependencyBuilder(reason=extention_reason, level=self.level)
        dep_builder.why = [original_dep]
        for extention_statement in extention_statements:
            dep = Dependency(
                extention_statement, reason=extention_reason, level=dep_builder.level
            )
            dep.why = statements_graph.resolve(dep, None)
            dep_builder.why.append(dep)
        return dep_builder

    def copy(self) -> "DependencyBuilder":
        other = DependencyBuilder(reason=self.reason, level=self.level)
        other.why = self.why.copy()
        return other
