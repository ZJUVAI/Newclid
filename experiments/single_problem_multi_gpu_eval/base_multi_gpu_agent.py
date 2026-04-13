from __future__ import annotations

from newclid.agent import base_multi_gpu as _impl

BaseMultiGPUAgent = _impl.BaseMultiGPUAgent
ray = _impl.ray

__all__ = [
    "BaseMultiGPUAgent",
    "ray",
]
