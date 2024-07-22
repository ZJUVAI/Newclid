from __future__ import annotations
import time
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from geosolver.agent.agents_interface import DeductiveAgent
    from geosolver.proof import Proof


def run_loop(
    deductive_agent: "DeductiveAgent",
    proof: "Proof",
) -> dict[str, Any]:
    """Run DeductiveAgent until saturation or goal found."""
    infos: dict[str, Any] = {}
    success = False
    t0 = time.time()

    step = 0
    running: bool = True
    while running:
        running = deductive_agent.step()
        step += 1
        success = proof.check_goals()
        if success:
            running = False

    infos["runtime"] = time.time() - t0
    infos["success"] = success
    infos["steps"] = step
    for goal in proof.goals:
        if goal.check():
            infos[goal.pretty()] = "succeeded"
        else:
            infos[goal.pretty()] = "failed"
    return infos
