from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

import cairosvg  # noqa: F401
import ray
import torch
from modelscope import AutoProcessor as ModelScopeAutoProcessor
from modelscope import Qwen3VLForConditionalGeneration
from qwen_vl_utils import process_vision_info
from transformers import AutoProcessor as TransformersAutoProcessor
from transformers import Qwen3_5ForConditionalGeneration, StoppingCriteria, StoppingCriteriaList
from transformers.utils import logging as hf_logging

from newclid.agent.runtime.batched_decode import decode_batched_continuations
from newclid.agent.runtime.model_resolution import resolve_model_path
from newclid.agent.runtime.text_worker import (
    _accumulate_request_profile,
    _build_request_profile,
    _count_generated_tokens,
    _count_prompt_tokens,
    _create_worker_batch_profile,
    _merge_worker_batch_profiles,
)


os.environ["TOKENIZERS_PARALLELISM"] = "false"

logger = logging.getLogger(__name__)
hf_logging.disable_progress_bar()
hf_logging.set_verbosity_error()

_QWEN3_VL_BASE_PROCESSOR_REPO = "Qwen/Qwen3-VL-2B-Instruct"
_QWEN3_VL_BASE_PROCESSOR_CACHE = (
    Path.home()
    / ".cache"
    / "modelscope"
    / "hub"
    / "models"
    / "Qwen"
    / "Qwen3-VL-2B-Instruct"
)


def _reset_torch_seed(torch_seed: int) -> None:
    # Qwen3-VL beam search on GPU is not stable unless we reset the torch RNG
    # state before each generate() call. Seeding only once at worker startup
    # is insufficient for reproducible text-only evaluation runs.
    torch.manual_seed(torch_seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(torch_seed)
        torch.cuda.manual_seed_all(torch_seed)


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


def _request_group_key(request: dict[str, Any]) -> tuple[Any, ...]:
    return (
        request.get("with_predicate", False),
        request.get("decoding_size"),
        request.get("response_prefix", "<aux> x00"),
    )


def _build_visual_messages(request: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": "You are a helpful assistant."},
        {
            "role": "user",
            "content": [
                {"type": "image", "image": request["img_path"]},
                {"type": "text", "text": request["query"]},
            ],
        },
    ]


def _build_text_only_messages(request: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": "You are a helpful assistant."},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": request["query"]},
            ],
        },
    ]


def _build_visual_prompt(processor, request: dict[str, Any]) -> str:
    text_prompt = processor.apply_chat_template(
        _build_visual_messages(request),
        tokenize=False,
        add_generation_prompt=True,
    )
    return (
        text_prompt
        + request.get("response_prefix", "<aux> x00")
        + " "
        + request["new_point_name"]
    )


def _build_text_only_prompt(processor, request: dict[str, Any]) -> str:
    text_prompt = processor.apply_chat_template(
        _build_text_only_messages(request),
        tokenize=False,
        add_generation_prompt=True,
    )
    return (
        text_prompt
        + request.get("response_prefix", "<aux> x00")
        + " "
        + request["new_point_name"]
    )


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


def _resolve_visual_stop_tokens(
    processor, agent_kind: str
) -> tuple[int | None, int | None]:
    if agent_kind == "qwen35_vl":
        pad_token_id = processor.tokenizer.pad_token_id
        eos_token_id = processor.tokenizer.encode(" ;", add_special_tokens=False)[0]
    else:
        pad_token_id = 151643
        eos_token_id = 2587
    return pad_token_id, eos_token_id


def _build_visual_batch_inputs(
    model,
    processor,
    requests: list[dict[str, Any]],
) -> dict[str, Any]:
    texts: list[str] = []
    images: list[Any] = []
    videos: list[Any] = []
    for request in requests:
        messages = _build_visual_messages(request)
        image_inputs, video_inputs = process_vision_info(messages, image_patch_size=16)
        final_text = _build_visual_prompt(processor, request)
        if len(image_inputs) != 1:
            raise ValueError(
                f"Expected exactly one image input per visual request, got {len(image_inputs)} "
                f"for request_id={request.get('request_id')}"
            )
        texts.append(final_text)
        images.append(image_inputs[0])
        if video_inputs:
            if len(video_inputs) != 1:
                raise ValueError(
                    f"Expected at most one video input per visual request, got {len(video_inputs)} "
                    f"for request_id={request.get('request_id')}"
                )
            videos.append(video_inputs[0])
        else:
            videos.append(None)
    if any(video is not None for video in videos):
        raise NotImplementedError(
            "Batched visual generation does not support video inputs."
        )
    return processor(
        text=texts,
        images=images,
        padding=True,
        return_tensors="pt",
        do_resize=False,
    ).to(model.device)


def _build_text_only_batch_inputs(
    model,
    processor,
    requests: list[dict[str, Any]],
) -> dict[str, Any]:
    prompts = [_build_text_only_prompt(processor, request) for request in requests]
    return processor(
        text=prompts,
        padding=True,
        return_tensors="pt",
    ).to(model.device)


def _load_visual_processor():
    processor_source = (
        str(_QWEN3_VL_BASE_PROCESSOR_CACHE)
        if _QWEN3_VL_BASE_PROCESSOR_CACHE.exists()
        else _QWEN3_VL_BASE_PROCESSOR_REPO
    )
    return ModelScopeAutoProcessor.from_pretrained(processor_source)


def generate_visual_aux_dsl_dict_batch(
    model,
    processor,
    requests: list[dict[str, Any]],
    *,
    agent_kind: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not requests:
        return [], _create_worker_batch_profile(batch_size=0)
    if any(request.get("with_predicate", False) for request in requests):
        raise NotImplementedError(
            "Batched visual generation currently supports with_predicate=False only."
        )
    decoding_size = int(requests[0]["decoding_size"])
    if any(int(request["decoding_size"]) != decoding_size for request in requests):
        raise ValueError("All requests in a batch must share decoding_size.")

    profile = _create_worker_batch_profile(batch_size=len(requests))
    input_build_start = time.perf_counter()
    model_inputs = _build_visual_batch_inputs(model, processor, requests)
    profile["input_build_time_s"] += time.perf_counter() - input_build_start
    pad_token_id, eos_token_id = _resolve_visual_stop_tokens(processor, agent_kind)
    stop_ids = processor.tokenizer.encode(" </aux>", add_special_tokens=False)
    stopping_criteria = StoppingCriteriaList([
        _EndAuxTagCriteria(stop_ids, device=model.device)
    ])

    generate_start = time.perf_counter()
    generated_output = model.generate(
        **model_inputs,
        max_new_tokens=512,
        num_beams=decoding_size,
        num_return_sequences=decoding_size,
        pad_token_id=pad_token_id,
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
            eos_token_id=None,
        )
        for index, sequence in enumerate(generated_output.sequences)
    ]
    decode_start = time.perf_counter()
    rebuilt_outputs = decode_batched_continuations(
        requests=requests,
        model_inputs=model_inputs,
        sequences=generated_output.sequences,
        decoding_size=decoding_size,
        decode_batch=lambda batch: processor.batch_decode(
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


def generate_qwen3_text_only_aux_dsl_dict_batch(
    model,
    processor,
    requests: list[dict[str, Any]],
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
    model_inputs = _build_text_only_batch_inputs(model, processor, requests)
    profile["input_build_time_s"] += time.perf_counter() - input_build_start
    pad_token_id = processor.tokenizer.pad_token_id
    stop_ids = processor.tokenizer.encode(" </aux>", add_special_tokens=False)
    stopping_criteria = StoppingCriteriaList([
        _EndAuxTagCriteria(stop_ids, device=model.device)
    ])

    generate_start = time.perf_counter()
    generated_output = model.generate(
        **model_inputs,
        max_new_tokens=512,
        num_beams=decoding_size,
        num_return_sequences=decoding_size,
        pad_token_id=pad_token_id,
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
            eos_token_id=None,
        )
        for index, sequence in enumerate(generated_output.sequences)
    ]
    decode_start = time.perf_counter()
    rebuilt_outputs = decode_batched_continuations(
        requests=requests,
        model_inputs=model_inputs,
        sequences=generated_output.sequences,
        decoding_size=decoding_size,
        decode_batch=lambda batch: processor.batch_decode(
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


class _BaseVisionWorker:
    def _finalize_batch(
        self,
        requests: list[dict[str, Any]],
        results: list[dict[str, Any]],
        worker_batch_profile: dict[str, Any],
        *,
        perf_start: float,
        inference_start: float,
    ) -> dict[str, Any]:
        worker_finished_at_unix_s = time.time()
        inference_time_s = worker_finished_at_unix_s - inference_start
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

    def stats(self) -> dict[str, Any]:
        return {
            "model_path": self.model_path,
            "agent_kind": self.agent_kind,
            "worker_id": self.worker_id,
            "worker_slot": self.worker_slot,
            "device": self.device_label,
            "num_requests": self.num_requests,
            "num_batches": self.num_batches,
            "avg_batch_size": (self.num_requests / self.num_batches)
            if self.num_batches
            else 0.0,
        }


@ray.remote(num_cpus=1, num_gpus=1, max_concurrency=1)
class VisionModelWorker(_BaseVisionWorker):
    def __init__(
        self,
        model_path: str,
        agent_kind: str,
        torch_seed: int = 123,
        worker_slot: int = 0,
    ):
        resolved_path = resolve_model_path(model_path)
        self.model_path = resolved_path
        self.agent_kind = agent_kind
        self.runtime = "transformers"
        self.torch_seed = int(torch_seed)
        self.worker_slot = int(worker_slot)
        self.worker_id = f"gpu:{self.worker_slot}"
        self.device_label = f"cuda:{self.worker_slot}"
        _reset_torch_seed(self.torch_seed)
        logger.info(
            "VisionModelWorker init start: agent_kind=%s model_path=%s torch_seed=%d worker_id=%s",
            agent_kind,
            resolved_path,
            self.torch_seed,
            self.worker_id,
        )
        if agent_kind == "vlm":
            self.model = Qwen3VLForConditionalGeneration.from_pretrained(
                resolved_path,
                torch_dtype="auto",
                device_map="auto",
                attn_implementation="flash_attention_2",
            )
            self.processor = _load_visual_processor()
        elif agent_kind == "qwen35_vl":
            self.model = Qwen3_5ForConditionalGeneration.from_pretrained(
                resolved_path,
                torch_dtype="auto",
                device_map="auto",
                attn_implementation="flash_attention_2",
                trust_remote_code=True,
            )
            self.processor = TransformersAutoProcessor.from_pretrained(
                resolved_path,
                trust_remote_code=True,
            )
        else:
            raise ValueError(f"Unsupported vision agent kind: {agent_kind}")
        self.processor.tokenizer.padding_side = "left"
        self.num_requests = 0
        self.num_batches = 0
        logger.info(
            "VisionModelWorker init done: agent_kind=%s model_device=%s padding_side=%s torch_seed=%d worker_id=%s",
            agent_kind,
            next(self.model.parameters()).device,
            self.processor.tokenizer.padding_side,
            self.torch_seed,
            self.worker_id,
        )

    def warmup(self) -> dict[str, Any]:
        return {
            "model_path": self.model_path,
            "agent_kind": self.agent_kind,
            "device": str(next(self.model.parameters()).device),
            "padding_side": self.processor.tokenizer.padding_side,
            "torch_seed": self.torch_seed,
            "runtime": self.runtime,
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
        logger.debug(
            "VisionModelWorker generate_batch start: agent_kind=%s batch_size=%d request_ids=%s",
            self.agent_kind,
            len(requests),
            [request.get("request_id", "<missing>") for request in requests],
        )
        _reset_torch_seed(self.torch_seed)
        inference_start = time.time()
        perf_start = time.perf_counter()
        results, worker_batch_profile = self._generate_batch_with_fallback(requests)
        logger.debug(
            "VisionModelWorker generate_batch done: agent_kind=%s batch_size=%d",
            self.agent_kind,
            len(requests),
        )
        return self._finalize_batch(
            requests,
            results,
            worker_batch_profile,
            perf_start=perf_start,
            inference_start=inference_start,
        )

    def _generate_batch_with_fallback(
        self, requests: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
        order: list[tuple[Any, str]] = []
        for request in requests:
            group_key = _request_group_key(request)
            grouped.setdefault(group_key, []).append(request)
            order.append((group_key, request["request_id"]))

        grouped_results: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
        grouped_profiles: dict[tuple[Any, ...], dict[str, Any]] = {}
        for group_key, group_requests in grouped.items():
            group_results, group_profile = self._generate_group_with_fallback(
                group_requests
            )
            grouped_results[group_key] = group_results
            grouped_profiles[group_key] = group_profile

        grouped_maps = {
            group_key: {result["request_id"]: result for result in results}
            for group_key, results in grouped_results.items()
        }
        return (
            [grouped_maps[group_key][request_id] for group_key, request_id in order],
            _merge_worker_batch_profiles(*grouped_profiles.values()),
        )

    def _generate_group_with_fallback(
        self, requests: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        try:
            return generate_visual_aux_dsl_dict_batch(
                self.model,
                self.processor,
                requests,
                agent_kind=self.agent_kind,
            )
        except Exception as exc:
            if len(requests) == 1:
                logger.exception(
                    "Visual generate failed for request_id=%s agent_kind=%s",
                    requests[0].get("request_id"),
                    self.agent_kind,
                )
                profile = _create_worker_batch_profile(batch_size=1)
                profile["fallback_mode"] = "single_error"
                return [
                    _empty_result(requests[0], error=str(exc), batch_size=1)
                ], profile
            if _is_oom_error(exc):
                logger.warning(
                    "Visual batched generate hit OOM; splitting batch_size=%d request_ids=%s",
                    len(requests),
                    [request.get("request_id") for request in requests],
                )
                fallback_start = time.perf_counter()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                midpoint = len(requests) // 2
                left_results, left_profile = self._generate_group_with_fallback(
                    requests[:midpoint]
                )
                right_results, right_profile = self._generate_group_with_fallback(
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
                "Visual batched generate failed; falling back to per-request execution for request_ids=%s",
                [request.get("request_id") for request in requests],
            )
            fallback_start = time.perf_counter()
            all_results: list[dict[str, Any]] = []
            profiles: list[dict[str, Any]] = []
            for request in requests:
                request_results, request_profile = self._generate_group_with_fallback(
                    [request]
                )
                all_results.extend(request_results)
                profiles.append(request_profile)
            merged_profile = _merge_worker_batch_profiles(*profiles)
            merged_profile["fallback_time_s"] += time.perf_counter() - fallback_start
            merged_profile["fallback_mode"] = "per_request"
            return all_results, merged_profile


@ray.remote(num_cpus=1, num_gpus=1, max_concurrency=1)
class Qwen3VLTextWorker(_BaseVisionWorker):
    def __init__(
        self,
        model_path: str,
        agent_kind: str,
        torch_seed: int = 123,
        worker_slot: int = 0,
    ):
        resolved_path = resolve_model_path(model_path)
        self.model_path = resolved_path
        self.agent_kind = agent_kind
        self.runtime = "transformers"
        self.torch_seed = int(torch_seed)
        self.worker_slot = int(worker_slot)
        self.worker_id = f"gpu:{self.worker_slot}"
        self.device_label = f"cuda:{self.worker_slot}"
        _reset_torch_seed(self.torch_seed)
        logger.info(
            "Qwen3VLTextWorker init start: model_path=%s torch_seed=%d worker_id=%s",
            resolved_path,
            self.torch_seed,
            self.worker_id,
        )
        self.model = Qwen3VLForConditionalGeneration.from_pretrained(
            resolved_path,
            torch_dtype="auto",
            device_map="auto",
            attn_implementation="flash_attention_2",
        )
        self.processor = _load_visual_processor()
        self.processor.tokenizer.padding_side = "left"
        self.num_requests = 0
        self.num_batches = 0
        logger.info(
            "Qwen3VLTextWorker init done: model_device=%s padding_side=%s torch_seed=%d worker_id=%s",
            next(self.model.parameters()).device,
            self.processor.tokenizer.padding_side,
            self.torch_seed,
            self.worker_id,
        )

    def warmup(self) -> dict[str, Any]:
        return {
            "model_path": self.model_path,
            "agent_kind": self.agent_kind,
            "device": str(next(self.model.parameters()).device),
            "padding_side": self.processor.tokenizer.padding_side,
            "torch_seed": self.torch_seed,
            "runtime": self.runtime,
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
        _reset_torch_seed(self.torch_seed)
        inference_start = time.time()
        perf_start = time.perf_counter()
        results, worker_batch_profile = self._generate_batch_with_fallback(requests)
        return self._finalize_batch(
            requests,
            results,
            worker_batch_profile,
            perf_start=perf_start,
            inference_start=inference_start,
        )

    def _generate_batch_with_fallback(
        self, requests: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        try:
            return generate_qwen3_text_only_aux_dsl_dict_batch(
                self.model,
                self.processor,
                requests,
            )
        except Exception as exc:
            if len(requests) == 1:
                logger.exception(
                    "Qwen3VLTextWorker generate failed for request_id=%s",
                    requests[0].get("request_id"),
                )
                profile = _create_worker_batch_profile(batch_size=1)
                profile["fallback_mode"] = "single_error"
                return [
                    _empty_result(requests[0], error=str(exc), batch_size=1)
                ], profile
            if _is_oom_error(exc):
                logger.warning(
                    "Qwen3VLTextWorker batched generate hit OOM; splitting batch_size=%d request_ids=%s",
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
                "Qwen3VLTextWorker batched generate failed; falling back to per-request execution for request_ids=%s",
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
