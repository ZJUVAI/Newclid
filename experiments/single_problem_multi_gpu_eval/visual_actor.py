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
    _accumulate_request_profile,
    _build_request_profile,
    _count_generated_tokens,
    _count_prompt_tokens,
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
_QWEN3_VL_BASE_PROCESSOR_REPO = "Qwen/Qwen3-VL-2B-Instruct"
_QWEN3_VL_BASE_PROCESSOR_CACHE = (
    Path.home() / ".cache" / "modelscope" / "hub" / "models" / "Qwen" / "Qwen3-VL-2B-Instruct"
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


def _extract_vllm_prompt_token_ids_from_output(output: Any) -> list[int]:
    prompt_token_ids = list(getattr(output, "prompt_token_ids", []) or [])
    if prompt_token_ids:
        return prompt_token_ids
    for sequence in getattr(output, "sequences", []) or []:
        orig_prompt = getattr(sequence, "orig_prompt", None) or {}
        decoder_prompt = orig_prompt.get("decoder_prompt", orig_prompt)
        prompt_token_ids = list(decoder_prompt.get("prompt_token_ids", []) or [])
        if prompt_token_ids:
            return prompt_token_ids
    for completion in getattr(output, "outputs", []) or []:
        prompt_token_ids = list(getattr(completion, "prompt_token_ids", []) or [])
        if prompt_token_ids:
            return prompt_token_ids
    return []


def _extract_vllm_first_token_latency_s(output: Any) -> float | None:
    candidates = [getattr(output, "metrics", None)]
    candidates.extend(getattr(output, "outputs", []) or [])
    candidates.extend(getattr(output, "sequences", []) or [])
    for candidate in candidates:
        metrics = getattr(candidate, "metrics", candidate)
        arrival_time = getattr(metrics, "arrival_time", None)
        first_token_time = getattr(metrics, "first_token_time", None)
        if arrival_time is None or first_token_time is None:
            continue
        latency = float(first_token_time) - float(arrival_time)
        if latency >= 0.0:
            return latency
    return None


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
        from vllm.sampling_params import SamplingParams
        from vllm.beam_search import get_beam_search_score
    except ImportError as exc:
        raise ImportError(
            "vLLM is installed, but the current version does not expose the beam-search API "
            "expected by this repo. Expected imports: "
            "`vllm.sampling_params.BeamSearchParams`, "
            "`vllm.sampling_params.SamplingParams`, and "
            "`vllm.beam_search.get_beam_search_score`."
        ) from exc
    return LLM, BeamSearchParams, SamplingParams, get_beam_search_score


def _effective_vllm_max_num_seqs(configured_max_num_seqs: int, *, gpu_batch_size: int, decoding_size: int) -> int:
    return max(int(configured_max_num_seqs), int(gpu_batch_size) * int(decoding_size))


def _effective_vllm_max_logprobs(
    *,
    decoding_size: int,
    generation_mode: str = "beam",
    configured_max_logprobs: int = 20,
) -> int:
    if generation_mode == "beam":
        return max(int(configured_max_logprobs), 2 * int(decoding_size))
    return int(configured_max_logprobs)


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


def _build_vllm_prompts(processor, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
    return prompts


def _normalize_vllm_generate_score(
    token_ids: list[int] | tuple[int, ...] | None,
    cumulative_logprob: float | None,
    *,
    eos_token_id: int | None,
) -> float:
    if cumulative_logprob is None:
        return float("-inf")
    tokens = list(token_ids or [])
    if not tokens:
        return float(cumulative_logprob)
    effective_len = len(tokens)
    if eos_token_id is not None and tokens[-1] == eos_token_id:
        effective_len -= 1
    effective_len = max(effective_len, 1)
    return float(cumulative_logprob) / float(effective_len)


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
    prompts = _build_vllm_prompts(processor, requests)
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
        prompt_token_ids = _extract_vllm_prompt_token_ids_from_output(output)
        prompt_token_count = len(prompt_token_ids)
        sequence_token_counts: list[int] = []
        raw_candidate_count = 0
        for sequence in getattr(output, "sequences", []):
            raw_candidate_count += 1
            text = _extract_vllm_continuation_text(processor, sequence)
            aux_dsl = f'{request.get("response_prefix", "<aux> x00")} {request["new_point_name"]}{text}'
            sequence_token_counts.append(
                _count_generated_tokens(
                    list(getattr(sequence, "tokens", []) or []),
                    prompt_token_count=prompt_token_count,
                    pad_token_id=None,
                    eos_token_id=eos_token_id,
                )
            )
            if aux_dsl in aux_dsl_dict:
                continue
            aux_dsl_dict[aux_dsl] = _compute_vllm_beam_score(
                sequence,
                eos_token_id=eos_token_id,
                get_beam_search_score=get_beam_search_score,
            )
        request_profile = _build_request_profile(
            prompt_token_count=prompt_token_count,
            generated_token_counts=sequence_token_counts,
            raw_candidate_count=raw_candidate_count,
            unique_candidate_count=len(aux_dsl_dict),
            first_token_latency_s=_extract_vllm_first_token_latency_s(output),
        )
        _accumulate_request_profile(profile, request_profile)
        results.append(
            {
                "request_id": request["request_id"],
                "aux_dsl_dict": aux_dsl_dict,
                "request_profile": request_profile,
            }
        )
    profile["decode_time_s"] += time.perf_counter() - decode_start
    return results, profile


def _generate_visual_aux_dsl_dict_batch_vllm_sampling(
    llm,
    processor,
    requests: list[dict[str, Any]],
    *,
    sampling_params_cls,
    temperature: float,
    top_p: float,
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
    prompts = _build_vllm_prompts(processor, requests)
    profile["input_build_time_s"] += time.perf_counter() - input_build_start

    _, eos_token_id = _resolve_visual_stop_tokens(processor, "vlm")
    sampling_params = sampling_params_cls(
        n=decoding_size,
        max_tokens=100,
        temperature=float(temperature),
        top_p=float(top_p),
        logprobs=0,
        stop_token_ids=None if eos_token_id is None else [eos_token_id],
        ignore_eos=False,
        detokenize=True,
    )

    generate_start = time.perf_counter()
    request_outputs = llm.generate(prompts, sampling_params, use_tqdm=False)
    profile["generate_time_s"] += time.perf_counter() - generate_start

    decode_start = time.perf_counter()
    results: list[dict[str, Any]] = []
    for request, output in zip(requests, request_outputs):
        scored_candidates: dict[str, float] = {}
        prompt_token_count = len(_extract_vllm_prompt_token_ids_from_output(output))
        sequence_token_counts: list[int] = []
        for completion in getattr(output, "outputs", []):
            text = getattr(completion, "text", "") or ""
            aux_dsl = f'{request.get("response_prefix", "<aux> x00")} {request["new_point_name"]}{text}'
            sequence_token_counts.append(
                _count_generated_tokens(
                    list(getattr(completion, "token_ids", []) or []),
                    prompt_token_count=0,
                    pad_token_id=None,
                    eos_token_id=eos_token_id,
                )
            )
            score = _normalize_vllm_generate_score(
                getattr(completion, "token_ids", None),
                getattr(completion, "cumulative_logprob", None),
                eos_token_id=eos_token_id,
            )
            prev_score = scored_candidates.get(aux_dsl)
            if prev_score is None or score > prev_score:
                scored_candidates[aux_dsl] = score
        ranked_aux_dsl_dict = dict(
            sorted(
                scored_candidates.items(),
                key=lambda item: (-item[1], item[0]),
            )
        )
        request_profile = _build_request_profile(
            prompt_token_count=prompt_token_count,
            generated_token_counts=sequence_token_counts,
            raw_candidate_count=len(getattr(output, "outputs", []) or []),
            unique_candidate_count=len(ranked_aux_dsl_dict),
            first_token_latency_s=_extract_vllm_first_token_latency_s(output),
        )
        _accumulate_request_profile(profile, request_profile)
        results.append(
            {
                "request_id": request["request_id"],
                "aux_dsl_dict": ranked_aux_dsl_dict,
                "request_profile": request_profile,
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
        worker_finished_at_unix_s = time.time()
        inference_time_s = worker_finished_at_unix_s - inference_start
        worker_batch_profile["worker_inference_time_s"] = time.perf_counter() - perf_start
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
            "avg_batch_size": (self.num_requests / self.num_batches) if self.num_batches else 0.0,
        }


@ray.remote(num_cpus=1, num_gpus=1, max_concurrency=1)
class VisionModelWorker(_BaseVisionWorker):
    def __init__(self, model_path: str, agent_kind: str, torch_seed: int = 123, worker_slot: int = 0):
        resolved_path = resolve_model_path(model_path)
        self.model_path = resolved_path
        self.agent_kind = agent_kind
        self.runtime = "transformers"
        self.torch_seed = int(torch_seed)
        self.worker_slot = int(worker_slot)
        self.worker_id = f"gpu:{self.worker_slot}"
        self.device_label = f"cuda:{self.worker_slot}"
        torch.manual_seed(self.torch_seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed(self.torch_seed)
            torch.cuda.manual_seed_all(self.torch_seed)
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
            "VisionModelWorker init done: agent_kind=%s model_device=%s padding_side=%s torch_seed=%d worker_id=%s",
            agent_kind,
            next(self.model.parameters()).device,
            self.processor.tokenizer.padding_side,
            self.torch_seed,
            self.worker_id,
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
            "worker_id": self.worker_id,
            "worker_slot": self.worker_slot,
        }

    @torch.no_grad()
    def generate_one(self, request: dict[str, Any]) -> dict[str, Any]:
        return self.generate_batch([request])

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
        worker_slot: int = 0,
        *,
        gpu_memory_utilization: float = 0.90,
        max_num_seqs: int = 128,
        gpu_batch_size: int = 1,
        decoding_size: int = 1,
        enforce_eager: bool = False,
        generation_mode: str = "beam",
        sampling_temperature: float = 0.8,
        sampling_top_p: float = 0.95,
    ):
        if agent_kind != "vlm":
            raise ValueError(f"Unsupported vision agent kind for vLLM runtime: {agent_kind}")
        if generation_mode not in {"beam", "sample"}:
            raise ValueError(f"Unsupported vLLM generation mode: {generation_mode}")
        resolved_path = resolve_model_path(model_path)
        self.model_path = resolved_path
        self.agent_kind = agent_kind
        self.runtime = "vllm"
        self.torch_seed = int(torch_seed)
        self.worker_slot = int(worker_slot)
        self.worker_id = f"gpu:{self.worker_slot}"
        self.device_label = f"cuda:{self.worker_slot}"
        self.gpu_memory_utilization = float(gpu_memory_utilization)
        self.configured_max_num_seqs = int(max_num_seqs)
        self.gpu_batch_size = int(gpu_batch_size)
        self.decoding_size = int(decoding_size)
        self.generation_mode = generation_mode
        self.sampling_temperature = float(sampling_temperature)
        self.sampling_top_p = float(sampling_top_p)
        self.max_num_seqs = _effective_vllm_max_num_seqs(
            self.configured_max_num_seqs,
            gpu_batch_size=self.gpu_batch_size,
            decoding_size=self.decoding_size,
        )
        self.max_logprobs = _effective_vllm_max_logprobs(
            decoding_size=self.decoding_size,
            generation_mode=self.generation_mode,
        )
        self.enforce_eager = bool(enforce_eager)
        self.vllm_distributed_executor_backend = "uni"
        torch.manual_seed(self.torch_seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed(self.torch_seed)
            torch.cuda.manual_seed_all(self.torch_seed)
        logger.info(
            "VLLMVisionModelWorker init start: agent_kind=%s model_path=%s torch_seed=%d gpu_memory_utilization=%.2f configured_max_num_seqs=%d effective_max_num_seqs=%d max_logprobs=%d gpu_batch_size=%d decoding_size=%d enforce_eager=%s generation_mode=%s sampling_temperature=%.3f sampling_top_p=%.3f worker_id=%s",
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
            self.generation_mode,
            self.sampling_temperature,
            self.sampling_top_p,
            self.worker_id,
        )
        llm_cls, beam_search_params_cls, sampling_params_cls, get_beam_search_score = _load_vllm_modules()
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
        self.sampling_params_cls = sampling_params_cls
        self.get_beam_search_score = get_beam_search_score
        self.processor = _load_visual_processor()
        self.processor.tokenizer.padding_side = "left"
        self.num_requests = 0
        self.num_batches = 0
        self._warmup_profile: dict[str, Any] | None = None
        logger.info(
            "VLLMVisionModelWorker init done: agent_kind=%s padding_side=%s torch_seed=%d distributed_executor_backend=%s worker_id=%s",
            agent_kind,
            self.processor.tokenizer.padding_side,
            self.torch_seed,
            self.vllm_distributed_executor_backend,
            self.worker_id,
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
            "generation_mode": self.generation_mode,
            "sampling_temperature": self.sampling_temperature,
            "sampling_top_p": self.sampling_top_p,
            "distributed_executor_backend": self.vllm_distributed_executor_backend,
            "worker_id": self.worker_id,
            "worker_slot": self.worker_slot,
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
            self._generate_batch_core(
                [
                    {
                        **warmup_request,
                        "img_path": "__warmup__",
                        "image": Image.new("RGB", (32, 32), color="white"),
                    }
                ]
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
                "worker_batch_profile": {
                    **_create_worker_batch_profile(batch_size=0),
                    "gpu_worker_id": self.worker_id,
                    "gpu_device": self.device_label,
                },
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
            return self._generate_batch_core(requests)
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

    def _generate_batch_core(self, requests: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if self.generation_mode == "beam":
            return _generate_visual_aux_dsl_dict_batch_vllm(
                self.llm,
                self.processor,
                requests,
                get_beam_search_score=self.get_beam_search_score,
                beam_search_params_cls=self.beam_search_params_cls,
            )
        return _generate_visual_aux_dsl_dict_batch_vllm_sampling(
            self.llm,
            self.processor,
            requests,
            sampling_params_cls=self.sampling_params_cls,
            temperature=self.sampling_temperature,
            top_p=self.sampling_top_p,
        )
