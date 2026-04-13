from __future__ import annotations

import ray

from newclid.agent import base_multi_gpu as _impl

BaseMultiGPUAgent = _impl.BaseMultiGPUAgent

__all__ = [
    "BaseMultiGPUAgent",
    "ray",
]
