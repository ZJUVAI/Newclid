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

_TRITON_LIBCUDA_CANDIDATE_DIRS = (
    "/usr/lib/x86_64-linux-gnu",
    "/usr/lib64",
    "/usr/lib",
    "/lib/x86_64-linux-gnu",
)


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


def _build_visual_messages(request: dict[str, Any], *, image: Any | None = None) -> list[dict[str, Any]]:
    image_input = request["img_path"] if image is None else image
    return [
        {"role": "system", "content": "You are a helpful assistant."},
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image_input},
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
    return text_prompt + request.get("response_prefix", "<aux> x00") + " " + request["new_point_name"]


def _resolve_visual_stop_tokens(processor, agent_kind: str) -> tuple[int | None, int | None]:
    if agent_kind == "qwen35":
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
        raise NotImplementedError("Batched visual generation does not support video inputs.")
    model_inputs = processor(
        text=texts,
        images=images,
        padding=True,
        return_tensors="pt",
        do_resize=False,
    ).to(model.device)
    return model_inputs


def _load_visual_processor(resolved_path: str):
    try:
        return ModelScopeAutoProcessor.from_pretrained(resolved_path)
    except Exception:
        logger.warning(
            "Failed to load VLM processor from local model path %s; falling back to Qwen/Qwen3-VL-2B-Instruct",
            resolved_path,
            exc_info=True,
        )
        return ModelScopeAutoProcessor.from_pretrained("Qwen/Qwen3-VL-2B-Instruct")


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
    pad_token_id, eos_token_id = _resolve_visual_stop_tokens(processor, agent_kind)

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


def _load_vllm_modules():
    os.environ["VLLM_ENABLE_V1_MULTIPROCESSING"] = "0"
    if "TRITON_LIBCUDA_PATH" not in os.environ:
        for candidate_dir in _TRITON_LIBCUDA_CANDIDATE_DIRS:
            if os.path.exists(os.path.join(candidate_dir, "libcuda.so.1")):
                os.environ["TRITON_LIBCUDA_PATH"] = candidate_dir
                break
    try:
        from vllm import LLM
        import vllm.envs as vllm_envs
    except ImportError as exc:
        raise ImportError(
            "vLLM runtime requested but the optional dependency 'vllm' is not installed."
        ) from exc
    vllm_envs.VLLM_ENABLE_V1_MULTIPROCESSING = False
    try:
        from vllm.sampling_params import BeamSearchParams
        from vllm.beam_search import get_beam_search_score
    except ImportError as exc:
        raise ImportError(
            "vLLM is installed, but the current version does not expose the beam-search API "
            "expected by this repo. Expected imports: "
            "`vllm.sampling_params.BeamSearchParams` and "
            "`vllm.beam_search.get_beam_search_score`."
        ) from exc
    return LLM, BeamSearchParams, get_beam_search_score


def _effective_vllm_max_num_seqs(configured_max_num_seqs: int, *, gpu_batch_size: int, decoding_size: int) -> int:
    return max(int(configured_max_num_seqs), int(gpu_batch_size) * int(decoding_size))


def _effective_vllm_max_logprobs(*, decoding_size: int, configured_max_logprobs: int = 20) -> int:
    return max(int(configured_max_logprobs), 2 * int(decoding_size))


def _compute_vllm_beam_score(
    sequence: Any,
    *,
    eos_token_id: int | None,
    get_beam_search_score,
) -> float:
    tokens = list(getattr(sequence, "tokens", []) or [])
    cumulative_logprob = float(getattr(sequence, "cum_logprob", 0.0))
    if eos_token_id is None:
        return cumulative_logprob
    return float(
        get_beam_search_score(
            tokens=tokens,
            cumulative_logprob=cumulative_logprob,
            eos_token_id=eos_token_id,
            length_penalty=1.0,
        )
    )


def _extract_vllm_continuation_text(processor, sequence: Any) -> str:
    full_text = getattr(sequence, "text", "") or ""
    orig_prompt = getattr(sequence, "orig_prompt", None) or {}
    decoder_prompt = orig_prompt.get("decoder_prompt", orig_prompt)
    prompt_text = decoder_prompt.get("prompt")
    if isinstance(prompt_text, str) and full_text.startswith(prompt_text):
        return full_text[len(prompt_text) :]

    prompt_token_ids = list(decoder_prompt.get("prompt_token_ids", []) or [])
    sequence_tokens = list(getattr(sequence, "tokens", []) or [])
    if prompt_token_ids and len(sequence_tokens) >= len(prompt_token_ids):
        continuation_tokens = sequence_tokens[len(prompt_token_ids) :]
        if continuation_tokens:
            return processor.tokenizer.decode(continuation_tokens, skip_special_tokens=True)
        return ""

    return full_text


def _generate_visual_aux_dsl_dict_batch_vllm(
    llm,
    processor,
    requests: list[dict[str, Any]],
    *,
    get_beam_search_score,
    beam_search_params_cls,
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
    prompts: list[dict[str, Any]] = []
    for request in requests:
        if "image" in request:
            image = request["image"]
            prompts.append(
                {
                    "prompt": _build_visual_prompt(processor, request),
                    "multi_modal_data": {"image": image.copy()},
                }
            )
            continue
        with Image.open(Path(request["img_path"])) as img:
            prompts.append(
                {
                    "prompt": _build_visual_prompt(processor, request),
                    "multi_modal_data": {"image": img.copy()},
                }
            )
    profile["input_build_time_s"] += time.perf_counter() - input_build_start

    _, eos_token_id = _resolve_visual_stop_tokens(processor, "vlm")
    beam_params = beam_search_params_cls(
        beam_width=decoding_size,
        max_tokens=100,
        temperature=0.0,
        ignore_eos=False,
    )

    generate_start = time.perf_counter()
    beam_outputs = llm.beam_search(prompts, beam_params, use_tqdm=False)
    profile["generate_time_s"] += time.perf_counter() - generate_start

    decode_start = time.perf_counter()
    results: list[dict[str, Any]] = []
    for request, output in zip(requests, beam_outputs):
        aux_dsl_dict: dict[str, float] = {}
        for sequence in getattr(output, "sequences", []):
            text = _extract_vllm_continuation_text(processor, sequence)
            aux_dsl = f'{request.get("response_prefix", "<aux> x00")} {request["new_point_name"]}{text}'
            if aux_dsl in aux_dsl_dict:
                continue
            aux_dsl_dict[aux_dsl] = _compute_vllm_beam_score(
                sequence,
                eos_token_id=eos_token_id,
                get_beam_search_score=get_beam_search_score,
            )
        results.append(
            {
                "request_id": request["request_id"],
                "aux_dsl_dict": aux_dsl_dict,
            }
        )
    profile["decode_time_s"] += time.perf_counter() - decode_start
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

    def stats(self) -> dict[str, Any]:
        return {
            "model_path": self.model_path,
            "agent_kind": self.agent_kind,
            "num_requests": self.num_requests,
            "num_batches": self.num_batches,
            "avg_batch_size": (self.num_requests / self.num_batches) if self.num_batches else 0.0,
        }


@ray.remote(num_cpus=1, num_gpus=1, max_concurrency=1)
class VisionModelWorker(_BaseVisionWorker):
    def __init__(self, model_path: str, agent_kind: str, torch_seed: int = 123):
        resolved_path = resolve_model_path(model_path)
        self.model_path = resolved_path
        self.agent_kind = agent_kind
        self.runtime = "transformers"
        self.torch_seed = int(torch_seed)
        torch.manual_seed(self.torch_seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed(self.torch_seed)
            torch.cuda.manual_seed_all(self.torch_seed)
        logger.info(
            "VisionModelWorker init start: agent_kind=%s model_path=%s torch_seed=%d",
            agent_kind,
            resolved_path,
            self.torch_seed,
        )
        if agent_kind == "vlm":
            self.model = Qwen3VLForConditionalGeneration.from_pretrained(
                resolved_path,
                torch_dtype="auto",
                device_map="auto",
                attn_implementation="flash_attention_2",
            )
            self.processor = _load_visual_processor(resolved_path)
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
            "VisionModelWorker init done: agent_kind=%s model_device=%s padding_side=%s torch_seed=%d",
            agent_kind,
            next(self.model.parameters()).device,
            self.processor.tokenizer.padding_side,
            self.torch_seed,
        )

    def warmup(self) -> dict[str, Any]:
        device = str(next(self.model.parameters()).device)
        return {
            "model_path": self.model_path,
            "agent_kind": self.agent_kind,
            "device": device,
            "padding_side": self.processor.tokenizer.padding_side,
            "torch_seed": self.torch_seed,
            "runtime": self.runtime,
        }

    @torch.no_grad()
    def generate_one(self, request: dict[str, Any]) -> dict[str, Any]:
        return self.generate_batch([request])

    @torch.no_grad()
    def generate_batch(self, requests: list[dict[str, Any]]) -> dict[str, Any]:
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


@ray.remote(num_cpus=1, num_gpus=1, max_concurrency=1)
class VLLMVisionModelWorker(_BaseVisionWorker):
    def __init__(
        self,
        model_path: str,
        agent_kind: str,
        torch_seed: int = 123,
        *,
        gpu_memory_utilization: float = 0.90,
        max_num_seqs: int = 128,
        gpu_batch_size: int = 1,
        decoding_size: int = 1,
        enforce_eager: bool = False,
    ):
        if agent_kind != "vlm":
            raise ValueError(f"Unsupported vision agent kind for vLLM runtime: {agent_kind}")
        resolved_path = resolve_model_path(model_path)
        self.model_path = resolved_path
        self.agent_kind = agent_kind
        self.runtime = "vllm"
        self.torch_seed = int(torch_seed)
        self.gpu_memory_utilization = float(gpu_memory_utilization)
        self.configured_max_num_seqs = int(max_num_seqs)
        self.gpu_batch_size = int(gpu_batch_size)
        self.decoding_size = int(decoding_size)
        self.max_num_seqs = _effective_vllm_max_num_seqs(
            self.configured_max_num_seqs,
            gpu_batch_size=self.gpu_batch_size,
            decoding_size=self.decoding_size,
        )
        self.max_logprobs = _effective_vllm_max_logprobs(decoding_size=self.decoding_size)
        self.enforce_eager = bool(enforce_eager)
        self.vllm_distributed_executor_backend = "uni"
        torch.manual_seed(self.torch_seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed(self.torch_seed)
            torch.cuda.manual_seed_all(self.torch_seed)
        logger.info(
            "VLLMVisionModelWorker init start: agent_kind=%s model_path=%s torch_seed=%d gpu_memory_utilization=%.2f configured_max_num_seqs=%d effective_max_num_seqs=%d max_logprobs=%d gpu_batch_size=%d decoding_size=%d enforce_eager=%s",
            agent_kind,
            resolved_path,
            self.torch_seed,
            self.gpu_memory_utilization,
            self.configured_max_num_seqs,
            self.max_num_seqs,
            self.max_logprobs,
            self.gpu_batch_size,
            self.decoding_size,
            self.enforce_eager,
        )
        llm_cls, beam_search_params_cls, get_beam_search_score = _load_vllm_modules()
        self.llm = llm_cls(
            model=resolved_path,
            trust_remote_code=True,
            tensor_parallel_size=1,
            distributed_executor_backend=self.vllm_distributed_executor_backend,
            gpu_memory_utilization=self.gpu_memory_utilization,
            max_num_seqs=self.max_num_seqs,
            max_logprobs=self.max_logprobs,
            enforce_eager=self.enforce_eager,
            limit_mm_per_prompt={"image": 1},
        )
        self.beam_search_params_cls = beam_search_params_cls
        self.get_beam_search_score = get_beam_search_score
        self.processor = _load_visual_processor(resolved_path)
        self.processor.tokenizer.padding_side = "left"
        self.num_requests = 0
        self.num_batches = 0
        self._warmup_profile: dict[str, Any] | None = None
        logger.info(
            "VLLMVisionModelWorker init done: agent_kind=%s padding_side=%s torch_seed=%d distributed_executor_backend=%s",
            agent_kind,
            self.processor.tokenizer.padding_side,
            self.torch_seed,
            self.vllm_distributed_executor_backend,
        )

    def warmup(self) -> dict[str, Any]:
        info = {
            "model_path": self.model_path,
            "agent_kind": self.agent_kind,
            "device": "cuda",
            "padding_side": self.processor.tokenizer.padding_side,
            "torch_seed": self.torch_seed,
            "runtime": self.runtime,
            "gpu_memory_utilization": self.gpu_memory_utilization,
            "configured_max_num_seqs": self.configured_max_num_seqs,
            "max_num_seqs": self.max_num_seqs,
            "max_logprobs": self.max_logprobs,
            "gpu_batch_size": self.gpu_batch_size,
            "decoding_size": self.decoding_size,
            "enforce_eager": self.enforce_eager,
            "distributed_executor_backend": self.vllm_distributed_executor_backend,
        }
        if self._warmup_profile is None:
            self._warmup_profile = self._run_warmup_request()
        info["warmup_profile"] = dict(self._warmup_profile)
        return info

    def _run_warmup_request(self) -> dict[str, Any]:
        warmup_request = {
            "request_id": "__warmup__",
            "query": "Construct one auxiliary point.",
            "new_point_name": "a",
            "response_prefix": "<aux> x00",
            "with_predicate": False,
            "decoding_size": 1,
        }
        try:
            generate_start = time.perf_counter()
            _generate_visual_aux_dsl_dict_batch_vllm(
                self.llm,
                self.processor,
                [{**warmup_request, "img_path": "__warmup__", "image": Image.new("RGB", (32, 32), color="white")}],
                get_beam_search_score=self.get_beam_search_score,
                beam_search_params_cls=self.beam_search_params_cls,
            )
            return {
                "status": "ok",
                "elapsed_s": time.perf_counter() - generate_start,
            }
        except Exception as exc:
            logger.warning("vLLM warmup request failed: %s", exc)
            return {
                "status": "error",
                "error": str(exc),
            }

    def generate_one(self, request: dict[str, Any]) -> dict[str, Any]:
        return self.generate_batch([request])

    def generate_batch(self, requests: list[dict[str, Any]]) -> dict[str, Any]:
        if not requests:
            return {
                "results": [],
                "worker_batch_profile": _create_worker_batch_profile(batch_size=0),
            }
        logger.debug(
            "VLLMVisionModelWorker generate_batch start: agent_kind=%s batch_size=%d request_ids=%s",
            self.agent_kind,
            len(requests),
            [request.get("request_id", "<missing>") for request in requests],
        )
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

    def _generate_batch_with_fallback(self, requests: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        try:
            return _generate_visual_aux_dsl_dict_batch_vllm(
                self.llm,
                self.processor,
                requests,
                get_beam_search_score=self.get_beam_search_score,
                beam_search_params_cls=self.beam_search_params_cls,
            )
        except Exception as exc:
            if len(requests) == 1:
                logger.exception("vLLM visual generate failed for request_id=%s", requests[0].get("request_id"))
                profile = _create_worker_batch_profile(batch_size=1)
                profile["fallback_mode"] = "single_error"
                return [_empty_result(requests[0], error=str(exc), batch_size=1)], profile
            if _is_oom_error(exc):
                logger.warning(
                    "vLLM visual batched generate hit OOM; splitting batch_size=%d request_ids=%s",
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
                "vLLM visual batched generate failed; falling back to per-request execution for request_ids=%s",
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
