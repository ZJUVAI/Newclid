from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from geosolver.predicates.predicate import Predicate

if TYPE_CHECKING:
    from geosolver.dependency.dependency import Dependency


class ReasoningEngine(ABC):
    @abstractmethod
    def ingest(self, dep: "Dependency"):
        """Ingest a new dependency from the core reasoning engine."""

    @abstractmethod
    def resolve(self, **kwargs: Any) -> list["Dependency"]:
        """Deduces new statements and their initialized dependencies."""

    @abstractmethod
    def check(self, predicate: type[Predicate], args: tuple[Any, ...]) -> bool:
        """Check if the statement is true"""

    @abstractmethod
    def why(
        self, predicate: type[Predicate], args: tuple[Any, ...]
    ) -> list["Dependency"]:
        """Why the statement is true"""
