"""Iterative level by level implementation of DD."""


from __future__ import annotations
from typing import TYPE_CHECKING, Union

import time
from geosolver.geometry import Angle, Point, Ratio
from geosolver.numerical.check import same_clock

from geosolver.problem import Dependency, EmptyDependency, Problem, Theorem, hashed
from geosolver.deductive.match_theorems import match_all_theorems

if TYPE_CHECKING:
    from geosolver.proof_graph import ProofGraph


def dd_bfs_one_level(
    g: "ProofGraph",
    theorems: list[Theorem],
    level: int,
    controller: Problem,
    verbose: bool = False,
    nm_check: bool = False,
    timeout: int = 600,
) -> tuple[
    list[Dependency],
    dict[str, list[tuple[Point, ...]]],
    dict[str, list[tuple[Point, ...]]],
    int,
]:
    """Forward deduce one breadth-first level."""

    # Step 1: match all theorems:
    theorem2mappings = match_all_theorems(g, theorems, controller.goal)

    # Step 2: traceback for each deduce:
    theorem2deps: dict[Theorem, list[Dependency]] = {}
    t0 = time.time()
    for theorem, mappings in theorem2mappings.items():
        if time.time() - t0 > timeout:
            break
        mp_deps = []
        for mp in mappings:
            deps = EmptyDependency(level=level, rule_name=theorem.rule_name)
            fail = False  # finding why deps might fail.

            for p in theorem.premise:
                p_args = [mp[a] for a in p.args]
                # Trivial deps.
                if p.name == "cong":
                    a, b, c, d = p_args
                    if {a, b} == {c, d}:
                        continue
                if p.name == "para":
                    a, b, c, d = p_args
                    if {a, b} == {c, d}:
                        continue

                if theorem.name in [
                    "cong_cong_eqangle6_ncoll_contri*",
                    "eqratio6_eqangle6_ncoll_simtri*",
                ]:
                    if p.name in ["eqangle", "eqangle6"]:  # SAS or RAR
                        b, a, b, c, y, x, y, z = p_args
                        if not same_clock(a.num, b.num, c.num, x.num, y.num, z.num):
                            p_args = b, a, b, c, y, z, y, x

                dep = Dependency(p.name, p_args, rule_name="", level=level)
                try:
                    dep = dep.why_me_or_cache(g, level)
                except Exception:
                    fail = True
                    break

                if dep.why is None:
                    fail = True
                    break
                g.cache_dep(p.name, p_args, dep)
                deps.why.append(dep)

            if fail:
                continue

            mp_deps.append((mp, deps))
        theorem2deps[theorem] = mp_deps

    # Step 3: add conclusions to graph.
    # Note that we do NOT mix step 2 and 3, strictly going for BFS.
    added = []
    for theorem, mp_deps in theorem2deps.items():
        for mp, deps in mp_deps:
            if time.time() - t0 > timeout:
                break
            name, args = theorem.conclusion_name_args(mp)
            hash_conclusion = hashed(name, args)
            if hash_conclusion in g.cache:
                continue

            add = g.add_piece(name, args, deps=deps)
            g.dependency_graph.add_theorem_edges(add, theorem)
            added += add

    branching = len(added)

    # Check if goal is found
    if controller.goal:
        args = []

        for a in controller.goal.args:
            if a in g.symbols_graph._name2node:
                a = g.symbols_graph._name2node[a]
            elif "/" in a:
                a = create_consts_str(g, a)
            elif a.isdigit():
                a = int(a)
            args.append(a)

        if g.check(controller.goal.name, args):
            return added, {}, {}, branching

    # Run AR, but do NOT apply to the proof state (yet).
    for dep in added:
        g.add_algebra(dep, level)
    derives, eq4s = g.alegbraic_manipulator.derive_algebra(level, verbose=False)

    branching += sum([len(x) for x in derives.values()])
    branching += sum([len(x) for x in eq4s.values()])

    return added, derives, eq4s, branching


def create_consts_str(proof_graph: "ProofGraph", s: str) -> Union[Ratio, Angle]:
    if "pi/" in s:
        n, d = s.split("pi/")
        n, d = int(n), int(d)
        p0, _ = proof_graph.alegbraic_manipulator.get_or_create_const_ang(
            proof_graph.symbols_graph, n, d
        )
    else:
        n, d = s.split("/")
        n, d = int(n), int(d)
        p0, _ = proof_graph.alegbraic_manipulator.get_or_create_const_rat(
            proof_graph.symbols_graph, n, d
        )
    return p0
