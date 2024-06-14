from fractions import Fraction
from itertools import combinations
from typing import TYPE_CHECKING
from geosolver.dependencies.dependency import Dependency, Reason
from geosolver.dependencies.dependency_building import DependencyBuilder
from geosolver.geometry import Ratio
from geosolver.predicates import Predicate
from geosolver.reasoning_engines.interface import Derivation, ReasoningEngine
from geosolver.statements.statement import Statement


if TYPE_CHECKING:
    from geosolver.symbols_graph import SymbolsGraph


def menelaus_solver(r1: Fraction, r2: Fraction) -> Fraction:
    return 1 / (r1 * r2)


class MenelausFormula(ReasoningEngine):
    def __init__(self, symbols_graph: "SymbolsGraph") -> None:
        self.ratios: list[Ratio] = []
        self.symbols_graph = symbols_graph

        self._new_colls: list[Dependency] = []

        self._coll_hash_to_dep: dict[tuple[str, ...], Dependency] = {}
        self._rconst_hash_to_dep: dict[tuple[str, ...], Dependency] = {}

        self.coll_candidates: dict[tuple[str, ...], list[tuple[str, ...]]] = {}
        self.triplet_candidates: dict[tuple[str, ...], list[tuple[str, ...]]] = {}

    def ingest(self, dependency: Dependency):
        statement = dependency.statement
        if statement.predicate is Predicate.COLLINEAR:
            self._new_colls.append(dependency)
        elif statement.predicate is Predicate.CONSTANT_RATIO:
            unique_points = set(statement.args[:-1])
            if len(unique_points) != 3:
                return
            hash_key = statement.hash_tuple[1:-1]
            self._rconst_hash_to_dep[hash_key] = dependency

    def resolve(self, **kwargs) -> list[Derivation]:
        level: int = kwargs.get("level")

        while self._new_colls:
            coll = self._new_colls.pop()
            coll_hash = coll.statement.hash_tuple[1:]
            self._coll_hash_to_dep[coll_hash] = coll
            self._make_candidates_from_coll(coll_hash)

        triplet_hits = self.triplet_candidates.copy()
        for representent_triplet, ratios_to_match in self.triplet_candidates.items():
            triplet_hits[representent_triplet] = []
            for r_points, rconst in self._rconst_hash_to_dep.items():
                if r_points not in ratios_to_match:
                    continue
                triplet_hits[representent_triplet].append(r_points)

        new_deps = []
        for representent_triplet, hits in triplet_hits.items():
            if len(hits) != 2:
                continue

            rconst_hit_deps = [self._rconst_hash_to_dep[hit] for hit in hits]
            know_ratios = [dep.statement.args[-1] for dep in rconst_hit_deps]
            new_ratio_frac = menelaus_solver(
                *[_ratio_to_fraction(r) for r in know_ratios]
            )
            new_ratio, _ = self.symbols_graph.get_or_create_const_rat(
                new_ratio_frac.numerator, new_ratio_frac.denominator
            )

            possible_hits = self.triplet_candidates[representent_triplet].copy()
            completed_ratio_points = [
                rconst for rconst in possible_hits if rconst not in hits
            ][0]

            ratio_point = self.symbols_graph.names2points(completed_ratio_points)

            new_statement = Statement(
                Predicate.CONSTANT_RATIO, (*ratio_point, new_ratio)
            )

            coll_deps = [
                self._coll_hash_to_dep[_rconst_hash_to_coll_hash(rconst_hash)]
                for rconst_hash in self.triplet_candidates[representent_triplet]
            ]
            initial_coll_triplet = tuple(sorted(representent_triplet))
            coll_deps.append(self._coll_hash_to_dep[initial_coll_triplet])

            dep_builder = DependencyBuilder(
                Reason("Menelaus"), why=coll_deps + rconst_hit_deps, level=level
            )
            new_deps.append(Derivation(new_statement, dep_builder))
            self.triplet_candidates.pop(representent_triplet)

        return new_deps

    def _make_candidates_from_coll(self, coll_points: tuple[str, ...]):
        self.coll_candidates[coll_points] = []

        for other_coll_points, compatible_colls in self.coll_candidates.items():
            if other_coll_points == coll_points:
                continue

            if set(coll_points).isdisjoint(set(other_coll_points)):
                continue

            self._make_new_triplet_ratio_candidate(
                other_coll_points, coll_points, compatible_colls
            )
            self._make_new_triplet_ratio_candidate(
                coll_points, other_coll_points, self.coll_candidates[coll_points]
            )
            self.coll_candidates[coll_points].append(other_coll_points)
            compatible_colls.append(coll_points)

    def _make_new_triplet_ratio_candidate(
        self,
        main_coll: tuple[str, ...],
        new_coll: tuple[str, ...],
        other_colls: list[tuple[str, ...]],
    ):
        if len(other_colls) < 2:
            return
        for triplet_points in combinations((new_coll, *other_colls), 3):
            self.triplet_candidates[main_coll] = make_rconst_hashs_from_colls(
                main_coll, triplet_points
            )
            self.triplet_candidates[main_coll[::-1]] = make_rconst_hashs_from_colls(
                main_coll, triplet_points, inverse=True
            )


def make_rconst_hashs_from_colls(
    main_coll: tuple[str, ...],
    triplet_points: list[tuple[str, ...]],
    inverse: bool = False,
) -> list[tuple[str, ...]]:
    """Make a triplet of rconst hashs for each coll triplet given a main coll statement.

    For example:
        main = a c e, triplet_points = a b f; d e f; b c d;
        -> rhashs = a b a f; c d b c; e f d e
        main = e c a, triplet_points = a b f; d e f; b c d;
        -> rhashs = a b a f; c d b c; e f d e

    """
    rconst_hashs: list[tuple[str, ...]] = []
    point_is_up: dict[str, bool] = {}

    is_first_point = True
    for point in main_coll:
        corresponding_triplet = [
            triplet for triplet in triplet_points if point in triplet
        ][0]

        non_mid_points = list([p for p in corresponding_triplet if p != point])

        p1, p2 = non_mid_points
        if (
            (is_first_point and not inverse)
            or (p2 in point_is_up and point_is_up[p2])
            or (p1 in point_is_up and not point_is_up[p1])
        ):
            up, down = non_mid_points
        else:
            down, up = non_mid_points

        if up not in point_is_up:
            point_is_up[up] = True
        else:
            point_is_up[up] = None
        if down not in point_is_up:
            point_is_up[down] = False
        else:
            point_is_up[down] = None

        is_first_point = False

        rconst_hashs.append(_rconst_hash(point, up, down))

    return rconst_hashs


def _rconst_hash(both_point: str, up_point: str, down_point: str):
    return (
        *sorted((both_point, up_point)),
        *sorted((both_point, down_point)),
    )


def _rconst_hash_to_coll_hash(rconst_hash: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(set(rconst_hash)))


def _ratio_to_fraction(ratio: Ratio) -> Fraction:
    return Fraction(ratio.name)
