"""Implements the combination DD+AR."""
from __future__ import annotations
from typing import TYPE_CHECKING

from geosolver.algebraic.derivations import apply_derivations
from geosolver.deductive.deduction_step import deduce_to_saturation_or_goal
from geosolver.deductive.deductive_agent import DeductiveAgent


if TYPE_CHECKING:
    from geosolver.dependencies.dependency import Dependency
    from geosolver.proof import Proof
    from geosolver.problem import Problem


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
    step_times = []

    dervs, eq4 = proof.alegbraic_manipulator.derive_algebra(level=0)
    derives = [dervs]
    eq4s = [eq4]
    branches = []
    all_added = []

    while len(step_times) < max_steps:
        dervs, eq4, next_branches, added, success = deduce_to_saturation_or_goal(
            deductive_agent,
            proof,
            theorems,
            problem,
            step_times=step_times,
            max_steps=max_steps,
            timeout=timeout,
        )
        all_added += added
        derives += dervs
        eq4s += eq4
        branches += next_branches

        if success:
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

    return proof, step_times, status, branches, all_added
