from __future__ import annotations

from collections import deque
import logging
import time
from typing import Any

import ray


logger = logging.getLogger(__name__)


class GenerationDispatcher:
    """Dispatch batched generation requests onto GPU workers while preserving backpressure."""

    def __init__(
        self,
        workers: list[Any],
        requests: list[dict[str, Any]] | None = None,
        *,
        gpu_batch_size: int = 1,
        gpu_batch_timeout_ms: int = 0,
    ):
        if gpu_batch_size <= 0:
            raise ValueError(f"gpu_batch_size must be positive, got {gpu_batch_size}.")
        if gpu_batch_timeout_ms < 0:
            raise ValueError(f"gpu_batch_timeout_ms must be non-negative, got {gpu_batch_timeout_ms}.")
        self.idle_workers = deque(workers)
        self.pending_requests = deque(requests or [])
        self.pending_enqueued_at: dict[str, float] = {
            request["request_id"]: time.perf_counter()
            for request in requests or []
            if "request_id" in request
        }
        self.request_dispatched_at: dict[str, float] = {}
        self.running: dict[Any, dict[str, Any]] = {}
        self.completed_submission_events: deque[dict[str, Any]] = deque()
        self.accept_new_work = True
        self.allow_partial_batches = gpu_batch_timeout_ms == 0
        self.gpu_batch_size = gpu_batch_size
        self.gpu_batch_timeout_s = gpu_batch_timeout_ms / 1000.0
        logger.debug(
            "GenerationDispatcher init: workers=%d requests=%d pending_requests=%d batch_size=%d timeout_ms=%d",
            len(workers),
            len(requests or []),
            len(self.pending_requests),
            self.gpu_batch_size,
            gpu_batch_timeout_ms,
        )
        self._fill()

    def _peek_oldest_wait_s(self) -> float | None:
        if not self.pending_requests:
            return None
        request_id = self.pending_requests[0].get("request_id")
        if request_id is None:
            return 0.0
        enqueued_at = self.pending_enqueued_at.get(request_id)
        if enqueued_at is None:
            return 0.0
        return time.perf_counter() - enqueued_at

    def _can_submit_partial_batch(self) -> bool:
        if not self.pending_requests:
            return False
        if self.allow_partial_batches:
            return True
        if len(self.pending_requests) >= self.gpu_batch_size:
            return True
        oldest_wait_s = self._peek_oldest_wait_s()
        return oldest_wait_s is not None and oldest_wait_s >= self.gpu_batch_timeout_s

    def _build_batch(self) -> list[dict[str, Any]]:
        if not self.pending_requests:
            return []
        if len(self.pending_requests) < self.gpu_batch_size and not self._can_submit_partial_batch():
            return []
        batch_size = min(len(self.pending_requests), self.gpu_batch_size)
        batch: list[dict[str, Any]] = []
        for _ in range(batch_size):
            request = self.pending_requests.popleft()
            request_id = request.get("request_id")
            if request_id is not None:
                self.pending_enqueued_at.pop(request_id, None)
            batch.append(request)
        return batch

    def _fill(self) -> None:
        # Keep issuing work until either all workers are busy or all queued
        # requests have been submitted.
        while self.accept_new_work and self.pending_requests and self.idle_workers:
            batch = self._build_batch()
            if not batch:
                return
            worker = self.idle_workers.popleft()
            submit_time = time.perf_counter()
            request_ids = [request.get("request_id", "<missing>") for request in batch]
            request_queue_time_s_sum = 0.0
            for request_id in request_ids:
                enqueued_at = self.pending_enqueued_at.pop(request_id, None)
                if enqueued_at is not None:
                    request_queue_time_s_sum += submit_time - enqueued_at
                    self.request_dispatched_at[request_id] = submit_time
            logger.debug(
                "GenerationDispatcher submit: remaining_requests=%d running=%d batch_size=%d request_ids=%s",
                len(self.pending_requests),
                len(self.running) + 1,
                len(batch),
                request_ids,
            )
            self.running[worker.generate_batch.remote(batch)] = {
                "worker": worker,
                "request_ids": request_ids,
                "batch_size": len(batch),
                "submitted_at": submit_time,
                "request_queue_time_s_sum": request_queue_time_s_sum,
            }
            self.completed_submission_events.append(
                {
                    "request_ids": request_ids,
                    "batch_size": len(batch),
                    "submitted_at": submit_time,
                    "request_queue_time_s_sum": request_queue_time_s_sum,
                }
            )

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
        request_id = request.get("request_id")
        if request_id is not None:
            self.pending_enqueued_at[request_id] = time.perf_counter()
        self._fill()

    def take_done(self, ref: Any) -> list[dict[str, Any]]:
        running_meta = self.running.pop(ref)
        ray_get_start = time.perf_counter()
        result = ray.get(ref)
        ray_get_elapsed_s = time.perf_counter() - ray_get_start
        done_time = time.perf_counter()
        logger.debug(
            "GenerationDispatcher complete: request_ids=%s batch_size=%d running_remaining=%d",
            running_meta["request_ids"],
            running_meta["batch_size"],
            len(self.running),
        )
        for request_id in running_meta["request_ids"]:
            self.request_dispatched_at.pop(request_id, None)
        self.idle_workers.append(running_meta["worker"])
        self._fill()
        worker_batch_profile = {}
        batch_results: list[dict[str, Any]]
        if isinstance(result, dict):
            batch_results = list(result.get("results", []))
            worker_batch_profile = dict(result.get("worker_batch_profile", {}))
        else:
            batch_results = list(result)
        return {
            "results": batch_results,
            "request_ids": running_meta["request_ids"],
            "batch_size": running_meta["batch_size"],
            "dispatcher_profile": {
                "request_queue_time_s_sum": running_meta["request_queue_time_s_sum"],
                "batch_round_trip_time_s": done_time - running_meta["submitted_at"],
                "batch_result_ray_get_time_s": ray_get_elapsed_s,
                "batch_oldest_request_wait_time_s": max(
                    (
                        done_time - running_meta["submitted_at"] + running_meta["request_queue_time_s_sum"]
                    )
                    / max(running_meta["batch_size"], 1),
                    0.0,
                ),
            },
            "worker_batch_profile": worker_batch_profile,
        }

    def tick(self) -> None:
        self._fill()

    def flush(self) -> None:
        self.allow_partial_batches = True
        self._fill()

    def take_submission_events(self) -> list[dict[str, Any]]:
        events = list(self.completed_submission_events)
        self.completed_submission_events.clear()
        return events

    def stop_submitting(self) -> None:
        self.accept_new_work = False
        self.pending_requests.clear()
        self.pending_enqueued_at.clear()
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
        *,
        gpu_batch_size: int = 1,
        gpu_batch_timeout_ms: int = 0,
    ) -> GenerationDispatcher:
        logger.debug(
            "ModelPool create_dispatcher: requests=%d workers=%d batch_size=%d timeout_ms=%d",
            len(requests or []),
            len(self.workers),
            gpu_batch_size,
            gpu_batch_timeout_ms,
        )
        return GenerationDispatcher(
            self.workers,
            requests,
            gpu_batch_size=gpu_batch_size,
            gpu_batch_timeout_ms=gpu_batch_timeout_ms,
        )
