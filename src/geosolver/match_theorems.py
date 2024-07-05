"""Implements theorem matching functions for the Deductive Database (DD)."""

from typing import TYPE_CHECKING, Generator
import itertools

from geosolver.dependency.symbols import Point
from geosolver.statement import Statement
from geosolver.dependency.dependency import Dependency

if TYPE_CHECKING:
    from geosolver.proof import Proof
    from geosolver.theorem import Theorem


def translate_sentence(
    mapping: dict[str, str], sentence: tuple[str, ...]
) -> tuple[str, ...]:
    return (sentence[0],) + tuple(
        mapping[a] if a in mapping else a for a in sentence[1:]
    )


def match_theorem(
    proof: "Proof", theorem: "Theorem"
) -> Generator["Dependency", None, None]:
    """Match any generic rule that is not one of the above match_*() rules."""
    points = [p.name for p in proof.symbols_graph.nodes_of_type(Point)]
    failed_checks: set[Statement] = set()
    variables = theorem.variables()
    brute = 720
    for point_list in itertools.permutations(points, len(variables)):
        mapping: dict[str, str] = {v: p for v, p in zip(variables, point_list)}
        why: list[Statement] = []
        reason = theorem.name
        applicable = True
        for p in theorem.premises:
            s = Statement.from_tokens(translate_sentence(mapping, p), proof.dep_graph)
            if not s.check():
                failed_checks.add(s)
                applicable = False
            why.append(s)
        if applicable:
            for conclusion in theorem.conclusions:
                yield Dependency(
                    Statement.from_tokens(
                        translate_sentence(mapping, conclusion), proof.dep_graph
                    ),
                    reason,
                    tuple(why),
                )
        brute -= 1
        if brute < 0:
            break
