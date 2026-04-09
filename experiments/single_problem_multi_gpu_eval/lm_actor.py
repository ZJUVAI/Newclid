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

from experiments.single_problem_multi_gpu_eval.batched_decode import decode_batched_continuations

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
    if candidate.is_absolute() or any(sep in path for sep in (os.sep, "/", "\\")):
        raise FileNotFoundError(f"Model path does not exist: {candidate}")

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


def _build_base_text(tokenizer, *, query: str) -> str:
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
    return text


def _build_prompt(tokenizer, *, query: str, new_point_name: str, response_prefix: str) -> str:
    return _build_base_text(tokenizer, query=query) + response_prefix + " " + new_point_name


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


def _create_worker_batch_profile(*, batch_size: int) -> dict[str, Any]:
    return {
        "batch_size": batch_size,
        "input_build_time_s": 0.0,
        "generate_time_s": 0.0,
        "decode_time_s": 0.0,
        "fallback_time_s": 0.0,
        "worker_inference_time_s": 0.0,
        "fallback_mode": "none",
    }


def _merge_worker_batch_profiles(*profiles: dict[str, Any]) -> dict[str, Any]:
    merged = _create_worker_batch_profile(batch_size=0)
    fallback_modes: list[str] = []
    for profile in profiles:
        if not profile:
            continue
        merged["batch_size"] += int(profile.get("batch_size", 0))
        for field in (
            "input_build_time_s",
            "generate_time_s",
            "decode_time_s",
            "fallback_time_s",
            "worker_inference_time_s",
        ):
            merged[field] += float(profile.get(field, 0.0))
        mode = str(profile.get("fallback_mode", "none"))
        if mode != "none":
            fallback_modes.append(mode)
    merged["fallback_mode"] = "+".join(fallback_modes) if fallback_modes else "none"
    return merged


def generate_aux_dsl_dict_batch(
    model,
    tokenizer,
    requests: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not requests:
        return [], _create_worker_batch_profile(batch_size=0)

    if any(request.get("with_predicate", False) for request in requests):
        raise NotImplementedError("Batched generation currently supports with_predicate=False only.")

    decoding_size = int(requests[0]["decoding_size"])
    if any(int(request["decoding_size"]) != decoding_size for request in requests):
        raise ValueError("All requests in a batch must share decoding_size.")

    profile = _create_worker_batch_profile(batch_size=len(requests))
    input_build_start = time.perf_counter()
    base_texts = [
        _build_base_text(
            tokenizer,
            query=request["query"],
        )
        for request in requests
    ]
    prompts = [
        base_text + request.get("response_prefix", "<aux> x00") + " " + request["new_point_name"]
        for base_text, request in zip(base_texts, requests)
    ]
    model_inputs = tokenizer(prompts, return_tensors="pt", padding=True).to(model.device)
    profile["input_build_time_s"] += time.perf_counter() - input_build_start
    pad_token_id = tokenizer.pad_token_id
    eos_token_id = tokenizer.encode(" ;", add_special_tokens=False)[0]

    generate_start = time.perf_counter()
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
    profile["generate_time_s"] += time.perf_counter() - generate_start
    scores = generated_output.sequences_scores.tolist()
    decode_start = time.perf_counter()
    rebuilt_outputs = decode_batched_continuations(
        requests=requests,
        model_inputs=model_inputs,
        sequences=generated_output.sequences,
        decoding_size=decoding_size,
        decode_batch=lambda batch: tokenizer.batch_decode(batch, skip_special_tokens=True),
    )
    profile["decode_time_s"] += time.perf_counter() - decode_start
    results: list[dict[str, Any]] = []
    for index, (request, aux_dsls) in enumerate(zip(requests, rebuilt_outputs)):
        aux_dsl_dict: dict[str, float] = {}
        start = index * decoding_size
        end = start + decoding_size
        for aux_dsl, score in zip(aux_dsls, scores[start:end]):
            aux_dsl_dict[aux_dsl] = float(score)
        results.append(
            {
                "request_id": request["request_id"],
                "aux_dsl_dict": aux_dsl_dict,
            }
        )
    return results, profile


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
        self.tokenizer.padding_side = "left"
        self.num_requests = 0
        self.num_batches = 0
        logger.info(
            "ModelWorker init done: model_path=%s device=%s padding_side=%s",
            self.model_path,
            next(self.model.parameters()).device,
            self.tokenizer.padding_side,
        )

    def warmup(self) -> dict[str, Any]:
        device = str(next(self.model.parameters()).device)
        return {
            "model_path": self.model_path,
            "device": device,
            "padding_side": self.tokenizer.padding_side,
        }

    @torch.no_grad()
    def generate_one(self, request: dict[str, Any]) -> dict[str, Any]:
        return self.generate_batch([request])[0]

    @torch.no_grad()
    def generate_batch(self, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not requests:
            return {
                "results": [],
                "worker_batch_profile": _create_worker_batch_profile(batch_size=0),
            }
        inference_start = time.time()
        perf_start = time.perf_counter()
        try:
            results, worker_batch_profile = self._generate_batch_with_fallback(requests)
        finally:
            inference_time_s = time.time() - inference_start
        worker_batch_profile["worker_inference_time_s"] = time.perf_counter() - perf_start
        batch_size = len(requests)
        self.num_requests += batch_size
        self.num_batches += 1
        for result in results:
            result["inference_time_s"] = inference_time_s
            result["batch_size"] = batch_size
        return {
            "results": results,
            "worker_batch_profile": worker_batch_profile,
        }

    def _generate_batch_with_fallback(self, requests: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        try:
            return generate_aux_dsl_dict_batch(self.model, self.tokenizer, requests)
        except Exception as exc:
            if len(requests) == 1:
                logger.exception("LM generate failed for request_id=%s", requests[0].get("request_id"))
                profile = _create_worker_batch_profile(batch_size=1)
                profile["fallback_mode"] = "single_error"
                return [_empty_result(requests[0], error=str(exc), batch_size=1)], profile
            if _is_oom_error(exc):
                logger.warning(
                    "LM batched generate hit OOM; splitting batch_size=%d request_ids=%s",
                    len(requests),
                    [request.get("request_id") for request in requests],
                )
                fallback_start = time.perf_counter()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                midpoint = len(requests) // 2
                left_results, left_profile = self._generate_batch_with_fallback(requests[:midpoint])
                right_results, right_profile = self._generate_batch_with_fallback(requests[midpoint:])
                merged_profile = _merge_worker_batch_profiles(left_profile, right_profile)
                merged_profile["fallback_time_s"] += time.perf_counter() - fallback_start
                merged_profile["fallback_mode"] = "oom_split"
                return left_results + right_results, merged_profile
            logger.exception(
                "LM batched generate failed; falling back to per-request execution for request_ids=%s",
                [request.get("request_id") for request in requests],
            )
            fallback_start = time.perf_counter()
            all_results: list[dict[str, Any]] = []
            profiles: list[dict[str, Any]] = []
            for request in requests:
                request_results, request_profile = self._generate_batch_with_fallback([request])
                all_results.extend(request_results)
                profiles.append(request_profile)
            merged_profile = _merge_worker_batch_profiles(*profiles)
            merged_profile["fallback_time_s"] += time.perf_counter() - fallback_start
            merged_profile["fallback_mode"] = "per_request"
            return all_results, merged_profile

    def stats(self) -> dict[str, Any]:
        return {
            "model_path": self.model_path,
            "num_requests": self.num_requests,
            "num_batches": self.num_batches,
            "avg_batch_size": (self.num_requests / self.num_batches) if self.num_batches else 0.0,
        }
