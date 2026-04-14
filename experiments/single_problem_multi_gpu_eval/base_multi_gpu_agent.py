from __future__ import annotations

import ray

from newclid.agent.base import BaseAgent

BaseMultiGPUAgent = BaseAgent

__all__ = [
    "BaseMultiGPUAgent",
    "ray",
]
