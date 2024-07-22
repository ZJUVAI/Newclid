from __future__ import annotations
from typing import TYPE_CHECKING, Iterable, Optional, Type, TypeVar

import geosolver.numerical.geometries as num_geo
from geosolver.dependency.symbols import Circle, Line, Point, Symbol

if TYPE_CHECKING:
    from geosolver.dependency.dependency import Dependency

S = TypeVar("S", bound="Symbol")
CircL = TypeVar("CircL", "Circle", "Line")


class SymbolsGraph:
    def __init__(self) -> None:
        self._type2nodes: dict[Type[Symbol], set[Symbol]] = {
            Point: set(),
            Line: set(),
            Circle: set(),
        }
        self.name2node: dict[str, Symbol] = {}

    def nodes_of_type(self, t: Type[S]) -> list[S]:
        return list(self._type2nodes[t])  # type: ignore

    def names2nodes(self, pnames: Iterable[str]) -> list[Symbol]:
        return [self.name2node[name] for name in pnames]

    def names2points(
        self, pnames: Iterable[str], create_new_point: bool = True
    ) -> list[Point]:
        """Return Point objects given names."""
        result: list[Point] = []
        for name in pnames:
            if name not in self.name2node and not create_new_point:
                raise ValueError(f"Cannot find point {name} in graph")
            elif name in self.name2node:
                obj = self.name2node[name]
                assert isinstance(obj, Point)
            else:
                obj = self.new_node(Point, name, None)
            result.append(obj)

        return result

    def _add_node(self, node: Symbol) -> None:
        if node.name in self.name2node:
            return
        self._type2nodes[type(node)].add(node)
        self.name2node[node.name] = node

    def new_node(
        self, oftype: Type[S], name: str, dep: Optional[Dependency] = None
    ) -> S:
        if name in self.name2node:
            raise ValueError(f"Node {name} already present")
        node = oftype(name, self, dep)
        self._add_node(node)
        return node

    def merge(self, node0: S, nodes: list[S], dep: Dependency) -> None:
        """Merge all nodes."""
        node0._merge(nodes, dep)  # type: ignore
        for node in nodes:
            if node.rep() != node:
                self._type2nodes[type(node)].remove(node)

    def _get_new_line_thru_pair(self, p1: Point, p2: Point) -> Line:
        name = p1.name + p2.name
        line = self.new_node(Line, name)
        line.num = num_geo.LineNum(p1.num, p2.num)
        line.points = {p1, p2}
        return line

    def line_thru_pair(self, p1: Point, p2: Point) -> Line:
        for line in self.nodes_of_type(Line):
            if {p1, p2} <= line.points:
                init_line: Optional[Line] = None
                for line1 in line.fellows:
                    if {p1, p2} <= line1.points and (
                        init_line is None or len(init_line.points) > len(line1.points)
                    ):
                        init_line = line1
                assert init_line is not None
                return init_line
        return self._get_new_line_thru_pair(p1, p2)

    def circle_thru_triplet(self, p1: Point, p2: Point, p3: Point) -> Circle:
        for c in self.nodes_of_type(Circle):
            if {p1, p2, p3} <= c.points:
                init_circle: Optional[Circle] = None
                for circle1 in c.fellows:
                    if {p1, p2} <= circle1.points and (
                        init_circle is None
                        or len(init_circle.points) > len(circle1.points)
                    ):
                        init_circle = circle1
                assert init_circle is not None
                return init_circle
        return self._get_new_circle_thru_triplet(p1, p2, p3)

    def _get_new_circle_thru_triplet(self, p1: Point, p2: Point, p3: Point) -> Circle:
        """Get a new Circle that goes thru three given Points."""
        circle = self.new_node(Circle, f"({p1.name + p2.name + p3.name})")
        circle.num = num_geo.CircleNum(p1=p1.num, p2=p2.num, p3=p3.num)
        circle.points = {p1, p2, p3}
        return circle
