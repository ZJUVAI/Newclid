from __future__ import annotations
import time
from typing import TYPE_CHECKING, Optional

from geosolver.deductive.deductive_agent import (
    ApplyTheoremFeedback,
    DeriveFeedback,
    StopAction,
)


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
    timeout: float = 600.0,
) -> tuple[list[Dependency], Derivations, Derivations, int, bool]:
    """Forward deduce the first conclusive step."""
    added = []
    action = ()

    t0 = time.time()
    while not (added or isinstance(action, (StopAction, DeriveFeedback))):
        action = deductive_agent.act(proof, theorems)
        feedback = proof.step(action)
        if isinstance(feedback, ApplyTheoremFeedback):
            added = feedback.added

        deductive_agent.remember_effects(action, feedback)
        if time.time() - t0 > timeout:
            break

    derives, eq4s = {}, {}
    if isinstance(feedback, DeriveFeedback):
        derives, eq4s = feedback.derives, feedback.eq4s

    return added, derives, eq4s


def deduce_to_saturation_or_goal(
    deductive_agent: "DeductiveAgent",
    proof: "Proof",
    theorems: list["Theorem"],
    problem: "Problem",
    step_times: Optional[list[float]] = None,
    max_steps: int = 10000,
    timeout: float = 600.0,
) -> tuple[list[list["Dependency"]], list[int], list, list, bool]:
    """Run DD until saturation or goal found."""
    derives = []
    eq4s = []
    all_added = []
    if step_times is None:
        step_times = []

    success = False
    overall_t0 = time.time()
    total_elapsed = time.time() - overall_t0

    while len(step_times) < max_steps:
        step_start = time.time()
        added, derv, eq4 = do_deduction_step(
            deductive_agent, proof, theorems, timeout - total_elapsed
        )
        all_added += added
        derives.append(derv)
        eq4s.append(eq4)
        step_times.append(time.time() - step_start)
        total_elapsed = time.time() - overall_t0

        success = proof.statements_checker.check_goal(problem.goal)
        if success or not added or total_elapsed > timeout:
            break

    return derives, eq4s, all_added, success
