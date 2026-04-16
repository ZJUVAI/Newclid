from __future__ import annotations

from newclid.agent.runtime import text_worker as _impl

ModelWorker = _impl.ModelWorker
resolve_model_path = _impl.resolve_model_path

__all__ = [
    "ModelWorker",
    "resolve_model_path",
]
