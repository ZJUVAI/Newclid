from geosolver.algebraic.algebraic_manipulator import AlgebraicManipulator
from geosolver.dependencies.caching import DependencyCache
from geosolver.dependencies.statements_hypergraph import StatementsHyperGraph
from geosolver.statements.adder import IntrinsicRules, StatementAdder
from geosolver.statements.checker import StatementChecker
from geosolver.statements.enumerator import StatementsEnumerator
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
        self.graph = StatementsHyperGraph(
            symbols_graph=symbols_graph,
            statements_checker=self.checker,
            dependency_cache=dependency_cache,
        )
        self.adder = StatementAdder(
            symbols_graph=symbols_graph,
            statements_graph=self.graph,
            alegbraic_manipulator=alegbraic_manipulator,
            statements_checker=self.checker,
            dependency_cache=dependency_cache,
            disabled_intrinsic_rules=disabled_intrinsic_rules,
        )
        self.enumerator = StatementsEnumerator(
            symbols_graph, self.checker, alegbraic_manipulator
        )
