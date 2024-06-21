"""DDAR geometric symbolic solver package"""

from typing import Type

from geosolver.agent.agents_interface import DeductiveAgent
from geosolver.api import GeometricSolver, GeometricSolverBuilder
from geosolver.agent.registry import AgentRegistry

AGENTS_REGISTRY = AgentRegistry()


def register_agent(agent_name: str, agent_class: Type[DeductiveAgent]):
    """Register a new DeductiveAgent implementation to be used by GeoSolver's cli."""
    AGENTS_REGISTRY.register(agent_name, agent_class)


__all__ = ["GeometricSolver", "GeometricSolverBuilder", "register_agent"]
