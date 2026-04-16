from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import logging
import time
from typing import Any

import ray


logger = logging.getLogger(__name__)


@dataclass
class WorkerHandleWrapper:
    handle: Any
    worker_trace_id: str
    worker_device: str | None = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self.handle, name)


def _request_group_key(request: dict[str, Any]) -> tuple[Any, ...]:
    return (
        request.get("with_predicate", False),
        request.get("decoding_size"),
        request.get("response_prefix", "<aux> x00"),
    )


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
            raise ValueError(
                f"gpu_batch_timeout_ms must be non-negative, got {gpu_batch_timeout_ms}."
            )
        self.idle_workers = deque(workers)
        self.pending_groups: dict[tuple[Any, ...], deque[dict[str, Any]]] = {}
        self.pending_enqueued_at: dict[str, float] = {}
        self.request_dispatched_at: dict[str, float] = {}
        self.running: dict[Any, dict[str, Any]] = {}
        self.completed_submission_events: deque[dict[str, Any]] = deque()
        self.accept_new_work = True
        self.allow_partial_batches = gpu_batch_timeout_ms == 0
        self.gpu_batch_size = gpu_batch_size
        self.gpu_batch_timeout_s = gpu_batch_timeout_ms / 1000.0
        for request in requests or []:
            self._enqueue_pending_request(request)
        logger.debug(
            "GenerationDispatcher init: workers=%d requests=%d pending_requests=%d batch_size=%d timeout_ms=%d",
            len(workers),
            len(requests or []),
            self._pending_group_count(),
            self.gpu_batch_size,
            gpu_batch_timeout_ms,
        )
        self._fill()

    def _enqueue_pending_request(self, request: dict[str, Any]) -> None:
        group_key = _request_group_key(request)
        self.pending_groups.setdefault(group_key, deque()).append(request)
        request_id = request.get("request_id")
        if request_id is not None:
            self.pending_enqueued_at[request_id] = time.perf_counter()

    def _pending_group_count(self) -> int:
        return sum(len(group) for group in self.pending_groups.values())

    def _peek_request_wait_s(self, request: dict[str, Any]) -> float:
        request_id = request.get("request_id")
        if request_id is None:
            return 0.0
        enqueued_at = self.pending_enqueued_at.get(request_id)
        if enqueued_at is None:
            return 0.0
        return time.perf_counter() - enqueued_at

    def _oldest_request_wait_s(self) -> float | None:
        oldest_wait_s: float | None = None
        for group in self.pending_groups.values():
            if not group:
                continue
            wait_s = self._peek_request_wait_s(group[0])
            if oldest_wait_s is None or wait_s > oldest_wait_s:
                oldest_wait_s = wait_s
        return oldest_wait_s

    def _select_group_key(self) -> tuple[Any, ...] | None:
        best_group_key: tuple[Any, ...] | None = None
        best_ready_size = -1
        best_oldest_wait_s = -1.0
        for group_key, group in self.pending_groups.items():
            if not group:
                continue
            group_size = len(group)
            ready_size = min(group_size, self.gpu_batch_size)
            oldest_wait_s = self._peek_request_wait_s(group[0])
            can_submit = (
                self.allow_partial_batches
                or group_size >= self.gpu_batch_size
                or oldest_wait_s >= self.gpu_batch_timeout_s
            )
            if not can_submit:
                continue
            if ready_size > best_ready_size or (
                ready_size == best_ready_size and oldest_wait_s > best_oldest_wait_s
            ):
                best_group_key = group_key
                best_ready_size = ready_size
                best_oldest_wait_s = oldest_wait_s
        return best_group_key

    def _build_batch(self) -> list[dict[str, Any]]:
        if not self.pending_groups:
            return []
        group_key = self._select_group_key()
        if group_key is None:
            return []
        group = self.pending_groups[group_key]
        batch_size = min(len(group), self.gpu_batch_size)
        batch = [group.popleft() for _ in range(batch_size)]
        if not group:
            self.pending_groups.pop(group_key, None)
        return batch

    def _fill(self) -> None:
        while self.accept_new_work and self.pending_groups and self.idle_workers:
            batch = self._build_batch()
            if not batch:
                return
            worker = self.idle_workers.popleft()
            submit_time = time.perf_counter()
            submit_time_unix_s = time.time()
            request_ids = [request.get("request_id", "<missing>") for request in batch]
            request_queue_time_s_sum = 0.0
            for request_id in request_ids:
                enqueued_at = self.pending_enqueued_at.pop(request_id, None)
                if enqueued_at is not None:
                    request_queue_time_s_sum += submit_time - enqueued_at
                    self.request_dispatched_at[request_id] = submit_time
            logger.debug(
                "GenerationDispatcher submit: remaining_requests=%d running=%d batch_size=%d request_ids=%s",
                self._pending_group_count(),
                len(self.running) + 1,
                len(batch),
                request_ids,
            )
            self.running[worker.generate_batch.remote(batch)] = {
                "worker": worker,
                "request_ids": request_ids,
                "batch_size": len(batch),
                "submitted_at": submit_time,
                "submitted_at_unix_s": submit_time_unix_s,
                "request_queue_time_s_sum": request_queue_time_s_sum,
                "gpu_worker_id": getattr(
                    worker, "worker_trace_id", getattr(worker, "name", None)
                ),
                "gpu_device": getattr(worker, "worker_device", None),
            }
            self.completed_submission_events.append(
                {
                    "request_ids": request_ids,
                    "batch_size": len(batch),
                    "submitted_at": submit_time,
                    "submitted_at_unix_s": submit_time_unix_s,
                    "request_queue_time_s_sum": request_queue_time_s_sum,
                    "gpu_worker_id": getattr(
                        worker, "worker_trace_id", getattr(worker, "name", None)
                    ),
                    "gpu_device": getattr(worker, "worker_device", None),
                }
            )

    def has_pending(self) -> bool:
        return bool(self.pending_groups or self.running)

    def idle_worker_count(self) -> int:
        return len(self.idle_workers)

    def pending_request_count(self) -> int:
        return self._pending_group_count()

    def active_refs(self) -> list[Any]:
        return list(self.running.keys())

    def owns_ref(self, ref: Any) -> bool:
        return ref in self.running

    def enqueue_request(self, request: dict[str, Any]) -> None:
        if not self.accept_new_work:
            raise RuntimeError("GenerationDispatcher is not accepting new work")
        self._enqueue_pending_request(request)
        self._fill()

    def take_done(self, ref: Any) -> dict[str, Any]:
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
                "submitted_at_unix_s": running_meta["submitted_at_unix_s"],
                "gpu_worker_id": running_meta["gpu_worker_id"],
                "gpu_device": running_meta["gpu_device"],
                "batch_oldest_request_wait_time_s": max(
                    (
                        done_time
                        - running_meta["submitted_at"]
                        + running_meta["request_queue_time_s_sum"]
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
        self.pending_groups.clear()
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
