from __future__ import annotations

import ray


def _missing_runtime_error() -> ImportError:
    return ImportError(
        "torch is required to use newclid.evaluation.multi_gpu.visual_actor.VisionModelWorker. "
        "Install the GPU runtime dependencies or run in an environment with torch available."
    )


try:
    from newclid.agent.runtime.vision_worker import (
        VisionModelWorker as VisionModelWorker,
    )
except ModuleNotFoundError as exc:
    if exc.name != "torch":
        raise

    @ray.remote(num_cpus=1, num_gpus=1, max_concurrency=1)
    class VisionModelWorker:
        def __init__(
            self,
            model_path: str,
            agent_kind: str,
            torch_seed: int = 123,
            worker_slot: int = 0,
        ):
            self.model_path = model_path
            self.agent_kind = agent_kind
            self.torch_seed = int(torch_seed)
            self.worker_slot = int(worker_slot)
            self.worker_id = f"gpu:{self.worker_slot}"
            self.device_label = f"cuda:{self.worker_slot}"
            self.num_requests = 0
            self.num_batches = 0
            self.processor = type(
                "_ProcessorStub",
                (),
                {"tokenizer": type("_TokenizerStub", (), {"padding_side": "left"})()},
            )()
            raise _missing_runtime_error()

        def warmup(self) -> dict[str, object]:
            return {
                "model_path": self.model_path,
                "agent_kind": self.agent_kind,
                "device": self.device_label,
                "padding_side": self.processor.tokenizer.padding_side,
                "torch_seed": self.torch_seed,
                "runtime": "transformers",
                "worker_id": self.worker_id,
                "worker_slot": self.worker_slot,
            }

        def stats(self) -> dict[str, object]:
            return {
                "model_path": self.model_path,
                "agent_kind": self.agent_kind,
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


__all__ = ["VisionModelWorker"]
