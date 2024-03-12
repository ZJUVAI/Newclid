from pathlib import Path
from typing import Dict, List
from networkx import MultiDiGraph
from pyvis.network import Network


from geosolver.algebraic import AlgebraicRules
from geosolver.problem import CONSTRUCTION_RULE, Dependency, Theorem


class DependencyGraph:
    def __init__(self) -> None:
        self.nx_graph = MultiDiGraph()

    def add_dependency(self, dependency: Dependency):
        node = dependency_node_name(dependency)

        dep_args_names = [arg.name for arg in dependency.args]
        self.nx_graph.add_node(
            node, name=dependency.name, level=dependency.level, args=dep_args_names
        )

    def add_edge(self, u_for_edge: Dependency, v_for_edge: Dependency, rule_name: str):
        pred = dependency_node_name(u_for_edge)
        succ = dependency_node_name(v_for_edge)
        # assert u in self.nx_graph.nodes
        # assert v in self.nx_graph.nodes
        self.nx_graph.add_edge(
            pred,
            succ,
            key=rule_name,
        )

    def show_html(self, html_path: Path, rules: Dict[str, Theorem]):
        nt = Network("1080px", directed=True)
        # populates the nodes and edges data structures
        vis_graph: MultiDiGraph = self.nx_graph.copy()
        for node, data in vis_graph.nodes(data=True):
            name: str = data.get("name", "Unknown")
            level: int = data.get("level", -1)
            args: List[str] = data.get("args", [])
            vis_graph.nodes[node]["group"] = level
            vis_graph.nodes[node]["title"] = (
                f"{name.capitalize()}" f"\nArgs:{args}" f"\nLevel {level}"
            )
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
