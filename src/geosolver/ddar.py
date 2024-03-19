"""Implements the combination DD+AR."""
from __future__ import annotations
import time
import logging
from typing import TYPE_CHECKING
from geosolver.algebraic.derivations import apply_derivations

from geosolver.deductive import dd_bfs_one_level

from geosolver.problem import Problem, Theorem, Dependency

if TYPE_CHECKING:
    from geosolver.proof import Proof


def solve(
    proof: "Proof",
    theorems: list[Problem],
    controller: Problem,
    max_level: int = 1000,
    timeout: int = 600,
) -> tuple["Proof", list[float], str, list[int], list[Dependency]]:
    """Alternate between DD and AR until goal is found."""
    status = "saturated"
    level_times = []

    dervs, eq4 = proof.alegbraic_manipulator.derive_algebra(level=0, verbose=False)
    derives = [dervs]
    eq4s = [eq4]
    branches = []
    all_added = []

    while len(level_times) < max_level:
        dervs, eq4, next_branches, added = saturate_or_goal(
            proof, theorems, level_times, controller, max_level, timeout=timeout
        )
        all_added += added

        derives += dervs
        eq4s += eq4
        branches += next_branches

        # Now, it is either goal or saturated
        if controller.goal is not None:
            goal_args = proof.symbols_graph.names2points(controller.goal.args)
            if proof.check(controller.goal.name, goal_args):  # found goal
                status = "solved"
                break

        if not derives:  # officially saturated.
            break

        # Now we resort to algebra derivations.
        added = []
        while derives and not added:
            added += apply_derivations(proof, derives.pop(0))

        if added:
            continue

        # Final help from AR.
        while eq4s and not added:
            added += apply_derivations(proof, eq4s.pop(0))

        all_added += added

        if not added:  # Nothing left. saturated.
            break

    return proof, level_times, status, branches, all_added


def saturate_or_goal(
    proof: "Proof",
    theorems: list["Theorem"],
    level_times: list[float],
    problem: "Problem",
    max_level: int = 100,
    timeout: int = 600,
) -> tuple[
    list[list["Dependency"]],
    list[int],
]:
    """Run DD until saturation or goal found."""
    derives = []
    eq4s = []
    branching = []
    all_added = []

    while len(level_times) < max_level:
        level = len(level_times) + 1

        t = time.time()
        added, derv, eq4, n_branching = dd_bfs_one_level(
            proof,
            theorems,
            level,
            problem,
            verbose=False,
            nm_check=True,
            timeout=timeout,
        )
        all_added += added
        branching.append(n_branching)

        derives.append(derv)
        eq4s.append(eq4)
        level_time = time.time() - t

        logging.info(f"Depth {level}/{max_level} time = {level_time}")
        level_times.append(level_time)

        if problem.goal is not None:
            goal_args = list(
                map(
                    lambda x: proof.symbols_graph.get_point(x, lambda: int(x)),
                    problem.goal.args,
                )
            )
            if proof.check(problem.goal.name, goal_args):  # found goal
                break

        if not added:  # saturated
            break

        if level_time > timeout:
            break

    return derives, eq4s, branching, all_added
