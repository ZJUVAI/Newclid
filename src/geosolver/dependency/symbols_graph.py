from __future__ import annotations
from typing import TYPE_CHECKING, Collection, Optional, Type, TypeVar

from geosolver.algebraic_reasoning.tables import Table
import geosolver.numerical.geometries as num_geo
from geosolver.dependency.symbols import Circle, Line, Point, Symbol

if TYPE_CHECKING:
    from geosolver.dependency.dependency import Dependency

S = TypeVar("S", bound="Symbol")
CircL = TypeVar("CircL", "Circle", "Line")


class SymbolsGraph:
    def __init__(self) -> None:
        self._type2nodes: dict[Type[Symbol], list[Symbol]] = {
            Point: list(),
            Line: list(),
            Circle: list(),
        }
        self.name2node: dict[str, Symbol] = {}

    def nodes_of_type(self, t: Type[S]) -> list[S]:
        return list(self._type2nodes[t])  # type: ignore

    def names2points(
        self, pnames: Collection[str], create_new_point: bool = True
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

    def container_of(self, pnames: set[Point], t: Type[CircL]) -> Optional[CircL]:
        for container in self.nodes_of_type(t):
            if pnames <= container.points:
                return container
        return None

    def new_node(
        self, oftype: Type[S], name: str, dep: Optional[Dependency] = None
    ) -> S:
        if name in self.name2node:
            raise ValueError(f"Node {name} already present")
        node = oftype(name, self, dep)
        self._type2nodes[type(node)].append(node)
        self.name2node[node.name] = node
        return node

    def _get_new_line_thru_pair(self, p1: Point, p2: Point) -> Line:
        name = p1.name + p2.name
        line = self.new_node(Line, name)
        line.num = num_geo.LineNum(p1.num, p2.num)
        line.points = {p1, p2}
        return line

    def line_thru_pair(self, p1: Point, p2: Point, table: Table) -> Line:
        for line in self.nodes_of_type(Line):
            if {p1, p2} <= line.points:
                for line1 in line.fellows:
                    if {p1, p2} == line1.points:
                        return line1
                res = self._get_new_line_thru_pair(p1, p2)
                assert line.dep
                table.add_expr(table.get_eq2(res.name, line.name), line.dep)
                line.fellows.append(res)
                return res
        return self._get_new_line_thru_pair(p1, p2)
