from __future__ import annotations
from collections import defaultdict
from typing import TYPE_CHECKING, Generator, Optional

from geosolver.combinatorics import arrangement_triplets, permutations_quadruplets
from geosolver.dependencies.dependency import Reason, Dependency


from geosolver.numerical import close_enough
from geosolver.numerical.geometries import CircleNum, PointNum
from geosolver.predicates.predicate import Predicate
from geosolver.intrinsic_rules import IntrinsicRules

from geosolver.geometry import Angle, Circle, Point, Ratio
from geosolver.statements.statement import Statement, hash_unordered_set_of_points
from geosolver.symbols_graph import SymbolsGraph


if TYPE_CHECKING:
    from geosolver.dependencies.why_graph import DependencyGraph
    from geosolver.dependencies.dependency_building import DependencyBody


class Cyclic(Predicate):
    """cyclic A B C D -
    Represent that 4 (or more) points lie on the same circle."""

    NAME = "cyclic"

    @staticmethod
    def add(
        args: list[Point | Ratio | Angle],
        dep_body: "DependencyBody",
        dep_graph: "DependencyGraph",
        symbols_graph: SymbolsGraph,
        disabled_intrinsic_rules: list[IntrinsicRules],
    ) -> tuple[list[Dependency], list[tuple[Statement, Dependency]]]:
        """Make the 4 or more points concyclic."""
        points = list(set(args))
        og_points = list(args)

        all_circles = []
        for p1, p2, p3 in arrangement_triplets(points):
            all_circles.append(symbols_graph.get_circle_thru_triplet(p1, p2, p3))
        points = sum([c.neighbors(Point) for c in all_circles], [])
        points = list(set(points))

        existed = set()
        new = set()
        for p1, p2, p3 in arrangement_triplets(points):
            p1, p2, p3 = sorted([p1, p2, p3], key=lambda x: x.name)

            if (p1, p2, p3) in symbols_graph._triplet2circle:
                circle = symbols_graph._triplet2circle[(p1, p2, p3)]
                existed.add(circle)
            else:
                circle = symbols_graph.get_new_circle_thru_triplet(p1, p2, p3)
                new.add(circle)

        existed = sorted(existed, key=lambda node: node.name)
        new = sorted(new, key=lambda node: node.name)

        existed, new = list(existed), list(new)
        if not existed:
            circle0, *circles = new
        else:
            circle0, circles = existed[0], existed[1:] + new

        add = []
        to_cache = []
        circle0, why0 = circle0.rep_and_why()
        a, b, c = circle0.points
        for circle in circles:
            d, e, f = circle.points
            args = list({a, b, c, d, e, f})
            if len(args) < 4:
                continue
            whys = []
            for x in [a, b, c, d, e, f]:
                if x not in og_points:
                    whys.append(Cyclic._cyclic_dep(og_points, x, symbols_graph))

            abcdef_deps = dep_body
            if IntrinsicRules.CYCLIC_FROM_CIRCLE:
                cyclic = Statement(Cyclic, og_points)
                abcdef_deps = abcdef_deps.extend_by_why(
                    dep_graph,
                    cyclic,
                    why=whys + why0,
                    extention_reason=Reason(IntrinsicRules.CYCLIC_FROM_CIRCLE),
                )

            is_cyclic = Cyclic.check(args, symbols_graph)
            cyclic = Statement(Cyclic, args)
            dep = abcdef_deps.build(dep_graph, cyclic)
            to_cache.append((cyclic, dep))
            symbols_graph.merge_into(circle0, [circle], dep)
            if not is_cyclic:
                add += [dep]

        return add, to_cache

    def _cyclic_dep(
        points: list[Point],
        p: Point,
        dep_graph: "DependencyGraph",
        symbols_graph: SymbolsGraph,
    ) -> list[Dependency]:
        for p1, p2, p3 in arrangement_triplets(points):
            if Cyclic.check([p1, p2, p3, p], symbols_graph):
                cyclic = Statement(Cyclic, (p1, p2, p3, p))
                return dep_graph.build_resolved_dependency(cyclic)

    @staticmethod
    def why(
        dep_graph: "DependencyGraph", statement: "Statement"
    ) -> tuple[Optional[Reason], list[Dependency]]:
        _, why = Cyclic._circle_of_and_why(statement.args)
        return None, why

    @staticmethod
    def _circle_of_and_why(
        points: list[Point],
    ) -> tuple[Optional[Circle], Optional[list[Dependency]]]:
        """Why points are concyclic."""
        for initial_circle in Cyclic._get_circles_thru_all(*points):
            for circle in initial_circle.equivs():
                if all([p in circle.edge_graph for p in points]):
                    cycls = list(set(points))
                    why = circle.why_cyclic(cycls)
                    if why is not None:
                        return circle, why

        return None, None

    @staticmethod
    def _get_circles_thru_all(*points: Point) -> list[Circle]:
        circle2count = defaultdict(lambda: 0)
        points = set(points)
        for point in points:
            for circle in point.neighbors(Circle):
                circle2count[circle] += 1
        return [c for c, count in circle2count.items() if count == len(points)]

    @staticmethod
    def check(args: list[Point], symbols_graph: SymbolsGraph) -> bool:
        points = list(set(args))
        if len(points) < 4:
            return True
        circle2count = defaultdict(lambda: 0)
        for p in points:
            for c in p.neighbors(Circle):
                circle2count[c] += 1
        return any([count == len(points) for _, count in circle2count.items()])

    @staticmethod
    def check_numerical(args: list[PointNum]) -> bool:
        points = list(set(args))
        a, b, c, *ps = points
        circle = CircleNum(p1=a, p2=b, p3=c)
        for d in ps:
            if not close_enough(d.distance(circle.center), circle.radius):
                return False
        return True

    @staticmethod
    def enumerate(
        symbols_graph: SymbolsGraph,
    ) -> Generator[tuple[Point, ...], None, None]:
        for c in symbols_graph.type2nodes[Circle]:
            for x, y, z, t in permutations_quadruplets(c.neighbors(Point)):
                yield x, y, z, t

    @staticmethod
    def pretty(args: list[str]) -> str:
        return "" + ",".join(args) + " are concyclic"

    @classmethod
    def hash(cls, args: list[Point]) -> tuple[str]:
        return hash_unordered_set_of_points(cls.NAME, args)
