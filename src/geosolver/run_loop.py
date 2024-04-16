from __future__ import annotations
import time
from typing import TYPE_CHECKING

from geosolver.agent.interface import StopAction
from geosolver.problem import Construction


if TYPE_CHECKING:
    from geosolver.agent.interface import DeductiveAgent
    from geosolver.problem import Theorem
    from geosolver.proof import Proof


def run_loop(
    deductive_agent: "DeductiveAgent",
    proof: "Proof",
    theorems: list["Theorem"],
    goal: "Construction",
    max_steps: int = 10000,
    timeout: float = 600.0,
) -> tuple[bool, dict]:
    """Run DeductiveAgent until saturation or goal found."""
    infos = {}
    success = False
    t0 = time.time()

    done = False
    step = 0
    while not done:
        action = deductive_agent.act(proof, theorems)
        feedback = proof.step(action)
        deductive_agent.remember_effects(action, feedback)

        step += 1
        total_elapsed = time.time() - t0

        success = proof.statements_checker.check_goal(goal)
        if (
            success
            or total_elapsed > timeout
            or step > max_steps
            or isinstance(action, StopAction)
        ):
            done = True

    infos["success"] = success
    infos["runtime"] = total_elapsed
    infos["timeout"] = total_elapsed > timeout
    infos["overstep"] = step > max_steps
    infos["step"] = step
    return success, infos
