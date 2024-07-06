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

    def add_edge_to_hyper_graph(self, dep: "Dependency"):
        s = self.hyper_graph.get(dep.statement)
        if s is None:
            self.hyper_graph[dep.statement] = {dep}
        else:
            if len(s) == 0:
                s.update(dep.statement.why())
            s.add(dep)

    def _proof_text(
        self,
        statement: Statement,
        id: dict[Statement, str],
        sub_proof: dict[Statement, Optional[tuple[str, ...]]],
    ) -> tuple[str, ...] | None:
        if statement in sub_proof:
            return sub_proof[statement]
        if statement not in id:
            id[statement] = str(len(id))
        sub_proof[statement] = None
        my_proof = None
        for dep in statement.why():
            cur_proof: tuple[str, ...] | None = tuple()
            for premise in dep.why:
                t = self._proof_text(premise, id, sub_proof)
                if t is None:
                    cur_proof = None
                    break
                else:
                    cur_proof += t
            if cur_proof is not None and (
                my_proof is None or len(my_proof) > len(cur_proof)
            ):
                my_proof = cur_proof + (
                    f"{', '.join(premise.pretty() + ' [' + id[premise] + ']' for premise in dep.why)} {dep.reason}=> {dep.statement.pretty()} [{id[dep.statement]}]",
                )
        if my_proof is None:
            return None
        sub_proof[statement] = my_proof
        return my_proof

    def proof_text(self, goals: list[Statement]) -> str:
        id: dict[Statement, str] = {}
        sub_proof: dict[Statement, Optional[tuple[str, ...]]] = {}
        res: list[str] = []
        for i, goal in enumerate(goals):
            id[goal] = "g" + str(i)
            proof_of_goal = self._proof_text(goal, id, sub_proof)
            if proof_of_goal is None:
                break
            for s in proof_of_goal:
                if s not in res:
                    res.append(s)
        return "\n".join(res)
