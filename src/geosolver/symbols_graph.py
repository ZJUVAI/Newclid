from pathlib import Path

from networkx import Graph
from pyvis.network import Network

import geosolver.numerical.geometries as num_geo
from geosolver.geometry import (
    Angle,
    Circle,
    Direction,
    Length,
    Line,
    Measure,
    Node,
    Point,
    Ratio,
    Segment,
    Value,
    line_of_and_why,
)
from geosolver.problem import Dependency


from typing import Callable, Dict, List, Optional, Type

NODES_VALUES: Dict[Type[Node], Type[Node]] = {
    Line: Direction,
    Segment: Length,
    Angle: Measure,
    Ratio: Value,
}

NODES_VALUES_MARKERS: Dict[Type[Node], str] = {
    Direction: "d",
    Length: "l",
    Measure: "m",
    Value: "r",
}


class SymbolsGraph:
    def __init__(self) -> None:
        self.type2nodes: Dict[Type[Node], List[Node]] = {
            Point: [],
            Line: [],
            Segment: [],
            Circle: [],
            Direction: [],
            Length: [],
            Angle: [],
            Ratio: [],
            Measure: [],
            Value: [],
        }
        self._name2point = {}
        self._name2node = {}
        self._pair2line = {}
        self._triplet2circle = {}

    def connect(self, a: Node, b: Node, deps: Dependency) -> None:
        a.connect_to(b, deps)
        b.connect_to(a, deps)

    def all_points(self) -> list[Point]:
        """Return all nodes of type Point."""
        return list(self.type2nodes[Point])

    def names2nodes(self, pnames: list[str]) -> list[Node]:
        return [self._name2node[name] for name in pnames]

    def names2points(
        self, pnames: list[str], create_new_point: bool = False
    ) -> list[Point]:
        """Return Point objects given names."""
        result = []
        for name in pnames:
            if name not in self._name2node and not create_new_point:
                raise ValueError(f"Cannot find point {name} in graph")
            elif name in self._name2node:
                obj = self._name2node[name]
            else:
                obj = self.new_node(Point, name)
            result.append(obj)

        return result

    def add_node(self, node: Node) -> None:
        self.type2nodes[type(node)].append(node)
        self._name2node[node.name] = node

        if isinstance(node, Point):
            self._name2point[node.name] = node

    def new_node(self, oftype: Type[Node], name: str = "") -> Node:
        node = oftype(name, self)
        self.add_node(node)
        return node

    def get_node_val(self, node: Node, deps: Optional[Dependency]) -> Node:
        """Get a node value (equality) node, creating it if necessary."""
        if node._val:
            return node._val

        val_type = NODES_VALUES[type(node)]
        marker = NODES_VALUES_MARKERS[val_type]
        name = f"{marker}({node.name})"

        v = self.new_node(val_type, name)
        self.connect(node, v, deps=deps)
        return v

    def get_point(self, pointname: str, default_fn: Callable[[str], Point]) -> Point:
        if pointname in self._name2point:
            return self._name2point[pointname]
        if pointname in self._name2node:
            return self._name2node[pointname]
        return default_fn()

    def merge(self, nodes: list[Node], deps: Dependency) -> Node:
        """Merge all nodes."""
        if len(nodes) < 2:
            return

        node0, *nodes1 = nodes
        all_nodes = self.type2nodes[type(node0)]

        # find node0 that exists in all_nodes to be the rep
        # and merge all other nodes into node0
        for node in nodes:
            if node in all_nodes:
                node0 = node
                nodes1 = [n for n in nodes if n != node0]
                break
        return self.merge_into(node0, nodes1, deps)

    def merge_into(self, node0: Node, nodes1: list[Node], deps: Dependency) -> Node:
        """Merge nodes1 into a single node0."""
        node0.merge(nodes1, deps)
        for n in nodes1:
            if n.rep() != n:
                self.remove([n])

        nodes = [node0] + nodes1
        if any([node._val for node in nodes]):
            for node in nodes:
                self.get_node_val(node, deps=None)

            vals1 = [n._val for n in nodes1]
            node0._val.merge(vals1, deps)

            for v in vals1:
                if v.rep() != v:
                    self.remove([v])

        return node0

    def remove(self, nodes: list[Node]) -> None:
        """Remove nodes out of self because they are merged."""
        if not nodes:
            return

        for node in nodes:
            all_nodes = self.type2nodes[type(nodes[0])]

            if node in all_nodes:
                all_nodes.remove(node)

            if node.name in self._name2node.values():
                self._name2node.pop(node.name)

    def get_new_line_thru_pair(self, p1: Point, p2: Point) -> Line:
        if p1.name.lower() > p2.name.lower():
            p1, p2 = p2, p1
        name = p1.name.lower() + p2.name.lower()
        line = self.new_node(Line, name)
        line.num = num_geo.Line(p1.num, p2.num)
        line.points = p1, p2

        self.connect(p1, line, deps=None)
        self.connect(p2, line, deps=None)
        self._pair2line[(p1, p2)] = line
        return line

    def get_line_thru_pair(self, p1: Point, p2: Point) -> Line:
        if (p1, p2) in self._pair2line:
            return self._pair2line[(p1, p2)]
        if (p2, p1) in self._pair2line:
            return self._pair2line[(p2, p1)]
        return self.get_new_line_thru_pair(p1, p2)

    def get_line_thru_pair_why(
        self, p1: Point, p2: Point
    ) -> tuple[Line, list[Dependency]]:
        """Get one line thru two given points and the corresponding dependency list."""
        if p1.name.lower() > p2.name.lower():
            p1, p2 = p2, p1
        if (p1, p2) in self._pair2line:
            return self._pair2line[(p1, p2)].rep_and_why()

        line, why = line_of_and_why([p1, p2])
        if line is None:
            line = self.get_new_line_thru_pair(p1, p2)
            why = []
        return line, why

    def get_circle_thru_triplet(self, p1: Point, p2: Point, p3: Point) -> Circle:
        p1, p2, p3 = sorted([p1, p2, p3], key=lambda x: x.name)
        if (p1, p2, p3) in self._triplet2circle:
            return self._triplet2circle[(p1, p2, p3)]
        return self.get_new_circle_thru_triplet(p1, p2, p3)

    def get_new_circle_thru_triplet(self, p1: Point, p2: Point, p3: Point) -> Circle:
        """Get a new Circle that goes thru three given Points."""
        p1, p2, p3 = sorted([p1, p2, p3], key=lambda x: x.name)
        name = p1.name.lower() + p2.name.lower() + p3.name.lower()
        circle = self.new_node(Circle, f"({name})")
        circle.num = num_geo.Circle(p1=p1.num, p2=p2.num, p3=p3.num)
        circle.points = p1, p2, p3

        self.connect(p1, circle, deps=None)
        self.connect(p2, circle, deps=None)
        self.connect(p3, circle, deps=None)
        self._triplet2circle[(p1, p2, p3)] = circle
        return circle

    def draw_html(self, html_path: Path):
        nt = Network("1080px")
        # populates the nodes and edges data structures
        nx_graph = Graph()
        for node_type, nodes in self.type2nodes.items():
            type_name = node_type.__name__
            for node in nodes:
                nx_graph.add_node(node.name, title=type_name, group=type_name)
                for neighbor_type in self.type2nodes.keys():
                    neighbor_type_name = neighbor_type.__name__
                    for neighbor in node.neighbors(neighbor_type):
                        nx_graph.add_node(
                            neighbor.name,
                            title=neighbor_type_name,
                            group=neighbor_type_name,
                        )
                        nx_graph.add_edge(neighbor.name, node.name)

        nt.from_nx(nx_graph)
        nt.show(str(html_path), notebook=False)
