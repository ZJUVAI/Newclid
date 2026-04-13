"""Compatibility exports for the single-problem multi-GPU evaluation workflow."""

from newclid.agent.runtime.model_pool import GenerationDispatcher, ModelPool

__all__ = [
    "GenerationDispatcher",
    "ModelPool",
]
