from __future__ import annotations
from enum import Enum

from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple, Union
from networkx import MultiDiGraph, ancestors
from pyvis.network import Network
import seaborn as sns


from geosolver.algebraic import AlgebraicRules
from geosolver.dependencies.dependency import Dependency
from geosolver.problem import CONSTRUCTION_RULE, Theorem
from geosolver.statement.adder import IntrinsicRules, ToCache

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

    @property
    def proof_subgraph(self) -> DependencyGraph:
        proof_graph = DependencyGraph()
        proof_graph.nx_graph = extract_sub_graph(
            self.nx_graph, self.premises, self.goal
        )
        return proof_graph

    @property
    def premises(self) -> List[str]:
        return [
            node
            for node, node_type in self.nx_graph.nodes(data="type")
            if DependencyType(node_type) is DependencyType.PREMISE
        ]

    def add_dependency(
        self,
        dependency: Dependency,
        dependency_type: DependencyType = DependencyType.STATEMENT,
    ):
        node = dependency_node_name(dependency)

        dep_type = dependency_type.value
        dep_level = dependency.level
        if node in self.nx_graph.nodes:
            # So goal stay as such
            dep_type = self.nx_graph.nodes[node]["type"]
            # First level counts
            dep_level = self.nx_graph.nodes[node].get("level")
            if dep_level is None:
                dep_level = dependency.level

        dep_args_names = [arg.name for arg in dependency.args]
        self.nx_graph.add_node(
            node,
            name=dependency.name,
            level=dep_level,
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
            none_why = u_for_edge.why is None
            if none_why:
                dependency_type = DependencyType.NUMERICAL_CHECK
            self.add_dependency(u_for_edge, dependency_type)
            if not none_why:
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
        self, to_cache: list[ToCache], theorem: Theorem, args: List["Point"]
    ):
        for cache_name, cache_args, added_dependency in to_cache:
            self.add_dependency(added_dependency)

            # Check for identical mapping A.B.D.C == A.B.C.D
            while (
                len(added_dependency.why) == 1
                and added_dependency.why[0].hashed() == added_dependency.hashed()
            ):
                added_dependency = added_dependency.why[0]

            for why_added in added_dependency.why:
                self.add_edge(
                    why_added,
                    added_dependency,
                    edge_name=added_dependency.rule_name,
                    edge_arguments=args,
                )

    def add_algebra_edges(
        self, to_cache: list[ToCache], args: List[Union["Point", int]]
    ):
        for cache_name, cache_args, added_dependency in to_cache:
            self.add_dependency(added_dependency)

            # Check for identical mapping A.B.D.C == A.B.C.D
            while (
                len(added_dependency.why) == 1
                and added_dependency.why[0].hashed() == added_dependency.hashed()
            ):
                added_dependency = added_dependency.why[0]

            dep_rule_name = added_dependency.rule_name
            for why_added in added_dependency.why:
                self.add_edge(
                    why_added,
                    added_dependency,
                    edge_name=dep_rule_name,
                    edge_arguments=args,
                )

    def add_construction_edges(self, to_cache: list[ToCache], args: List["Point"]):
        for cache_name, cache_args, added_dependency in to_cache:
            self.add_dependency(added_dependency, DependencyType.PREMISE)

            # Check for identical mapping A.B.D.C == A.B.C.D
            while (
                len(added_dependency.why) == 1
                and added_dependency.why[0].hashed() == added_dependency.hashed()
            ):
                added_dependency = added_dependency.why[0]

            dep_rule_name = added_dependency.rule_name
            for why_added in added_dependency.why:
                self.add_dependency(why_added)
                self.add_edge(
                    why_added,
                    added_dependency,
                    edge_name=dep_rule_name,
                    edge_arguments=args,
                )

    def add_goal(self, goal_name: str, goal_args: List["Point"]):
        goal_dep = Dependency(goal_name, goal_args, None, None)
        self.goal = dependency_node_name(goal_dep)
        self.add_dependency(goal_dep, DependencyType.GOAL)

    def show_html(self, html_path: Path, rules: Dict[str, Theorem]):
        nt = Network("1080px", directed=True)
        # populates the nodes and edges data structures
        vis_graph: MultiDiGraph = self.nx_graph.copy()

        levels = [
            lvl for _, lvl in self.nx_graph.nodes(data="level") if lvl is not None
        ]
        max_level = max(levels) if levels else 0
        nodes_colors = build_nodes_colors(max_level + 1)
        for node, data in vis_graph.nodes(data=True):
            name: str = data.get("name", "Unknown")
            dep_type: str = data.get("type", "Unknown")
            level: Optional[int] = data.get("level")
            if level is None:
                level = -1
            args: List[str] = data.get("args", [])
            vis_graph.nodes[node]["color"] = rgba_to_hex(*nodes_colors[level], a=1.0)
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
        for u, v, k, data in vis_graph.edges(data=True, keys=True):
            name = k.split(".")[0]
            theorem = rules.get(name)
            if theorem:
                edge_name = theorem.name
            elif name == CONSTRUCTION_RULE:
                edge_name = "Construction"
            elif name in [ar.value for ar in AlgebraicRules]:
                edge_name = AlgebraicRules(name).name.replace("_", " ")
            elif name in [ir.value for ir in IntrinsicRules]:
                edge_name = IntrinsicRules(name).name.replace("_", " ")
            else:
                edge_name = "NOT FOUND"
            vis_graph.edges[u, v, k]["title"] = edge_name
            vis_graph.edges[u, v, k]["arrows"] = {
                "middle": {"enabled": True},
                "to": {"enabled": True},
            }
            vis_graph.edges[u, v, k]["label"] = k
            vis_graph.edges[u, v, k]["font"] = {"size": 8}

            node_edges_keys = sorted(
                key
                for _, _, key in list(vis_graph.in_edges(v, keys=True))
                + list(vis_graph.out_edges(u, keys=True))
            )
            edge_index = node_edges_keys.index(k)
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
        nt.options.physics.solver = "barnesHut"
        nt.options.physics.use_barnes_hut(
            {
                "gravity": -15000,
                "central_gravity": 2.0,
                "spring_length": 100,
                "spring_strength": 0.05,
                "damping": 0.2,
                "overlap": 0.01,
            }
        )
        nt.show_buttons(filter_=["physics"])
        nt.show(str(html_path), notebook=False)


def extract_sub_graph(
    graph: MultiDiGraph, roots: List[str], goal: Optional[str]
) -> MultiDiGraph:
    if goal is None:
        raise ValueError("Cannot extract proof subgraph without goal.")

    subgraph: MultiDiGraph = graph.copy()
    subgraph.remove_nodes_from(
        [n for n in subgraph if n not in ancestors(subgraph, goal) | {goal}]
    )

    subgraph.remove_edges_from([e for e in subgraph.out_edges(goal)])
    for root in roots:
        subgraph.remove_edges_from([e for e in subgraph.in_edges(root)])

    down_edges = []
    for u, v, k in subgraph.edges(keys=True):
        in_level = subgraph.nodes[u].get("level")
        out_level = subgraph.nodes[v].get("level")
        if in_level is not None and out_level is not None and in_level > out_level:
            down_edges.append((u, v, k))

    subgraph.remove_edges_from(down_edges)

    subgraph.remove_nodes_from([n for n in subgraph if subgraph.degree(n) == 0])
    return subgraph


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
    return sns.color_palette("colorblind", n_colors=20)


def build_nodes_colors(n_colors: int):
    """Build a nodes colors palette according to levels.

    Color from this SO post:
    https://stackoverflow.com/questions/7251872/is-there-a-better-color-scale-than-the-rainbow-colormap
    """
    return sns.blend_palette(
        colors=[
            (0.847, 0.057, 0.057),
            (0.527, 0.527, 0),
            (0, 0.592, 0),
            (0, 0.559, 0.559),
            (0.316, 0.316, 0.991),
            (0.718, 0, 0.718),
        ],
        n_colors=n_colors,
    )
