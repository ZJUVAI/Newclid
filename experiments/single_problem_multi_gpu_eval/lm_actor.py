from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

import ray
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from transformers.utils import logging as hf_logging


os.environ["TOKENIZERS_PARALLELISM"] = "false"

logger = logging.getLogger(__name__)
hf_logging.disable_progress_bar()
hf_logging.set_verbosity_error()

AUX_PREDICATES: list[str] = []


def resolve_model_path(path: str) -> str:
    candidate = Path(path).expanduser()
    if candidate.exists():
        resolved = str(candidate.resolve())
        logger.info("Loading experiment model from local path: %s", resolved)
        return resolved

    try:
        from modelscope import snapshot_download
    except ImportError as exc:
        raise ImportError(
            "modelscope is required to load remote model ids like "
            f"'{path}'. Install it or pass a local model path."
        ) from exc

    logger.info("Downloading/loading experiment model via ModelScope: %s", path)
    resolved = snapshot_download(path)
    logger.info("Resolved experiment model id %s to local path: %s", path, resolved)
    return resolved


def _build_prompt(tokenizer, *, query: str, new_point_name: str, response_prefix: str) -> str:
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": query},
    ]
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    text += "<think>\n\n</think>\n\n"
    return text + response_prefix + " " + new_point_name


def _empty_result(request: dict[str, Any], *, error: str, batch_size: int) -> dict[str, Any]:
    return {
        "request_id": request["request_id"],
        "aux_dsl_dict": {},
        "inference_time_s": 0.0,
        "batch_size": batch_size,
        "error": error,
    }


def _is_oom_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return isinstance(exc, torch.cuda.OutOfMemoryError) or "out of memory" in message


def generate_aux_dsl_dict_batch(
    model,
    tokenizer,
    requests: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not requests:
        return []

    if any(request.get("with_predicate", False) for request in requests):
        raise NotImplementedError("Batched generation currently supports with_predicate=False only.")

    decoding_size = int(requests[0]["decoding_size"])
    if any(int(request["decoding_size"]) != decoding_size for request in requests):
        raise ValueError("All requests in a batch must share decoding_size.")

    prompts = [
        _build_prompt(
            tokenizer,
            query=request["query"],
            new_point_name=request["new_point_name"],
            response_prefix=request.get("response_prefix", "<aux> x00"),
        )
        for request in requests
    ]
    model_inputs = tokenizer(prompts, return_tensors="pt", padding=True).to(model.device)
    attention_mask = model_inputs["attention_mask"]
    prompt_lens = attention_mask.sum(dim=1).tolist()
    pad_token_id = tokenizer.pad_token_id
    eos_token_id = tokenizer.encode(" ;", add_special_tokens=False)[0]

    generated_output = model.generate(
        **model_inputs,
        max_new_tokens=100,
        num_beams=decoding_size,
        num_return_sequences=decoding_size,
        pad_token_id=pad_token_id,
        eos_token_id=eos_token_id,
        return_dict_in_generate=True,
        output_scores=True,
    )
    scores = generated_output.sequences_scores.tolist()
    sequences = generated_output.sequences
    results: list[dict[str, Any]] = []
    for index, request in enumerate(requests):
        aux_dsl_dict: dict[str, float] = {}
        start = index * decoding_size
        end = start + decoding_size
        prompt_len = int(prompt_lens[index])
        trimmed = [sequence[prompt_len:] for sequence in sequences[start:end]]
        aux_dsls = tokenizer.batch_decode(trimmed, skip_special_tokens=True)
        for aux_dsl, score in zip(aux_dsls, scores[start:end]):
            aux_dsl_dict[aux_dsl] = float(score)
        results.append(
            {
                "request_id": request["request_id"],
                "aux_dsl_dict": aux_dsl_dict,
            }
        )
    return results


@ray.remote(num_cpus=1, num_gpus=1, max_concurrency=1)
class ModelWorker:
    """Keep one LM replica resident on one GPU for repeated generation calls."""

    def __init__(self, model_path: str):
        resolved_path = resolve_model_path(model_path)
        self.model_path = resolved_path
        self.model = AutoModelForCausalLM.from_pretrained(
            resolved_path,
            torch_dtype="auto",
            device_map="auto",
            attn_implementation="flash_attention_2",
            trust_remote_code=True,
        )
        self.tokenizer = AutoTokenizer.from_pretrained(
            resolved_path,
            trust_remote_code=True,
        )
        self.num_requests = 0
        self.num_batches = 0

    def warmup(self) -> dict[str, Any]:
        device = str(next(self.model.parameters()).device)
        return {
            "model_path": self.model_path,
            "device": device,
        }

    @torch.no_grad()
    def generate_one(self, request: dict[str, Any]) -> dict[str, Any]:
        return self.generate_batch([request])[0]

    @torch.no_grad()
    def generate_batch(self, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not requests:
            return []
        inference_start = time.time()
        try:
            results = self._generate_batch_with_fallback(requests)
        finally:
            inference_time_s = time.time() - inference_start
        batch_size = len(requests)
        self.num_requests += batch_size
        self.num_batches += 1
        for result in results:
            result["inference_time_s"] = inference_time_s
            result["batch_size"] = batch_size
        return results

    def _generate_batch_with_fallback(self, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        try:
            return generate_aux_dsl_dict_batch(self.model, self.tokenizer, requests)
        except Exception as exc:
            if len(requests) == 1:
                logger.exception("LM generate failed for request_id=%s", requests[0].get("request_id"))
                return [_empty_result(requests[0], error=str(exc), batch_size=1)]
            if _is_oom_error(exc):
                logger.warning(
                    "LM batched generate hit OOM; splitting batch_size=%d request_ids=%s",
                    len(requests),
                    [request.get("request_id") for request in requests],
                )
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                midpoint = len(requests) // 2
                return (
                    self._generate_batch_with_fallback(requests[:midpoint])
                    + self._generate_batch_with_fallback(requests[midpoint:])
                )
            logger.exception(
                "LM batched generate failed; falling back to per-request execution for request_ids=%s",
                [request.get("request_id") for request in requests],
            )
            return [
                self._generate_batch_with_fallback([request])[0]
                for request in requests
            ]

    def stats(self) -> dict[str, Any]:
        return {
            "model_path": self.model_path,
            "num_requests": self.num_requests,
            "num_batches": self.num_batches,
            "avg_batch_size": (self.num_requests / self.num_batches) if self.num_batches else 0.0,
        }
