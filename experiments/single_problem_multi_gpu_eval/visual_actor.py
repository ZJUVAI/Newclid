from __future__ import annotations

import logging
import os
import time
from typing import Any

import cairosvg  # noqa: F401
import ray
import torch
from modelscope import AutoProcessor as ModelScopeAutoProcessor
from modelscope import Qwen3VLForConditionalGeneration
from PIL import Image, ImageOps  # noqa: F401
from qwen_vl_utils import process_vision_info
from transformers import AutoProcessor as TransformersAutoProcessor
from transformers import Qwen3_5ForConditionalGeneration
from transformers.utils import logging as hf_logging

from experiments.single_problem_multi_gpu_eval.batched_decode import decode_batched_continuations
from experiments.single_problem_multi_gpu_eval.lm_actor import (
    _create_worker_batch_profile,
    _merge_worker_batch_profiles,
    resolve_model_path,
)


os.environ["TOKENIZERS_PARALLELISM"] = "false"

logger = logging.getLogger(__name__)
hf_logging.disable_progress_bar()
hf_logging.set_verbosity_error()

AUX_PREDICATES: list[str] = []


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


def _request_group_key(request: dict[str, Any]) -> tuple[Any, ...]:
    return (
        request.get("with_predicate", False),
        request.get("decoding_size"),
        request.get("response_prefix", "<aux> x00"),
    )


def _build_visual_batch_inputs(
    model,
    processor,
    requests: list[dict[str, Any]],
) -> dict[str, Any]:
    base_texts: list[str] = []
    texts: list[str] = []
    images: list[Any] = []
    videos: list[Any] = []
    for request in requests:
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": request["img_path"]},
                    {"type": "text", "text": request["query"]},
                ],
            },
        ]
        image_inputs, video_inputs = process_vision_info(messages, image_patch_size=16)
        text_prompt = processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        base_texts.append(text_prompt)
        final_text = text_prompt + request.get("response_prefix", "<aux> x00") + " " + request["new_point_name"]
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
        raise NotImplementedError("Batched visual generation does not support video inputs.")
    model_inputs = processor(
        text=texts,
        images=images,
        padding=True,
        return_tensors="pt",
        do_resize=False,
    ).to(model.device)
    return model_inputs


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
        raise NotImplementedError("Batched visual generation currently supports with_predicate=False only.")
    decoding_size = int(requests[0]["decoding_size"])
    if any(int(request["decoding_size"]) != decoding_size for request in requests):
        raise ValueError("All requests in a batch must share decoding_size.")

    profile = _create_worker_batch_profile(batch_size=len(requests))
    input_build_start = time.perf_counter()
    model_inputs = _build_visual_batch_inputs(model, processor, requests)
    profile["input_build_time_s"] += time.perf_counter() - input_build_start
    if agent_kind == "qwen35":
        pad_token_id = processor.tokenizer.pad_token_id
        eos_token_id = processor.tokenizer.encode(" ;", add_special_tokens=False)[0]
    else:
        pad_token_id = 151643
        eos_token_id = 2587

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
        decode_batch=lambda batch: processor.batch_decode(batch, skip_special_tokens=True),
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
class VisionModelWorker:
    def __init__(self, model_path: str, agent_kind: str):
        resolved_path = resolve_model_path(model_path)
        self.model_path = resolved_path
        self.agent_kind = agent_kind
        logger.info(
            "VisionModelWorker init start: agent_kind=%s model_path=%s",
            agent_kind,
            resolved_path,
        )
        if agent_kind == "vlm":
            self.model = Qwen3VLForConditionalGeneration.from_pretrained(
                resolved_path,
                torch_dtype="auto",
                device_map="auto",
                attn_implementation="flash_attention_2",
            )
            self.processor = ModelScopeAutoProcessor.from_pretrained("Qwen/Qwen3-VL-2B-Instruct")
        elif agent_kind == "qwen35":
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
            "VisionModelWorker init done: agent_kind=%s model_device=%s padding_side=%s",
            agent_kind,
            next(self.model.parameters()).device,
            self.processor.tokenizer.padding_side,
        )

    def warmup(self) -> dict[str, Any]:
        device = str(next(self.model.parameters()).device)
        logger.debug(
            "VisionModelWorker warmup: agent_kind=%s model_path=%s device=%s",
            self.agent_kind,
            self.model_path,
            device,
        )
        return {
            "model_path": self.model_path,
            "agent_kind": self.agent_kind,
            "device": device,
            "padding_side": self.processor.tokenizer.padding_side,
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
        logger.debug(
            "VisionModelWorker generate_batch start: agent_kind=%s batch_size=%d request_ids=%s",
            self.agent_kind,
            len(requests),
            [request.get("request_id", "<missing>") for request in requests],
        )
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
        logger.debug(
            "VisionModelWorker generate_batch done: agent_kind=%s batch_size=%d total_requests=%d total_batches=%d",
            self.agent_kind,
            batch_size,
            self.num_requests,
            self.num_batches,
        )
        return {
            "results": results,
            "worker_batch_profile": worker_batch_profile,
        }

    def _generate_batch_with_fallback(self, requests: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
        order: list[tuple[Any, str]] = []
        for request in requests:
            group_key = _request_group_key(request)
            grouped.setdefault(group_key, []).append(request)
            order.append((group_key, request["request_id"]))

        grouped_results: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
        grouped_profiles: dict[tuple[Any, ...], dict[str, Any]] = {}
        for group_key, group_requests in grouped.items():
            group_results, group_profile = self._generate_group_with_fallback(group_requests)
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

    def _generate_group_with_fallback(self, requests: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
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
                return [_empty_result(requests[0], error=str(exc), batch_size=1)], profile
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
                left_results, left_profile = self._generate_group_with_fallback(requests[:midpoint])
                right_results, right_profile = self._generate_group_with_fallback(requests[midpoint:])
                merged_profile = _merge_worker_batch_profiles(left_profile, right_profile)
                merged_profile["fallback_time_s"] += time.perf_counter() - fallback_start
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
                request_results, request_profile = self._generate_group_with_fallback([request])
                all_results.extend(request_results)
                profiles.append(request_profile)
            merged_profile = _merge_worker_batch_profiles(*profiles)
            merged_profile["fallback_time_s"] += time.perf_counter() - fallback_start
            merged_profile["fallback_mode"] = "per_request"
            return all_results, merged_profile

    def stats(self) -> dict[str, Any]:
        return {
            "model_path": self.model_path,
            "agent_kind": self.agent_kind,
            "num_requests": self.num_requests,
            "num_batches": self.num_batches,
            "avg_batch_size": (self.num_requests / self.num_batches) if self.num_batches else 0.0,
        }
