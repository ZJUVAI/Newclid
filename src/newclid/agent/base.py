from __future__ import annotations

from collections import deque
from concurrent.futures import (
    FIRST_COMPLETED,
    Future,
    ThreadPoolExecutor,
    wait as futures_wait,
)
import logging
import threading
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

import ray

from newclid.agent.agents_interface import DeductiveAgent
from newclid.formulations.problem import ProblemJGEX
from newclid.profiling import (
    add_profiling_time,
    create_profiling_payload,
    finalize_profiling,
    increment_profiling_count,
    update_profiling_max,
)
from newclid.proof import ProofState
from newclid.search_trace import build_attempt_key

from newclid.agent.runtime.search_runtime import BeamQueue, run_ddar_c, run_ddar_remote

if TYPE_CHECKING:
    from newclid.formulations.rule import Rule


logger = logging.getLogger(__name__)


class BaseAgent(DeductiveAgent, ABC):
    def __init__(
        self,
        model_pool,
        decoding_size: int,
        beam_size: int,
        search_depth: int,
        *,
        gpu_batch_size: int = 1,
        gpu_batch_timeout_ms: int = 0,
        agent_type: str,
        max_pending_ddar: int = 128,
        prepare_request_workers: int = 1,
        prepare_prefetch_limit: int = 1,
        ddar_returns_proof: bool = False,
        trace_writer=None,
    ):
        self.any_new_statement_has_been_added = True
        self.problemJGEX = None
        self.model_pool = model_pool
        self.decoding_size = decoding_size
        self.beam_size = beam_size
        self.search_depth = search_depth
        self.gpu_batch_size = gpu_batch_size
        self.gpu_batch_timeout_ms = gpu_batch_timeout_ms
        self.agent_type = agent_type
        self.max_pending_ddar = max_pending_ddar
        self.prepare_request_workers = prepare_request_workers
        self.prepare_prefetch_limit = prepare_prefetch_limit
        self.ddar_returns_proof = ddar_returns_proof
        self.trace_writer = trace_writer
        self._scheduler_trace_interval_s = 0.5
        self._last_scheduler_trace_at = 0.0
        self._last_scheduler_trace_state: dict[str, Any] | None = None

    def step(self, proof: ProofState, rules: list["Rule"]) -> bool:
        return True

    @abstractmethod
    def seed_state(self, proof: ProofState, base_proof: ProofState) -> Any:
        raise NotImplementedError

    @abstractmethod
    def get_problem_from_state(self, state: Any) -> ProblemJGEX:
        raise NotImplementedError

    @abstractmethod
    def prepare_request(
        self,
        *,
        request_id: str,
        state: Any,
        proof: ProofState,
        depth: int,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def make_next_state_from_unsolved_ddar(
        self,
        *,
        new_problem: ProblemJGEX,
        prior_state: Any,
        ddar_result: dict[str, Any],
        proof: ProofState,
        request: dict[str, Any],
        aux_dsl: str,
        raw_aux_text: str,
    ) -> Any | None:
        raise NotImplementedError

    @abstractmethod
    def try_dsl_to_constructions(self, content: str):
        raise NotImplementedError

    def base_ddar_proof(self, proof: ProofState) -> ProofState:
        return proof

    def run_ddar_c(
        self,
        proof: ProofState,
        rules: list["Rule"],
        start_time: float,
        timeout: int = 3600,
    ) -> bool:
        return run_ddar_c(proof, rules, start_time, timeout)

    def finalize_next_queue(
        self,
        *,
        next_queue: BeamQueue,
        profiling: dict[str, Any],
    ) -> BeamQueue:
        return next_queue

    def extract_raw_aux_text(self, aux_dsl: str, *, request: dict[str, Any]) -> str:
        response_prefix = str(request.get("response_prefix", "<aux> x00"))
        if aux_dsl.startswith(response_prefix):
            return aux_dsl[len(response_prefix) :]
        return aux_dsl

    def _child_path_key(
        self, parent_path_key: tuple[int, ...], candidate_rank: int
    ) -> tuple[int, ...]:
        return parent_path_key + (candidate_rank,)

    def _path_key_to_request_id(self, *, depth: int, path_key: tuple[int, ...]) -> str:
        suffix = "root" if not path_key else "-".join(str(rank) for rank in path_key)
        return f"d{depth}_p{suffix}"

    def _build_info_payload(
        self,
        *,
        t0: float,
        step: int,
        is_success: bool,
        profiling: dict[str, Any],
        error_msg: str | None = None,
        final_node_id: int | None = None,
        runtime_s: float | None = None,
    ):
        infos: dict[str, Any] = {}
        runtime = time.time() - t0 if runtime_s is None else runtime_s
        infos["runtime"] = runtime
        infos["success"] = is_success
        infos["steps"] = step
        infos["gpu_worker_stats"] = self.model_pool.get_worker_stats()
        infos["final_node_id"] = final_node_id
        infos["profiling"] = finalize_profiling(profiling, runtime)
        if error_msg:
            infos["error"] = error_msg
        return infos

    def _trace(self, event: str, **payload: Any) -> None:
        if self.trace_writer is not None:
            self.trace_writer.log(event, **payload)

    def _trace_scheduler_state(
        self,
        *,
        depth: int,
        dispatcher,
        running_prepare_futures: dict[Future[dict[str, Any]], dict[str, Any]],
        prepared_requests: list[tuple[int, dict[str, Any]]],
        pending_ddar_submit: deque[dict[str, Any]],
        running_futures: list[Any],
        frontier_exhausted: bool,
        force: bool = False,
    ) -> None:
        del depth, dispatcher, running_prepare_futures, prepared_requests
        del pending_ddar_submit, running_futures, frontier_exhausted, force
        return

    def _trace_ddar_result(
        self, *, depth: int, future_meta: dict[str, Any], ddar_result: dict[str, Any]
    ) -> None:
        self._trace(
            "ddar_result",
            attempt_key=future_meta["attempt_key"],
            node_id=future_meta["node_id"],
            parent_node_id=future_meta["parent_node_id"],
            depth=depth,
            status=ddar_result.get("status"),
            elapsed_time=ddar_result.get("elapsed_time"),
            ddar_build_work_time_s=ddar_result.get("ddar_build_work_time_s"),
            ddar_engine_work_time_s=ddar_result.get("ddar_engine_work_time_s"),
            ddar_worker_id=ddar_result.get("ddar_worker_id"),
            ddar_started_at_unix_s=ddar_result.get("ddar_started_at_unix_s"),
            ddar_finished_at_unix_s=ddar_result.get("ddar_finished_at_unix_s"),
            ddar_build_started_at_unix_s=ddar_result.get(
                "ddar_build_started_at_unix_s"
            ),
            ddar_build_finished_at_unix_s=ddar_result.get(
                "ddar_build_finished_at_unix_s"
            ),
            ddar_engine_started_at_unix_s=ddar_result.get(
                "ddar_engine_started_at_unix_s"
            ),
            ddar_engine_finished_at_unix_s=ddar_result.get(
                "ddar_engine_finished_at_unix_s"
            ),
            error_type=ddar_result.get("error_type"),
            error_message=ddar_result.get("error_message"),
            raw_aux_text=future_meta.get("raw_aux_text"),
            construction_text=future_meta.get("construction_text"),
        )

    def _handle_ddar_done(
        self,
        *,
        done_futures: list[Any],
        running_futures: list[Any],
        future_info: dict[Any, dict[str, Any]],
        next_queue: BeamQueue,
        depth: int,
        t0: float,
        step: int,
        profiling: dict[str, Any],
        proof: ProofState,
        runtime_s: float,
    ):
        # DDAR completions mark the hand-off between the current depth's
        # validation work and the next depth's frontier.
        handle_start = time.perf_counter()
        for future in done_futures:
            ray_get_start = time.perf_counter()
            ddar_result = ray.get(future)
            add_profiling_time(
                profiling,
                "ddar_result_ray_get_wall_time_s",
                time.perf_counter() - ray_get_start,
            )
            future_meta = future_info.pop(future)
            increment_profiling_count(profiling, "ddar_completed_count")
            add_profiling_time(
                profiling,
                "ddar_build_work_time_s",
                ddar_result.get("ddar_build_work_time_s"),
            )
            add_profiling_time(
                profiling,
                "ddar_engine_work_time_s",
                ddar_result.get("ddar_engine_work_time_s"),
            )

            if ddar_result["status"] == "invalid":
                self._trace_ddar_result(
                    depth=depth, future_meta=future_meta, ddar_result=ddar_result
                )
                continue

            if ddar_result["status"] == "solved":
                self._cancel_ddar_futures(running_futures, future_info)
                self._trace_ddar_result(
                    depth=depth, future_meta=future_meta, ddar_result=ddar_result
                )
                handle_elapsed_s = time.perf_counter() - handle_start
                add_profiling_time(
                    profiling, "ddar_result_handle_wall_time_s", handle_elapsed_s
                )
                return self._build_info_payload(
                    t0=t0,
                    step=step,
                    is_success=True,
                    profiling=profiling,
                    error_msg=str(future_meta["problem"]),
                    final_node_id=future_meta["node_id"],
                    runtime_s=runtime_s,
                )

            self._trace_ddar_result(
                depth=depth, future_meta=future_meta, ddar_result=ddar_result
            )
            if depth < self.search_depth - 1:
                next_state_start = time.perf_counter()
                next_state = self.make_next_state_from_unsolved_ddar(
                    new_problem=future_meta["problem"],
                    prior_state=future_meta["state"],
                    ddar_result=ddar_result,
                    proof=proof,
                    request=future_meta["request"],
                    aux_dsl=future_meta["aux_dsl"],
                    raw_aux_text=future_meta["raw_aux_text"],
                )
                add_profiling_time(
                    profiling,
                    "ddar_result_next_state_wall_time_s",
                    time.perf_counter() - next_state_start,
                )
                if next_state is not None:
                    child_score = future_meta["prev_score"] + future_meta["score"]
                    queue_start = time.perf_counter()
                    next_queue.add(
                        node=(
                            future_meta["node_id"],
                            future_meta["parent_node_id"],
                            future_meta["path_key"],
                            next_state,
                        ),
                        val=child_score,
                        stable_key=future_meta["path_key"],
                    )
                    add_profiling_time(
                        profiling,
                        "ddar_result_queue_wall_time_s",
                        time.perf_counter() - queue_start,
                    )
                    increment_profiling_count(
                        profiling, "candidate_queued_next_depth_count"
                    )
                    self._trace(
                        "candidate_transition",
                        attempt_key=future_meta["attempt_key"],
                        request_id=future_meta["request_id"],
                        parent_node_id=future_meta["parent_node_id"],
                        node_id=future_meta["node_id"],
                        candidate_rank=future_meta["candidate_rank"],
                        depth=depth,
                        decision="queued_next_depth",
                        beam_score_before=future_meta["prev_score"],
                        beam_score_after=child_score,
                        raw_aux_text=future_meta.get("raw_aux_text"),
                        construction_text=future_meta.get("construction_text"),
                    )
        handle_elapsed_s = time.perf_counter() - handle_start
        add_profiling_time(
            profiling, "ddar_result_handle_wall_time_s", handle_elapsed_s
        )
        return None

    def _poll_ddar_futures(
        self,
        *,
        running_futures: list[Any],
        future_info: dict[Any, dict[str, Any]],
        next_queue: BeamQueue,
        depth: int,
        t0: float,
        step: int,
        profiling: dict[str, Any],
        proof: ProofState,
        runtime_s: float,
    ):
        if not running_futures:
            return None
        done, remaining = ray.wait(
            running_futures,
            num_returns=len(running_futures),
            timeout=0,
        )
        if not done:
            return None
        running_futures[:] = remaining
        return self._handle_ddar_done(
            done_futures=done,
            running_futures=running_futures,
            future_info=future_info,
            next_queue=next_queue,
            depth=depth,
            t0=t0,
            step=step,
            profiling=profiling,
            proof=proof,
            runtime_s=runtime_s,
        )

    def _cancel_ddar_futures(
        self, running_futures: list[Any], future_info: dict[Any, dict[str, Any]]
    ) -> None:
        for future in running_futures:
            try:
                ray.cancel(future, force=True)
            except Exception:
                pass
        running_futures.clear()
        future_info.clear()

    def _run_prepare_request(
        self,
        *,
        request_id: str,
        state: Any,
        proof: ProofState,
        depth: int,
    ) -> dict[str, Any]:
        prepare_started_at_unix_s = time.time()
        request = self.prepare_request(
            request_id=request_id,
            state=state,
            proof=proof,
            depth=depth,
        )
        prepare_finished_at_unix_s = time.time()
        return {
            "request": request,
            "trace": {
                "prepare_worker_id": threading.current_thread().name,
                "prepare_started_at_unix_s": prepare_started_at_unix_s,
                "prepare_finished_at_unix_s": prepare_finished_at_unix_s,
            },
        }

    def _submit_prepare_request(
        self,
        *,
        prepare_executor: ThreadPoolExecutor,
        frontier_iter,
        request_index: int,
        request_meta: dict[str, dict[str, Any]],
        running_prepare_futures: dict[Future[dict[str, Any]], dict[str, Any]],
        proof: ProofState,
        depth: int,
    ) -> int | None:
        try:
            prev_score, node = next(frontier_iter)
        except StopIteration:
            return None

        node_id, parent_node_id, path_key, state = node
        request_id = self._path_key_to_request_id(depth=depth, path_key=path_key)
        request_meta[request_id] = {
            "state": state,
            "prev_score": prev_score,
            "node_id": node_id,
            "parent_node_id": parent_node_id,
            "path_key": path_key,
            "request": None,
            "request_order": request_index,
        }
        future = prepare_executor.submit(
            self._run_prepare_request,
            request_id=request_id,
            state=state,
            proof=proof,
            depth=depth,
        )
        running_prepare_futures[future] = {
            "request_id": request_id,
            "node_id": node_id,
            "parent_node_id": parent_node_id,
            "path_key": path_key,
            "depth": depth,
            "submitted_at_perf_s": time.perf_counter(),
        }
        self._trace(
            "prepare_request_submitted",
            node_id=node_id,
            parent_node_id=parent_node_id,
            depth=depth,
            request_id=request_id,
        )
        return request_index + 1

    def _poll_prepare_futures(
        self,
        *,
        running_prepare_futures: dict[Future[dict[str, Any]], dict[str, Any]],
        request_meta: dict[str, dict[str, Any]],
        prepared_requests: list[tuple[int, dict[str, Any]]],
        profiling: dict[str, Any],
        block_timeout_s: float = 0.0,
    ) -> bool:
        if not running_prepare_futures:
            return False

        done_futures, _ = futures_wait(
            tuple(running_prepare_futures.keys()),
            timeout=block_timeout_s,
            return_when=FIRST_COMPLETED,
        )
        if not done_futures:
            return False

        progressed = False
        for future in list(done_futures):
            future_meta = running_prepare_futures.pop(future)
            request_id = future_meta["request_id"]
            request_state = request_meta.get(request_id)
            try:
                prepare_payload = future.result()
            except Exception as exc:
                logger.warning(
                    "Prepare request failed: request_id=%s depth=%s error=%s",
                    request_id,
                    future_meta["depth"],
                    exc,
                )
                request_meta.pop(request_id, None)
                continue

            if request_state is None:
                continue
            request = prepare_payload["request"]
            prepare_trace = dict(prepare_payload.get("trace", {}))
            request["depth"] = future_meta["depth"]
            request_built_at_perf_s = time.perf_counter()
            request_state["request_built_at_perf_s"] = request_built_at_perf_s
            request_state["request"] = request
            prepared_requests.append((request_state["request_order"], request))
            prepared_requests.sort(key=lambda item: item[0])
            add_profiling_time(
                profiling,
                "prepared_request_ready_wall_time_s",
                request_built_at_perf_s - future_meta["submitted_at_perf_s"],
            )
            increment_profiling_count(profiling, "prepare_request_completed_count")
            self._trace(
                "prepare_request_ready",
                node_id=future_meta["node_id"],
                parent_node_id=future_meta["parent_node_id"],
                depth=future_meta["depth"],
                request_id=request_id,
                **prepare_trace,
            )
            progressed = True
        return progressed

    def _cleanup_prepare_futures(
        self,
        *,
        running_prepare_futures: dict[Future[dict[str, Any]], dict[str, Any]],
        request_meta: dict[str, dict[str, Any]],
    ) -> None:
        for future, future_meta in list(running_prepare_futures.items()):
            future.cancel()
            request_meta.pop(future_meta["request_id"], None)
        running_prepare_futures.clear()

    def _wait_for_next_event(
        self,
        *,
        dispatcher,
        running_futures: list[Any],
        running_prepare_futures: dict[Future[dict[str, Any]], dict[str, Any]],
        profiling: dict[str, Any],
    ) -> None:
        # In the parallel prepare pipeline, worker runtime is not wall-clock on
        # the main thread. We only attribute wall time here when the scheduler
        # is actually blocked waiting for some stage to finish.
        wait_start = time.perf_counter()
        wait_refs = dispatcher.active_refs() + running_futures

        # If only prepare work is outstanding, this blocked interval is the
        # prepare stage on the critical path.
        if running_prepare_futures and not wait_refs:
            futures_wait(
                tuple(running_prepare_futures.keys()),
                timeout=0.1,
                return_when=FIRST_COMPLETED,
            )
            add_profiling_time(
                profiling,
                "request_prepare_wall_time_s",
                time.perf_counter() - wait_start,
            )
            return

        if running_prepare_futures:
            done_futures, _ = futures_wait(
                tuple(running_prepare_futures.keys()),
                timeout=0.1,
                return_when=FIRST_COMPLETED,
            )
            if done_futures:
                add_profiling_time(
                    profiling, "wait_wall_time_s", time.perf_counter() - wait_start
                )
                return

        remaining_timeout_s = max(0.0, 1.0 - (time.perf_counter() - wait_start))
        if not wait_refs:
            return
        ray.wait(wait_refs, num_returns=1, timeout=remaining_timeout_s)
        add_profiling_time(
            profiling, "wait_wall_time_s", time.perf_counter() - wait_start
        )
        return

    def _drain_dispatcher_submission_events(
        self, *, dispatcher, depth: int, profiling: dict[str, Any]
    ) -> None:
        for event in dispatcher.take_submission_events():
            increment_profiling_count(profiling, "gpu_batch_submitted_count")
            increment_profiling_count(
                profiling,
                "gpu_request_dispatched_count",
                len(event.get("request_ids", [])),
            )
            increment_profiling_count(
                profiling, "gpu_batch_size_sum", int(event.get("batch_size", 0))
            )
            update_profiling_max(
                profiling, "gpu_batch_size_max", event.get("batch_size")
            )
            self._trace(
                "gpu_batch_submitted",
                depth=depth,
                request_ids=event.get("request_ids", []),
                batch_size=event.get("batch_size"),
                gpu_worker_id=event.get("gpu_worker_id"),
                gpu_device=event.get("gpu_device"),
            )

    def _handle_gpu_result(
        self,
        *,
        gpu_batch_payload: dict[str, Any],
        request_meta: dict[str, dict[str, Any]],
        pending_ddar_submit,
        depth: int,
        profiling: dict[str, Any],
        next_node_id: int,
    ) -> int:
        # This stage is the CPU-side post-processing after a GPU worker returns.
        # If it grows large, the bottleneck is in DSL parsing / construction
        # handling rather than the model's forward pass.
        handle_start = time.perf_counter()
        dispatcher_profile = gpu_batch_payload.get("dispatcher_profile", {})
        worker_batch_profile = gpu_batch_payload.get("worker_batch_profile", {})
        batch_results = list(gpu_batch_payload.get("results", []))
        batch_size = int(gpu_batch_payload.get("batch_size", len(batch_results)))
        add_profiling_time(
            profiling,
            "gpu_request_queue_wall_time_s",
            dispatcher_profile.get("request_queue_time_s_sum"),
        )
        add_profiling_time(
            profiling,
            "gpu_batch_round_trip_wall_time_s",
            dispatcher_profile.get("batch_round_trip_time_s"),
        )
        add_profiling_time(
            profiling,
            "gpu_result_ray_get_wall_time_s",
            dispatcher_profile.get("batch_result_ray_get_time_s"),
        )
        add_profiling_time(
            profiling,
            "gpu_worker_inference_wall_time_s",
            worker_batch_profile.get("worker_inference_time_s"),
        )
        add_profiling_time(
            profiling,
            "gpu_input_build_wall_time_s",
            worker_batch_profile.get("input_build_time_s"),
        )
        add_profiling_time(
            profiling,
            "gpu_generate_wall_time_s",
            worker_batch_profile.get("generate_time_s"),
        )
        add_profiling_time(
            profiling,
            "gpu_decode_wall_time_s",
            worker_batch_profile.get("decode_time_s"),
        )
        add_profiling_time(
            profiling,
            "gpu_fallback_wall_time_s",
            worker_batch_profile.get("fallback_time_s"),
        )
        increment_profiling_count(profiling, "gpu_batch_completed_count")
        increment_profiling_count(profiling, "gpu_request_completed_count", batch_size)
        increment_profiling_count(
            profiling,
            "gpu_prompt_token_count_sum",
            worker_batch_profile.get("prompt_token_count_sum"),
        )
        update_profiling_max(
            profiling,
            "gpu_prompt_token_count_max",
            worker_batch_profile.get("prompt_token_count_max"),
        )
        increment_profiling_count(
            profiling,
            "gpu_generated_token_count_sum",
            worker_batch_profile.get("generated_token_count_sum"),
        )
        update_profiling_max(
            profiling,
            "gpu_generated_token_count_max",
            worker_batch_profile.get("generated_token_count_max"),
        )
        increment_profiling_count(
            profiling,
            "gpu_generated_sequence_count",
            worker_batch_profile.get("generated_sequence_count"),
        )
        increment_profiling_count(
            profiling,
            "gpu_raw_candidate_count",
            worker_batch_profile.get("raw_candidate_count_sum"),
        )
        increment_profiling_count(
            profiling,
            "gpu_unique_candidate_count",
            worker_batch_profile.get("unique_candidate_count_sum"),
        )
        increment_profiling_count(
            profiling,
            "gpu_duplicate_candidate_count",
            worker_batch_profile.get("duplicate_candidate_count_sum"),
        )
        add_profiling_time(
            profiling,
            "gpu_first_token_latency_sum_s",
            worker_batch_profile.get("first_token_latency_sum_s"),
        )
        increment_profiling_count(
            profiling,
            "gpu_first_token_latency_count",
            worker_batch_profile.get("first_token_latency_count"),
        )

        self._trace(
            "gpu_batch_done",
            depth=depth,
            request_ids=gpu_batch_payload.get("request_ids", []),
            batch_size=batch_size,
            gpu_worker_id=worker_batch_profile.get("gpu_worker_id")
            or dispatcher_profile.get("gpu_worker_id"),
            gpu_device=worker_batch_profile.get("gpu_device")
            or dispatcher_profile.get("gpu_device"),
            worker_batch_profile={
                "gpu_worker_id": worker_batch_profile.get("gpu_worker_id")
                or dispatcher_profile.get("gpu_worker_id"),
                "gpu_device": worker_batch_profile.get("gpu_device")
                or dispatcher_profile.get("gpu_device"),
                "worker_started_at_unix_s": worker_batch_profile.get(
                    "worker_started_at_unix_s"
                ),
                "worker_finished_at_unix_s": worker_batch_profile.get(
                    "worker_finished_at_unix_s"
                ),
                "worker_inference_time_s": worker_batch_profile.get(
                    "worker_inference_time_s"
                ),
                "generate_time_s": worker_batch_profile.get("generate_time_s"),
            },
        )

        for gpu_result in batch_results:
            request_id = gpu_result["request_id"]
            request_state = request_meta.pop(request_id)
            request = request_state["request"]
            if request is None:
                logger.warning(
                    "GPU result missing prepared request context: request_id=%s",
                    request_id,
                )
                continue
            state = request_state["state"]
            prev_score = request_state["prev_score"]
            parent_node_id = request_state["node_id"]
            parent_path_key = request_state["path_key"]
            problem = self.get_problem_from_state(state)
            logger.debug(
                "Search depth=%d request=%s candidate_count=%d",
                depth,
                request_id,
                len(gpu_result["aux_dsl_dict"]),
            )

            for candidate_rank, (aux_dsl, score) in enumerate(
                gpu_result["aux_dsl_dict"].items()
            ):
                raw_aux_text = self.extract_raw_aux_text(aux_dsl, request=request)
                try:
                    aux = self.try_dsl_to_constructions(raw_aux_text)
                except Exception:
                    increment_profiling_count(profiling, "candidate_parse_failed_count")
                    self._trace(
                        "candidate_transition",
                        attempt_key=build_attempt_key(request_id, candidate_rank, None),
                        request_id=request_id,
                        parent_node_id=parent_node_id,
                        node_id=None,
                        candidate_rank=candidate_rank,
                        depth=depth,
                        decision="parse_failed",
                        beam_score_before=prev_score,
                        beam_score_after=None,
                        raw_aux_text=raw_aux_text,
                        construction_text=None,
                    )
                    continue

                if not aux:
                    increment_profiling_count(profiling, "candidate_parse_failed_count")
                    self._trace(
                        "candidate_transition",
                        attempt_key=build_attempt_key(request_id, candidate_rank, None),
                        request_id=request_id,
                        parent_node_id=parent_node_id,
                        node_id=None,
                        candidate_rank=candidate_rank,
                        depth=depth,
                        decision="parse_failed",
                        beam_score_before=prev_score,
                        beam_score_after=None,
                        raw_aux_text=raw_aux_text,
                        construction_text=None,
                    )
                    continue

                increment_profiling_count(profiling, "candidate_parse_success_count")
                try:
                    new_problem = problem.with_more_construction(aux)
                except Exception:
                    increment_profiling_count(profiling, "candidate_build_failed_count")
                    self._trace(
                        "candidate_transition",
                        attempt_key=build_attempt_key(request_id, candidate_rank, None),
                        request_id=request_id,
                        parent_node_id=parent_node_id,
                        node_id=None,
                        candidate_rank=candidate_rank,
                        depth=depth,
                        decision="build_failed",
                        beam_score_before=prev_score,
                        beam_score_after=None,
                        raw_aux_text=raw_aux_text,
                        construction_text=aux,
                    )
                    continue

                increment_profiling_count(profiling, "candidate_build_success_count")
                child_node_id = next_node_id
                next_node_id += 1
                child_path_key = self._child_path_key(parent_path_key, candidate_rank)
                pending_ddar_submit.append(
                    {
                        "problem": new_problem,
                        "state": state,
                        "request": request,
                        "prev_score": prev_score,
                        "score": score,
                        "node_id": child_node_id,
                        "parent_node_id": parent_node_id,
                        "request_id": request_id,
                        "candidate_rank": candidate_rank,
                        "path_key": child_path_key,
                        "attempt_key": build_attempt_key(
                            request_id, candidate_rank, child_node_id
                        ),
                        "aux_dsl": aux_dsl,
                        "raw_aux_text": raw_aux_text,
                        "construction_text": aux,
                    }
                )

        handle_elapsed_s = time.perf_counter() - handle_start
        add_profiling_time(profiling, "gpu_result_handle_wall_time_s", handle_elapsed_s)
        return next_node_id

    def _submit_pending_ddar(
        self,
        *,
        pending_ddar_submit,
        running_futures: list[Any],
        future_info: dict[Any, dict[str, Any]],
        rules_ref,
        proof: ProofState,
        depth: int,
        t0: float,
        timeout: int,
        profiling: dict[str, Any],
    ) -> None:
        # Submitting DDAR work is the backpressure boundary between generation
        # and validation. We measure it separately from the DDAR execution so
        # we can see whether the bottleneck is queueing or the engine itself.
        submit_start = time.perf_counter()
        while pending_ddar_submit and len(running_futures) < self.max_pending_ddar:
            candidate_meta = pending_ddar_submit.popleft()
            candidate_meta["ddar_submitted_at_perf_s"] = time.perf_counter()
            candidate_meta["ddar_submitted_at_unix_s"] = time.time()
            self._trace(
                "candidate_transition",
                attempt_key=candidate_meta["attempt_key"],
                request_id=candidate_meta["request_id"],
                parent_node_id=candidate_meta["parent_node_id"],
                node_id=candidate_meta["node_id"],
                candidate_rank=candidate_meta["candidate_rank"],
                depth=depth,
                decision="ddar_submitted",
                beam_score_before=candidate_meta["prev_score"],
                beam_score_after=candidate_meta["prev_score"] + candidate_meta["score"],
                raw_aux_text=candidate_meta.get("raw_aux_text"),
                construction_text=candidate_meta.get("construction_text"),
            )
            self._trace(
                "ddar_submit",
                attempt_key=candidate_meta["attempt_key"],
                node_id=candidate_meta["node_id"],
                parent_node_id=candidate_meta["parent_node_id"],
                depth=depth,
                ddar_submitted_at_unix_s=candidate_meta["ddar_submitted_at_unix_s"],
                raw_aux_text=candidate_meta.get("raw_aux_text"),
                construction_text=candidate_meta.get("construction_text"),
            )
            future = run_ddar_remote.remote(
                candidate_meta["problem"],
                proof.defs,
                rules_ref,
                t0,
                timeout,
                return_proof=self.ddar_returns_proof,
            )
            logger.debug(
                "Search depth=%d request=%s queued DDAR future; pending_ddar=%d queued_ddar=%d",
                depth,
                candidate_meta["request_id"],
                len(running_futures) + 1,
                len(pending_ddar_submit),
            )
            future_info[future] = candidate_meta
            running_futures.append(future)
            increment_profiling_count(profiling, "ddar_submitted_count")
        submit_elapsed_s = time.perf_counter() - submit_start
        add_profiling_time(profiling, "ddar_submit_wall_time_s", submit_elapsed_s)

    def run(
        self, proof: ProofState, rules: list["Rule"], timeout: int = 3600
    ) -> dict[str, Any]:
        logger.info(
            "Agent run start: agent_type=%s decoding_size=%d beam_size=%d search_depth=%d max_pending_ddar=%d timeout=%d",
            self.agent_type,
            self.decoding_size,
            self.beam_size,
            self.search_depth,
            self.max_pending_ddar,
            timeout,
        )
        t0 = time.time()
        perf_t0 = time.perf_counter()
        step = 0
        next_node_id = 1
        profiling = create_profiling_payload()
        self._last_scheduler_trace_at = 0.0
        self._last_scheduler_trace_state = None

        for goal in proof.goals:
            if not goal.check_numerical():
                logger.warning(
                    "Agent run abort: goal failed numerical check: %s", goal.pretty()
                )
                return self._build_info_payload(
                    t0=t0,
                    step=step,
                    is_success=False,
                    profiling=profiling,
                    error_msg=f"{goal.pretty()} fails numerical check",
                )

        base_proof = self.base_ddar_proof(proof)
        logger.debug("Agent base DDAR start")
        self._trace(
            "base_ddar",
            attempt_key="base:0",
            node_id=0,
            parent_node_id=None,
            depth=-1,
        )
        base_ddar_started_at_unix_s = time.time()
        ddar_start = time.perf_counter()
        base_solved = self.run_ddar_c(base_proof, rules, t0, timeout)
        base_ddar_elapsed_s = time.perf_counter() - ddar_start
        add_profiling_time(profiling, "base_ddar_wall_time_s", base_ddar_elapsed_s)
        base_ddar_finished_at_unix_s = time.time()
        base_ddar_trace = {
            "ddar_worker_id": "ddar:base_main",
            "ddar_started_at_unix_s": base_ddar_started_at_unix_s,
            "ddar_finished_at_unix_s": base_ddar_finished_at_unix_s,
            "ddar_build_work_time_s": 0.0,
            "ddar_engine_work_time_s": base_ddar_finished_at_unix_s
            - base_ddar_started_at_unix_s,
            "ddar_build_started_at_unix_s": base_ddar_started_at_unix_s,
            "ddar_build_finished_at_unix_s": base_ddar_started_at_unix_s,
            "ddar_engine_started_at_unix_s": base_ddar_started_at_unix_s,
            "ddar_engine_finished_at_unix_s": base_ddar_finished_at_unix_s,
        }
        if base_solved:
            self._trace(
                "ddar_result",
                attempt_key="base:0",
                node_id=0,
                parent_node_id=None,
                depth=-1,
                status="solved",
                elapsed_time=None,
                error_type=None,
                error_message=None,
                **base_ddar_trace,
            )
            logger.info("Agent base DDAR solved problem before search")
            return self._build_info_payload(
                t0=t0,
                step=step,
                is_success=True,
                profiling=profiling,
                final_node_id=0,
                runtime_s=time.perf_counter() - perf_t0,
            )
        self._trace(
            "ddar_result",
            attempt_key="base:0",
            node_id=0,
            parent_node_id=None,
            depth=-1,
            status="unsolved",
            elapsed_time=None,
            error_type=None,
            error_message=None,
            **base_ddar_trace,
        )
        logger.debug("Agent base DDAR unsolved; entering search")

        rules_ref = ray.put(rules)
        beam_queue = BeamQueue(max_size=self.beam_size)
        beam_queue.add(
            node=(0, None, (), self.seed_state(proof, base_proof)),
            val=0.0,
            stable_key=(),
        )

        with ThreadPoolExecutor(
            max_workers=self.prepare_request_workers, thread_name_prefix="prepare"
        ) as prepare_executor:
            # Search stays depth-by-depth to preserve the beam semantics. Within
            # one depth we pipeline request preparation, GPU inference, and DDAR
            # validation so CPU and GPU resources can overlap useful work.
            for depth in range(self.search_depth):
                step = depth + 1
                frontier_size = len(list(beam_queue))
                self._trace("depth_start", depth=depth, frontier_size=frontier_size)
                logger.info(
                    "Search depth start: depth=%d frontier_size=%d elapsed=%.2fs",
                    depth,
                    frontier_size,
                    time.time() - t0,
                )
                if time.time() - t0 > timeout:
                    logger.warning("Agent timeout before depth=%d", depth)
                    return self._build_info_payload(
                        t0=t0,
                        step=step,
                        is_success=False,
                        profiling=profiling,
                        error_msg="Timeout",
                        runtime_s=time.perf_counter() - perf_t0,
                    )

                if frontier_size == 0:
                    logger.info("Search depth=%d produced no requests; stopping", depth)
                    break

                dispatcher = self.model_pool.create_dispatcher(
                    gpu_batch_size=self.gpu_batch_size,
                    gpu_batch_timeout_ms=self.gpu_batch_timeout_ms,
                )
                next_queue = BeamQueue(max_size=self.beam_size)
                frontier_iter = iter(beam_queue)
                prepared_requests: list[tuple[int, dict[str, Any]]] = []
                running_prepare_futures: dict[
                    Future[dict[str, Any]], dict[str, Any]
                ] = {}
                pending_ddar_submit = deque()
                request_meta: dict[str, dict[str, Any]] = {}
                running_futures: list[Any] = []
                future_info: dict[Any, dict[str, Any]] = {}
                request_index = 0
                frontier_exhausted = False
                ddar_backlog_high_watermark = max(
                    self.max_pending_ddar + 1, 2 * self.max_pending_ddar
                )
                self._trace_scheduler_state(
                    depth=depth,
                    dispatcher=dispatcher,
                    running_prepare_futures=running_prepare_futures,
                    prepared_requests=prepared_requests,
                    pending_ddar_submit=pending_ddar_submit,
                    running_futures=running_futures,
                    frontier_exhausted=frontier_exhausted,
                    force=True,
                )

                while True:
                    loop_start = time.perf_counter()
                    # Track which wall-clock buckets changed in this loop body
                    # so any residual bookkeeping can be attributed to scheduler
                    # overhead rather than useful work.
                    wall_before = {
                        field: float(profiling.get(field, 0.0))
                        for field in (
                            "request_prepare_wall_time_s",
                            "wait_wall_time_s",
                            "gpu_result_handle_wall_time_s",
                            "ddar_submit_wall_time_s",
                            "ddar_result_handle_wall_time_s",
                            "scheduler_overhead_wall_time_s",
                        )
                    }
                    progress = False
                    self._trace_scheduler_state(
                        depth=depth,
                        dispatcher=dispatcher,
                        running_prepare_futures=running_prepare_futures,
                        prepared_requests=prepared_requests,
                        pending_ddar_submit=pending_ddar_submit,
                        running_futures=running_futures,
                        frontier_exhausted=frontier_exhausted,
                    )
                    dispatcher.tick()
                    self._drain_dispatcher_submission_events(
                        dispatcher=dispatcher, depth=depth, profiling=profiling
                    )

                    # 1. Consume finished DDAR tasks first so validated states
                    # can immediately contribute to the next-depth frontier.
                    ddar_before_poll = len(running_futures)
                    solved_payload = self._poll_ddar_futures(
                        running_futures=running_futures,
                        future_info=future_info,
                        next_queue=next_queue,
                        depth=depth,
                        t0=t0,
                        step=step,
                        profiling=profiling,
                        proof=proof,
                        runtime_s=time.perf_counter() - perf_t0,
                    )
                    if solved_payload is not None:
                        dispatcher.cancel_running()
                        self._cleanup_prepare_futures(
                            running_prepare_futures=running_prepare_futures,
                            request_meta=request_meta,
                        )
                        return solved_payload
                    if len(running_futures) != ddar_before_poll:
                        progress = True

                    # 2. Drain any completed GPU work without blocking so model
                    # outputs can flow into DDAR as quickly as possible.
                    active_gpu_refs = dispatcher.active_refs()
                    if active_gpu_refs:
                        done_gpu_refs, _ = ray.wait(
                            active_gpu_refs,
                            num_returns=len(active_gpu_refs),
                            timeout=0,
                        )
                        for done_ref in done_gpu_refs:
                            gpu_batch_payload = dispatcher.take_done(done_ref)
                            next_node_id = self._handle_gpu_result(
                                gpu_batch_payload=gpu_batch_payload,
                                request_meta=request_meta,
                                pending_ddar_submit=pending_ddar_submit,
                                depth=depth,
                                profiling=profiling,
                                next_node_id=next_node_id,
                            )
                            progress = True

                    # 3. Submit as many validated DDAR candidates as the current
                    # backlog limit allows.
                    before_submit = len(running_futures)
                    self._submit_pending_ddar(
                        pending_ddar_submit=pending_ddar_submit,
                        running_futures=running_futures,
                        future_info=future_info,
                        rules_ref=rules_ref,
                        proof=proof,
                        depth=depth,
                        t0=t0,
                        timeout=timeout,
                        profiling=profiling,
                    )
                    if len(running_futures) != before_submit:
                        progress = True

                    ddar_backlog = len(pending_ddar_submit) + len(running_futures)

                    # 4. Collect finished prepare tasks so fully-built requests
                    # can be handed to idle GPU workers.
                    if self._poll_prepare_futures(
                        running_prepare_futures=running_prepare_futures,
                        request_meta=request_meta,
                        prepared_requests=prepared_requests,
                        profiling=profiling,
                    ):
                        progress = True

                    # 5. Feed any idle GPU workers while DDAR backlog remains
                    # under control.
                    while (
                        prepared_requests
                        and dispatcher.idle_worker_count() > 0
                        and (len(pending_ddar_submit) + len(running_futures))
                        <= ddar_backlog_high_watermark
                    ):
                        _, request = prepared_requests.pop(0)
                        enqueue_at = time.perf_counter()
                        request_state = request_meta[request["request_id"]]
                        add_profiling_time(
                            profiling,
                            "prepared_request_queue_wall_time_s",
                            enqueue_at
                            - request_state.get("request_built_at_perf_s", enqueue_at),
                        )
                        request_state["gpu_submitted_at_perf_s"] = enqueue_at
                        dispatcher.enqueue_request(request)
                        increment_profiling_count(
                            profiling, "gpu_request_enqueued_count"
                        )
                        self._trace(
                            "gpu_request_enqueued",
                            request_id=request["request_id"],
                            node_id=request_state["node_id"],
                            parent_node_id=request_state["parent_node_id"],
                            depth=depth,
                        )
                        self._drain_dispatcher_submission_events(
                            dispatcher=dispatcher, depth=depth, profiling=profiling
                        )
                        progress = True

                    # 6. Launch more prepare work on demand instead of building
                    # the whole depth eagerly. This keeps CPU work bounded by
                    # the amount of GPU/DDAR capacity we can actually use.
                    while (
                        not frontier_exhausted
                        and (len(running_prepare_futures) + len(prepared_requests))
                        < self.prepare_prefetch_limit
                        and ddar_backlog <= ddar_backlog_high_watermark
                    ):
                        next_request_index = self._submit_prepare_request(
                            prepare_executor=prepare_executor,
                            frontier_iter=frontier_iter,
                            request_index=request_index,
                            request_meta=request_meta,
                            running_prepare_futures=running_prepare_futures,
                            proof=proof,
                            depth=depth,
                        )
                        if next_request_index is None:
                            frontier_exhausted = True
                            break
                        request_index = next_request_index
                        increment_profiling_count(
                            profiling, "prepare_request_submitted_count"
                        )
                        progress = True

                    if (
                        frontier_exhausted
                        and not running_prepare_futures
                        and prepared_requests
                    ):
                        dispatcher.flush()
                        self._drain_dispatcher_submission_events(
                            dispatcher=dispatcher, depth=depth, profiling=profiling
                        )
                        progress = True

                    if (
                        frontier_exhausted
                        and not running_prepare_futures
                        and not prepared_requests
                        and not dispatcher.has_pending()
                        and not pending_ddar_submit
                        and not running_futures
                    ):
                        # The next depth only starts after the current depth
                        # fully drains, so frontier replacement remains
                        # deterministic.
                        break

                    self._trace_scheduler_state(
                        depth=depth,
                        dispatcher=dispatcher,
                        running_prepare_futures=running_prepare_futures,
                        prepared_requests=prepared_requests,
                        pending_ddar_submit=pending_ddar_submit,
                        running_futures=running_futures,
                        frontier_exhausted=frontier_exhausted,
                    )

                    loop_elapsed_s = time.perf_counter() - loop_start
                    accounted_delta = sum(
                        float(profiling.get(field, 0.0)) - wall_before[field]
                        for field in wall_before
                    )
                    add_profiling_time(
                        profiling,
                        "scheduler_overhead_wall_time_s",
                        max(loop_elapsed_s - accounted_delta, 0.0),
                    )

                    if progress:
                        continue

                    # 7. If no stage made progress, block until either prepare,
                    # GPU, or DDAR work completes. The next loop iteration then
                    # consumes whatever became ready through the normal poll
                    # path at the top of the loop.
                    self._wait_for_next_event(
                        dispatcher=dispatcher,
                        running_futures=running_futures,
                        running_prepare_futures=running_prepare_futures,
                        profiling=profiling,
                    )
                    continue

                finalize_start = time.perf_counter()
                beam_queue = self.finalize_next_queue(
                    next_queue=next_queue,
                    profiling=profiling,
                )
                add_profiling_time(
                    profiling,
                    "next_frontier_finalize_wall_time_s",
                    time.perf_counter() - finalize_start,
                )
                self._trace_scheduler_state(
                    depth=depth,
                    dispatcher=dispatcher,
                    running_prepare_futures=running_prepare_futures,
                    prepared_requests=prepared_requests,
                    pending_ddar_submit=pending_ddar_submit,
                    running_futures=running_futures,
                    frontier_exhausted=True,
                    force=True,
                )
                next_frontier_size = len(list(beam_queue))
                self._trace(
                    "depth_end", depth=depth, next_frontier_size=next_frontier_size
                )
                logger.info(
                    "Search depth end: depth=%d next_frontier_size=%d",
                    depth,
                    next_frontier_size,
                )

        logger.info("Agent run finished without solution")
        return self._build_info_payload(
            t0=t0,
            step=step,
            is_success=False,
            profiling=profiling,
            error_msg="Tried but failed.",
            runtime_s=time.perf_counter() - perf_t0,
        )
