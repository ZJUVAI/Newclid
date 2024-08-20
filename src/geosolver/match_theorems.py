"""Implements theorem matching functions for the Deductive Database (DD)."""

import itertools
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Generator, Optional
import json

from geosolver.definition.clause import translate_sentence
from geosolver.dependency.symbols import Point
from geosolver.statement import Statement
from geosolver.dependency.dependency import Dependency

if TYPE_CHECKING:
    import numpy as np
    from geosolver.rule import Rule
    from geosolver.dependency.dependency_graph import DependencyGraph


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
        self.cache: dict["Rule", tuple[Dependency, ...]] = {}
        if self.runtime_cache_path is not None and not self.runtime_cache_path.exists():
            os.makedirs(os.path.dirname(self.runtime_cache_path), exist_ok=True)
            self.runtime_cache_path.touch()
            with open(self.runtime_cache_path, "w") as f:
                json.dump({}, f)

    def cache_theorem(self, theorem: "Rule"):
        file_cache = None
        write = False
        read = False
        mappings: list[dict[str, str]] = []
        if self.runtime_cache_path is not None:
            with open(self.runtime_cache_path) as f:
                file_cache = json.load(f)
            if "matcher" not in file_cache:
                file_cache["matcher"] = {}
            if str(theorem) in file_cache["matcher"]:
                mappings = file_cache["matcher"][str(theorem)]
                read = True
            else:
                file_cache["matcher"][str(theorem)] = mappings
                write = True
        res: set[Dependency] = set()
        self.cache[theorem] = ()
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
            why: list[Statement] = []
            reason = theorem.descrption
            applicable = True
            for premise in theorem.premises:
                s = Statement.from_tokens(
                    translate_sentence(mapping, premise), self.dep_graph
                )
                if s is None:
                    applicable = False
                    break
                if not s.check_numerical():
                    applicable = False
                    break
                why.append(s)
            if not applicable:
                continue
            if write:
                mappings.append(mapping)
            for conclusion in theorem.conclusions:
                conclusion_statement = Statement.from_tokens(
                    translate_sentence(mapping, conclusion), self.dep_graph
                )
                # assert conclusion_statement.check_numerical()
                if conclusion_statement is None:
                    continue
                dep = Dependency.mk(conclusion_statement, reason, tuple(why))
                res.add(dep)
        self.cache[theorem] = tuple(
            sorted(res, key=lambda x: repr(x))
        )  # to maintain determinism
        if self.runtime_cache_path is not None and write:
            with open(self.runtime_cache_path, "w") as f:
                json.dump(file_cache, f)
        logging.info(
            f"{theorem} matching cache : now {len(self.cache[theorem])=} {read=} {write=} {len(mappings)=}"
        )

    def match_theorem(self, theorem: "Rule") -> Generator["Dependency", None, None]:
        logging.info("Start caching")
        if theorem not in self.cache:
            self.cache_theorem(theorem)
        logging.info("Finish caching")
        logging.info("Start matching")
        for dep in self.cache[theorem]:
            if dep.statement in dep.statement.dep_graph.hyper_graph:
                continue
            applicable = True
            for premise in dep.why:
                if not premise.check():
                    applicable = False
            if applicable:
                yield dep
        logging.info("Finish matching")
