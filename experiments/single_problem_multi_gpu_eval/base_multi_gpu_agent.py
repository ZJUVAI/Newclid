from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

import ray

from newclid.agent.agents_interface import DeductiveAgent
from newclid.formulations.problem import ProblemJGEX
from newclid.profiling import add_profiling_time, create_profiling_payload, finalize_profiling
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
    def build_request(
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
        profiling: dict[str, float],
        error_msg: str | None = None,
        final_node_id: int | None = None,
    ):
        infos: dict[str, Any] = {}
        runtime = time.time() - t0
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
        profiling: dict[str, float],
        proof: ProofState,
    ):
        for future in done_futures:
            ddar_result = ray.get(future)
            future_meta = future_info.pop(future)
            add_profiling_time(profiling, "build_time_s", ddar_result.get("build_time_s"))
            add_profiling_time(profiling, "ddar_time_s", ddar_result.get("ddar_time_s"))

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
                return self._build_info_payload(
                    t0=t0,
                    step=step,
                    is_success=True,
                    profiling=profiling,
                    error_msg=str(future_meta["problem"]),
                    final_node_id=future_meta["node_id"],
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
        profiling: dict[str, float],
        proof: ProofState,
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
        )

    def _drain_ddar_futures(
        self,
        *,
        running_futures: list[Any],
        future_info: dict[Any, dict[str, Any]],
        next_queue: BeamQueue,
        depth: int,
        t0: float,
        step: int,
        profiling: dict[str, float],
        proof: ProofState,
    ):
        solved_payload = None
        while running_futures:
            done, remaining = ray.wait(
                running_futures,
                num_returns=min(32, len(running_futures)),
                timeout=1,
            )
            running_futures[:] = remaining
            solved_payload = self._handle_ddar_done(
                done_futures=done,
                running_futures=running_futures,
                future_info=future_info,
                next_queue=next_queue,
                depth=depth,
                t0=t0,
                step=step,
                profiling=profiling,
                proof=proof,
            )
            if solved_payload is not None:
                return solved_payload
        return solved_payload

    def _cancel_ddar_futures(self, running_futures: list[Any], future_info: dict[Any, dict[str, Any]]) -> None:
        for future in running_futures:
            try:
                ray.cancel(future, force=True)
            except Exception:
                pass
        running_futures.clear()
        future_info.clear()

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
        ddar_start = time.time()
        base_solved = self.run_ddar_c(base_proof, rules, t0, timeout)
        add_profiling_time(profiling, "ddar_time_s", time.time() - ddar_start)
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
                )

            requests: list[dict[str, Any]] = []
            request_meta: dict[str, dict[str, Any]] = {}
            for idx, (prev_score, node) in enumerate(beam_queue):
                node_id, parent_node_id, state = node
                request_id = f"d{depth}_n{idx}"
                request = self.build_request(
                    request_id=request_id,
                    state=state,
                    proof=proof,
                    depth=depth,
                )
                request["depth"] = depth
                requests.append(request)
                request_meta[request_id] = {
                    "state": state,
                    "prev_score": prev_score,
                    "node_id": node_id,
                    "parent_node_id": parent_node_id,
                }
                self._trace(
                    "model_request",
                    node_id=node_id,
                    parent_node_id=parent_node_id,
                    depth=depth,
                    request_id=request_id,
                    query=request.get("query"),
                    img_path=request.get("img_path"),
                    new_point_name=request.get("new_point_name"),
                    response_prefix=request.get("response_prefix"),
                    with_predicate=request.get("with_predicate"),
                    decoding_size=request.get("decoding_size"),
                )

            if not requests:
                logger.info("Search depth=%d produced no requests; stopping", depth)
                break

            logger.debug(
                "Search depth=%d built requests=%d request_ids=%s",
                depth,
                len(requests),
                [request["request_id"] for request in requests],
            )

            dispatcher = self.model_pool.create_dispatcher(
                requests=requests,
                batch_size=1,
            )
            next_queue = BeamQueue(max_size=self.beam_size)
            running_futures: list[Any] = []
            future_info: dict[Any, dict[str, Any]] = {}

            while dispatcher.has_pending() or running_futures:
                wait_refs = dispatcher.active_refs() + running_futures
                if not wait_refs:
                    break
                done_refs, _ = ray.wait(wait_refs, num_returns=1)
                done_ref = done_refs[0]

                if dispatcher.owns_ref(done_ref):
                    logger.debug(
                        "Search depth=%d received GPU batch result; running_ddar=%d",
                        depth,
                        len(running_futures),
                    )
                    gpu_results = dispatcher.take_done(done_ref)
                    logger.debug(
                        "Search depth=%d GPU batch decoded request_count=%d",
                        depth,
                        len(gpu_results),
                    )
                    for gpu_result in gpu_results:
                        add_profiling_time(
                            profiling,
                            "inference_time_s",
                            gpu_result.get("inference_time_s"),
                        )
                        request_id = gpu_result["request_id"]
                        request_state = request_meta[request_id]
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

                            while len(running_futures) >= self.max_pending_ddar:
                                done, remaining = ray.wait(running_futures, num_returns=1, timeout=1)
                                running_futures[:] = remaining
                                solved_payload = self._handle_ddar_done(
                                    done_futures=done,
                                    running_futures=running_futures,
                                    future_info=future_info,
                                    next_queue=next_queue,
                                    depth=depth,
                                    t0=t0,
                                    step=step,
                                    profiling=profiling,
                                    proof=proof,
                                )
                                if solved_payload is not None:
                                    dispatcher.cancel_running()
                                    return solved_payload

                            child_node_id = next_node_id
                            next_node_id += 1
                            attempt_key = build_attempt_key(request_id, candidate_rank, child_node_id)
                            self._trace(
                                "candidate_transition",
                                attempt_key=attempt_key,
                                request_id=request_id,
                                parent_node_id=parent_node_id,
                                node_id=child_node_id,
                                candidate_rank=candidate_rank,
                                depth=depth,
                                raw_aux_text=raw_aux_text,
                                translated_aux=aux,
                                new_problem_text=str(new_problem),
                                decision="ddar_submitted",
                                beam_score_before=prev_score,
                                beam_score_after=prev_score + score,
                            )
                            self._trace(
                                "ddar_submit",
                                attempt_key=attempt_key,
                                node_id=child_node_id,
                                parent_node_id=parent_node_id,
                                depth=depth,
                                problem_text=str(new_problem),
                                ddar_input=None,
                            )
                            future = run_ddar_remote.remote(
                                new_problem,
                                proof.defs,
                                rules_ref,
                                t0,
                                timeout,
                                return_proof=self.ddar_returns_proof,
                            )
                            logger.debug(
                                "Search depth=%d request=%s queued DDAR future; pending_ddar=%d",
                                depth,
                                request_id,
                                len(running_futures) + 1,
                            )
                            future_info[future] = {
                                "problem": new_problem,
                                "state": state,
                                "prev_score": prev_score,
                                "score": score,
                                "node_id": child_node_id,
                                "parent_node_id": parent_node_id,
                                "request_id": request_id,
                                "candidate_rank": candidate_rank,
                                "attempt_key": attempt_key,
                                "raw_aux_text": raw_aux_text,
                                "translated_aux": aux,
                            }
                            running_futures.append(future)

                            solved_payload = self._poll_ddar_futures(
                                running_futures=running_futures,
                                future_info=future_info,
                                next_queue=next_queue,
                                depth=depth,
                                t0=t0,
                                step=step,
                                profiling=profiling,
                                proof=proof,
                            )
                            if solved_payload is not None:
                                dispatcher.cancel_running()
                                return solved_payload

                    solved_payload = self._poll_ddar_futures(
                        running_futures=running_futures,
                        future_info=future_info,
                        next_queue=next_queue,
                        depth=depth,
                        t0=t0,
                        step=step,
                        profiling=profiling,
                        proof=proof,
                    )
                    if solved_payload is not None:
                        dispatcher.cancel_running()
                        return solved_payload
                else:
                    logger.debug(
                        "Search depth=%d received standalone DDAR completion; running_ddar_before_remove=%d",
                        depth,
                        len(running_futures),
                    )
                    running_futures.remove(done_ref)
                    solved_payload = self._handle_ddar_done(
                        done_futures=[done_ref],
                        running_futures=running_futures,
                        future_info=future_info,
                        next_queue=next_queue,
                        depth=depth,
                        t0=t0,
                        step=step,
                        profiling=profiling,
                        proof=proof,
                    )
                    if solved_payload is not None:
                        dispatcher.cancel_running()
                        return solved_payload

            solved_payload = self._drain_ddar_futures(
                running_futures=running_futures,
                future_info=future_info,
                next_queue=next_queue,
                depth=depth,
                t0=t0,
                step=step,
                profiling=profiling,
                proof=proof,
            )
            if solved_payload is not None:
                return solved_payload

            beam_queue = next_queue
            self._trace("depth_end", depth=depth, next_frontier_size=len(list(beam_queue)))
            logger.info(
                "Search depth end: depth=%d next_frontier_size=%d",
                depth,
                len(list(beam_queue)),
            )

        logger.info("Agent run finished without solution")
        return self._build_info_payload(
            t0=t0,
            step=step,
            is_success=False,
            profiling=profiling,
            error_msg="Tried but failed.",
        )
