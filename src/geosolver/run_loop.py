from __future__ import annotations
import time
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from geosolver.agent.agents_interface import DeductiveAgent
    from geosolver.proof import ProofState


def run_loop(
    deductive_agent: "DeductiveAgent",
    proof: "ProofState",
) -> dict[str, Any]:
    """Run DeductiveAgent until saturation or goal found."""
    infos: dict[str, Any] = {}
    for goal in proof.goals:
        if not goal.check_numerical():
            infos["error"] = f"{goal.pretty()} fails numerical check"
            return infos
    t0 = time.time()

    step = 0
    running = True
    while running:
        running = deductive_agent.step()
        step += 1

    infos["runtime"] = time.time() - t0
    infos["success"] = proof.check_goals()
    infos["steps"] = step
    for goal in proof.goals:
        if goal.check():
            infos[goal.pretty() + " succeeded"] = True
        else:
            infos[goal.pretty() + " succeeded"] = False
    return infos
