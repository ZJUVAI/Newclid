from __future__ import annotations
from enum import Enum
import logging

from pathlib import Path
import random
from typing import TYPE_CHECKING, Dict, List, Tuple, Union
from networkx import MultiDiGraph
from pyvis.network import Network
import seaborn as sns


from geosolver.algebraic import AlgebraicRules
from geosolver.problem import CONSTRUCTION_RULE, Dependency, Theorem

if TYPE_CHECKING:
    from geosolver.geometry import Point, Node


class DependencyType(Enum):
    GOAL = "goal"
    PREMISE = "premise"
    STATEMENT = "statement"
    NUMERICAL_CHECK = "numerical_check"


DEPTYPE_TO_SHAPE = {
    DependencyType.GOAL.value: "star",
    DependencyType.PREMISE.value: "hexagon",
    DependencyType.STATEMENT.value: "dot",
    DependencyType.NUMERICAL_CHECK.value: "square",
}


class DependencyGraph:
    def __init__(self) -> None:
        self.nx_graph = MultiDiGraph()
        self.goal = None

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

    def add_edge(
        self,
        u_for_edge: Dependency,
        v_for_edge: Union[Dependency, str],
        edge_arguments: List[Union[str, "Node"]],
        edge_name: str = "",
    ):
        edge_name = edge_name if edge_name else "NAN"

        pred = dependency_node_name(u_for_edge)
        if pred not in self.nx_graph.nodes:
            dependency_type = DependencyType.STATEMENT
            if not u_for_edge.why:
                dependency_type = DependencyType.NUMERICAL_CHECK
            self.add_dependency(u_for_edge, dependency_type)
            for why_u in u_for_edge.why:
                self.add_edge(
                    why_u,
                    u_for_edge,
                    edge_name=u_for_edge.rule_name,
                    edge_arguments=u_for_edge.args,
                )

        if isinstance(v_for_edge, Dependency):
            v_for_edge = dependency_node_name(v_for_edge)
        assert v_for_edge in self.nx_graph.nodes
        edge_key = f"{edge_name}." + ".".join(_str_arguments(edge_arguments))
        self.nx_graph.add_edge(pred, v_for_edge, key=edge_key)

    def add_theorem_edges(
        self, dependencies: list[Dependency], theorem: Theorem, args: List["Point"]
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
                if dep_rule_name != theorem.rule_name:
                    logging.warning(
                        "Dependency rule was different from the theorem. %s != %s",
                        dep_rule_name,
                        theorem.rule_name,
                    )
                self.add_edge(
                    why_added,
                    added_dependency,
                    edge_name=dep_rule_name,
                    edge_arguments=args,
                )

    def add_algebra_edges(
        self, dependencies: list[Dependency], args: List[Union["Point", int]]
    ):
        for added_dependency in dependencies:
            self.add_dependency(added_dependency)
            for why_added in added_dependency.why:
                dep_rule_name = added_dependency.rule_name
                if dep_rule_name not in [ar.value for ar in AlgebraicRules]:
                    logging.warning("Dependency rule was unknown: '%s'", dep_rule_name)
                self.add_edge(
                    why_added,
                    added_dependency,
                    edge_name=dep_rule_name,
                    edge_arguments=args,
                )

    def add_construction_edges(
        self, dependencies: list[Dependency], args: List["Point"]
    ):
        for added_dependency in dependencies:
            self.add_dependency(added_dependency, DependencyType.PREMISE)

            for why_added in added_dependency.why:
                self.add_dependency(why_added)
                dep_rule_name = added_dependency.rule_name
                if dep_rule_name != CONSTRUCTION_RULE:
                    logging.warning(
                        "Dependency rule was different"
                        "from the construction rule. %s != %s",
                        dep_rule_name,
                        CONSTRUCTION_RULE,
                    )
                self.add_edge(
                    why_added,
                    added_dependency,
                    edge_name=dep_rule_name,
                    edge_arguments=args,
                )

    def add_goal(self, goal_name: str, goal_args: List["Point"]):
        goal_dep = Dependency(goal_name, goal_args, None, -1)
        self.goal = dependency_node_name(goal_dep)
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

        edges_colors = build_edges_colors()
        edges_keys_indexes = []
        for u, v, k, data in vis_graph.edges(data=True, keys=True):
            name = k.split(".")[0]
            theorem = rules.get(name)
            if theorem:
                edge_name = theorem.name
            elif name == CONSTRUCTION_RULE:
                edge_name = "Construction"
            elif name in [ar.value for ar in AlgebraicRules]:
                edge_name = AlgebraicRules(name).name.replace("_", " ")
            else:
                edge_name = "NOT FOUND"
            vis_graph.edges[u, v, k]["title"] = edge_name
            vis_graph.edges[u, v, k]["label"] = k
            vis_graph.edges[u, v, k]["font"] = {"size": 8}

            if k in edges_keys_indexes:
                edge_index = edges_keys_indexes.index(k)
            else:
                edge_index = len(edges_keys_indexes)
                edges_keys_indexes.append(k)

            edge_color_index = edge_index % len(edges_colors)
            base_edge_color = edges_colors[edge_color_index]

            idle_edge_color = rgba_to_hex(*base_edge_color, a=0.6)
            edge_color = rgba_to_hex(*base_edge_color, a=1.0)
            vis_graph.edges[u, v, k]["color"] = {
                "color": idle_edge_color,
                "highlight": edge_color,
                "hover": edge_color,
            }

        nt.from_nx(vis_graph)
        nt.options.interaction.hover = True
        nt.show_buttons(filter_=["physics"])
        nt.show(str(html_path), notebook=False)


def dependency_node_name(dependency: Dependency):
    return node_name_from_hash(dependency.hashed())


def node_name_from_hash(hash_tuple: Tuple[str]):
    return ".".join(hash_tuple)


def _str_arguments(args: List[Union[str, int, "Node"]]) -> List[str]:
    args_str = []
    for arg in args:
        if isinstance(arg, (int, str, float)):
            args_str.append(str(arg))
        else:
            args_str.append(arg.name)
    return args_str


def rgba_to_hex(r, g, b, a=0.5):
    hexes = "%02x%02x%02x%02x" % (
        int(r * 255),
        int(g * 255),
        int(b * 255),
        int(a * 255),
    )
    return f"#{hexes.upper()}"


def build_edges_colors() -> List[str]:
    edge_colors = sns.color_palette("colorblind")
    random.shuffle(edge_colors)
    return edge_colors
