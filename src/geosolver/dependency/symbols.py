"""Implements geometric objects used in the graph representation."""

from __future__ import annotations
from abc import ABC
from typing import TYPE_CHECKING, Optional, Self, TypeVar

from geosolver.dependency.dependency import Dependency
from geosolver.numerical.geometries import CircleNum, LineNum, PointNum

if TYPE_CHECKING:
    from geosolver.dependency.symbols_graph import SymbolsGraph
    from geosolver.dependency.dependency import Dependency

S = TypeVar("S", bound="Symbol")


class Symbol(ABC):
    r"""Symbol in the symbols graph.

    Can be Point, Line, Circle, etc.

    Each node maintains a merge history to
    other nodes if they are (found out to be) equivalent

    ::
        a -> b -
                \
            c -> d -> e -> f -> g


    d.merged_to = e
    d.rep = g
    d.merged_from = {a, b, c, d}
    d.equivs = {a, b, c, d, e, f, g}
    d.members = {a, b, c, d}

    """

    def __init__(
        self, name: str, symbols_graph: "SymbolsGraph", dep: Optional[Dependency]
    ):
        self.name = name
        self.symbols_graph = symbols_graph
        self.dep = dep
        self.merge_graph: dict[Self, Dependency] = {}
        self._rep: Self = self

    def rep(self) -> Self:
        if self._rep != self:
            self._rep = self._rep.rep()
        return self._rep

    def _merge_one(self, node: Self, dep: Dependency) -> Self:
        selfrep = self.rep()
        noderep = node.rep()
        if selfrep == noderep:
            return selfrep
        noderep._rep = selfrep

        selfrep.merge_graph[noderep] = dep
        noderep.merge_graph[selfrep] = dep
        return selfrep

    def _merge(self, nodes: list[Self], dep: Dependency) -> Self:
        for node in nodes:
            self._merge_one(node, dep)
        return self.rep()

    def why_equiv(self, others: set[Self]) -> list[Dependency]:
        """Why this node is equivalent to other nodes (BFS)."""
        found = 0

        parent: dict[Self, Self] = {}
        queue: list[Self] = [self]
        i = 0

        while i < len(queue):
            current = queue[i]
            i += 1

            if current in others:
                found += 1
            if found == len(others):
                return bfs_backtrack(self, others, parent)

            for neighbor in current.merge_graph:
                if neighbor in parent:
                    continue
                queue.append(neighbor)
                parent[neighbor] = current
        raise Exception("Why resolution fails")

    def __repr__(self) -> str:
        return self.name


def bfs_backtrack(root: S, leafs: set[S], parent: dict[S, S]) -> list[Dependency]:
    """Return the path given BFS trace of parent nodes."""
    backtracked: set[S] = {root}  # no need to backtrack further when touching this set.
    deps: list[Dependency] = []
    for node in leafs:
        if node in backtracked:
            continue
        while node not in backtracked:
            backtracked.add(node)
            deps.append(node.merge_graph[parent[node]])
            if node.dep is not None:
                deps.append(node.dep)
            node = parent[node]

    return list(set(deps))


class Point(Symbol):
    num: PointNum


class Line(Symbol):
    """Symbol of type Line."""

    points: set[Point]
    num: LineNum

    @classmethod
    def check_coll(cls, points: list[Point] | tuple[Point]) -> bool:
        symbols_graph = points[0].symbols_graph
        s = set(points)
        for line in symbols_graph.nodes_of_type(Line):
            if s <= line.points:
                return True
        return False

    @classmethod
    def make_coll(
        cls, points: list[Point] | tuple[Point], dep: Dependency
    ) -> tuple[Line, list[Line]]:
        symbols_graph = points[0].symbols_graph
        s = set(points)
        merge: list[Line] = []
        for line in symbols_graph.nodes_of_type(Line):
            if s <= line.points:
                return line, []
            if len(s & line.points) >= 2:
                merge.append(line)
                s.update(line.points)
        line = symbols_graph.new_node(
            Line, f"line/{'-'.join(p.name for p in points)}/", dep
        )
        line.points = s
        symbols_graph.merge(line, merge, dep)
        return line, merge


class Circle(Symbol):
    """Symbol of type Circle."""

    points: set[Point]
    num: CircleNum

    @classmethod
    def check_concyclic(cls, points: list[Point] | tuple[Point]) -> bool:
        symbols_graph = points[0].symbols_graph
        s = set(points)
        for c in symbols_graph.nodes_of_type(Circle):
            if s <= c.points:
                return True
        return False

    @classmethod
    def make_concyclic(cls, points: list[Point] | tuple[Point], dep: Dependency):
        symbols_graph = points[0].symbols_graph
        s = set(points)
        merge: list[Circle] = []
        for c in symbols_graph.nodes_of_type(Circle):
            if s <= c.points:
                return
            if len(s & c.points) >= 3:
                merge.append(c)
                s.update(c.points)
        c = symbols_graph.new_node(
            Circle, f"circle({''.join(p.name for p in points)})", dep
        )
        c.points = s
        symbols_graph.merge(c, merge, dep)
