from __future__ import annotations
from enum import Enum
import logging

from pathlib import Path
from typing import Dict, List
from networkx import MultiDiGraph
from pyvis.network import Network


from geosolver.algebraic import AlgebraicRules
from geosolver.geometry import Point
from geosolver.problem import CONSTRUCTION_RULE, Dependency, Theorem


class DependencyType(Enum):
    GOAL = "goal"
    PREMISE = "premise"
    STATEMENT = "statement"


DEPTYPE_TO_SHAPE = {
    DependencyType.GOAL.value: "star",
    DependencyType.PREMISE.value: "hexagon",
    DependencyType.STATEMENT.value: "dot",
}


class DependencyGraph:
    def __init__(self) -> None:
        self.nx_graph = MultiDiGraph()
        self._goal_node = None

    def add_dependency(
        self,
        dependency: Dependency,
        dependency_type: DependencyType = DependencyType.STATEMENT,
    ):
        node = dependency_node_name(dependency)

        dep_type = dependency_type.value
        if node in self.nx_graph.nodes:
            # So goal stay as such
            dep_type = self.nx_graph.nodes[node]["type"]

        dep_args_names = [arg.name for arg in dependency.args]
        self.nx_graph.add_node(
            node,
            name=dependency.name,
            level=dependency.level,
            args=dep_args_names,
            type=dep_type,
        )

    def add_edge(self, u_for_edge: Dependency, v_for_edge: Dependency, rule_name: str):
        pred = dependency_node_name(u_for_edge)

        if pred not in self.nx_graph.nodes:
            self.add_dependency(u_for_edge)
            for why_u in u_for_edge.why:
                self.add_edge(why_u, u_for_edge, rule_name=u_for_edge.rule_name)

        succ = dependency_node_name(v_for_edge)
        assert succ in self.nx_graph.nodes
        self.nx_graph.add_edge(
            pred,
            succ,
            key=rule_name,
        )

    def add_theorem_edges(
        self,
        dependencies: list[Dependency],
        theorem: Theorem,
    ):
        for added_dependency in dependencies:
            self.add_dependency(added_dependency)

            # Check for identical mapping A.B.D.C == A.B.C.D
            while (
                len(added_dependency.why) == 1
                and added_dependency.why[0].hashed() == added_dependency.hashed()
            ):
                added_dependency = added_dependency.why[0]

            for why_added in added_dependency.why:
                dep_rule_name = added_dependency.rule_name
                if dep_rule_name and dep_rule_name != theorem.rule_name:
                    logging.warning(
                        "Dependency rule was different from the theorem. %s != %s",
                        dep_rule_name,
                        theorem.rule_name,
                    )
                self.add_edge(
                    why_added,
                    added_dependency,
                    rule_name=theorem.rule_name,
                )

    def add_construction_edges(self, dependencies: list[Dependency]):
        for added_dependency in dependencies:
            self.add_dependency(added_dependency, DependencyType.PREMISE)

            for why_added in added_dependency.why:
                self.add_dependency(why_added)
                dep_rule_name = added_dependency.rule_name
                if dep_rule_name and dep_rule_name != CONSTRUCTION_RULE:
                    logging.warning(
                        "Dependency rule was different"
                        "from the construction rule. %s != %s",
                        dep_rule_name,
                        CONSTRUCTION_RULE,
                    )
                self.add_edge(
                    why_added,
                    added_dependency,
                    rule_name=CONSTRUCTION_RULE,
                )

    def add_goal(self, goal_name: str, goal_args: List[Point]):
        goal_dep = Dependency(goal_name, goal_args, None, -1)
        self.add_dependency(goal_dep, DependencyType.GOAL)

    def show_html(self, html_path: Path, rules: Dict[str, Theorem]):
        nt = Network("1080px", directed=True)
        # populates the nodes and edges data structures
        vis_graph: MultiDiGraph = self.nx_graph.copy()
        for node, data in vis_graph.nodes(data=True):
            name: str = data.get("name", "Unknown")
            dep_type: str = data.get("type", "Unknown")
            level: int = data.get("level", -1)
            args: List[str] = data.get("args", [])
            vis_graph.nodes[node]["group"] = level
            vis_graph.nodes[node]["title"] = (
                f"{name.capitalize()}"
                f"\n {dep_type.capitalize()}"
                f"\nArgs:{args}"
                f"\nLevel {level}"
            )
            vis_graph.nodes[node]["shape"] = DEPTYPE_TO_SHAPE.get(dep_type, "dot")
            if dep_type == DependencyType.PREMISE.value:
                vis_graph.nodes[node]["size"] = 20
            if dep_type == DependencyType.GOAL.value:
                vis_graph.nodes[node]["size"] = 40
        for u, v, k, data in vis_graph.edges(data=True, keys=True):
            theorem = rules.get(k)
            if theorem:
                edge_name = theorem.name
            elif k == CONSTRUCTION_RULE:
                edge_name = "Construction"
            elif k in [ar.value for ar in AlgebraicRules]:
                edge_name = AlgebraicRules(k).name.replace("_", " ")
            else:
                edge_name = "NOT FOUND"
            vis_graph.edges[u, v, k]["title"] = edge_name
            vis_graph.edges[u, v, k]["label"] = k if k else "NAN"
        nt.from_nx(vis_graph)
        nt.show(str(html_path), notebook=False)


def dependency_node_name(dependency: Dependency):
    return ".".join(dependency.hashed())
