from __future__ import annotations

from newclid.evaluation.multi_gpu import model_pool as _impl

GenerationDispatcher = _impl.GenerationDispatcher
ModelPool = _impl.ModelPool
WorkerHandleWrapper = _impl.WorkerHandleWrapper
ray = _impl.ray

__all__ = [
    "GenerationDispatcher",
    "ModelPool",
    "WorkerHandleWrapper",
    "ray",
]
