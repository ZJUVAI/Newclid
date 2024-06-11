from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from geosolver.agent.interface import DeriveFeedback
from geosolver.dependencies.empty_dependency import EmptyDependency
from geosolver.predicates import Predicate
from geosolver.statements.statement import Statement

if TYPE_CHECKING:
    from geosolver.dependencies.dependency import Dependency

Derivation = tuple[Statement, EmptyDependency]
Derivations = dict[Predicate, list[Derivation]]


class ReasoningEngine(ABC):
    @abstractmethod
    def ingest(self, dependency: "Dependency"):
        """Ingest a new dependency from the core reasoning engine."""

    @abstractmethod
    def resolve(self, **kwargs) -> DeriveFeedback:
        """Deduces new statements and their initialized dependencies."""
