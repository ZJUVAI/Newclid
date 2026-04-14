"""DDAR geometric symbolic solver package"""

from newclid.agent.agents_interface import DeductiveAgent
from newclid.agent.ddarn import DDARN
from newclid.agent.human_agent import HumanAgent

AGENTS_REGISTRY: dict[str, type[DeductiveAgent]] = {
    "ddarn": DDARN,
    "human_agent": HumanAgent,
}

__all__ = [
    "AGENTS_REGISTRY",
    "DDARN",
    "DeductiveAgent",
    "GeometricSolver",
    "GeometricSolverBuilder",
    "HumanAgent",
]


def __getattr__(name: str):
    if name in {"GeometricSolver", "GeometricSolverBuilder"}:
        from newclid.api import GeometricSolver, GeometricSolverBuilder

        return {
            "GeometricSolver": GeometricSolver,
            "GeometricSolverBuilder": GeometricSolverBuilder,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
