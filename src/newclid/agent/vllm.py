from __future__ import annotations

import base64
from copy import deepcopy
from functools import lru_cache
import logging
from pathlib import Path
import time
from typing import TYPE_CHECKING, Any

import ray
import requests
from transformers import AutoTokenizer

from newclid.agent.base import BaseAgent
from newclid.agent.runtime.model_pool import WorkerHandleWrapper
from newclid.agent.runtime.search_runtime import (
    BeamQueue,
    build_problem_proof,
    get_new_point_name,
    problem_to_text_dsl,
    problem_to_visual_dsl,
    run_ddar_on_proof,
    translate_dsl_to_construction,
    try_dsl_to_constructions,
)
from newclid.agent.runtime.text_worker import (
    _accumulate_request_profile,
    _build_request_profile,
    _create_worker_batch_profile,
)
from newclid.formulations.problem import ProblemJGEX
from newclid.generation.writer import save_figure_as_png
from newclid.numerical.draw_clause_figure import draw_clause_figure
from newclid.proof import ProofState

if TYPE_CHECKING:
    from newclid.formulations.rule import Rule


logger = logging.getLogger(__name__)

SYSTEM_PROMPT = "You are a helpful assistant."
MAX_NEW_TOKENS = 100
LENGTH_PENALTY = 1.0
AUX_STOP = "</aux>"
AUX_CANDIDATE_STOP = " ;"
DEFAULT_VLLM_WORKERS = 16


@lru_cache(maxsize=8)
def _load_tokenizer(tokenizer_name: str):
    return AutoTokenizer.from_pretrained(tokenizer_name, trust_remote_code=True)


def discover_served_model(base_url: str) -> tuple[str, list[str | None]]:
    response = requests.get(f"{base_url.rstrip('/')}/v1/models", timeout=120.0)
    response.raise_for_status()
    server_models = [item.get("id") for item in response.json().get("data", [])]
    if not server_models or not server_models[0]:
        raise ValueError(f"No served models returned by {base_url}/v1/models.")
    return str(server_models[0]), server_models


def build_chat_messages(
    *, query: str, response_prefix: str, new_point_name: str
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": query},
        {
            "role": "assistant",
            "content": f"<think>\n\n</think>\n\n{response_prefix} {new_point_name}",
        },
    ]


def build_visual_messages(
    *,
    image_data_url: str,
    query: str,
    response_prefix: str,
    new_point_name: str,
) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_data_url}},
                {"type": "text", "text": query},
            ],
        },
        {
            "role": "assistant",
            "content": f"<think>\n\n</think>\n\n{response_prefix} {new_point_name}",
        },
    ]


def _sequence_score(token_logprobs: list[float | None]) -> float:
    total = sum(float(lp) for lp in token_logprobs if lp is not None)
    length = max(sum(lp is not None for lp in token_logprobs), 1)
    return total / (length**LENGTH_PENALTY)


def _score_chat_choices(
    *,
    choices: list[dict[str, Any]],
    request: dict[str, Any],
    stop_token_ids: list[int],
) -> tuple[dict[str, float], list[int]]:
    response_prefix = str(request.get("response_prefix", "<aux> x00"))
    new_point_name = str(request["new_point_name"])
    stop_set = {int(token_id) for token_id in stop_token_ids}
    aux_dsl_dict: dict[str, float] = {}
    generated_token_counts: list[int] = []
    for choice in choices:
        message = choice.get("message") or {}
        text = str(message.get("content", "")) if isinstance(message, dict) else ""
        idx_stop = text.find(AUX_STOP)
        continuation = (text[:idx_stop] if idx_stop >= 0 else text).rstrip()
        token_ids = [int(token_id) for token_id in choice.get("token_ids", [])]
        raw_content_logprobs = (choice.get("logprobs") or {}).get("content", [])
        token_logprobs = [
            item.get("logprob") if isinstance(item, dict) else item
            for item in raw_content_logprobs
        ]
        limit = next(
            (index for index, token_id in enumerate(token_ids) if token_id in stop_set),
            min(len(token_ids), len(token_logprobs)),
        )
        trimmed_logprobs = token_logprobs[:limit]
        generated_token_counts.append(limit)
        aux_dsl = f"{response_prefix} {new_point_name}{continuation}"
        score = _sequence_score(trimmed_logprobs)
        if aux_dsl not in aux_dsl_dict or score > aux_dsl_dict[aux_dsl]:
            aux_dsl_dict[aux_dsl] = score
    return aux_dsl_dict, generated_token_counts


def create_vllm_workers(
    *,
    base_url: str,
    served_model_name: str,
    worker_count: int = DEFAULT_VLLM_WORKERS,
) -> list[WorkerHandleWrapper]:
    if worker_count <= 0:
        raise ValueError(f"worker_count must be positive, got {worker_count}.")
    return [
        WorkerHandleWrapper(
            VLLMWorker.remote(
                base_url=base_url,
                served_model_name=served_model_name,
                worker_slot=worker_slot,
            ),
            worker_trace_id=f"vllm:{worker_slot}",
            worker_device="http",
        )
        for worker_slot in range(worker_count)
    ]


class _BaseQwen3Agent(BaseAgent):
    def __init__(
        self,
        model_pool,
        decoding_size: int,
        beam_size: int,
        search_depth: int,
        *,
        search_version: str = "v1",
        max_pending_ddar: int = 1,
        trace_writer=None,
    ):
        if search_version not in {"v1", "v2", "hybrid"}:
            raise ValueError(f"Unsupported search_version: {search_version}")
        super().__init__(
            model_pool=model_pool,
            decoding_size=decoding_size,
            beam_size=beam_size,
            search_depth=search_depth,
            gpu_batch_size=1,
            gpu_batch_timeout_ms=0,
            agent_type=self.agent_name,
            max_pending_ddar=max_pending_ddar,
            prepare_request_workers=1,
            prepare_prefetch_limit=max(1, 2 * beam_size),
            ddar_returns_proof=False,
            trace_writer=trace_writer,
        )
        self.search_version = search_version
        self._active_search_mode = "v1"

    @property
    def agent_name(self) -> str:
        raise NotImplementedError

    def run(
        self, proof: ProofState, rules: list["Rule"], timeout: int = 3600
    ) -> dict[str, Any]:
        if self.search_version != "hybrid":
            self._active_search_mode = self.search_version
            self._trace("search_mode", mode=self._active_search_mode)
            return super().run(proof, rules, timeout)

        started_at = time.time()
        self._active_search_mode = "v1"
        self._trace("search_mode", mode="v1")
        first_result = super().run(proof, rules, timeout)
        if first_result.get("success") or first_result.get("error") == "Timeout":
            return first_result

        remaining_timeout = max(0, timeout - int(time.time() - started_at))
        if remaining_timeout <= 0:
            first_result["error"] = "Timeout"
            return first_result

        self._active_search_mode = "v2"
        self._trace("search_mode", mode="v2")
        return super().run(proof, rules, remaining_timeout)

    def _response_prefix(self, aux_prefix: str) -> str:
        if self._active_search_mode != "v2":
            return "<aux> x00"
        separator = " ;" if aux_prefix.strip() else ""
        return f"<aux>{aux_prefix}{separator} x00"

    def get_problem_from_state(self, state: Any) -> ProblemJGEX:
        if self._active_search_mode == "v2":
            return state[0]
        return state

    def make_next_state_from_unsolved_ddar(
        self,
        *,
        new_problem: ProblemJGEX,
        prior_state: Any,
        ddar_result: dict[str, object],
        proof: ProofState,
        request: dict[str, Any],
        aux_dsl: str,
        raw_aux_text: str,
    ) -> Any:
        del ddar_result, proof, request, raw_aux_text
        if self._active_search_mode == "v2":
            return new_problem, aux_dsl[len("<aux>") :]
        del prior_state, aux_dsl
        return new_problem

    def get_new_point_name(self, problem: ProblemJGEX) -> str:
        return get_new_point_name(problem)

    def try_dsl_to_constructions(self, content: str):
        return try_dsl_to_constructions(content)

    def translate_dsl_to_construction(
        self, point: str, predicate: str, args: list[str]
    ):
        return translate_dsl_to_construction(point, predicate, args)

    def run_ddar_c(
        self,
        proof: ProofState,
        rules: list["Rule"],
        start_time: float,
        timeout: int = 3600,
    ) -> bool:
        del rules, start_time, timeout
        return run_ddar_on_proof(proof)


class Qwen3Agent(_BaseQwen3Agent):
    agent_name = "qwen3_text"

    def __init__(self, model_pool, decoding_size: int, beam_size: int, search_depth: int, *, search_version: str = "v1", max_pending_ddar: int = 1, trace_writer=None):
        super().__init__(
            model_pool,
            decoding_size,
            beam_size,
            search_depth,
            search_version=search_version,
            max_pending_ddar=max_pending_ddar,
            trace_writer=trace_writer,
        )
        self._root_problem_dsl: str | None = None

    def seed_state(self, proof: ProofState, base_proof: ProofState) -> Any:
        del proof
        self._root_problem_dsl = self.problem_to_dsl(self.problemJGEX, base_proof.defs)
        if self._active_search_mode == "v2":
            return self.problemJGEX, ""
        return self.problemJGEX

    def prepare_request(
        self, *, request_id: str, state: Any, proof: ProofState, depth: int
    ) -> dict[str, Any]:
        del depth
        if self._active_search_mode == "v2":
            problem, aux_prefix = state
            query = self._root_problem_dsl
            response_prefix = self._response_prefix(aux_prefix)
        else:
            problem = state
            query = self.problem_to_dsl(problem, proof.defs)
            response_prefix = self._response_prefix("")
        if query is None:
            raise ValueError("Root text DSL is unavailable during request preparation.")
        return {
            "request_id": request_id,
            "runtime_kind": "vllm",
            "search_mode": self._active_search_mode,
            "messages": build_chat_messages(
                query=query,
                response_prefix=response_prefix,
                new_point_name=self.get_new_point_name(problem),
            ),
            "query": query,
            "new_point_name": self.get_new_point_name(problem),
            "response_prefix": response_prefix,
            "with_predicate": False,
            "decoding_size": self.decoding_size,
        }

    def problem_to_dsl(self, problem: ProblemJGEX, defs) -> str:
        return problem_to_text_dsl(problem, defs)


class Qwen3VLAgent(_BaseQwen3Agent):
    agent_name = "qwen3_vl"

    def __init__(
        self,
        model_pool,
        decoding_size: int,
        beam_size: int,
        search_depth: int,
        *,
        search_version: str = "v1",
        render_root: str | Path = "temp/eval_rendered_images",
        max_pending_ddar: int = 1,
        trace_writer=None,
    ):
        super().__init__(
            model_pool,
            decoding_size,
            beam_size,
            search_depth,
            search_version=search_version,
            max_pending_ddar=max_pending_ddar,
            trace_writer=trace_writer,
        )
        self.render_root = Path(render_root)
        self.render_root.mkdir(parents=True, exist_ok=True)
        self._proof_defs: dict[str, Any] | None = None
        self._root_problem_dsl: str | None = None

    def base_ddar_proof(self, proof: ProofState) -> ProofState:
        return deepcopy(proof)

    def seed_state(self, proof: ProofState, base_proof: ProofState) -> Any:
        del proof
        self._proof_defs = base_proof.defs
        self._root_problem_dsl = self.problem_to_dsl(self.problemJGEX, base_proof.defs)
        if self._active_search_mode == "v2":
            return self.problemJGEX, base_proof, ""
        return self.problemJGEX, base_proof

    def prepare_request(
        self, *, request_id: str, state: Any, proof: ProofState, depth: int
    ) -> dict[str, Any]:
        del proof
        if self._active_search_mode == "v2":
            problem, current_proof, aux_prefix = state
            query = self._root_problem_dsl
            response_prefix = self._response_prefix(aux_prefix)
        else:
            problem, current_proof = state
            query = self.problem_to_dsl(problem, current_proof.defs)
            response_prefix = self._response_prefix("")
        if current_proof is None:
            raise ValueError("Visual frontier state is missing a materialized proof.")
        if query is None:
            raise ValueError("Root visual DSL is unavailable during request preparation.")
        png_path = self.render_root / f"d{depth}_{request_id}.png"
        fig = draw_clause_figure(
            current_proof,
            problem,
            None,
            current_proof.rng,
            draw_annotations=True,
            theme=None,
        )
        save_figure_as_png(
            fig,
            png_path=str(png_path),
            img_pixels=512,
            direct_png=True,
        )
        data_url = "data:image/png;base64," + base64.b64encode(
            png_path.read_bytes()
        ).decode("ascii")
        return {
            "request_id": request_id,
            "runtime_kind": "vllm",
            "search_mode": self._active_search_mode,
            "messages": build_visual_messages(
                image_data_url=data_url,
                query=query,
                response_prefix=response_prefix,
                new_point_name=self.get_new_point_name(problem),
            ),
            "query": query,
            "image_data_url": data_url,
            "new_point_name": self.get_new_point_name(problem),
            "response_prefix": response_prefix,
            "with_predicate": False,
            "decoding_size": self.decoding_size,
        }

    def finalize_next_queue(
        self, *, next_queue: BeamQueue, profiling: dict[str, Any]
    ) -> BeamQueue:
        del profiling
        if self._proof_defs is None:
            raise ValueError("Visual agent definitions are unavailable.")
        materialized_queue = BeamQueue(max_size=next_queue.max_size)
        for val, stable_key, _, node in next_queue.iter_entries():
            node_id, parent_node_id, path_key, state = node
            if self._active_search_mode == "v2":
                problem, current_proof, aux_prefix = state
            else:
                problem, current_proof = state
                aux_prefix = None
            if current_proof is None:
                current_proof = build_problem_proof(problem, self._proof_defs)
            next_state = (
                (problem, current_proof, aux_prefix)
                if self._active_search_mode == "v2"
                else (problem, current_proof)
            )
            materialized_queue.add(
                node=(node_id, parent_node_id, path_key, next_state),
                val=val,
                stable_key=stable_key,
            )
        return materialized_queue

    def problem_to_dsl(self, problem: ProblemJGEX, defs) -> str:
        return problem_to_visual_dsl(problem, defs)


@ray.remote(num_cpus=0, max_concurrency=1)
class VLLMWorker:
    def __init__(
        self,
        *,
        base_url: str,
        served_model_name: str,
        worker_slot: int = 0,
    ):
        self.base_url = base_url.rstrip("/")
        self.served_model_name = served_model_name
        self.worker_slot = int(worker_slot)
        self.worker_id = f"vllm:{self.worker_slot}"
        self.device_label = "http"
        self.tokenizer = _load_tokenizer(self.served_model_name)
        self.stop_token_ids = self.tokenizer.encode(
            AUX_CANDIDATE_STOP, add_special_tokens=False
        )
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=1, pool_maxsize=1)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.num_requests = 0
        self.num_batches = 0

    def warmup(self) -> dict[str, Any]:
        return {
            "served_model_name": self.served_model_name,
            "worker_id": self.worker_id,
            "device": self.device_label,
            "runtime": "vllm",
        }

    def stats(self) -> dict[str, Any]:
        return {
            "served_model_name": self.served_model_name,
            "worker_id": self.worker_id,
            "device": self.device_label,
            "num_requests": self.num_requests,
            "num_batches": self.num_batches,
            "avg_batch_size": (self.num_requests / self.num_batches)
            if self.num_batches
            else 0.0,
            "runtime": "vllm",
        }

    def generate_batch(self, requests_batch: list[dict[str, Any]]) -> dict[str, Any]:
        perf_start = time.perf_counter()
        started_at_unix_s = time.time()
        worker_batch_profile = _create_worker_batch_profile(batch_size=len(requests_batch))
        worker_batch_profile["runtime"] = "vllm"
        results: list[dict[str, Any]] = []
        for request in requests_batch:
            request_start = time.perf_counter()
            payload = {
                "model": self.served_model_name,
                "messages": request["messages"],
                "continue_final_message": True,
                "add_generation_prompt": False,
                "max_tokens": MAX_NEW_TOKENS,
                "n": int(request["decoding_size"]),
                "temperature": 1.0,
                "top_p": 1.0,
                "top_k": -1,
                "min_p": 0.0,
                "repetition_penalty": 1.0,
                "logprobs": True,
                "top_logprobs": 1,
                "return_token_ids": True,
                "stream": False,
                "include_stop_str_in_output": False,
                "stop": [AUX_CANDIDATE_STOP],
                "stop_token_ids": self.stop_token_ids,
            }
            worker_batch_profile["input_build_time_s"] += time.perf_counter() - request_start
            response = self.session.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                timeout=120.0,
            )
            response.raise_for_status()
            generate_done = time.perf_counter()
            worker_batch_profile["generate_time_s"] += generate_done - request_start
            choices = list(response.json().get("choices", []))
            if len(choices) != int(request["decoding_size"]):
                raise ValueError(
                    f"Expected {request['decoding_size']} choices, got {len(choices)}."
                )
            aux_dsl_dict, generated_token_counts = _score_chat_choices(
                choices=choices,
                request=request,
                stop_token_ids=self.stop_token_ids,
            )
            decode_done = time.perf_counter()
            worker_batch_profile["decode_time_s"] += decode_done - generate_done
            usage = response.json().get("usage") or {}
            request_profile = _build_request_profile(
                prompt_token_count=int(usage.get("prompt_tokens", 0)),
                generated_token_counts=generated_token_counts,
                raw_candidate_count=len(choices),
                unique_candidate_count=len(aux_dsl_dict),
            )
            _accumulate_request_profile(worker_batch_profile, request_profile)
            results.append(
                {
                    "request_id": request["request_id"],
                    "aux_dsl_dict": aux_dsl_dict,
                    "request_profile": request_profile,
                }
            )

        finished_at_unix_s = time.time()
        worker_batch_profile["worker_inference_time_s"] = time.perf_counter() - perf_start
        worker_batch_profile["gpu_worker_id"] = self.worker_id
        worker_batch_profile["gpu_device"] = self.device_label
        worker_batch_profile["worker_started_at_unix_s"] = started_at_unix_s
        worker_batch_profile["worker_finished_at_unix_s"] = finished_at_unix_s
        self.num_requests += len(requests_batch)
        self.num_batches += 1
        return {
            "results": results,
            "worker_batch_profile": worker_batch_profile,
        }
