from __future__ import annotations
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional, Type

from networkx import Graph
from pyvis.network import Network

import geosolver.numerical.geometries as num_geo
from geosolver.numerical.draw_figure import draw_figure as draw_numerical_figure
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


if TYPE_CHECKING:
    from geosolver.dependencies.dependency import Dependency


NODES_VALUES: dict[Type[Node], Type[Node]] = {
    Line: Direction,
    Segment: Length,
    Angle: Measure,
    Ratio: Value,
}

NODES_VALUES_MARKERS: dict[Type[Node], str] = {
    Direction: "d",
    Length: "l",
    Measure: "m",
    Value: "r",
}


class SymbolsGraph:
    def __init__(self) -> None:
        self.type2nodes: dict[Type[Node], list[Node]] = {
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
        self._name2point: dict[str, Point] = {}
        self._name2node: dict[str, Node] = {}
        self._pair2line: dict[tuple[Point, Point], Line] = {}
        self._triplet2circle: dict[tuple[Point, Point, Point], Circle] = {}

    def connect(self, a: Node, b: Node, deps: "Dependency") -> None:
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

    def get_node_val(self, node: Node, deps: Optional["Dependency"]) -> Node:
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
        return default_fn(pointname)

    def merge(self, nodes: list[Node], deps: "Dependency") -> Node:
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

    def merge_into(self, node0: Node, nodes1: list[Node], deps: "Dependency") -> Node:
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

    def get_line(self, a: Point, b: Point) -> Optional[Line]:
        linesa = a.neighbors(Line)
        for line in b.neighbors(Line):
            if line in linesa:
                return line
        return None

    def get_segment(self, p1: Point, p2: Point) -> Optional[Segment]:
        for s in self.type2nodes[Segment]:
            if s.points == {p1, p2}:
                return s
        return None

    def get_angle(self, d1: Direction, d2: Direction) -> tuple[Angle, Optional[Angle]]:
        for a in self.type2nodes[Angle]:
            if a.directions == (d1, d2):
                return a, a.opposite
        return None, None

    def get_ratio(self, l1: Length, l2: Length) -> tuple[Ratio, Ratio]:
        for r in self.type2nodes[Ratio]:
            if r.lengths == (l1, l2):
                return r, r.opposite
        return None, None

    def get_circles(self, *points: list[Point]) -> list[Circle]:
        circle2count = defaultdict(lambda: 0)
        for p in points:
            for c in p.neighbors(Circle):
                circle2count[c] += 1
        return [c for c, count in circle2count.items() if count >= 3]

    def get_or_create_segment(
        self, p1: Point, p2: Point, deps: "Dependency"
    ) -> Segment:
        """Get or create a Segment object between two Points p1 and p2."""
        if p1 == p2:
            raise ValueError(f"Creating same 0-length segment {p1.name}")

        for s in self.type2nodes[Segment]:
            if s.points == {p1, p2}:
                return s

        if p1.name > p2.name:
            p1, p2 = p2, p1
        s = self.new_node(Segment, name=f"{p1.name.upper()}{p2.name.upper()}")
        self.connect(p1, s, deps=deps)
        self.connect(p2, s, deps=deps)
        s.points = {p1, p2}
        return s

    def get_or_create_angle_from_lines(
        self, l1: Line, l2: Line, deps: "Dependency"
    ) -> tuple[Angle, Angle, list["Dependency"]]:
        return self.get_or_create_angle_from_directions(l1._val, l2._val, deps)

    def get_or_create_angle_from_directions(
        self, d1: Direction, d2: Direction, deps: "Dependency"
    ) -> tuple[Angle, Angle, list["Dependency"]]:
        """Get or create an angle between two Direction d1 and d2."""
        for a in self.type2nodes[Angle]:
            if a.directions == (d1.rep(), d2.rep()):  # directions = _d.rep()
                d1_, d2_ = a._d
                why1 = d1.why_equal([d1_], None) + d1_.why_rep()
                why2 = d2.why_equal([d2_], None) + d2_.why_rep()
                return a, a.opposite, why1 + why2

        d1, why1 = d1.rep_and_why()
        d2, why2 = d2.rep_and_why()
        a12 = self.new_node(Angle, f"{d1.name}-{d2.name}")
        a21 = self.new_node(Angle, f"{d2.name}-{d1.name}")
        self.connect(d1, a12, deps)
        self.connect(d2, a21, deps)
        self.connect(a12, a21, deps)
        a12.set_directions(d1, d2)
        a21.set_directions(d2, d1)
        a12.opposite = a21
        a21.opposite = a12
        return a12, a21, why1 + why2

    def get_or_create_ratio_from_segments(
        self, s1: Segment, s2: Segment, deps: "Dependency"
    ) -> tuple[Ratio, Ratio, list["Dependency"]]:
        return self.get_or_create_ratio_from_lenghts(s1._val, s2._val, deps)

    def get_or_create_ratio_from_lenghts(
        self, l1: Length, l2: Length, deps: "Dependency"
    ) -> tuple[Ratio, Ratio, list["Dependency"]]:
        """Get or create a new Ratio from two Lenghts l1 and l2."""
        for r in self.type2nodes[Ratio]:
            if r.lengths == (l1.rep(), l2.rep()):
                l1_, l2_ = r._l
                why1 = l1.why_equal([l1_], None) + l1_.why_rep()
                why2 = l2.why_equal([l2_], None) + l2_.why_rep()
                return r, r.opposite, why1 + why2

        l1, why1 = l1.rep_and_why()
        l2, why2 = l2.rep_and_why()
        r12 = self.new_node(Ratio, f"{l1.name}/{l2.name}")
        r21 = self.new_node(Ratio, f"{l2.name}/{l1.name}")
        self.connect(l1, r12, deps)
        self.connect(l2, r21, deps)
        self.connect(r12, r21, deps)
        r12.set_lengths(l1, l2)
        r21.set_lengths(l2, l1)
        r12.opposite = r21
        r21.opposite = r12
        return r12, r21, why1 + why2

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
    ) -> tuple[Line, list["Dependency"]]:
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

    @staticmethod
    def two_points_of_length(lenght: Length) -> tuple[Point, Point]:
        s = lenght.neighbors(Segment)[0]
        p1, p2 = s.points
        return p1, p2

    @staticmethod
    def two_points_on_direction(d: Direction) -> tuple[Point, Point]:
        line_neighbor = d.neighbors(Line)[0]
        p1, p2 = line_neighbor.neighbors(Point)[:2]
        return p1, p2

    def draw_html(self, html_path: Path):
        nt = Network("1080px")
        # populates the nodes and edges data structures
        nx_graph = Graph()
        for node_type, nodes in self.type2nodes.items():
            type_name = node_type.__name__
            for node in nodes:
                nx_graph.add_node(node.name, title=type_name, group=type_name)
                rep = node.rep()
                if rep != node:
                    rep_type = rep.__class__.__name__
                    nx_graph.add_node(rep.name, title=rep_type, group=rep_type)
                    nx_graph.add_edge(rep.name, node.name, dashes=True)
                for neighbor_type in self.type2nodes.keys():
                    neighbor_type_name = neighbor_type.__name__
                    for neighbor in node.neighbors(neighbor_type):
                        nx_graph.add_node(
                            neighbor.name,
                            title=neighbor_type_name,
                            group=neighbor_type_name,
                        )
                        nx_graph.add_edge(neighbor.name, rep.name)

        nt.from_nx(nx_graph)
        nt.show(str(html_path), notebook=False)

    def draw_figure(self, save_path: Optional[Path] = None):
        if save_path is not None:
            save_path = str(save_path)
        draw_numerical_figure(
            self.type2nodes[Point],
            self.type2nodes[Line],
            self.type2nodes[Circle],
            self.type2nodes[Segment],
            save_to=save_path,
            block=save_path is None,
        )
