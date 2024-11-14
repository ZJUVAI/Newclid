"""DDAR geometric symbolic solver package"""

from newclid.agent.agents_interface import DeductiveAgent
from newclid.agent.breadth_first_search import BFSDDAR
from newclid.agent.flemmard import Flemmard
from newclid.agent.human_agent import HumanAgent
from newclid.api import GeometricSolver as GeometricSolver
from newclid.api import GeometricSolverBuilder as GeometricSolverBuilder

AGENTS_REGISTRY: dict[str, type[DeductiveAgent]] = {
    "bfsddar": BFSDDAR,
    "human_agent": HumanAgent,
    "flemmard": Flemmard,
}
