from __future__ import annotations
from typing import TYPE_CHECKING, Optional
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

    def has_edge(self, dep: Dependency):
        return (
            dep.statement in self.hyper_graph and dep in self.hyper_graph[dep.statement]
        )

    def _proof_text(
        self,
        statement: Statement,
        sub_proof: dict[Statement, Optional[tuple[Dependency, ...]]],
    ) -> Optional[tuple[Dependency, ...]]:
        if statement in sub_proof:
            return sub_proof[statement]
        sub_proof[statement] = None
        my_proof = None
        deps = self.hyper_graph[statement]
        extra_dep = statement.why()
        if extra_dep is not None:
            deps.add(extra_dep)
        for dep in deps:
            cur_proof: Optional[tuple[Dependency, ...]] = tuple()
            for premise in dep.why:
                t = self._proof_text(premise, sub_proof)
                if t is None:
                    cur_proof = None
                    break
                else:
                    cur_proof += t
            if cur_proof is not None and (
                my_proof is None or len(my_proof) > len(cur_proof)
            ):
                my_proof = cur_proof + (dep,)
        if my_proof is None:
            del sub_proof[statement]
            return None
        sub_proof[statement] = my_proof
        return my_proof

    def proof_deps(self, goals: list[Statement]) -> tuple[Dependency, ...]:
        sub_proof: dict[Statement, Optional[tuple[Dependency, ...]]] = {}
        res: list[Dependency] = []
        for goal in goals:
            proof_of_goal = self._proof_text(goal, sub_proof)
            if proof_of_goal is None:
                assert False
            for s in proof_of_goal:
                if s not in res:
                    res.append(s)
        return tuple(res)
