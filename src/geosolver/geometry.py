"""Implements geometric objects used in the graph representation."""

from __future__ import annotations
from typing import TYPE_CHECKING, Optional, Type, TypeVar
from typing_extensions import Self

from geosolver.numerical.geometries import PointNum

if TYPE_CHECKING:
    from geosolver.dependencies.dependency import Dependency

T = TypeVar("T")


class Symbol:
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

    def __init__(self, name: str = ""):
        if name:
            self.name = name

        self.edge_graph: dict[Self, dict[Self, list["Dependency"]]] = {}
        # Edge graph: what other nodes is merged to this node.
        # edge graph = {
        #   u1: {v1: deps, v2: deps},
        #   u2: {v1: deps, v2: deps}
        # }

        self.merge_graph: dict[Self, list["Dependency"]] = {}
        # Merge graph: history of merges with other nodes.
        # u.merge_graph = {v1: deps, v2: deps}
        # v1.merge_graph = {u: deps}

        self.rep_by = None  # represented by.
        self.members = {self}

        self._val: Optional[Symbol] = None
        self._obj: Optional[Symbol] = None

        # numerical representation.
        self.num: Optional[PointNum] = None

    def rep(self) -> Self:
        x = self
        while x.rep_by:
            x = x.rep_by
        return x

    def why_rep(self) -> list[Dependency]:
        return self.why_equal([self.rep()])

    def rep_and_why(self) -> tuple[Self, list[Dependency]]:
        rep = self.rep()
        return rep, self.why_equal([rep])

    def neighbors(self, oftype: Type[T]) -> set[T]:
        """Neighbors of this node in the proof state graph."""
        rep = self.rep()
        result = set()

        for n in rep.edge_graph:
            if (oftype is None) or (oftype and isinstance(n, oftype)):
                result.add(n.rep())

        return result

    def merge_edge_graph(
        self, new_edge_graph: dict[Symbol, dict[Symbol, list[Symbol]]]
    ) -> None:
        for x, xdict in new_edge_graph.items():
            if x in self.edge_graph:
                self.edge_graph[x].update(dict(xdict))
            else:
                self.edge_graph[x] = dict(xdict)

    def merge_one(self, node: Symbol, deps: list["Dependency"]) -> None:
        selfrep = self.rep()
        noderep = node.rep()
        if selfrep == noderep:
            return
        noderep.rep_by = selfrep
        selfrep.merge_edge_graph(node.edge_graph)
        selfrep.members.update(selfrep.members)

        self.merge_graph[node] = deps
        node.merge_graph[self] = deps

    def merge(self, nodes: list[Symbol], deps: list["Dependency"]) -> None:
        for node in nodes:
            self.merge_one(node, deps)

    def is_val(self, node: Symbol) -> bool:
        return type(self) in NODES_VALUES and isinstance(node, NODES_VALUES[type(self)])

    @property
    def val(self) -> Symbol:
        if self._val is None:
            return None
        return self._val.rep()

    @property
    def obj(self) -> Symbol:
        if self._obj is None:
            return None
        return self._obj.rep()

    def equivs(self) -> set[Self]:
        return self.rep().members

    def connect_to(self, node: Symbol, deps: list["Dependency"] = None) -> None:
        rep = self.rep()

        if node in rep.edge_graph:
            rep.edge_graph[node].update({self: deps})
        else:
            rep.edge_graph[node] = {self: deps}

        if self.is_val(node):
            self._val = node
            node._obj = self

    def equivs_upto(self) -> dict[Symbol, Symbol]:
        """Return equivalent nodes upto self and their parents"""
        parent = {self: None}
        visited = set()
        queue = [self]
        i = 0

        while i < len(queue):
            current = queue[i]
            i += 1
            visited.add(current)

            for neighbor in current.merge_graph:
                if neighbor in visited:
                    continue
                queue.append(neighbor)
                parent[neighbor] = current

        return parent

    def why_equal(self, others: list[Symbol]) -> Optional[list["Dependency"]]:
        """Why this node is equal to other nodes (BFS)."""
        others = set(others)
        found = 0

        parent = {}
        queue = [self]
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
        return None

    def why_equal_groups(
        self, groups: list[list[Symbol]]
    ) -> tuple[Optional[list["Dependency"]], Optional[list[Symbol]]]:
        """Why self is equal to at least one member of each group (BFS)."""
        others = [None] * len(groups)
        found = 0

        parent = {}
        queue = [self]
        i = 0

        while i < len(queue):
            current = queue[i]
            i += 1

            for j, grp in enumerate(groups):
                if others[j] is None and current in grp:
                    others[j] = current
                    found += 1

            if found == len(others):
                return bfs_backtrack(self, others, parent), others

            for neighbor in current.merge_graph:
                if neighbor in parent:
                    continue
                queue.append(neighbor)
                parent[neighbor] = current
        return None, None

    def why_connected_to(self, points: list[Point]) -> Optional[list[Dependency]]:
        """Why points are connected to form a thing of Self."""
        rep = self.rep()
        groups: list[list[Self]] = []
        for p in points:
            group = [obj for obj, dep in rep.edge_graph[p].items() if dep == []]
            if not group:
                return None
            groups.append(group)

        min_deps = None
        for con in groups[0]:
            deps, _ = con.why_equal_groups(groups[1:])
            if deps is None:
                continue

            if min_deps is None or len(deps) < len(min_deps):
                min_deps = deps

        if min_deps is None:
            return None
        return min_deps

    def __repr__(self) -> str:
        return self.name


def bfs_backtrack(
    root: Symbol, leafs: list[Symbol], parent: dict[Symbol, Symbol]
) -> list["Dependency"]:
    """Return the path given BFS trace of parent nodes."""
    backtracked = {root}  # no need to backtrack further when touching this set.
    deps = []
    for node in leafs:
        if node in backtracked:
            continue
        while node not in backtracked:
            backtracked.add(node)
            dep = node.merge_graph[parent[node]]
            deps.append(dep)
            node = parent[node]

    return deps


class Point(Symbol):
    rely_on: list[Point] = None
    plevel: int
    group: list[Self]
    dep_points = set[Self]
    why: list["Dependency"]  # to generate txt logs.


class Line(Symbol):
    """Symbol of type Line."""

    points: set[Point]
    _val: Optional[Direction]


class Segment(Symbol):
    points: set[Point]
    _val: Optional[Length]


class Circle(Symbol):
    """Symbol of type Circle."""

    points: list[Point]


class Angle(Symbol):
    """Symbol of type Angle."""

    _d: tuple[Optional[Direction], Optional[Direction]] = (None, None)
    _val: Optional[AngleValue]
    opposite: Angle = None

    def set_directions(self, d1: Direction, d2: Direction) -> None:
        self._d = d1, d2

    @property
    def directions(self) -> tuple[Optional[Direction], Optional[Direction]]:
        d1, d2 = self._d
        if d1 is None:
            return None, None
        return d1.rep(), d2.rep()


class Ratio(Symbol):
    """Symbol of type Ratio."""

    _l: tuple[Optional[Length], Optional[Length]] = (None, None)
    _val: Optional[RatioValue]
    opposite: Ratio = None

    def set_lengths(self, l1: Length, l2: Length) -> None:
        self._l = l1, l2

    @property
    def lengths(self) -> tuple[Optional[Length], Optional[Length]]:
        l1, l2 = self._l
        if l1 is None:
            return None, None
        return l1.rep(), l2.rep()


class Direction(Symbol):
    _obj: Optional[Line]


class Length(Symbol):
    _obj: Optional[Segment]

    @property
    def value(self) -> float:
        return float(self.name)


class AngleValue(Symbol):
    _obj: Optional[Angle]


class RatioValue(Symbol):
    _obj: Optional[Ratio]

    @property
    def value(self) -> float:
        n, d = self.name.split("/")
        return int(n) / int(d)


RANKING = {
    Point: 0,
    Line: 1,
    Segment: 2,
    Circle: 3,
    Direction: 4,
    Length: 5,
    Angle: 6,
    Ratio: 7,
    AngleValue: 8,
    RatioValue: 9,
}

NODES_VALUES: dict[Type[Symbol], Type[Symbol]] = {
    Line: Direction,
    Segment: Length,
    Angle: AngleValue,
    Ratio: RatioValue,
}

NODES_VALUES_MARKERS: dict[Type[Symbol], str] = {
    Direction: "d",
    Length: "l",
    AngleValue: "m",
    RatioValue: "r",
}
