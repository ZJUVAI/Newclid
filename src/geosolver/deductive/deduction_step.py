from __future__ import annotations
import time
from typing import TYPE_CHECKING, Optional

from geosolver.deductive.deductive_agent import StopAction


if TYPE_CHECKING:
    from geosolver.deductive.deductive_agent import DeductiveAgent
    from geosolver.problem import Problem, Theorem
    from geosolver.proof import Proof
    from geosolver.dependencies.dependency import Dependency
    from geosolver.algebraic.algebraic_manipulator import Derivations


def do_deduction_step(
    deductive_agent: "DeductiveAgent",
    proof: "Proof",
    theorems: list["Theorem"],
) -> tuple[list[Dependency], Derivations, Derivations, int]:
    """Forward deduce the first conclusive step."""
    added = []
    action = ()
    while not added and not isinstance(action, StopAction):
        action = deductive_agent.act(proof, theorems)
        added, to_cache, success = proof.step(action)
        deductive_agent.remember_effects(action, success, added, to_cache)

    derives, eq4s = {}, {}
    if proof.alegbraic_manipulator and added:
        # Run AR, but do NOT apply to the proof state (yet)
        for dep in added:
            proof.alegbraic_manipulator.add_algebra(dep)
        derives, eq4s = proof.alegbraic_manipulator.derive_algebra(
            deductive_agent.level
        )

    branching = len(added)
    branching += sum([len(x) for x in derives.values()])
    branching += sum([len(x) for x in eq4s.values()])
    return added, derives, eq4s, branching


def deduce_to_saturation_or_goal(
    deductive_agent: "DeductiveAgent",
    proof: "Proof",
    theorems: list["Theorem"],
    problem: "Problem",
    step_times: Optional[list[float]] = None,
    max_steps: int = 10000,
    timeout: float = 600,
) -> tuple[list[list["Dependency"]], list[int], list, list, bool]:
    """Run DD until saturation or goal found."""
    derives = []
    eq4s = []
    branching = []
    all_added = []
    if step_times is None:
        step_times = []

    overall_t0 = time.time()
    success = False

    while len(step_times) < max_steps:
        step_start = time.time()
        added, derv, eq4, n_branching = do_deduction_step(
            deductive_agent, proof, theorems
        )
        all_added += added
        branching.append(n_branching)
        derives.append(derv)
        eq4s.append(eq4)
        step_times.append(time.time() - step_start)

        if problem.goal is not None:
            goal_args = proof.symbols_graph.names2points(problem.goal.args)
            if proof.check(problem.goal.name, goal_args):
                # Found goal
                success = True
                break

        if not added:
            # Saturated
            break

        if time.time() - overall_t0 > timeout:
            break

    return derives, eq4s, branching, all_added, success
