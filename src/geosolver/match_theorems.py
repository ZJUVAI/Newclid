"""Implements theorem matching functions for the Deductive Database (DD)."""

import itertools
from typing import TYPE_CHECKING, Generator

from geosolver.dependency.symbols import Point
from geosolver.predicates.predicate import IllegalPredicate
from geosolver.statement import Statement
from geosolver.dependency.dependency import Dependency

if TYPE_CHECKING:
    import numpy as np
    from geosolver.theorem import Theorem
    from geosolver.dependency.dependency_graph import DependencyGraph


def translate_sentence(
    mapping: dict[str, str], sentence: tuple[str, ...]
) -> tuple[str, ...]:
    return (sentence[0],) + tuple(
        mapping[a] if a in mapping else a for a in sentence[1:]
    )


class Matcher:
    def __init__(
        self, dep_graph: "DependencyGraph", rng: "np.random.Generator"
    ) -> None:
        self.dep_graph = dep_graph
        self.rng = rng
        self.cache: dict["Theorem", set[Dependency]] = {}

    def cache_theorem(self, theorem: "Theorem"):
        self.cache[theorem] = set()
        points = [p.name for p in self.dep_graph.symbols_graph.nodes_of_type(Point)]
        variables = theorem.variables()
        for point_list in itertools.product(points, repeat=len(variables)):
            if point_list == ("e", "a", "d", "b", "c", "e"):
                pass
            try:
                mapping: dict[str, str] = {v: p for v, p in zip(variables, point_list)}
                why: list[Statement] = []
                reason = theorem.descrption
                applicable = True
                for premise in theorem.premises:
                    s = Statement.from_tokens(
                        translate_sentence(mapping, premise), self.dep_graph
                    )
                    if not s.check_numerical():
                        applicable = False
                        break
                    why.append(s)
                if not applicable:
                    continue
                for conclusion in theorem.conclusions:
                    self.cache[theorem].add(
                        Dependency.mk(
                            Statement.from_tokens(
                                translate_sentence(mapping, conclusion), self.dep_graph
                            ),
                            reason,
                            tuple(why),
                        )
                    )
            except IllegalPredicate:
                continue

    def match_theorem(self, theorem: "Theorem") -> Generator["Dependency", None, None]:
        if theorem not in self.cache:
            self.cache_theorem(theorem)
        pass
        for dep in self.cache[theorem]:
            applicable = True
            assert dep.why is not None
            for premise in dep.why:
                if not premise.check():
                    applicable = False
            if applicable:
                yield dep
