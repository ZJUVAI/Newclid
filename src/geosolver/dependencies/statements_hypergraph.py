from pathlib import Path
from typing import TYPE_CHECKING


from geosolver.dependencies.caching import DependencyCache
from geosolver.dependencies.dependency import Dependency
from geosolver.dependencies.dependency_graph import build_diverse_colors, rgba_to_hex
from geosolver.dependencies.why_predicates import why_dependency
from geosolver.statements.checker import StatementChecker
from geosolver.statements.statement import Statement
from geosolver.symbols_graph import SymbolsGraph
from geosolver._lazy_loading import lazy_import

if TYPE_CHECKING:
    import pyvis
    import networkx

vis: "pyvis" = lazy_import("pyvis")
nx: "networkx" = lazy_import("networkx")


class StatementsHyperGraph:
    def __init__(
        self,
        symbols_graph: "SymbolsGraph",
        statements_checker: "StatementChecker",
        dependency_cache: "DependencyCache",
    ) -> None:
        self.nx_graph = nx.DiGraph()
        self.symbols_graph = symbols_graph
        self.statements_checker = statements_checker
        self.dependency_cache = dependency_cache

    def resolve(self, dependency: "Dependency", level: int) -> list["Dependency"]:
        if dependency not in self.nx_graph.nodes:
            self.nx_graph.add_node(
                dependency,
                level=dependency.level,
                name=dependency.rule_name,
            )
        if dependency.statement not in self.nx_graph.nodes:
            self.nx_graph.add_node(dependency.statement)
        self.nx_graph.add_edge(dependency, dependency.statement)

        why_deps = why_dependency(self, dependency, level)
        for why_dep in why_deps:
            if why_dep.statement not in self.nx_graph.nodes:
                self.nx_graph.add_node(why_dep.statement)
            self.nx_graph.add_edge(why_dep.statement, dependency)

        return why_deps

    def show_html(self, html_path: Path):
        nt = vis.network.Network("1080px", directed=True)
        # populates the nodes and edges data structures
        vis_graph: "networkx.DiGraph" = nx.DiGraph()

        colors = build_diverse_colors()
        dep_index = 0
        for node, data in self.nx_graph.nodes(data=True):
            node_name = self._node_name(node)
            if isinstance(node, Dependency):
                size = 2
                shape = "square"
                label = node.rule_name
                color_index = dep_index % len(colors)
                color = rgba_to_hex(*colors[color_index], a=1.0)
                mass = 0.1
                dep_index += 1
            elif isinstance(node, Statement):
                size = 40
                shape = "box"
                label = node_name
                mass = 1.0

            vis_graph.add_node(
                node_name,
                label=label,
                color=color,
                size=size,
                shape=shape,
                mass=mass,
            )

        for u, v, data in self.nx_graph.edges(data=True):
            arrows = {"to": {"enabled": True}}
            font = {"size": 8}

            attached_dependency: Dependency = u if isinstance(u, Dependency) else v
            color = vis_graph.nodes[self._node_name(attached_dependency)]["color"]

            vis_graph.add_edge(
                self._node_name(u),
                self._node_name(v),
                arrows=arrows,
                font=font,
                color=color,
            )

        nt.from_nx(vis_graph)
        nt.options.layout.hierarchical = True
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

    @staticmethod
    def _node_name(node: Statement | Dependency) -> str:
        if isinstance(node, Dependency):
            return str(node.rule_name) + f" for {node.statement}"
        if isinstance(node, Statement):
            return str(node)
        raise TypeError
