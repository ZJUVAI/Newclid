from __future__ import annotations

from collections import deque
import logging
from typing import Any

import ray


logger = logging.getLogger(__name__)


class GenerationDispatcher:
    """Dispatch single generation requests onto GPU workers while preserving backpressure."""

    def __init__(self, workers: list[Any], requests: list[dict[str, Any]] | None = None):
        self.idle_workers = deque(workers)
        self.pending_requests = deque(requests or [])
        self.running: dict[Any, Any] = {}
        self.accept_new_work = True
        logger.debug(
            "GenerationDispatcher init: workers=%d requests=%d pending_requests=%d",
            len(workers),
            len(requests or []),
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

    def idle_worker_count(self) -> int:
        return len(self.idle_workers)

    def active_refs(self) -> list[Any]:
        return list(self.running.keys())

    def owns_ref(self, ref: Any) -> bool:
        return ref in self.running

    def enqueue_request(self, request: dict[str, Any]) -> None:
        if not self.accept_new_work:
            raise RuntimeError("GenerationDispatcher is not accepting new work")
        self.pending_requests.append(request)
        self._fill()

    def take_done(self, ref: Any) -> dict[str, Any]:
        worker = self.running.pop(ref)
        result = ray.get(ref)
        logger.debug(
            "GenerationDispatcher complete: request_id=%s running_remaining=%d",
            result.get("request_id"),
            len(self.running),
        )
        self.idle_workers.append(worker)
        self._fill()
        return result

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
        requests: list[dict[str, Any]] | None = None,
    ) -> GenerationDispatcher:
        logger.debug(
            "ModelPool create_dispatcher: requests=%d workers=%d",
            len(requests or []),
            len(self.workers),
        )
        return GenerationDispatcher(self.workers, requests)
