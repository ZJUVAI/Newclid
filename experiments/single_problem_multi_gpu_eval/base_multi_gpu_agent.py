from __future__ import annotations

from collections import deque
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait as futures_wait
import logging
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
)
from newclid.proof import ProofState
from newclid.search_trace import build_attempt_key, proof_to_ddar_input

from experiments.single_problem_multi_gpu_eval.search_common import BeamQueue, run_ddar_c, run_ddar_remote

if TYPE_CHECKING:
    from newclid.formulations.rule import Rule


logger = logging.getLogger(__name__)


class BaseMultiGPUAgent(DeductiveAgent, ABC):
    def __init__(
        self,
        model_pool,
        decoding_size: int,
        beam_size: int,
        search_depth: int,
        *,
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
        self.agent_type = agent_type
        self.max_pending_ddar = max_pending_ddar
        self.prepare_request_workers = prepare_request_workers
        self.prepare_prefetch_limit = prepare_prefetch_limit
        self.ddar_returns_proof = ddar_returns_proof
        self.trace_writer = trace_writer

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
    ) -> Any | None:
        raise NotImplementedError

    @abstractmethod
    def try_dsl_to_constructions(self, content: str):
        raise NotImplementedError

    def base_ddar_proof(self, proof: ProofState) -> ProofState:
        return proof

    def run_ddar_c(self, proof: ProofState, rules: list["Rule"], start_time: float, timeout: int = 3600) -> bool:
        return run_ddar_c(proof, rules, start_time, timeout)

    def extract_raw_aux_text(self, aux_dsl: str) -> str:
        return aux_dsl[len("<aux> x00"):]

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
            ddar_result = ray.get(future)
            future_meta = future_info.pop(future)

            if ddar_result["status"] == "invalid":
                self._trace(
                    "ddar_result",
                    attempt_key=future_meta["attempt_key"],
                    node_id=future_meta["node_id"],
                    parent_node_id=future_meta["parent_node_id"],
                    depth=depth,
                    status=ddar_result["status"],
                    elapsed_time=ddar_result.get("elapsed_time"),
                    error_type=ddar_result.get("error_type"),
                    error_message=ddar_result.get("error_message"),
                    problem_text=ddar_result.get("problem_text"),
                    ddar_input=ddar_result.get("ddar_input"),
                )
                continue

            if ddar_result["status"] == "solved":
                self._cancel_ddar_futures(running_futures, future_info)
                self._trace(
                    "ddar_result",
                    attempt_key=future_meta["attempt_key"],
                    node_id=future_meta["node_id"],
                    parent_node_id=future_meta["parent_node_id"],
                    depth=depth,
                    status=ddar_result["status"],
                    elapsed_time=ddar_result.get("elapsed_time"),
                    error_type=ddar_result.get("error_type"),
                    error_message=ddar_result.get("error_message"),
                    problem_text=ddar_result.get("problem_text"),
                    ddar_input=ddar_result.get("ddar_input"),
                )
                handle_elapsed_s = time.perf_counter() - handle_start
                add_profiling_time(profiling, "ddar_result_handle_wall_time_s", handle_elapsed_s)
                return self._build_info_payload(
                    t0=t0,
                    step=step,
                    is_success=True,
                    profiling=profiling,
                    error_msg=str(future_meta["problem"]),
                    final_node_id=future_meta["node_id"],
                    runtime_s=runtime_s,
                )

            self._trace(
                "ddar_result",
                attempt_key=future_meta["attempt_key"],
                node_id=future_meta["node_id"],
                parent_node_id=future_meta["parent_node_id"],
                depth=depth,
                status=ddar_result["status"],
                elapsed_time=ddar_result.get("elapsed_time"),
                error_type=ddar_result.get("error_type"),
                error_message=ddar_result.get("error_message"),
                problem_text=ddar_result.get("problem_text"),
                ddar_input=ddar_result.get("ddar_input"),
            )
            if depth < self.search_depth - 1:
                next_state = self.make_next_state_from_unsolved_ddar(
                    new_problem=future_meta["problem"],
                    prior_state=future_meta["state"],
                    ddar_result=ddar_result,
                    proof=proof,
                )
                if next_state is not None:
                    child_score = future_meta["prev_score"] + future_meta["score"]
                    next_queue.add(
                        node=(future_meta["node_id"], future_meta["parent_node_id"], next_state),
                        val=child_score,
                    )
                    self._trace(
                        "candidate_transition",
                        attempt_key=future_meta["attempt_key"],
                        request_id=future_meta["request_id"],
                        parent_node_id=future_meta["parent_node_id"],
                        node_id=future_meta["node_id"],
                        candidate_rank=future_meta["candidate_rank"],
                        depth=depth,
                        raw_aux_text=future_meta["raw_aux_text"],
                        translated_aux=future_meta["translated_aux"],
                        new_problem_text=str(future_meta["problem"]),
                        decision="queued_next_depth",
                        beam_score_before=future_meta["prev_score"],
                        beam_score_after=child_score,
                    )
        handle_elapsed_s = time.perf_counter() - handle_start
        add_profiling_time(profiling, "ddar_result_handle_wall_time_s", handle_elapsed_s)
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

    def _cancel_ddar_futures(self, running_futures: list[Any], future_info: dict[Any, dict[str, Any]]) -> None:
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
        return self.prepare_request(
            request_id=request_id,
            state=state,
            proof=proof,
            depth=depth,
        )

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

        node_id, parent_node_id, state = node
        request_id = f"d{depth}_n{request_index}"
        request_meta[request_id] = {
            "state": state,
            "prev_score": prev_score,
            "node_id": node_id,
            "parent_node_id": parent_node_id,
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
            "depth": depth,
        }
        return request_index + 1

    def _poll_prepare_futures(
        self,
        *,
        running_prepare_futures: dict[Future[dict[str, Any]], dict[str, Any]],
        request_meta: dict[str, dict[str, Any]],
        prepared_requests: deque[dict[str, Any]],
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
                request = future.result()
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
            request["depth"] = future_meta["depth"]
            request_state["request_built_at_perf_s"] = time.perf_counter()
            prepared_requests.append(request)
            self._trace(
                "model_request",
                node_id=future_meta["node_id"],
                parent_node_id=future_meta["parent_node_id"],
                depth=future_meta["depth"],
                request_id=request_id,
                query=request.get("query"),
                img_path=request.get("img_path"),
                new_point_name=request.get("new_point_name"),
                response_prefix=request.get("response_prefix"),
                with_predicate=request.get("with_predicate"),
                decoding_size=request.get("decoding_size"),
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
            add_profiling_time(profiling, "request_prepare_wall_time_s", time.perf_counter() - wait_start)
            return

        if running_prepare_futures:
            done_futures, _ = futures_wait(
                tuple(running_prepare_futures.keys()),
                timeout=0.1,
                return_when=FIRST_COMPLETED,
            )
            if done_futures:
                add_profiling_time(profiling, "wait_wall_time_s", time.perf_counter() - wait_start)
                return

        remaining_timeout_s = max(0.0, 1.0 - (time.perf_counter() - wait_start))
        if not wait_refs:
            return
        ray.wait(wait_refs, num_returns=1, timeout=remaining_timeout_s)
        add_profiling_time(profiling, "wait_wall_time_s", time.perf_counter() - wait_start)
        return

    def _handle_gpu_result(
        self,
        *,
        gpu_result: dict[str, Any],
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
        request_id = gpu_result["request_id"]
        request_state = request_meta.pop(request_id)
        state = request_state["state"]
        prev_score = request_state["prev_score"]
        parent_node_id = request_state["node_id"]
        problem = self.get_problem_from_state(state)
        outputs = [
            {
                "rank": rank,
                "aux_dsl": aux_dsl,
                "score": score,
            }
            for rank, (aux_dsl, score) in enumerate(gpu_result["aux_dsl_dict"].items())
        ]
        self._trace(
            "model_response",
            request_id=request_id,
            node_id=parent_node_id,
            depth=depth,
            outputs=outputs,
        )
        logger.debug(
            "Search depth=%d request=%s candidate_count=%d",
            depth,
            request_id,
            len(gpu_result["aux_dsl_dict"]),
        )

        for candidate_rank, (aux_dsl, score) in enumerate(gpu_result["aux_dsl_dict"].items()):
            try:
                raw_aux_text = self.extract_raw_aux_text(aux_dsl)
                aux = self.try_dsl_to_constructions(raw_aux_text)
            except Exception:
                self._trace(
                    "candidate_transition",
                    attempt_key=build_attempt_key(request_id, candidate_rank, None),
                    request_id=request_id,
                    parent_node_id=parent_node_id,
                    node_id=None,
                    candidate_rank=candidate_rank,
                    depth=depth,
                    raw_aux_text=self.extract_raw_aux_text(aux_dsl),
                    translated_aux=None,
                    new_problem_text=None,
                    decision="parse_failed",
                    beam_score_before=prev_score,
                    beam_score_after=None,
                )
                continue

            if not aux:
                self._trace(
                    "candidate_transition",
                    attempt_key=build_attempt_key(request_id, candidate_rank, None),
                    request_id=request_id,
                    parent_node_id=parent_node_id,
                    node_id=None,
                    candidate_rank=candidate_rank,
                    depth=depth,
                    raw_aux_text=raw_aux_text,
                    translated_aux=None,
                    new_problem_text=None,
                    decision="parse_failed",
                    beam_score_before=prev_score,
                    beam_score_after=None,
                )
                continue

            try:
                new_problem = problem.with_more_construction(aux)
            except Exception:
                self._trace(
                    "candidate_transition",
                    attempt_key=build_attempt_key(request_id, candidate_rank, None),
                    request_id=request_id,
                    parent_node_id=parent_node_id,
                    node_id=None,
                    candidate_rank=candidate_rank,
                    depth=depth,
                    raw_aux_text=raw_aux_text,
                    translated_aux=aux,
                    new_problem_text=None,
                    decision="build_failed",
                    beam_score_before=prev_score,
                    beam_score_after=None,
                )
                continue

            child_node_id = next_node_id
            next_node_id += 1
            pending_ddar_submit.append(
                {
                    "problem": new_problem,
                    "state": state,
                    "prev_score": prev_score,
                    "score": score,
                    "node_id": child_node_id,
                    "parent_node_id": parent_node_id,
                    "request_id": request_id,
                    "candidate_rank": candidate_rank,
                    "attempt_key": build_attempt_key(request_id, candidate_rank, child_node_id),
                    "raw_aux_text": raw_aux_text,
                    "translated_aux": aux,
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
            self._trace(
                "candidate_transition",
                attempt_key=candidate_meta["attempt_key"],
                request_id=candidate_meta["request_id"],
                parent_node_id=candidate_meta["parent_node_id"],
                node_id=candidate_meta["node_id"],
                candidate_rank=candidate_meta["candidate_rank"],
                depth=depth,
                raw_aux_text=candidate_meta["raw_aux_text"],
                translated_aux=candidate_meta["translated_aux"],
                new_problem_text=str(candidate_meta["problem"]),
                decision="ddar_submitted",
                beam_score_before=candidate_meta["prev_score"],
                beam_score_after=candidate_meta["prev_score"] + candidate_meta["score"],
            )
            self._trace(
                "ddar_submit",
                attempt_key=candidate_meta["attempt_key"],
                node_id=candidate_meta["node_id"],
                parent_node_id=candidate_meta["parent_node_id"],
                depth=depth,
                problem_text=str(candidate_meta["problem"]),
                ddar_input=None,
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
        submit_elapsed_s = time.perf_counter() - submit_start
        add_profiling_time(profiling, "ddar_submit_wall_time_s", submit_elapsed_s)

    def run(self, proof: ProofState, rules: list["Rule"], timeout: int = 3600) -> dict[str, Any]:
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

        for goal in proof.goals:
            if not goal.check_numerical():
                logger.warning("Agent run abort: goal failed numerical check: %s", goal.pretty())
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
            problem_text=str(self.problemJGEX),
            ddar_input=proof_to_ddar_input(base_proof),
        )
        ddar_start = time.perf_counter()
        base_solved = self.run_ddar_c(base_proof, rules, t0, timeout)
        add_profiling_time(profiling, "base_ddar_wall_time_s", time.perf_counter() - ddar_start)
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
                problem_text=str(self.problemJGEX),
                ddar_input=proof_to_ddar_input(base_proof),
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
            problem_text=str(self.problemJGEX),
            ddar_input=proof_to_ddar_input(base_proof),
        )
        logger.debug("Agent base DDAR unsolved; entering search")

        rules_ref = ray.put(rules)
        beam_queue = BeamQueue(max_size=self.beam_size)
        beam_queue.add(node=(0, None, self.seed_state(proof, base_proof)), val=0.0)

        with ThreadPoolExecutor(max_workers=self.prepare_request_workers) as prepare_executor:
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

                dispatcher = self.model_pool.create_dispatcher()
                next_queue = BeamQueue(max_size=self.beam_size)
                frontier_iter = iter(beam_queue)
                prepared_requests: deque[dict[str, Any]] = deque()
                running_prepare_futures: dict[Future[dict[str, Any]], dict[str, Any]] = {}
                pending_ddar_submit = deque()
                request_meta: dict[str, dict[str, Any]] = {}
                running_futures: list[Any] = []
                future_info: dict[Any, dict[str, Any]] = {}
                request_index = 0
                frontier_exhausted = False
                ddar_backlog_high_watermark = max(self.max_pending_ddar + 1, 2 * self.max_pending_ddar)

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
                            gpu_result = dispatcher.take_done(done_ref)
                            next_node_id = self._handle_gpu_result(
                                gpu_result=gpu_result,
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
                        and (len(pending_ddar_submit) + len(running_futures)) <= ddar_backlog_high_watermark
                    ):
                        request = prepared_requests.popleft()
                        request_meta[request["request_id"]]["gpu_submitted_at_perf_s"] = time.perf_counter()
                        dispatcher.enqueue_request(request)
                        progress = True

                    # 6. Launch more prepare work on demand instead of building
                    # the whole depth eagerly. This keeps CPU work bounded by
                    # the amount of GPU/DDAR capacity we can actually use.
                    while (
                        not frontier_exhausted
                        and (len(running_prepare_futures) + len(prepared_requests)) < self.prepare_prefetch_limit
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

                beam_queue = next_queue
                next_frontier_size = len(list(beam_queue))
                self._trace("depth_end", depth=depth, next_frontier_size=next_frontier_size)
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
