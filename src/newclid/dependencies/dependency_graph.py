from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING, Collection, Optional
from newclid.dependencies.dependency import IN_PREMISES, NUMERICAL_CHECK
from newclid.dependencies.symbols import Point
from newclid.dependencies.symbols_graph import SymbolsGraph
from pyvis.network import Network  # type: ignore

from newclid.tools import add_edge, boring_statement  # type: ignore

if TYPE_CHECKING:
    from newclid.dependencies.dependency import Dependency
    from newclid.statement import Statement
    from newclid.algebraic_reasoning.algebraic_manipulator import (
        AlgebraicManipulator,
    )


class DependencyGraph:
    """Hyper graph linking statements by dependencies as hyper-edges."""

    def __init__(self, ar: "AlgebraicManipulator") -> None:
        self.symbols_graph = SymbolsGraph()
        self.hyper_graph: dict[Statement, Dependency] = {}
        self.ar = ar
        self.check_numerical: dict[Statement, bool] = {}
        self.token_statement: dict[tuple[str, ...], Optional[Statement]] = {}

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
    
    def get_proof_steps(
            self,
            goals: list[Statement]
    ) -> tuple[
        set[Point],
        list[Dependency],
        list[Dependency],
        set[Point],
        list[Dependency],
        list[Dependency],
        list[Dependency],
    ]:
        proof_deps = self.proof_deps(goals)

        points: set[Point] = set()
        for goal in goals:
            points.update(goal.args)
        queue: list[Point] = list(points)
        i = 0
        while i < len(queue):
            q = queue[i]
            i += 1
            assert isinstance(q, Point)
            for p in q.rely_on:
                if p not in points:
                    points.add(p)
                    queue.append(p)
        
        premises: list[Dependency] = []
        numercial_checked_premises: list[Dependency] = []
        aux_points: set[Point] = set()
        aux: list[Dependency] = []
        numercial_checked_aux: list[Dependency] = []
        proof_steps: list[Dependency] = []

        for line in proof_deps:
            is_aux = any([p not in points for p in line.statement.args if isinstance(p, Point)])
            if IN_PREMISES == line.reason:
                if is_aux:
                    aux.append(line)
                    aux_points.update(
                        [p for p in line.statement.args if isinstance(p, Point)
                        and p not in points]
                    )
                else:
                    premises.append(line)
            elif NUMERICAL_CHECK == line.reason:
                if is_aux:
                    numercial_checked_aux.append(line)
                    aux_points.update(
                        [p for p in line.statement.args if isinstance(p, Point)
                        and p not in points]
                    )
                else:
                    numercial_checked_premises.append(line)
            else:
                proof_steps.append(line)
        
        return (
            points,
            premises,
            numercial_checked_premises,
            aux_points,
            aux,
            numercial_checked_aux,
            proof_steps,
        )

    def get_essential_clauses(
        self,
        goals: list[Statement],
    ) -> tuple[
        set[str],
        set[str]
    ]:
        essential_clauses: set[str] = set()
        essential_clauses_aux: set[str] = set()

        points, _, _, aux_points, _, _, _ = self.get_proof_steps(goals)
        for p in points:
            essential_clauses.add(str(p.clause))
        for p in aux_points:
            essential_clauses_aux.add(str(p.clause))
        return essential_clauses, essential_clauses_aux

    def save_pyvis(self, *, path: Path, stars: Collection[Statement] = []):
        if stars:
            deps = self.proof_deps(list(stars))
        else:
            deps = tuple(dep for _, dep in self.hyper_graph.items())
        net = Network("1080px", directed=True)
        for dep in deps:
            if boring_statement(dep.statement):
                continue
            shape = "dot"
            color = "#97c2fc"
            if dep.statement in stars:
                shape = "star"
                color = "gold"
            net.add_node(  # type: ignore
                dep.statement.pretty(),
                title=f"{dep.reason}",
                shape=shape,
                color=color,
                size=10,
            )
        for dep in deps:
            if boring_statement(dep.statement):
                continue
            for premise in dep.why:
                add_edge(net, premise.pretty(), dep.statement.pretty())  # type: ignore
        net.options.layout = {  # type: ignore
            "hierarchical": {
                "enabled": True,
                "direction": "LR",
                "sortMethod": "directed",
            },
        }
        net.show_buttons(filter_=["physics", "layout"])  # type: ignore
        net.show(str(path), notebook=False)  # type: ignore
