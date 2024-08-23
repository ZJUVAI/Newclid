from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING
from geosolver.dependencies.dependency import IN_PREMISES
from geosolver.dependencies.symbols_graph import SymbolsGraph
from pyvis.network import Network  # type: ignore

from geosolver.tools import add_edge  # type: ignore

if TYPE_CHECKING:
    from geosolver.dependencies.dependency import Dependency
    from geosolver.statement import Statement
    from geosolver.algebraic_reasoning.algebraic_manipulator import (
        AlgebraicManipulator,
    )


class DependencyGraph:
    """Hyper graph linking statements by dependencies as hyper-edges."""

    def __init__(self, ar: "AlgebraicManipulator") -> None:
        self.symbols_graph = SymbolsGraph()
        self.hyper_graph: dict[Statement, Dependency] = {}
        self.ar = ar

    def has_edge(self, dep: Dependency):
        return (
            dep.statement in self.hyper_graph and dep in self.hyper_graph[dep.statement]
        )

    def checked(self):
        return list(self.hyper_graph.keys())

    def premises(self):
        res: list[Dependency] = []
        for _, dep in self.hyper_graph.items():
            if dep.reason == IN_PREMISES:
                res.append(dep)
        return res

    def _proof_text(
        self,
        statement: Statement,
        sub_proof: dict[Statement, tuple[Dependency, ...]],
    ) -> tuple[Dependency, ...]:
        if statement in sub_proof:
            return sub_proof[statement]
        dep = self.hyper_graph[statement]
        cur_proof: tuple[Dependency, ...] = ()
        for premise in dep.why:
            cur_proof += self._proof_text(premise, sub_proof)
        sub_proof[statement] = cur_proof
        return cur_proof + (dep,)

    def proof_deps(self, goals: list[Statement]) -> tuple[Dependency, ...]:
        sub_proof: dict[Statement, tuple[Dependency, ...]] = {}
        res: list[Dependency] = []
        for goal in goals:
            proof_of_goal = self._proof_text(goal, sub_proof)
            for s in proof_of_goal:
                if s not in res:
                    res.append(s)
        return tuple(res)

    def save_pyvis(self, path: Path):
        net = Network("1080px", directed=True)
        for _, dep in self.hyper_graph.items():
            for premise in dep.why:
                add_edge(net, premise.pretty(), dep.statement.pretty())
        net.show(str(path), notebook=False)  # type: ignore
