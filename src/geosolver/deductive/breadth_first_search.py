"""Iterative level by level implementation of DD."""


from __future__ import annotations
from typing import TYPE_CHECKING, Union

import time


from geosolver.concepts import ConceptName
from geosolver.dependencies.dependency import Dependency
from geosolver.dependencies.empty_dependency import EmptyDependency
from geosolver.geometry import Angle, Point, Ratio
from geosolver.numerical.check import same_clock
from geosolver.deductive.match_theorems import match_all_theorems

if TYPE_CHECKING:
    from geosolver.problem import Problem, Theorem
    from geosolver.proof import Proof
    from geosolver.algebraic.algebraic_manipulator import AlgebraicManipulator


def dd_bfs_one_level(
    proof: "Proof",
    theorems: list["Theorem"],
    level: int,
    problem: "Problem",
    timeout: int = 600,
) -> tuple[
    list[Dependency],
    dict[str, list[tuple[Point, ...]]],
    dict[str, list[tuple[Point, ...]]],
    int,
]:
    """Forward deduce one breadth-first level."""

    # Step 1: match all theorems:
    theorem2mappings = match_all_theorems(proof, theorems, problem.goal)

    # Step 2: traceback for each deduce:
    theorem2deps: dict["Theorem", list[Dependency]] = {}
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
                if p.name in [ConceptName.PARALLEL.value, ConceptName.CONGRUENT.value]:
                    a, b, c, d = p_args
                    if {a, b} == {c, d}:
                        continue

                if theorem.name in [
                    "cong_cong_eqangle6_ncoll_contri*",
                    "eqratio6_eqangle6_ncoll_simtri*",
                ]:
                    if p.name in [
                        ConceptName.EQANGLE.value,
                        ConceptName.EQANGLE6.value,
                    ]:  # SAS or RAR
                        b, a, b, c, y, x, y, z = p_args
                        if not same_clock(a.num, b.num, c.num, x.num, y.num, z.num):
                            p_args = b, a, b, c, y, z, y, x

                dep = Dependency(p.name, p_args, rule_name="", level=level)
                try:
                    dep = dep.why_me_or_cache(
                        proof.symbols_graph,
                        proof.statements_checker,
                        proof.dependency_cache,
                        level,
                    )
                except Exception:
                    fail = True
                    break

                if dep.why is None:
                    fail = True
                    break
                proof.dependency_cache.add_dependency(p.name, p_args, dep)
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
            conclusion_name, args = theorem.conclusion_name_args(mp)
            cached_conclusion = proof.dependency_cache.get(conclusion_name, args)
            add, to_cache = proof.resolve_dependencies(conclusion_name, args, deps=deps)
            proof.dependency_graph.add_theorem_edges(to_cache, theorem, args)
            if cached_conclusion is not None:
                continue

            proof.cache_deps(to_cache)
            added += add

    branching = len(added)

    # Check if goal is found
    if problem.goal:
        args = []

        for a in problem.goal.args:
            if a in proof.symbols_graph._name2node:
                a = proof.symbols_graph._name2node[a]
            elif "/" in a:
                a = create_consts_str(proof.alegbraic_manipulator, a)
            elif a.isdigit():
                a = int(a)
            args.append(a)

        if proof.check(problem.goal.name, args):
            return added, {}, {}, branching

    # Run AR, but do NOT apply to the proof state (yet).
    for dep in added:
        proof.add_algebra(dep)
    derives, eq4s = proof.alegbraic_manipulator.derive_algebra(level)

    branching += sum([len(x) for x in derives.values()])
    branching += sum([len(x) for x in eq4s.values()])

    return added, derives, eq4s, branching


def create_consts_str(
    alegbraic_manipulator: "AlgebraicManipulator", s: str
) -> Union[Ratio, Angle]:
    if "pi/" in s:
        n, d = s.split("pi/")
        n, d = int(n), int(d)
        p0, _ = alegbraic_manipulator.get_or_create_const_ang(n, d)
    else:
        n, d = s.split("/")
        n, d = int(n), int(d)
        p0, _ = alegbraic_manipulator.get_or_create_const_rat(n, d)
    return p0
