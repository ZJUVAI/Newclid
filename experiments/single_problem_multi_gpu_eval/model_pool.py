from __future__ import annotations

from collections import deque
import logging
from typing import Any

import ray


logger = logging.getLogger(__name__)


class GenerationDispatcher:
    """Dispatch single generation requests onto GPU workers while preserving backpressure."""

    def __init__(self, workers: list[Any], requests: list[dict[str, Any]]):
        self.idle_workers = deque(workers)
        self.pending_requests = deque(requests)
        self.running: dict[Any, Any] = {}
        self.accept_new_work = True
        logger.debug(
            "GenerationDispatcher init: workers=%d requests=%d pending_requests=%d",
            len(workers),
            len(requests),
            len(self.pending_requests),
        )
        self._fill()

    def _fill(self) -> None:
        # Keep issuing work until either all workers are busy or all queued
        # requests have been submitted.
        while self.accept_new_work and self.pending_requests and self.idle_workers:
            worker = self.idle_workers.popleft()
            request = self.pending_requests.popleft()
            logger.debug(
                "GenerationDispatcher submit: remaining_requests=%d running=%d request_id=%s",
                len(self.pending_requests),
                len(self.running) + 1,
                request.get("request_id", "<missing>"),
            )
            self.running[worker.generate_one.remote(request)] = worker

    def has_pending(self) -> bool:
        return bool(self.pending_requests or self.running)

    def active_refs(self) -> list[Any]:
        return list(self.running.keys())

    def owns_ref(self, ref: Any) -> bool:
        return ref in self.running

    def take_done(self, ref: Any) -> list[dict[str, Any]]:
        worker = self.running.pop(ref)
        results = ray.get(ref)
        logger.debug(
            "GenerationDispatcher complete: results=%d running_remaining=%d",
            len(results),
            len(self.running),
        )
        self.idle_workers.append(worker)
        self._fill()
        return results

    def stop_submitting(self) -> None:
        self.accept_new_work = False
        self.pending_requests.clear()
        logger.debug("GenerationDispatcher stop_submitting")

    def cancel_running(self) -> None:
        self.stop_submitting()
        logger.debug("GenerationDispatcher cancel_running: refs=%d", len(self.running))
        for ref in list(self.running.keys()):
            try:
                ray.cancel(ref, force=False)
            except Exception:
                pass


class ModelPool:
    def __init__(self, workers: list[Any]):
        if not workers:
            raise ValueError("ModelPool requires at least one worker")
        self.workers = workers

    def warmup(self) -> list[dict[str, Any]]:
        logger.info("ModelPool warmup start: workers=%d", len(self.workers))
        infos = ray.get([worker.warmup.remote() for worker in self.workers])
        logger.info("ModelPool warmup done: infos=%s", infos)
        return infos

    def get_worker_stats(self) -> list[dict[str, Any]]:
        return ray.get([worker.stats.remote() for worker in self.workers])

    def create_dispatcher(
        self,
        requests: list[dict[str, Any]],
        batch_size: int | None = None,
    ) -> GenerationDispatcher:
        # `batch_size` is kept temporarily for call-site compatibility. This
        # runner now dispatches exactly one request per worker call.
        del batch_size
        logger.debug(
            "ModelPool create_dispatcher: requests=%d workers=%d",
            len(requests),
            len(self.workers),
        )
        return GenerationDispatcher(self.workers, requests)
