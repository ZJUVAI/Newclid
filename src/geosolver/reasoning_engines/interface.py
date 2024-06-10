from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from geosolver.dependencies.dependency import Dependency


class ExternalReasoningEngine(ABC):
    @abstractmethod
    def ingest(self, dependency: "Dependency"):
        """Ingest a new dependency from the core reasoning engine."""

    @abstractmethod
    def resolve(self, **kwargs) -> list["Dependency"]:
        """Deduces new statements and their dependencies."""
