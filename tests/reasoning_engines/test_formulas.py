from fractions import Fraction
import pytest
from typing_extensions import Self

from geosolver.api import GeometricSolverBuilder
from geosolver.dependencies.dependency import Dependency, Reason
from geosolver.dependencies.dependency_building import DependencyBody
from geosolver.geometry import Point
from geosolver.predicates import Predicate
from geosolver.reasoning_engines.formulas import (
    MenelausFormula,
    make_rconst_hashs_from_colls,
)
from geosolver.reasoning_engines.interface import Derivation, ReasoningEngine
from geosolver.statements.statement import Statement
from geosolver.symbols_graph import SymbolsGraph


class TestMenelaus:
    @pytest.fixture(autouse=True)
    def setup(self, reasoning_fixture: "ReasoningEngineFixture"):
        self.solver_builder = GeometricSolverBuilder()
        self.reasoning_fixture = reasoning_fixture
        points_names = ["a", "b", "c", "d", "e", "f"]
        ratios = ["1/3", "1/2"]

        self.symbols_graph = (
            SymbolsGraphBuilder()
            .with_point_named(points_names)
            .with_ratios(ratios)
            .build()
        )
        self.points = self.symbols_graph.names2points(points_names)
        self.ratios = self.symbols_graph.names2nodes(ratios)

    def test_implication_ddar_fails(self):
        solver = self.solver_builder.load_problem_from_txt(
            "a b c = triangle a b c; "
            "f = on_line f a b, rconst2 f a b 1/2; "
            "d = on_line d b c, rconst2 d b c 1/2; "
            "e = on_line e d f, on_line e c a "
            "? rconst c e a e 4/1"
        ).build()
        success = solver.run()
        assert not success

    def test_implication_menelaus_succeed(self):
        solver = (
            self.solver_builder.load_problem_from_txt(
                "a b c = triangle a b c; "
                "f = on_line f a b, rconst2 f a b 1/2; "
                "d = on_line d b c, rconst2 d b c 1/2; "
                "e = on_line e d f, on_line e c a "
                "? rconst c e a e 4/1"
            )
            .with_additional_reasoning_engine(MenelausFormula, "Menelaus")
            .build()
        )
        success = solver.run()
        assert success

    def test_implication(self):
        """Should be able to use Menelaus theorem to get the completing ratio.

        ncoll e d f, coll a b f, coll c d b, coll e d f, coll c e a
        => AF/FB * BD/DC * CE/DA = 1

        """

        points_names = ["a", "b", "c", "d", "e", "f"]
        ratios = ["1/3", "1/2"]

        symbols_graph = (
            SymbolsGraphBuilder()
            .with_point_named(points_names)
            .with_ratios(ratios)
            .build()
        )
        a, b, c, d, e, f = symbols_graph.names2points(points_names)
        r1_3, r1_2 = symbols_graph.names2nodes(ratios)

        self.reasoning_fixture.given_engine(MenelausFormula(symbols_graph))

        given_dependencies = [
            Dependency(Statement(Predicate.COLLINEAR, (a, b, f)), why=[]),
            Dependency(Statement(Predicate.COLLINEAR, (c, b, d)), why=[]),
            Dependency(Statement(Predicate.COLLINEAR, (e, d, f)), why=[]),
            Dependency(Statement(Predicate.COLLINEAR, (c, e, a)), why=[]),
            Dependency(Statement(Predicate.CONSTANT_RATIO, (a, f, f, b, r1_3)), why=[]),
            Dependency(Statement(Predicate.CONSTANT_RATIO, (b, d, d, c, r1_2)), why=[]),
        ]
        for dep in given_dependencies:
            self.reasoning_fixture.given_added_dependencies(dep)

        self.reasoning_fixture.when_resolving_dependencies()

        expected_r_inv_fraction = Fraction(r1_2.name) * Fraction(r1_3.name)
        expected_r, _ = symbols_graph.get_or_create_const_rat(
            expected_r_inv_fraction.denominator, expected_r_inv_fraction.numerator
        )

        self.reasoning_fixture.then_new_derivations_should_be(
            [
                Derivation(
                    Statement(Predicate.CONSTANT_RATIO, (c, e, a, e, expected_r)),
                    DependencyBody(Reason("Menelaus"), why=given_dependencies),
                ),
            ]
        )


@pytest.mark.parametrize(
    "main_coll,triplet_points,inverse,output",
    [
        (
            ("a", "c", "e"),
            [("a", "b", "f"), ("d", "e", "f"), ("b", "c", "d")],
            False,
            [("a", "b", "a", "f"), ("c", "d", "b", "c"), ("e", "f", "d", "e")],
        ),
        (
            ("a", "c", "e"),
            [("a", "b", "f"), ("d", "e", "f"), ("b", "c", "d")],
            True,
            [("a", "f", "a", "b"), ("b", "c", "c", "d"), ("d", "e", "e", "f")],
        ),
        (
            ("a", "b", "i"),
            [("a", "b", "e"), ("a", "c", "k"), ("b", "c", "j")],
            False,
            [],
        ),
        (
            ("a", "c", "e"),
            [("a", "b", "f"), ("d", "c", "e"), ("b", "c", "d")],
            False,
            [],
        ),
    ],
)
def test_make_rconst_hashs_from_colls(
    main_coll: tuple[str, ...],
    triplet_points: list[tuple[str, ...]],
    inverse: bool,
    output: list[tuple[str, ...]],
):
    assert make_rconst_hashs_from_colls(main_coll, triplet_points, inverse) == output


@pytest.fixture
def reasoning_fixture() -> "ReasoningEngineFixture":
    return ReasoningEngineFixture()


class ReasoningEngineFixture:
    def given_engine(self, engine: ReasoningEngine):
        self._engine = engine

    def given_added_dependencies(self, dependency: Dependency):
        self._engine.ingest(dependency)

    def when_resolving_dependencies(self):
        self._derivations = self._engine.resolve()

    def then_new_derivations_should_be(self, expected_derivation: list[Derivation]):
        assert self._derivations == expected_derivation


class SymbolsGraphBuilder:
    def __init__(self) -> None:
        self.points: list[Point] = []
        self.ratios_tuples: list[tuple[int, int]] = []

    def with_point_named(self, points_names: list[str]) -> Self:
        self.points += [Point(name) for name in points_names]
        return self

    def with_ratios(self, ratios: list[str]) -> Self:
        for ratio in ratios:
            fraction = Fraction(ratio)
            self.ratios_tuples.append((fraction.numerator, fraction.denominator))
        return self

    def build(self) -> SymbolsGraph:
        symbols_graph = SymbolsGraph()
        for point in self.points:
            symbols_graph.add_node(point)
        for ratio in self.ratios_tuples:
            symbols_graph.get_or_create_const_rat(*ratio)
        return symbols_graph
