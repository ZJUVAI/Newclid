from __future__ import annotations
import time
from typing import TYPE_CHECKING

from geosolver.agent.interface import StopAction, StopFeedback


if TYPE_CHECKING:
    from geosolver.agent.interface import DeductiveAgent
    from geosolver.problem import Theorem
    from geosolver.proof import Proof
    from geosolver.problem import Problem


def run_loop(
    deductive_agent: "DeductiveAgent",
    proof: "Proof",
    theorems: list["Theorem"],
    problem: "Problem",
    max_steps: int = 10000,
    timeout: float = 600.0,
) -> tuple[bool, dict]:
    """Run DeductiveAgent until saturation or goal found."""
    infos = {}
    success = False
    t0 = time.time()

    deductive_agent.load_problem(problem)

    done = False
    step = 0
    while not done:
        action = deductive_agent.act(proof, theorems)
        feedback = proof.step(action)
        deductive_agent.remember_effects(action, feedback)

        step += 1
        total_elapsed = time.time() - t0

        # Force StopAction on goal success
        success = proof.check_goal(problem.goal)
        if success:
            feedback = proof.step(StopAction())
            deductive_agent.remember_effects(action, feedback)

        if (
            isinstance(feedback, StopFeedback)
            or total_elapsed > timeout
            or step > max_steps
        ):
            done = True

    infos["success"] = success
    infos["runtime"] = total_elapsed
    infos["timeout"] = total_elapsed > timeout
    infos["overstep"] = step > max_steps
    infos["step"] = step
    return success, infos
