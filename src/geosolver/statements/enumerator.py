from __future__ import annotations
from typing import TYPE_CHECKING, Generator

from geosolver.combinatorics import (
    arrangement_pairs,
    cross_product,
)
from geosolver.geometry import (
    Angle,
    Line,
    AngleValue,
    Point,
)
from geosolver.predicate_name import PredicateName


if TYPE_CHECKING:
    from geosolver.symbols_graph import SymbolsGraph
    from geosolver.statements.checker import StatementChecker


class StatementsEnumerator:
    def __init__(
        self,
        symbols_graph: "SymbolsGraph",
        statements_checker: "StatementChecker",
    ) -> None:
        self.symbols_graph = symbols_graph
        self.statements_checker = statements_checker

    def all(
        self, predicate_name: str | PredicateName
    ) -> Generator[tuple[Point, ...], None, None]:
        """Enumerate all instances of a certain predicate."""

        try:
            predicate = PredicateName(predicate_name)
        except ValueError:
            raise ValueError(f"Unrecognize predicate: {predicate_name}")

        if predicate in [
            PredicateName.NON_COLLINEAR,
            PredicateName.NON_PARALLEL,
            PredicateName.NON_PERPENDICULAR,
        ]:
            return []

        PREDICATE_TO_METHOD = {}

        if predicate not in PREDICATE_TO_METHOD:
            raise NotImplementedError(
                f"Enumerator not implemented for predicate: {predicate_name}"
            )

        return PREDICATE_TO_METHOD[predicate]()

    def all_eqangles_distinct_linepairss(
        self,
    ) -> Generator[tuple[Line, ...], None, None]:
        """No eqangles betcause para-para, or para-corresponding, or same."""

        for measure in self.symbols_graph.type2nodes[AngleValue]:
            angs = measure.neighbors(Angle)
            line_pairss = []
            for ang in angs:
                d1, d2 = ang.directions
                if d1 is None or d2 is None:
                    continue
                l1s = d1.neighbors(Line)
                l2s = d2.neighbors(Line)
                # Any pair in this is para-para.
                para_para = list(cross_product(l1s, l2s))
                line_pairss.append(para_para)

            for pairs1, pairs2 in arrangement_pairs(line_pairss):
                for pair1, pair2 in cross_product(pairs1, pairs2):
                    (l1, l2), (l3, l4) = pair1, pair2
                    yield l1, l2, l3, l4
