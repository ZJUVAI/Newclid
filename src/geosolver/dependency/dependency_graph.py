from __future__ import annotations
from typing import TYPE_CHECKING
from geosolver.dependency.symbols_graph import SymbolsGraph

if TYPE_CHECKING:
    from geosolver.dependency.dependency import Dependency
    from geosolver.statement import Statement
    from geosolver.reasoning_engines.algebraic_reasoning.algebraic_manipulator import (
        AlgebraicManipulator,
    )


class DependencyGraph:
    """Hyper graph linking statements by dependencies as hyper-edges."""

    def __init__(self, ar: "AlgebraicManipulator") -> None:
        self.symbols_graph = SymbolsGraph()
        self.hyper_graph: dict[Statement, set[Dependency]] = {}
        self.ar = ar

    def add_edge_to_hyper_graph(self, dep: "Dependency"):
        if dep.statement in self.hyper_graph:
            self.hyper_graph[dep.statement].add(dep)
        else:
            self.hyper_graph[dep.statement] = {dep}

    def get_rank(self, statement: Statement, rank: dict[Statement, int]) -> int:
        ...
        # if statement in rank:
        #     return rank[statement]
        # rank[statement] = -1
        # for dep in self.hyper_graph[statement]:
        #     pass

    def resolve(self, goals: list[Statement]) -> DependencyGraph:
        ...
        # rank : dict[Statement, int] = {}
        # for goal in goals:
        #     self.get_rank(goal)
