"""DDAR geometric symbolic solver package"""

from geosolver.agent.agents_interface import DeductiveAgent
from geosolver.agent.breadth_first_search import BFSDDAR
from geosolver.api import GeometricSolver as GeometricSolver
from geosolver.api import GeometricSolverBuilder as GeometricSolverBuilder

AGENTS_REGISTRY: dict[str, type[DeductiveAgent]] = {"bfsddar": BFSDDAR}
