"""DDAR geometric symbolic solver package"""

from newclid.agent.agents_interface import DeductiveAgent
from newclid.agent.ddarn import DDARN
from newclid.agent.human_agent import HumanAgent
from newclid.api import GeometricSolver as GeometricSolver
from newclid.api import GeometricSolverBuilder as GeometricSolverBuilder

# Core agents registry (no ML dependencies)
AGENTS_REGISTRY: dict[str, type[DeductiveAgent]] = {
    "ddarn": DDARN,
    "human_agent": HumanAgent,
}

_ml_agents_registered = False


def _try_register_ml_agents():
    """Try to register ML-dependent agents if dependencies are available.

    This function is called lazily when ML agents are first accessed.
    """
    global _ml_agents_registered
    if _ml_agents_registered:
        return
    _ml_agents_registered = True

    try:
        from newclid.agent.lm import LMAgent
        AGENTS_REGISTRY["lm"] = LMAgent
    except ImportError:
        pass

    try:
        from newclid.agent.vlm import VLMAgent
        AGENTS_REGISTRY["vlm"] = VLMAgent
    except ImportError:
        pass

    try:
        from newclid.agent.internvlm import InternVLMAgent
        AGENTS_REGISTRY["internvlm"] = InternVLMAgent
    except ImportError:
        pass


def get_agent(name: str) -> type[DeductiveAgent]:
    """Get an agent class by name, loading ML agents if needed."""
    if name not in AGENTS_REGISTRY:
        _try_register_ml_agents()
    if name not in AGENTS_REGISTRY:
        raise KeyError(f"Unknown agent: {name}. Available: {list(AGENTS_REGISTRY.keys())}")
    return AGENTS_REGISTRY[name]


def has_ml_support() -> bool:
    """Check if ML support (LMAgent) is available."""
    _try_register_ml_agents()
    return "lm" in AGENTS_REGISTRY


def has_vlm_support() -> bool:
    """Check if VLM support is available."""
    _try_register_ml_agents()
    return "vlm" in AGENTS_REGISTRY
