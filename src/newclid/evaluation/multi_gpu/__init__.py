"""Compatibility exports for the single-problem multi-GPU runtime."""

from newclid.evaluation.multi_gpu.model_pool import (
    GenerationDispatcher,
    ModelPool,
    WorkerHandleWrapper,
)

__all__ = [
    "GenerationDispatcher",
    "ModelPool",
    "WorkerHandleWrapper",
]
