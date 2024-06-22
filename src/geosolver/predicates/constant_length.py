from __future__ import annotations
from typing import TYPE_CHECKING, Generator, Optional
from typing_extensions import Self

from geosolver.dependencies.dependency import Reason, Dependency


from geosolver.numerical import close_enough
from geosolver.numerical.geometries import PointNum

from geosolver.predicates.predicate import Predicate
from geosolver.intrinsic_rules import IntrinsicRules

from geosolver.geometry import Angle, Direction, Length, Point, Ratio, Segment
from geosolver.statements.statement import (
    Statement,
    hash_unordered_set_of_points_with_value,
)
from geosolver.symbols_graph import SymbolsGraph, is_equal


if TYPE_CHECKING:
    from geosolver.dependencies.dependency_building import DependencyBody
    from geosolver.dependencies.why_graph import DependencyGraph


class ConstantLength(Predicate):
    """lconst A B L -
    Represent that the length of segment AB is L

    L should be given as a float.
    """

    NAME = "lconst"

    @staticmethod
    def add(
        args: list[Point | Ratio],
        dep_body: "DependencyBody",
        dep_graph: "DependencyGraph",
        symbols_graph: SymbolsGraph,
        disabled_intrinsic_rules: list[IntrinsicRules],
    ) -> tuple[list[Dependency], list[tuple[Statement, Dependency]]]:
        """Add new algebraic predicates of type eqratio-constant."""
        a, b, length = args

        ab = symbols_graph.get_or_create_segment(a, b, dep=None)
        l_ab = symbols_graph.get_node_val(ab, dep=None)

        lconst = Statement(ConstantLength, args)

        lconst_dep = dep_body.build(dep_graph, lconst)
        symbols_graph.make_equal(length, l_ab, dep=lconst_dep)

        add = [lconst_dep]
        to_cache = [(lconst, lconst_dep)]
        return add, to_cache

    @staticmethod
    def why(
        dep_graph: "DependencyGraph", statement: Statement
    ) -> tuple[Optional[Reason], list[Dependency]]:
        raise NotImplementedError

    @staticmethod
    def check(args: tuple[Point, Point, Length], symbols_graph: SymbolsGraph) -> bool:
        """Check whether a length is equal to some given constant."""
        a, b, length = args
        ab = symbols_graph.get_segment(a, b)

        if not ab or not ab.val:
            return False

        for len1, _ in all_lengths(ab):
            if is_equal(len1, length):
                return True
        return False

    @staticmethod
    def check_numerical(args: tuple[PointNum, PointNum, Length]) -> bool:
        a, b, length = args
        ab = a.distance(b)
        return close_enough(ab, float(length.name))

    @staticmethod
    def enumerate(
        symbols_graph: SymbolsGraph,
    ) -> Generator[tuple[Point, ...], None, None]:
        raise NotImplementedError

    @staticmethod
    def pretty(args: list[str]) -> str:
        a, b, length = args
        return f"{a}{b} = {length}"

    @classmethod
    def hash(
        cls: Self, args: list[Point | Ratio | Angle]
    ) -> tuple[str | Point | Ratio | Angle]:
        return hash_unordered_set_of_points_with_value(cls.NAME, args)


def all_lengths(segment: Segment) -> Generator[Angle, list[Direction], list[Direction]]:
    equivalent_segments = segment.equivs_upto()
    for neighbor_lenght in segment.rep().neighbors(Length):
        if neighbor_lenght._obj in equivalent_segments:
            yield neighbor_lenght, equivalent_segments
