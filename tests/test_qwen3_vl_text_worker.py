from __future__ import annotations

import pytest
from unittest.mock import patch

vision_worker = pytest.importorskip(
    "newclid.agent.runtime.vision_worker",
    reason="vision worker optional dependencies are not installed",
)


def test_reset_torch_seed_resets_cpu_and_cuda_rng():
    with patch.object(vision_worker.torch, "manual_seed") as manual_seed:
        with patch.object(vision_worker.torch.cuda, "is_available", return_value=True):
            with patch.object(
                vision_worker.torch.cuda, "manual_seed"
            ) as cuda_manual_seed:
                with patch.object(
                    vision_worker.torch.cuda, "manual_seed_all"
                ) as cuda_manual_seed_all:
                    vision_worker._reset_torch_seed(123)

    manual_seed.assert_called_once_with(123)
    cuda_manual_seed.assert_called_once_with(123)
    cuda_manual_seed_all.assert_called_once_with(123)
