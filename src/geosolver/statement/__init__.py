from typing import TYPE_CHECKING


from geosolver.dependencies.caching import DependencyCache
from geosolver.statement.adder import IntrinsicRules, StatementAdder
from geosolver.statement.checker import StatementChecker
from geosolver.statement.enumerator import StatementsEnumerator


if TYPE_CHECKING:
    from geosolver.algebraic.algebraic_manipulator import AlgebraicManipulator
    from geosolver.symbols_graph import SymbolsGraph


class StatementsHandler:
    def __init__(
        self,
        symbols_graph: "SymbolsGraph",
        alegbraic_manipulator: "AlgebraicManipulator",
        dependency_cache: "DependencyCache",
        disabled_intrinsic_rules: list[IntrinsicRules],
    ) -> None:
        self.checker = StatementChecker(symbols_graph, alegbraic_manipulator)
        self.adder = StatementAdder(
            symbols_graph,
            alegbraic_manipulator,
            self.checker,
            dependency_cache,
            disabled_intrinsic_rules=disabled_intrinsic_rules,
        )
        self.enumerator = StatementsEnumerator(
            symbols_graph, self.checker, alegbraic_manipulator
        )
