from __future__ import annotations

from pathlib import Path
import sys
import types

import ray

try:
    import modelscope as _modelscope
except ModuleNotFoundError:
    _modelscope = types.ModuleType("modelscope")

    def _missing_snapshot_download(*args, **kwargs):
        raise ImportError(
            "modelscope is required to resolve remote model ids. Install modelscope "
            "or pass a local model path."
        )

    _modelscope.snapshot_download = _missing_snapshot_download
    sys.modules["modelscope"] = _modelscope


def resolve_model_path(path: str) -> str:
    candidate = Path(path).expanduser()
    if candidate.exists():
        return str(candidate.resolve())
    if candidate.is_absolute() or path.startswith(".") or path.startswith("~"):
        raise FileNotFoundError(f"Model path does not exist: {candidate}")
    return _modelscope.snapshot_download(path)


def _missing_runtime_error() -> ImportError:
    return ImportError(
        "torch is required to use newclid.evaluation.multi_gpu.lm_actor.ModelWorker. "
        "Install the GPU runtime dependencies or run in an environment with torch available."
    )


try:
    from newclid.agent.runtime.text_worker import ModelWorker as ModelWorker
except ModuleNotFoundError as exc:
    if exc.name != "torch":
        raise

    @ray.remote(num_cpus=1, num_gpus=1, max_concurrency=1)
    class ModelWorker:
        def __init__(
            self,
            model_path: str,
            agent_kind: str = "lm",
            torch_seed: int = 123,
            worker_slot: int = 0,
        ):
            self.model_path = resolve_model_path(model_path)
            self.agent_kind = agent_kind
            self.torch_seed = int(torch_seed)
            self.worker_slot = int(worker_slot)
            self.worker_id = f"gpu:{self.worker_slot}"
            self.device_label = f"cuda:{self.worker_slot}"
            self.num_requests = 0
            self.num_batches = 0
            self.tokenizer = type("_TokenizerStub", (), {"padding_side": "left"})()
            raise _missing_runtime_error()

        def warmup(self) -> dict[str, object]:
            agent_kind = getattr(self, "agent_kind", "lm")
            device = getattr(self, "device_label", "cuda:0")
            return {
                "model_path": self.model_path,
                "agent_kind": agent_kind,
                "device": device,
                "padding_side": self.tokenizer.padding_side,
                "torch_seed": self.torch_seed,
                "runtime": "transformers",
                "worker_id": self.worker_id,
                "worker_slot": self.worker_slot,
            }

        def stats(self) -> dict[str, object]:
            agent_kind = getattr(self, "agent_kind", "lm")
            return {
                "model_path": self.model_path,
                "agent_kind": agent_kind,
                "worker_id": self.worker_id,
                "worker_slot": self.worker_slot,
                "device": self.device_label,
                "num_requests": self.num_requests,
                "num_batches": self.num_batches,
                "avg_batch_size": (self.num_requests / self.num_batches)
                if self.num_batches
                else 0.0,
            }

        def generate_batch(self, requests):
            del requests
            raise _missing_runtime_error()


__all__ = [
    "ModelWorker",
    "resolve_model_path",
]
