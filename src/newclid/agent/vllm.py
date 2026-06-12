from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from typing import Any

import ray
import requests
from transformers import AutoTokenizer

from newclid.agent.agents_interface import DeductiveAgent
from newclid.agent.runtime.search_runtime import (
    BeamQueue,
    get_new_point_name,
    problem_to_text_dsl,
    run_aux_ddar_remote,
    run_ddar_on_proof,
    try_dsl_to_constructions,
)
from newclid.proof import ProofState

SYSTEM_PROMPT = "You are a helpful assistant."
MAX_NEW_TOKENS = 100
LENGTH_PENALTY = 1.0
AUX_STOP = "</aux>"
AUX_CANDIDATE_STOP = " ;"
RESPONSE_PREFIX = "<aux> x00"
HTTP_WORKERS = 16


@lru_cache(maxsize=4)
def _load_tokenizer(tokenizer_name: str):
    return AutoTokenizer.from_pretrained(tokenizer_name, trust_remote_code=True)


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


def _sequence_score(token_logprobs: list[float | None]) -> float:
    total = sum(float(lp) for lp in token_logprobs if lp is not None)
    length = max(sum(lp is not None for lp in token_logprobs), 1)
    return total / (length**LENGTH_PENALTY)


def _rank(aux_dsl_scores: dict[str, float]) -> list[tuple[str, float]]:
    return sorted(aux_dsl_scores.items(), key=lambda item: item[1], reverse=True)


class VLLMLMAgent(DeductiveAgent):
    def __init__(
        self,
        *,
        base_url: str,
        decoding_size: int,
        beam_size: int,
        search_depth: int,
        served_model_name: str | None = None,
        search_version: str = "v1",
    ):
        self.problemJGEX = None
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=HTTP_WORKERS, pool_maxsize=HTTP_WORKERS
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.server_models: list[str | None] = []
        self.served_model_name = served_model_name or self._discover_model()
        self.tokenizer = _load_tokenizer(self.served_model_name)
        stop_ids = self.tokenizer.encode(AUX_CANDIDATE_STOP, add_special_tokens=False)
        if len(stop_ids) != 1:
            raise ValueError(
                f"Expected {AUX_CANDIDATE_STOP!r} to map to one token, got {stop_ids}."
            )
        self.stop_token_ids = stop_ids
        self.decoding_size = decoding_size
        self.beam_size = beam_size
        self.search_depth = search_depth
        self.search_version = search_version
        self._defs_ref: Any | None = None
        self._root_dsl: str | None = None
        self._max_pending = 1
        self._step = 0
        self._ddar_calls = 0
        self._ddar_wall = 0.0
        self._llm_calls = 0
        self._llm_wall = 0.0

    def step(self, proof: ProofState, rules) -> bool:
        del proof, rules
        return True

    def _discover_model(self) -> str:
        resp = self.session.get(f"{self.base_url}/v1/models", timeout=120.0)
        resp.raise_for_status()
        self.server_models = [item.get("id") for item in resp.json().get("data", [])]
        if not self.server_models or not self.server_models[0]:
            raise ValueError(f"No served models returned by {self.base_url}/v1/models.")
        return str(self.server_models[0])

    def server_info(self) -> dict[str, Any]:
        if not self.server_models:
            self.server_models = [self.served_model_name]
        return {
            "served_model_name": self.served_model_name,
            "server_models": self.server_models,
            "search_version": self.search_version,
        }

    def run(self, proof: ProofState, rules, timeout: int = 3600) -> dict[str, Any]:
        del rules
        t0 = time.time()
        deadline = t0 + timeout
        self._step = 0
        self._ddar_calls = 0
        self._ddar_wall = 0.0
        self._llm_calls = 0
        self._llm_wall = 0.0
        self._max_pending = max(1, 2 * int(ray.cluster_resources().get("CPU", 1)))

        if any(not g.check_numerical() for g in proof.goals):
            return self._infos(t0, False, "goal fails numerical check")
        if run_ddar_on_proof(proof):
            return self._infos(t0, True)

        self._defs_ref = ray.put(proof.defs)
        self._root_dsl = problem_to_text_dsl(self.problemJGEX, proof.defs)
        modes = ("v1", "v2") if self.search_version == "hybrid" else (self.search_version,)
        error = "Tried but failed."
        for mode in modes:
            if time.time() >= deadline:
                return self._infos(t0, False, "Timeout")
            solved, error = self._search(mode, proof, deadline)
            if solved:
                return self._infos(t0, True)
        if time.time() >= deadline:
            return self._infos(t0, False, "Timeout")
        return self._infos(t0, False, error)

    def _search(
        self, mode: str, proof: ProofState, deadline: float
    ) -> tuple[bool, str]:
        beam = BeamQueue(max_size=self.beam_size)
        beam.add(node=((), self.problemJGEX, ""), val=0.0, stable_key=())

        for depth in range(self.search_depth):
            self._step = depth + 1
            frontier = list(beam)
            if not frontier:
                break
            if time.time() >= deadline:
                return False, "Timeout"

            last_depth = depth == self.search_depth - 1
            next_beam = BeamQueue(max_size=self.beam_size)
            requests_list, context = self._build_requests(
                mode, depth, frontier, proof
            )
            if not requests_list:
                beam = next_beam
                continue

            pending: list[Any] = []
            meta: dict[Any, dict[str, Any]] = {}
            solved = False
            lm_start = time.time()
            last_lm_done = lm_start

            with ThreadPoolExecutor(max_workers=HTTP_WORKERS) as executor:
                future_to_request = {
                    executor.submit(self._request_chat_completions, request): request
                    for request in requests_list
                }
                for future in as_completed(future_to_request):
                    result = future.result()
                    self._llm_calls += 1
                    last_lm_done = float(
                        result.get("completed_at_unix_s", time.time())
                    )
                    solved = self._submit(
                        result, context, pending, meta, next_beam, last_depth, deadline
                    )
                    if solved:
                        break
                    if self._collect(
                        pending, meta, next_beam, last_depth, deadline, block=False
                    ):
                        solved = True
                        break

            self._llm_wall += max(last_lm_done - lm_start, 0.0)

            if not solved:
                solved = self._collect(
                    pending, meta, next_beam, last_depth, deadline, block=True
                )
            if solved:
                self._cancel(pending)
                return True, ""
            beam = next_beam

        return False, "Tried but failed."

    def _submit(
        self,
        result: dict[str, Any],
        context: dict[str, dict[str, Any]],
        pending: list[Any],
        meta: dict[Any, dict[str, Any]],
        next_beam: BeamQueue,
        last_depth: bool,
        deadline: float,
    ) -> bool:
        ctx = context[result["request_id"]]
        request = ctx["request"]
        response_prefix = str(request["response_prefix"])
        aux_scores = self._score_choices(list(result["choices"]), request)

        for rank, (aux_dsl, score) in enumerate(_rank(aux_scores)):
            if not aux_dsl.startswith(response_prefix):
                continue
            aux_content = aux_dsl[len(response_prefix) :].strip()
            aux_construction = try_dsl_to_constructions(aux_content)
            if aux_construction is None:
                continue

            while len(pending) >= self._max_pending:
                if self._collect(
                    pending, meta, next_beam, last_depth, deadline, block=True
                ):
                    return True

            future = run_aux_ddar_remote.options(max_retries=0).remote(
                ctx["problem_ref"],
                self._defs_ref,
                aux_construction,
                content_is_construction=True,
                return_problem=not last_depth,
            )
            pending.append(future)
            meta[future] = {
                "prev_score": ctx["prev_score"],
                "path_key": ctx["path_key"],
                "rank": rank,
                "score": score,
                "child_aux_prefix": aux_dsl[len("<aux>") :],
            }
        return False

    def _collect(
        self,
        pending: list[Any],
        meta: dict[Any, dict[str, Any]],
        next_beam: BeamQueue,
        last_depth: bool,
        deadline: float,
        *,
        block: bool,
    ) -> bool:
        while pending:
            if block and time.time() >= deadline:
                self._cancel(pending)
                return False

            wait_start = time.perf_counter()
            done, remaining = ray.wait(
                pending, num_returns=1, timeout=1.0 if block else 0.0
            )
            self._ddar_wall += time.perf_counter() - wait_start
            if not done:
                if block:
                    continue
                return False

            pending[:] = remaining
            result = ray.get(done[0])
            info = meta.pop(done[0])

            if not result.get("candidate_valid", False):
                if block:
                    continue
                return False

            self._ddar_calls += 1
            if result.get("status") == "solved":
                self._cancel(pending)
                return True

            if (
                result.get("status") == "unsolved"
                and not last_depth
                and result.get("problem") is not None
            ):
                path_key = info["path_key"] + (info["rank"],)
                next_beam.add(
                    node=(path_key, result["problem"], info["child_aux_prefix"]),
                    val=float(info["prev_score"]) + float(info["score"]),
                    stable_key=path_key,
                )

            if not block:
                return False
        return False

    def _cancel(self, pending: list[Any]) -> None:
        for future in pending:
            try:
                ray.cancel(future, force=False)
            except Exception:
                pass
        pending.clear()

    def _build_requests(
        self, mode: str, depth: int, frontier: list, proof: ProofState
    ) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
        requests_list: list[dict[str, Any]] = []
        context: dict[str, dict[str, Any]] = {}
        for prev_score, (path_key, problem, aux_prefix) in frontier:
            suffix = "root" if not path_key else "-".join(map(str, path_key))
            request_id = f"d{depth}_p{suffix}"
            if mode == "v2":
                separator = " ;" if aux_prefix.strip() else ""
                response_prefix = f"<aux>{aux_prefix}{separator} x00"
                query = self._root_dsl
            else:
                response_prefix = RESPONSE_PREFIX
                query = problem_to_text_dsl(problem, proof.defs)

            new_point_name = get_new_point_name(problem)
            request = {
                "request_id": request_id,
                "search_mode": mode,
                "depth": depth,
                "messages": build_chat_messages(
                    query=query,
                    response_prefix=response_prefix,
                    new_point_name=new_point_name,
                ),
                "new_point_name": new_point_name,
                "response_prefix": response_prefix,
            }
            requests_list.append(request)
            context[request_id] = {
                "prev_score": prev_score,
                "path_key": path_key,
                "problem_ref": ray.put(problem),
                "request": request,
            }
        return requests_list, context

    def _request_chat_completions(self, request: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "model": self.served_model_name,
            "messages": request["messages"],
            "continue_final_message": True,
            "add_generation_prompt": False,
            "max_tokens": MAX_NEW_TOKENS,
            "n": self.decoding_size,
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
        resp = self.session.post(
            f"{self.base_url}/v1/chat/completions", json=payload, timeout=120.0
        )
        if not resp.ok:
            raise requests.HTTPError(
                f"vLLM chat completion failed status={resp.status_code}: {resp.text}",
                response=resp,
            )
        choices = list(resp.json().get("choices", []))
        if len(choices) != self.decoding_size:
            raise ValueError(
                f"Expected {self.decoding_size} choices, got {len(choices)}."
            )
        return {
            "request_id": request["request_id"],
            "choices": choices,
            "completed_at_unix_s": time.time(),
        }

    def _score_choices(
        self, choices: list[dict[str, Any]], request: dict[str, Any]
    ) -> dict[str, float]:
        response_prefix = str(request.get("response_prefix", RESPONSE_PREFIX))
        new_point_name = str(request["new_point_name"])
        stop_set = {int(t) for t in self.stop_token_ids}
        aux_dsl_dict: dict[str, float] = {}
        for choice in choices:
            message = choice.get("message") or {}
            text = str(message.get("content", "")) if isinstance(message, dict) else ""
            idx_stop = text.find(AUX_STOP)
            continuation = (text[:idx_stop] if idx_stop >= 0 else text).rstrip()
            logprobs = choice.get("logprobs") or {}
            token_ids = [int(t) for t in choice.get("token_ids", [])]
            raw_content_logprobs = logprobs.get("content", [])
            token_logprobs = [
                item.get("logprob") if isinstance(item, dict) else item
                for item in raw_content_logprobs
            ]
            limit = next(
                (j + 1 for j, token_id in enumerate(token_ids) if token_id in stop_set),
                min(len(token_ids), len(token_logprobs)),
            )
            token_logprobs = token_logprobs[:limit]
            aux_dsl = f"{response_prefix} {new_point_name}{continuation}"
            score = _sequence_score(token_logprobs)
            if aux_dsl not in aux_dsl_dict or score > aux_dsl_dict[aux_dsl]:
                aux_dsl_dict[aux_dsl] = score
        return aux_dsl_dict

    def _infos(
        self, t0: float, success: bool, error: str | None = None
    ) -> dict[str, Any]:
        infos: dict[str, Any] = {
            "runtime": time.time() - t0,
            "success": success,
            "steps": self._step,
            "ddar_calls": self._ddar_calls,
            "ddar_real_time_s": round(self._ddar_wall, 3),
            "llm_calls": self._llm_calls,
            "llm_real_time_s": round(self._llm_wall, 3),
        }
        if error:
            infos["error"] = error
        return infos
