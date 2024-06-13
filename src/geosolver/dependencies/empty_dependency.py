from __future__ import annotations
from typing import TYPE_CHECKING


from geosolver.dependencies.dependency import Reason, Dependency

if TYPE_CHECKING:
    from geosolver.statements.statement import Statement
    from geosolver.dependencies.why_graph import WhyHyperGraph


class DependencyBuilder:
    """A builder to construct a subgraph of reasoning."""

    def __init__(self, reason: Reason, level: int, why: tuple[Dependency]):
        assert isinstance(reason, Reason)
        self.reason: Reason = reason
        self.level: int = level
        self.why: tuple[Dependency] = tuple(why)

    def extend(
        self,
        statements_graph: "WhyHyperGraph",
        statement: "Statement",
        extention_statement: "Statement",
        extention_reason: Reason,
    ) -> "DependencyBuilder":
        """Extend the dependency list by (name, args)."""
        original_dep = statements_graph.build_dependency(statement, builder=self)
        extension_dep = statements_graph.build_resolved_dependency(
            extention_statement, level=self.level
        )
        if extension_dep is None:
            raise
        return DependencyBuilder(
            reason=extention_reason,
            level=self.level,
            why=(original_dep, extension_dep),
        )

    def extend_by_why(
        self,
        statements_graph: "WhyHyperGraph",
        original_statement: "Statement",
        why: list[Dependency],
        extention_reason: Reason,
    ) -> "DependencyBuilder":
        if not why:
            return self
        original_dep = statements_graph.build_dependency(
            original_statement, builder=self
        )
        dep_builder = DependencyBuilder(
            reason=extention_reason,
            level=self.level,
            why=(original_dep, *why),
        )
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
        original_dep = statements_graph.build_dependency(
            original_statement, builder=self
        )
        extended_dep = [
            statements_graph.build_resolved_dependency(e_statement, level=self.level)
            for e_statement in extention_statements
        ]
        return DependencyBuilder(
            reason=extention_reason,
            level=self.level,
            why=(original_dep, *extended_dep),
        )

    def copy(self) -> "DependencyBuilder":
        return DependencyBuilder(reason=self.reason, level=self.level, why=self.why)

    def __eq__(self, value: object) -> bool:
        if not isinstance(value, DependencyBuilder):
            return False
        return self.reason == value.reason and self.why == value.why
