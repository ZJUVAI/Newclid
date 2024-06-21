from __future__ import annotations
from typing import TYPE_CHECKING, Generator
from typing_extensions import Self

from geosolver.dependencies.dependency import Dependency, Reason
from geosolver.dependencies.why_predicates import line_of_and_why
from geosolver.geometry import Point
from geosolver.numerical.geometries import PointNum
from geosolver.predicates.predicate import Predicate
from geosolver.statements.statement import Statement, hashed_unordered_two_lines_points
from geosolver.symbols_graph import SymbolsGraph


import geosolver.predicates as preds

if TYPE_CHECKING:
    from geosolver.dependencies.why_graph import WhyHyperGraph


class Collx(Predicate):
    NAME = "collx"

    @staticmethod
    def add(
        *args, **kwargs
    ) -> tuple[list[Dependency], list[tuple[Statement, Dependency]]]:
        return preds.Coll.add(*args, **kwargs)

    @staticmethod
    def why(
        statements_graph: "WhyHyperGraph", statement: Statement
    ) -> tuple[Reason | None, list[Dependency]]:
        if preds.Coll.check(statement.args):
            args = list(set(statement.args))
            coll = Statement(preds.Coll.NAME, args)
            cached_dep = statements_graph.dependency_cache.get(coll)
            if cached_dep is not None:
                return None, [cached_dep]
            _, why = line_of_and_why(args)
            return None, why

        para = Statement(preds.Para.NAME, statement.args)
        return preds.Para.why(statements_graph, para)

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
    def hash(cls: Self, args: list[Point]) -> tuple[str]:
        return hashed_unordered_two_lines_points(cls.NAME, args)
