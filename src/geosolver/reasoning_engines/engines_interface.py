from abc import ABC
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from geosolver.dependency.dependency import Dependency
    from geosolver.statement import Statement


class ReasoningEngine(ABC):
    def ingest(self, dep: "Dependency") -> None:
        """Ingest a new dependency from the core reasoning engine."""
        raise NotImplementedError

    def resolve(self, **kwargs: Any) -> list["Dependency"]:
        """Deduces new statements and their initialized dependencies."""
        raise NotImplementedError

    def check(self, statement: "Statement") -> bool:
        """Check if the statement is true"""
        raise NotImplementedError

    def why(self, statement: "Statement") -> list["Dependency"]:
        """Why the statement is true"""
        raise NotImplementedError
