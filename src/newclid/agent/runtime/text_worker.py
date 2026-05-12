from __future__ import annotations

import logging
import os
import time
from typing import Any

import ray
import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    StoppingCriteria,
    StoppingCriteriaList,
)
from transformers.utils import logging as hf_logging

from newclid.agent.runtime.batched_decode import decode_batched_continuations
from newclid.agent.runtime.model_resolution import resolve_model_path

os.environ["TOKENIZERS_PARALLELISM"] = "false"

logger = logging.getLogger(__name__)
hf_logging.disable_progress_bar()
hf_logging.set_verbosity_error()


def _build_base_text(tokenizer, *, query: str, agent_kind: str) -> str:
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": query},
    ]
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    if agent_kind == "lm":
        text += "<think>\n\n</think>\n\n"
    return text


def _empty_result(
    request: dict[str, Any], *, error: str, batch_size: int
) -> dict[str, Any]:
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
        "prompt_token_count_sum": 0,
        "prompt_token_count_max": 0,
        "generated_token_count_sum": 0,
        "generated_token_count_max": 0,
        "generated_sequence_count": 0,
        "raw_candidate_count_sum": 0,
        "unique_candidate_count_sum": 0,
        "duplicate_candidate_count_sum": 0,
        "first_token_latency_sum_s": 0.0,
        "first_token_latency_count": 0,
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
            "prompt_token_count_sum",
            "generated_token_count_sum",
            "generated_sequence_count",
            "raw_candidate_count_sum",
            "unique_candidate_count_sum",
            "duplicate_candidate_count_sum",
            "first_token_latency_sum_s",
            "first_token_latency_count",
        ):
            merged[field] += float(profile.get(field, 0.0))
        for field in (
            "prompt_token_count_max",
            "generated_token_count_max",
        ):
            merged[field] = max(
                float(merged.get(field, 0.0)), float(profile.get(field, 0.0))
            )
        mode = str(profile.get("fallback_mode", "none"))
        if mode != "none":
            fallback_modes.append(mode)
    merged["fallback_mode"] = "+".join(fallback_modes) if fallback_modes else "none"
    return merged


def _count_prompt_tokens(model_inputs: dict[str, Any]) -> list[int]:
    attention_mask = model_inputs.get("attention_mask")
    if attention_mask is not None:
        return [int(value) for value in attention_mask.sum(dim=1).tolist()]
    input_ids = model_inputs.get("input_ids")
    if input_ids is None:
        return []
    return [int(input_ids.shape[1])] * int(input_ids.shape[0])


def _count_generated_tokens(
    sequence_token_ids: list[int],
    *,
    prompt_token_count: int,
    pad_token_id: int | None,
    eos_token_id: int | None,
) -> int:
    if prompt_token_count > 0 and len(sequence_token_ids) >= prompt_token_count:
        continuation = list(sequence_token_ids[prompt_token_count:])
    else:
        continuation = list(sequence_token_ids)
    if pad_token_id is not None:
        while continuation and continuation[-1] == pad_token_id:
            continuation.pop()
    if eos_token_id is not None and continuation and continuation[-1] == eos_token_id:
        continuation.pop()
    return len(continuation)


def _build_request_profile(
    *,
    prompt_token_count: int,
    generated_token_counts: list[int],
    raw_candidate_count: int,
    unique_candidate_count: int,
    first_token_latency_s: float | None = None,
) -> dict[str, Any]:
    generated_token_count_sum = sum(int(count) for count in generated_token_counts)
    generated_sequence_count = len(generated_token_counts)
    duplicate_candidate_count = max(
        int(raw_candidate_count) - int(unique_candidate_count), 0
    )
    request_profile = {
        "prompt_token_count": int(prompt_token_count),
        "generated_token_count_sum": int(generated_token_count_sum),
        "generated_token_count_max": max(generated_token_counts, default=0),
        "generated_sequence_count": int(generated_sequence_count),
        "raw_candidate_count": int(raw_candidate_count),
        "unique_candidate_count": int(unique_candidate_count),
        "duplicate_candidate_count": int(duplicate_candidate_count),
        "avg_generated_tokens_per_sequence": (
            float(generated_token_count_sum) / float(generated_sequence_count)
            if generated_sequence_count
            else 0.0
        ),
    }
    if first_token_latency_s is not None:
        request_profile["first_token_latency_s"] = float(first_token_latency_s)
    return request_profile


def _accumulate_request_profile(
    worker_batch_profile: dict[str, Any], request_profile: dict[str, Any]
) -> None:
    worker_batch_profile["prompt_token_count_sum"] += int(
        request_profile.get("prompt_token_count", 0)
    )
    worker_batch_profile["prompt_token_count_max"] = max(
        int(worker_batch_profile.get("prompt_token_count_max", 0)),
        int(request_profile.get("prompt_token_count", 0)),
    )
    worker_batch_profile["generated_token_count_sum"] += int(
        request_profile.get("generated_token_count_sum", 0)
    )
    worker_batch_profile["generated_token_count_max"] = max(
        int(worker_batch_profile.get("generated_token_count_max", 0)),
        int(request_profile.get("generated_token_count_max", 0)),
    )
    worker_batch_profile["generated_sequence_count"] += int(
        request_profile.get("generated_sequence_count", 0)
    )
    worker_batch_profile["raw_candidate_count_sum"] += int(
        request_profile.get("raw_candidate_count", 0)
    )
    worker_batch_profile["unique_candidate_count_sum"] += int(
        request_profile.get("unique_candidate_count", 0)
    )
    worker_batch_profile["duplicate_candidate_count_sum"] += int(
        request_profile.get("duplicate_candidate_count", 0)
    )
    first_token_latency_s = request_profile.get("first_token_latency_s")
    if first_token_latency_s is not None:
        worker_batch_profile["first_token_latency_sum_s"] += float(
            first_token_latency_s
        )
        worker_batch_profile["first_token_latency_count"] += 1


class _EndAuxTagCriteria(StoppingCriteria):
    """Stop generation when all sequences end with the ` </aux>` token sequence."""

    def __init__(self, stop_ids: list[int], device):
        self._stop = torch.tensor(stop_ids, device=device)

    def __call__(self, input_ids: torch.LongTensor, scores, **kwargs) -> bool:
        n = len(self._stop)
        if input_ids.shape[1] < n:
            return False
        tail = input_ids[:, -n:]
        return bool((tail == self._stop).all())


def _resolve_text_stop_config(
    tokenizer,
    *,
    stop_at_semicolon: bool,
    device,
) -> tuple[int | None, StoppingCriteriaList | None, int]:
    if stop_at_semicolon:
        eos_token_id = tokenizer.encode(" ;", add_special_tokens=False)[0]
        return eos_token_id, None, 100
    stop_ids = tokenizer.encode(" </aux>", add_special_tokens=False)
    stopping_criteria = StoppingCriteriaList(
        [_EndAuxTagCriteria(stop_ids, device=device)]
    )
    return None, stopping_criteria, 512


def generate_aux_dsl_dict_batch(
    model,
    tokenizer,
    requests: list[dict[str, Any]],
    *,
    agent_kind: str,
    stop_at_semicolon: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not requests:
        return [], _create_worker_batch_profile(batch_size=0)

    if any(request.get("with_predicate", False) for request in requests):
        raise NotImplementedError(
            "Batched generation currently supports with_predicate=False only."
        )

    decoding_size = int(requests[0]["decoding_size"])
    if any(int(request["decoding_size"]) != decoding_size for request in requests):
        raise ValueError("All requests in a batch must share decoding_size.")

    profile = _create_worker_batch_profile(batch_size=len(requests))
    input_build_start = time.perf_counter()
    base_texts = [
        _build_base_text(
            tokenizer,
            query=request["query"],
            agent_kind=agent_kind,
        )
        for request in requests
    ]
    prompts = [
        base_text
        + request.get("response_prefix", "<aux> x00")
        + " "
        + request["new_point_name"]
        for base_text, request in zip(base_texts, requests)
    ]
    model_inputs = tokenizer(prompts, return_tensors="pt", padding=True).to(
        model.device
    )
    profile["input_build_time_s"] += time.perf_counter() - input_build_start
    pad_token_id = tokenizer.pad_token_id
    eos_token_id, stopping_criteria, max_new_tokens = _resolve_text_stop_config(
        tokenizer,
        stop_at_semicolon=stop_at_semicolon,
        device=model.device,
    )

    generate_start = time.perf_counter()
    generated_output = model.generate(
        **model_inputs,
        max_new_tokens=max_new_tokens,
        num_beams=decoding_size,
        num_return_sequences=decoding_size,
        pad_token_id=pad_token_id,
        eos_token_id=eos_token_id,
        stopping_criteria=stopping_criteria,
        return_dict_in_generate=True,
        output_scores=True,
    )
    profile["generate_time_s"] += time.perf_counter() - generate_start
    scores = generated_output.sequences_scores.tolist()
    prompt_token_counts = _count_prompt_tokens(model_inputs)
    generated_token_counts = [
        _count_generated_tokens(
            sequence.tolist(),
            prompt_token_count=prompt_token_counts[index // decoding_size],
            pad_token_id=pad_token_id,
            eos_token_id=eos_token_id,
        )
        for index, sequence in enumerate(generated_output.sequences)
    ]
    decode_start = time.perf_counter()
    rebuilt_outputs = decode_batched_continuations(
        requests=requests,
        model_inputs=model_inputs,
        sequences=generated_output.sequences,
        decoding_size=decoding_size,
        decode_batch=lambda batch: tokenizer.batch_decode(
            batch, skip_special_tokens=True
        ),
    )
    profile["decode_time_s"] += time.perf_counter() - decode_start
    results: list[dict[str, Any]] = []
    for index, (request, aux_dsls) in enumerate(zip(requests, rebuilt_outputs)):
        aux_dsl_dict: dict[str, float] = {}
        start = index * decoding_size
        end = start + decoding_size
        for aux_dsl, score in zip(aux_dsls, scores[start:end]):
            aux_dsl_dict[aux_dsl] = float(score)
        request_profile = _build_request_profile(
            prompt_token_count=prompt_token_counts[index],
            generated_token_counts=generated_token_counts[start:end],
            raw_candidate_count=len(aux_dsls),
            unique_candidate_count=len(aux_dsl_dict),
        )
        _accumulate_request_profile(profile, request_profile)
        results.append(
            {
                "request_id": request["request_id"],
                "aux_dsl_dict": aux_dsl_dict,
                "request_profile": request_profile,
            }
        )
    return results, profile


@ray.remote(num_cpus=1, num_gpus=1, max_concurrency=1)
class ModelWorker:
    """Keep one LM replica resident on one GPU for repeated generation calls."""

    def __init__(
        self,
        model_path: str,
        agent_kind: str = "lm",
        torch_seed: int = 123,
        worker_slot: int = 0,
        stop_at_semicolon: bool = False,
    ):
        resolved_path = resolve_model_path(model_path)
        self.model_path = resolved_path
        self.agent_kind = agent_kind
        self.torch_seed = int(torch_seed)
        self.worker_slot = int(worker_slot)
        self.stop_at_semicolon = bool(stop_at_semicolon)
        self.worker_id = f"gpu:{self.worker_slot}"
        self.device_label = f"cuda:{self.worker_slot}"
        torch.manual_seed(self.torch_seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed(self.torch_seed)
            torch.cuda.manual_seed_all(self.torch_seed)
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
            "ModelWorker init done: model_path=%s device=%s padding_side=%s torch_seed=%d worker_id=%s",
            self.model_path,
            next(self.model.parameters()).device,
            self.tokenizer.padding_side,
            self.torch_seed,
            self.worker_id,
        )

    def warmup(self) -> dict[str, Any]:
        device = str(next(self.model.parameters()).device)
        agent_kind = getattr(self, "agent_kind", "lm")
        return {
            "model_path": self.model_path,
            "agent_kind": agent_kind,
            "device": device,
            "padding_side": self.tokenizer.padding_side,
            "torch_seed": self.torch_seed,
            "runtime": "transformers",
            "worker_id": self.worker_id,
            "worker_slot": self.worker_slot,
        }

    @torch.no_grad()
    def generate_batch(self, requests: list[dict[str, Any]]) -> dict[str, Any]:
        if not requests:
            return {
                "results": [],
                "worker_batch_profile": {
                    **_create_worker_batch_profile(batch_size=0),
                    "gpu_worker_id": self.worker_id,
                    "gpu_device": self.device_label,
                },
            }
        inference_start = time.time()
        perf_start = time.perf_counter()
        try:
            results, worker_batch_profile = self._generate_batch_with_fallback(requests)
        finally:
            inference_time_s = time.time() - inference_start
        worker_finished_at_unix_s = time.time()
        worker_batch_profile["worker_inference_time_s"] = (
            time.perf_counter() - perf_start
        )
        worker_batch_profile["gpu_worker_id"] = self.worker_id
        worker_batch_profile["gpu_device"] = self.device_label
        worker_batch_profile["worker_started_at_unix_s"] = inference_start
        worker_batch_profile["worker_finished_at_unix_s"] = worker_finished_at_unix_s
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

    def _generate_batch_with_fallback(
        self, requests: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        try:
            return generate_aux_dsl_dict_batch(
                self.model,
                self.tokenizer,
                requests,
                agent_kind=getattr(self, "agent_kind", "lm"),
                stop_at_semicolon=self.stop_at_semicolon,
            )
        except Exception as exc:
            if len(requests) == 1:
                logger.exception(
                    "LM generate failed for request_id=%s",
                    requests[0].get("request_id"),
                )
                profile = _create_worker_batch_profile(batch_size=1)
                profile["fallback_mode"] = "single_error"
                return [
                    _empty_result(requests[0], error=str(exc), batch_size=1)
                ], profile
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
                left_results, left_profile = self._generate_batch_with_fallback(
                    requests[:midpoint]
                )
                right_results, right_profile = self._generate_batch_with_fallback(
                    requests[midpoint:]
                )
                merged_profile = _merge_worker_batch_profiles(
                    left_profile, right_profile
                )
                merged_profile["fallback_time_s"] += (
                    time.perf_counter() - fallback_start
                )
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
                request_results, request_profile = self._generate_batch_with_fallback(
                    [request]
                )
                all_results.extend(request_results)
                profiles.append(request_profile)
            merged_profile = _merge_worker_batch_profiles(*profiles)
            merged_profile["fallback_time_s"] += time.perf_counter() - fallback_start
            merged_profile["fallback_mode"] = "per_request"
            return all_results, merged_profile

    def stats(self) -> dict[str, Any]:
        agent_kind = getattr(self, "agent_kind", "lm")
        return {
            "model_path": self.model_path,
            "agent_kind": agent_kind,
            "worker_id": self.worker_id,
            "worker_slot": self.worker_slot,
            "device": self.device_label,
            "num_requests": self.num_requests,
            "num_batches": self.num_batches,
            "avg_batch_size": (self.num_requests / self.num_batches)
            if self.num_batches
            else 0.0,
        }
