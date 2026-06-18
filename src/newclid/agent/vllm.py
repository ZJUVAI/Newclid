from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path
import time
from typing import Any

import requests
from transformers import AutoTokenizer

from newclid.agent.base import BaseAgent, RESPONSE_PREFIX
from newclid.evaluation.search_runtime import (
    build_problem_proof,
    get_new_point_name,
    problem_to_dsl,
)
from newclid.formulations.problem import ProblemJGEX
from newclid.generation.writer import save_figure_as_png
from newclid.numerical.draw_clause_figure import draw_clause_figure
from newclid.proof import ProofState

SYSTEM_PROMPT = "You are a helpful assistant."
MAX_NEW_TOKENS = 100
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


def _build_messages(
    *, query: str, response_prefix: str, new_point_name: str, image_url: str | None = None
) -> list[dict[str, Any]]:
    user_content: Any = query if image_url is None else [
        {"type": "image_url", "image_url": {"url": image_url}},
        {"type": "text", "text": query},
    ]
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
        {"role": "assistant", "content": f"<think>\n\n</think>\n\n{response_prefix} {new_point_name}"},
    ]


def _score_chat_choices(
    *,
    choices: list[dict[str, Any]],
    request: dict[str, Any],
    stop_token_id: int,
) -> dict[str, float]:
    response_prefix = str(request.get("response_prefix", RESPONSE_PREFIX))
    new_point_name = str(request["new_point_name"])
    aux_dsl_dict: dict[str, float] = {}
    for choice in choices:
        text = str(choice.get("message", {}).get("content", ""))
        continuation = text.partition(AUX_STOP)[0].rstrip()
        token_ids = choice.get("token_ids", [])
        token_logprobs = [
            item.get("logprob") for item in choice.get("logprobs", {}).get("content", [])
        ]
        stop_idx = next(
            (i for i, tid in enumerate(token_ids) if tid == stop_token_id),
            min(len(token_ids), len(token_logprobs)),
        )
        valid = [lp for lp in token_logprobs[:stop_idx] if lp is not None]
        score = sum(valid) / max(len(valid), 1)
        aux_dsl = f"{response_prefix} {new_point_name}{continuation}"
        if aux_dsl not in aux_dsl_dict or score > aux_dsl_dict[aux_dsl]:
            aux_dsl_dict[aux_dsl] = score
    return aux_dsl_dict


class _BaseQwen3Agent(BaseAgent):
    agent_name = "qwen3"

    def __init__(
        self,
        *,
        base_url: str,
        served_model_name: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=HTTP_WORKERS, pool_maxsize=HTTP_WORKERS
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        if served_model_name is None:
            self.served_model_name, self.server_models = discover_served_model(self.base_url)
        else:
            self.served_model_name = served_model_name
            self.server_models: list[str | None] = [served_model_name]
        tokenizer = _load_tokenizer(self.served_model_name)
        stop_token_ids = tokenizer.encode(AUX_CANDIDATE_STOP, add_special_tokens=False)
        if len(stop_token_ids) != 1:
            raise ValueError(
                f"Expected {AUX_CANDIDATE_STOP!r} to map to one token, got {stop_token_ids}."
            )
        self.stop_token_id = stop_token_ids[0]
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
        self._root_problem_dsl = problem_to_dsl(self.problemJGEX, proof.defs)

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
            "stop_token_ids": [self.stop_token_id],
        }
        response = self.session.post(
            f"{self.base_url}/v1/chat/completions", json=payload, timeout=120.0
        )
        response.raise_for_status()
        choices = list(response.json().get("choices", []))
        if len(choices) != self.decoding_size:
            raise ValueError(f"Expected {self.decoding_size} choices, got {len(choices)}.")
        return {
            "request_id": request["request_id"],
            "aux_dsl_scores": _score_chat_choices(
                choices=choices, request=request, stop_token_id=self.stop_token_id
            ),
            "completed_at_unix_s": time.time(),
        }

    def _get_query(self, mode: str, problem: ProblemJGEX, proof: ProofState) -> str:
        if mode == "v2":
            if self._root_problem_dsl is None:
                raise ValueError("Root DSL is unavailable.")
            return self._root_problem_dsl
        return problem_to_dsl(problem, proof.defs)

    def _build_request_dict(
        self,
        *,
        request_id: str,
        query: str,
        response_prefix: str,
        new_point_name: str,
        image_url: str | None = None,
        extra: dict | None = None,
    ) -> dict[str, Any]:
        result = {
            "request_id": request_id,
            "messages": _build_messages(
                query=query,
                response_prefix=response_prefix,
                new_point_name=new_point_name,
                image_url=image_url,
            ),
            "query": query,
            "new_point_name": new_point_name,
            "response_prefix": response_prefix,
            "decoding_size": self.decoding_size,
        }
        if extra:
            result.update(extra)
        return result


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
        query = self._get_query(mode, problem, proof)
        return self._build_request_dict(
            request_id=request_id,
            query=query,
            response_prefix=self.response_prefix(mode=mode, aux_prefix=aux_prefix),
            new_point_name=get_new_point_name(problem),
        )

class Qwen3VLAgent(_BaseQwen3Agent):
    agent_name = "qwen3_vl"

    def __init__(
        self,
        *,
        render_root: str | Path = "temp/eval_rendered_images",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
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
        query = self._get_query(mode, problem, proof)
        current_proof = build_problem_proof(problem, proof.defs)
        png_path = self.render_root / f"d{depth}_{request_id}.png"
        save_figure_as_png(
            draw_clause_figure(
                current_proof, problem, None, current_proof.rng,
                draw_annotations=True, theme=None,
            ),
            png_path=str(png_path),
            img_pixels=512,
            direct_png=True,
        )
        image_url = "data:image/png;base64," + base64.b64encode(
            png_path.read_bytes()
        ).decode("ascii")
        return self._build_request_dict(
            request_id=request_id,
            query=query,
            response_prefix=self.response_prefix(mode=mode, aux_prefix=aux_prefix),
            new_point_name=get_new_point_name(problem),
            image_url=image_url,
            extra={"image_data_url": image_url},
        )
