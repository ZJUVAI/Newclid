from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path
import time
from typing import Any

import requests
from transformers import AutoTokenizer

from newclid.agent.base import BaseAgent, RESPONSE_PREFIX
from newclid.agent.runtime.search_runtime import (
    build_problem_proof,
    get_new_point_name,
    problem_to_text_dsl,
    problem_to_visual_dsl,
)
from newclid.formulations.problem import ProblemJGEX
from newclid.generation.writer import save_figure_as_png
from newclid.numerical.draw_clause_figure import draw_clause_figure
from newclid.proof import ProofState

SYSTEM_PROMPT = "You are a helpful assistant."
MAX_NEW_TOKENS = 100
LENGTH_PENALTY = 1.0
AUX_STOP = "</aux>"
AUX_CANDIDATE_STOP = " ;"
HTTP_WORKERS = 16


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
    response_prefix = str(request.get("response_prefix", RESPONSE_PREFIX))
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


class _BaseQwen3Agent(BaseAgent):
    agent_name = "qwen3"

    def __init__(
        self,
        *,
        base_url: str,
        decoding_size: int,
        beam_size: int,
        search_depth: int,
        served_model_name: str | None = None,
        search_version: str = "v1",
        max_pending_ddar: int | None = None,
        ddar_config: dict[str, bool] | None = None,
        trace_writer=None,
    ) -> None:
        super().__init__(
            decoding_size=decoding_size,
            beam_size=beam_size,
            search_depth=search_depth,
            search_version=search_version,
            max_pending_ddar=max_pending_ddar,
            ddar_config=ddar_config,
            trace_writer=trace_writer,
        )
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=HTTP_WORKERS, pool_maxsize=HTTP_WORKERS
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.server_models: list[str | None] = []
        if served_model_name is None:
            self.served_model_name, self.server_models = discover_served_model(self.base_url)
        else:
            self.served_model_name = served_model_name
            self.server_models = [served_model_name]
        self.tokenizer = _load_tokenizer(self.served_model_name)
        self.stop_token_ids = self.tokenizer.encode(
            AUX_CANDIDATE_STOP, add_special_tokens=False
        )
        if len(self.stop_token_ids) != 1:
            raise ValueError(
                f"Expected {AUX_CANDIDATE_STOP!r} to map to one token, got {self.stop_token_ids}."
            )
        self._root_problem_dsl: str | None = None

    def server_info(self) -> dict[str, Any]:
        return {
            "served_model_name": self.served_model_name,
            "server_models": self.server_models,
            "search_version": self.search_version,
        }

    def prepare_search(self, proof: ProofState) -> None:
        if self.problemJGEX is None:
            raise ValueError("Missing problemJGEX.")
        self._root_problem_dsl = self.problem_to_dsl(self.problemJGEX, proof.defs)

    def response_prefix(self, *, mode: str, aux_prefix: str) -> str:
        if mode != "v2":
            return RESPONSE_PREFIX
        separator = " ;" if aux_prefix.strip() else ""
        return f"<aux>{aux_prefix}{separator} x00"

    def request_completions(self, request: dict[str, Any]) -> dict[str, Any]:
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
        response = self.session.post(
            f"{self.base_url}/v1/chat/completions",
            json=payload,
            timeout=120.0,
        )
        response.raise_for_status()
        choices = list(response.json().get("choices", []))
        if len(choices) != self.decoding_size:
            raise ValueError(f"Expected {self.decoding_size} choices, got {len(choices)}.")
        aux_dsl_scores, _ = _score_chat_choices(
            choices=choices,
            request=request,
            stop_token_ids=self.stop_token_ids,
        )
        return {
            "request_id": request["request_id"],
            "aux_dsl_scores": aux_dsl_scores,
            "completed_at_unix_s": time.time(),
        }

    def problem_to_dsl(self, problem: ProblemJGEX, defs) -> str:
        raise NotImplementedError


class Qwen3Agent(_BaseQwen3Agent):
    agent_name = "qwen3_text"

    def build_request(
        self,
        *,
        mode: str,
        depth: int,
        request_id: str,
        problem: ProblemJGEX,
        aux_prefix: str,
        proof: ProofState,
    ) -> dict[str, Any]:
        del depth
        if mode == "v2":
            if self._root_problem_dsl is None:
                raise ValueError("Root text DSL is unavailable.")
            query = self._root_problem_dsl
        else:
            query = self.problem_to_dsl(problem, proof.defs)
        new_point_name = get_new_point_name(problem)
        response_prefix = self.response_prefix(mode=mode, aux_prefix=aux_prefix)
        return {
            "request_id": request_id,
            "messages": build_chat_messages(
                query=query,
                response_prefix=response_prefix,
                new_point_name=new_point_name,
            ),
            "query": query,
            "new_point_name": new_point_name,
            "response_prefix": response_prefix,
            "decoding_size": self.decoding_size,
        }

    def problem_to_dsl(self, problem: ProblemJGEX, defs) -> str:
        return problem_to_text_dsl(problem, defs)


class Qwen3VLAgent(_BaseQwen3Agent):
    agent_name = "qwen3_vl"

    def __init__(
        self,
        *,
        base_url: str,
        decoding_size: int,
        beam_size: int,
        search_depth: int,
        served_model_name: str | None = None,
        search_version: str = "v1",
        render_root: str | Path = "temp/eval_rendered_images",
        max_pending_ddar: int | None = None,
        ddar_config: dict[str, bool] | None = None,
        trace_writer=None,
    ) -> None:
        super().__init__(
            base_url=base_url,
            decoding_size=decoding_size,
            beam_size=beam_size,
            search_depth=search_depth,
            served_model_name=served_model_name,
            search_version=search_version,
            max_pending_ddar=max_pending_ddar,
            ddar_config=ddar_config,
            trace_writer=trace_writer,
        )
        self.render_root = Path(render_root)
        self.render_root.mkdir(parents=True, exist_ok=True)

    def build_request(
        self,
        *,
        mode: str,
        depth: int,
        request_id: str,
        problem: ProblemJGEX,
        aux_prefix: str,
        proof: ProofState,
    ) -> dict[str, Any]:
        if mode == "v2":
            if self._root_problem_dsl is None:
                raise ValueError("Root visual DSL is unavailable.")
            query = self._root_problem_dsl
        else:
            query = self.problem_to_dsl(problem, proof.defs)

        current_proof = build_problem_proof(problem, proof.defs)
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
        image_data_url = "data:image/png;base64," + base64.b64encode(
            png_path.read_bytes()
        ).decode("ascii")
        new_point_name = get_new_point_name(problem)
        response_prefix = self.response_prefix(mode=mode, aux_prefix=aux_prefix)
        return {
            "request_id": request_id,
            "messages": build_visual_messages(
                image_data_url=image_data_url,
                query=query,
                response_prefix=response_prefix,
                new_point_name=new_point_name,
            ),
            "query": query,
            "image_data_url": image_data_url,
            "new_point_name": new_point_name,
            "response_prefix": response_prefix,
            "decoding_size": self.decoding_size,
        }

    def problem_to_dsl(self, problem: ProblemJGEX, defs) -> str:
        return problem_to_visual_dsl(problem, defs)
