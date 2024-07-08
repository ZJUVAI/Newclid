"""Implements theorem matching functions for the Deductive Database (DD)."""

import itertools
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Generator, Optional
import json

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
        self,
        dep_graph: "DependencyGraph",
        runtime_cache_path: Optional[Path],
        rng: "np.random.Generator",
    ) -> None:
        self.dep_graph = dep_graph
        self.rng = rng
        self.runtime_cache_path = runtime_cache_path
        self.cache: dict["Theorem", set[Dependency]] = {}
        if self.runtime_cache_path is not None and not self.runtime_cache_path.exists():
            with open(self.runtime_cache_path, "w") as f:
                json.dump({}, f)

    def cache_theorem(self, theorem: "Theorem"):
        file_cache = None
        write = False
        read = False
        mappings: list[dict[str, str]] = []
        if self.runtime_cache_path is not None:
            with open(self.runtime_cache_path) as f:
                file_cache = json.load(f)
            if "matcher" not in file_cache:
                file_cache["matcher"] = {}
            if str(theorem) in file_cache["matcher"] is not None:
                mappings = file_cache["matcher"][str(theorem)]
                read = True
            else:
                file_cache["matcher"][str(theorem)] = mappings
                write = True
        self.cache[theorem] = set()
        points = [p.name for p in self.dep_graph.symbols_graph.nodes_of_type(Point)]
        variables = theorem.variables()
        logging.info(
            f"{theorem} matching cache : before {len(self.cache[theorem])=} {read=} {write=} {len(mappings)=}"
        )
        for mapping in (
            mappings
            if read
            else (
                {v: p for v, p in zip(variables, point_list)}
                for point_list in itertools.product(points, repeat=len(variables))
            )
        ):
            try:
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
                if write:
                    mappings.append(mapping)
                for conclusion in theorem.conclusions:
                    dep = Dependency.mk(
                        Statement.from_tokens(
                            translate_sentence(mapping, conclusion), self.dep_graph
                        ),
                        reason,
                        tuple(why),
                    )
                    self.cache[theorem].add(dep)
            except IllegalPredicate:
                continue
        if self.runtime_cache_path is not None and write:
            with open(self.runtime_cache_path, "w") as f:
                json.dump(file_cache, f)
        logging.info(
            f"{theorem} matching cache : now {len(self.cache[theorem])=} {read=} {write=} {len(mappings)=}"
        )

    def match_theorem(self, theorem: "Theorem") -> Generator["Dependency", None, None]:
        logging.info("Start caching")
        if theorem not in self.cache:
            self.cache_theorem(theorem)
        logging.info("Finish caching")
        logging.info("Start matching")
        for dep in self.cache[theorem]:
            applicable = True
            assert dep.why is not None
            for premise in dep.why:
                if not premise.check():
                    applicable = False
            if applicable:
                yield dep
        logging.info("Finish matching")
