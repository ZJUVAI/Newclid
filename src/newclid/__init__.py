"""DDAR geometric symbolic solver package"""

from newclid.agent.agents_interface import DeductiveAgent
from newclid.agent.ddarn import DDARN
from newclid.agent.human_agent import HumanAgent
from newclid.api import GeometricSolver as GeometricSolver
from newclid.api import GeometricSolverBuilder as GeometricSolverBuilder

AGENTS_REGISTRY: dict[str, type[DeductiveAgent]] = {
    "ddarn": DDARN,
    "human_agent": HumanAgent,
}
