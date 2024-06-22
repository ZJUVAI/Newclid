from __future__ import annotations
from collections import defaultdict
from typing import TYPE_CHECKING, Generator, Optional
from typing_extensions import Self

from geosolver.dependencies.dependency import Reason, Dependency

from geosolver.dependencies.why_predicates import line_of_and_why
from geosolver.numerical import ATOM
from geosolver.numerical.geometries import LineNum, PointNum

from geosolver.predicates.predicate import Predicate, PredicateArgument
from geosolver.intrinsic_rules import IntrinsicRules

from geosolver.geometry import Point, Line
from geosolver.combinatorics import arrangement_pairs, permutations_triplets
from geosolver.statements.statement import (
    Statement,
    hash_unordered_set_of_points,
    hashed_unordered_two_lines_points,
)
from geosolver.symbols_graph import SymbolsGraph

import geosolver.predicates as preds

if TYPE_CHECKING:
    from geosolver.dependencies.why_graph import DependencyGraph
    from geosolver.dependencies.dependency_building import DependencyBody


class Coll(Predicate):
    """coll A B C ... -
    Represent that the 3 (or more) points in the arguments are collinear."""

    NAME = "coll"

    @staticmethod
    def add(
        args: list[PredicateArgument],
        dep_body: "DependencyBody",
        dep_graph: "DependencyGraph",
        symbols_graph: "SymbolsGraph",
        disabled_intrinsic_rules: list["IntrinsicRules"],
    ) -> tuple[list["Dependency"], list[tuple[Statement, Dependency]]]:
        """Add a predicate that `points` are collinear."""
        points = list(set(args))
        og_points = points.copy()

        all_lines: list[Line] = []
        for p1, p2 in arrangement_pairs(points):
            all_lines.append(symbols_graph.get_line_thru_pair(p1, p2))
        points = sum([line.neighbors(Point) for line in all_lines], [])
        points = list(set(points))

        existed: set[Line] = set()
        new: set[Line] = set()
        for p1, p2 in arrangement_pairs(points):
            if p1.name > p2.name:
                p1, p2 = p2, p1
            if (p1, p2) in symbols_graph._pair2line:
                line = symbols_graph._pair2line[(p1, p2)]
                existed.add(line)
            else:
                line = symbols_graph.get_new_line_thru_pair(p1, p2)
                new.add(line)

        sorted_existed: list[Line] = list(sorted(existed, key=lambda node: node.name))
        sorted_new: list[Line] = list(sorted(new, key=lambda node: node.name))
        if not sorted_existed:
            line0, *lines = sorted_new
        else:
            line0, lines = sorted_existed[0], sorted_existed[1:] + sorted_new

        add = []
        to_cache = []
        line0, why0 = line0.rep_and_why()
        a, b = line0.points
        for line in lines:
            c, d = line.points
            args = list({a, b, c, d})
            if len(args) < 3:
                continue

            whys: list[Dependency] = []
            for x in args:
                if x not in og_points:
                    whys.append(Coll._coll_dep(og_points, x, dep_graph, symbols_graph))

            abcd_deps = dep_body
            if IntrinsicRules.POINT_ON_SAME_LINE not in disabled_intrinsic_rules:
                abcd_deps = dep_body.extend_by_why(
                    dep_graph,
                    Statement(Coll, og_points),
                    why=whys + why0,
                    extention_reason=Reason(IntrinsicRules.POINT_ON_SAME_LINE),
                )

            is_coll = Coll.check(args, symbols_graph)
            coll = Statement(Coll, args)
            dep = abcd_deps.build(dep_graph, coll)
            to_cache.append((coll, dep))
            symbols_graph.merge_into(line0, [line], dep)

            if not is_coll:
                add += [dep]

        return add, to_cache

    @staticmethod
    def _coll_dep(
        points: list[Point],
        p: Point,
        dep_graph: "DependencyGraph",
        symbols_graph: "SymbolsGraph",
    ) -> list[Dependency]:
        """Return the dep(.why) explaining why p is coll with points."""
        for p1, p2 in arrangement_pairs(points):
            if Coll.check([p1, p2, p], symbols_graph):
                coll = Statement(Coll, (p1, p2, p))
                return dep_graph.build_resolved_dependency(coll)

    @staticmethod
    def why(
        dep_graph: "DependencyGraph", statement: "Statement"
    ) -> tuple[Optional[Reason], list[Dependency]]:
        _, why = line_of_and_why(statement.args)
        return None, why

    @staticmethod
    def check(args: list[PredicateArgument], symbols_graph: SymbolsGraph) -> bool:
        points = list(set(args))
        if len(points) < 3:
            return True
        line2count = defaultdict(lambda: 0)
        for p in points:
            for line in p.neighbors(Line):
                line2count[line] += 1
        return any([count == len(points) for _, count in line2count.items()])

    @staticmethod
    def check_numerical(args: list["PointNum"]) -> bool:
        a, b = args[:2]
        line = LineNum(a, b)
        for p in args[2:]:
            if abs(line(p.x, p.y)) > ATOM:
                return False
        return True

    @staticmethod
    def enumerate(
        symbols_graph: "SymbolsGraph",
    ) -> Generator[tuple[Point, ...], None, None]:
        for line in symbols_graph.type2nodes[Line]:
            for x, y, z in permutations_triplets(line.neighbors(Point)):
                yield x, y, z

    @staticmethod
    def pretty(args: list[str]) -> str:
        return "" + ",".join(args) + " are collinear"

    @classmethod
    def hash(
        cls: Self, args: list[PredicateArgument]
    ) -> tuple[str | PredicateArgument]:
        return hash_unordered_set_of_points(cls.NAME, args)


class Collx(Predicate):
    NAME = "collx"

    @staticmethod
    def add(
        *args, **kwargs
    ) -> tuple[list[Dependency], list[tuple[Statement, Dependency]]]:
        return preds.Coll.add(*args, **kwargs)

    @staticmethod
    def why(
        dep_graph: "DependencyGraph", statement: Statement
    ) -> tuple[Optional[Reason], list[Dependency]]:
        if preds.Coll.check(statement.args, dep_graph.symbols_graph):
            args = list(set(statement.args))
            coll = Statement(preds.Coll, args)
            cached_dep = dep_graph.dependency_cache.get(coll)
            if cached_dep is not None:
                return None, [cached_dep]
            _, why = line_of_and_why(args)
            return None, why

        para = Statement(preds.Para, statement.args)
        return preds.Para.why(dep_graph, para)

    @staticmethod
    def check(args: list[Point], symbols_graph: SymbolsGraph) -> bool:
        raise NotImplementedError

    @staticmethod
    def check_numerical(args: list[PointNum]) -> bool:
        raise NotImplementedError

    @staticmethod
    def enumerate(
        symbols_graph: SymbolsGraph,
    ) -> Generator[tuple[Point, ...], None, None]:
        raise NotImplementedError

    @staticmethod
    def pretty(args: list[str]) -> str:
        return "" + ",".join(list(set(args))) + " are collinear"

    @classmethod
    def hash(cls, args: list[Point]) -> tuple[str]:
        return hashed_unordered_two_lines_points(cls.NAME, args)


class NColl(Predicate):
    """ncoll A B C ... -
    Represent that any of the 3 (or more) points is not aligned with the others.

    Numerical only.
    """

    NAME = "ncoll"

    @staticmethod
    def add(
        args: list[Point],
        dep_body: "DependencyBody",
        dep_graph: "DependencyGraph",
        symbols_graph: SymbolsGraph,
        disabled_intrinsic_rules: list[IntrinsicRules],
    ) -> tuple[list[Dependency], list[tuple[Statement, Dependency]]]:
        raise NotImplementedError

    @staticmethod
    def why(
        dep_graph: "DependencyGraph", statement: Statement
    ) -> tuple[Optional[Reason], list[Dependency]]:
        return None, []

    @staticmethod
    def check(args: list[Point], symbols_graph: SymbolsGraph) -> bool:
        if preds.Coll.check(args, symbols_graph):
            return False
        return not preds.Coll.check_numerical([p.num for p in args])

    @staticmethod
    def check_numerical(args: list[PointNum]) -> bool:
        return not preds.Coll.check_numerical(args)

    @staticmethod
    def enumerate(
        symbols_graph: SymbolsGraph,
    ) -> Generator[tuple[Point, ...], None, None]:
        raise NotImplementedError

    @staticmethod
    def pretty(args: list[str]) -> str:
        raise NotImplementedError

    @classmethod
    def hash(cls, args: list[Point]) -> tuple[str]:
        return hash_unordered_set_of_points(cls.NAME, args)
