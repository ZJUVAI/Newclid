from __future__ import annotations
from typing import TYPE_CHECKING


from geosolver.dependencies.dependency import Reason, Dependency

if TYPE_CHECKING:
    from geosolver.statements.statement import Statement
    from geosolver.dependencies.why_graph import WhyHyperGraph


class DependencyBody:
    """Statement-less body of a dependency that can be extended
    before becoming a dependency."""

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
    ) -> "DependencyBody":
        """Extend the dependency list by (name, args)."""
        original_dep = statements_graph.build_dependency(statement, body=self)
        extension_dep = statements_graph.build_resolved_dependency(
            extention_statement, level=self.level
        )
        if extension_dep is None:
            raise
        return DependencyBody(
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
    ) -> "DependencyBody":
        if not why:
            return self
        original_dep = statements_graph.build_dependency(original_statement, body=self)
        return DependencyBody(
            reason=extention_reason,
            level=self.level,
            why=(original_dep, *why),
        )

    def extend_many(
        self,
        statements_graph: "WhyHyperGraph",
        original_statement: "Statement",
        extention_statements: list["Statement"],
        extention_reason: Reason,
    ) -> "DependencyBody":
        """Extend the dependency list by many name_args."""
        if not extention_statements:
            return self
        original_dep = statements_graph.build_dependency(original_statement, body=self)
        extended_dep = [
            statements_graph.build_resolved_dependency(e_statement, level=self.level)
            for e_statement in extention_statements
        ]
        return DependencyBody(
            reason=extention_reason,
            level=self.level,
            why=(original_dep, *extended_dep),
        )

    def copy(self) -> "DependencyBody":
        return DependencyBody(reason=self.reason, level=self.level, why=self.why)

    def __eq__(self, value: object) -> bool:
        if not isinstance(value, DependencyBody):
            return False
        return self.reason == value.reason and set(self.why) == set(value.why)
