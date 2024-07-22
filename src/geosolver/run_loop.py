from __future__ import annotations
import time
from typing import TYPE_CHECKING, Any

from geosolver.agent.agents_interface import ResetAction, StopAction, StopFeedback


if TYPE_CHECKING:
    from geosolver.agent.agents_interface import DeductiveAgent
    from geosolver.proof import Proof


def run_loop(
    deductive_agent: "DeductiveAgent",
    proof: "Proof",
    stop_on_goal: bool,
) -> dict[str, Any]:
    """Run DeductiveAgent until saturation or goal found."""
    infos: dict[str, Any] = {}
    success = False
    t0 = time.time()
    total_elapsed = 0

    feedback = proof.init()
    deductive_agent.remember_effects(ResetAction(), feedback)

    step = 0
    while True:
        action = deductive_agent.act()
        feedback = proof.step(action)
        deductive_agent.remember_effects(action, feedback)

        step += 1
        total_elapsed = time.time() - t0

        success = proof.check_goals()
        if success and stop_on_goal:
            # Force StopAction on goal success
            feedback = proof.step(StopAction())
            step += 1
            deductive_agent.remember_effects(action, feedback)

        if isinstance(feedback, StopFeedback):
            break

    infos["success"] = success
    infos["runtime"] = total_elapsed
    infos["steps"] = step
    for goal in proof.goals:
        if goal.check():
            infos[goal.pretty()] = "succeeded"
        else:
            infos[goal.pretty()] = "failed"
    return infos
