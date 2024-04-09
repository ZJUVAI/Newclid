"""Implements the combination DD+AR."""
from __future__ import annotations
import time
from typing import TYPE_CHECKING

from geosolver.algebraic.derivations import apply_derivations
from geosolver.deductive.breadth_first_search import DeductiveAgent, do_deduction


if TYPE_CHECKING:
    from geosolver.dependencies.dependency import Dependency
    from geosolver.proof import Proof
    from geosolver.problem import Problem, Theorem


def ddar_solve(
    deductive_agent: DeductiveAgent,
    proof: "Proof",
    theorems: list["Problem"],
    problem: "Problem",
    max_steps: int = 10000,
    timeout: int = 600,
) -> tuple["Proof", list[float], str, list[int], list["Dependency"]]:
    """Alternate between DD and AR until goal is found."""
    status = "saturated"
    level_times = []

    dervs, eq4 = proof.alegbraic_manipulator.derive_algebra(level=0)
    derives = [dervs]
    eq4s = [eq4]
    branches = []
    all_added = []

    while len(level_times) < max_steps:
        dervs, eq4, next_branches, added = deduce_to_saturation_or_goal(
            deductive_agent,
            proof,
            theorems,
            problem,
            step_times=level_times,
            max_steps=max_steps,
            timeout=timeout,
        )
        all_added += added
        derives += dervs
        eq4s += eq4
        branches += next_branches

        if problem.goal is not None:
            goal_args = proof.symbols_graph.names2points(problem.goal.args)
            if proof.check(problem.goal.name, goal_args):  # found goal
                status = "solved"
                break

        if not derives:
            # Even AR is saturated.
            break

        # Now we resort to simple algebra derivations.
        added = []
        while derives and not added:
            added += apply_derivations(proof, derives.pop(0))

        if added:
            continue

        # Final help from AR with slower eqangles & eqratios.
        while eq4s and not added:
            added += apply_derivations(proof, eq4s.pop(0))

        all_added += added

        if not added:
            # Nothing left... completely saturated.
            break

    return proof, level_times, status, branches, all_added


def deduce_to_saturation_or_goal(
    deductive_agent: DeductiveAgent,
    proof: "Proof",
    theorems: list["Theorem"],
    problem: "Problem",
    step_times: list[float],
    max_steps: int = 10000,
    timeout: float = 600,
) -> tuple[list[list["Dependency"]], list[int], list, list]:
    """Run DD until saturation or goal found."""
    derives = []
    eq4s = []
    branching = []
    all_added = []

    overall_t0 = time.time()

    while len(step_times) < max_steps:
        step_start = time.time()
        added, derv, eq4, n_branching = do_deduction(deductive_agent, proof, theorems)
        all_added += added
        branching.append(n_branching)
        derives.append(derv)
        eq4s.append(eq4)
        step_times.append(time.time() - step_start)

        if problem.goal is not None:
            goal_args = proof.symbols_graph.names2points(problem.goal.args)
            if proof.check(problem.goal.name, goal_args):
                # Found goal
                break

        if not added:
            # Saturated
            break

        if time.time() - overall_t0 > timeout:
            break

    return derives, eq4s, branching, all_added
