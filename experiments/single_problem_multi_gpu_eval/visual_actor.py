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

from experiments.single_problem_multi_gpu_eval.lm_actor import resolve_model_path


os.environ["TOKENIZERS_PARALLELISM"] = "false"

logger = logging.getLogger(__name__)
hf_logging.disable_progress_bar()
hf_logging.set_verbosity_error()

AUX_PREDICATES: list[str] = []


def generate_visual_aux_dsl_dict(
    model,
    processor,
    *,
    query: str,
    img_path: str,
    new_point_name: str,
    decoding_size: int,
    agent_kind: str,
    response_prefix: str = "<aux> x00",
    with_predicate: bool = False,
) -> dict[str, float]:
    aux_dsl_dict: dict[str, float] = {}
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {
            "role": "user",
            "content": [
                {"type": "image", "image": img_path},
                {"type": "text", "text": query},
            ],
        },
    ]
    image_inputs, video_inputs = process_vision_info(messages, image_patch_size=16)
    text_prompt = processor.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    inputs_without_prefix = processor(
        text=[text_prompt],
        images=image_inputs,
        videos=video_inputs,
        padding=True,
        return_tensors="pt",
        do_resize=False,
    )
    prompt_len = inputs_without_prefix.input_ids.shape[1]

    def build_model_inputs(final_text: str):
        return processor(
            text=[final_text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
            do_resize=False,
        ).to(model.device)

    if agent_kind == "qwen35":
        pad_token_id = processor.tokenizer.pad_token_id
        eos_token_id = processor.tokenizer.encode(" ;", add_special_tokens=False)[0]
    else:
        pad_token_id = 151643
        eos_token_id = 2587

    if with_predicate and AUX_PREDICATES:
        beams_per_predicate = decoding_size // len(AUX_PREDICATES)
        if beams_per_predicate:
            for aux_predicate_str in AUX_PREDICATES:
                final_text = text_prompt + response_prefix + " " + new_point_name + " : " + aux_predicate_str
                model_inputs = build_model_inputs(final_text)
                generated_output = model.generate(
                    **model_inputs,
                    max_new_tokens=100,
                    num_beams=beams_per_predicate,
                    num_return_sequences=beams_per_predicate,
                    pad_token_id=pad_token_id,
                    eos_token_id=eos_token_id,
                    return_dict_in_generate=True,
                    output_scores=True,
                )
                scores = generated_output.sequences_scores
                sequences = generated_output.sequences[:, prompt_len:]
                aux_dsls = processor.batch_decode(sequences, skip_special_tokens=True)
                for aux_dsl, score in zip(aux_dsls, scores):
                    aux_dsl_dict[aux_dsl] = score.item()

    if not with_predicate:
        final_text = text_prompt + response_prefix + " " + new_point_name
        model_inputs = build_model_inputs(final_text)
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
        scores = generated_output.sequences_scores
        sequences = generated_output.sequences[:, prompt_len:]
        aux_dsls = processor.batch_decode(sequences, skip_special_tokens=True)
        for aux_dsl, score in zip(aux_dsls, scores):
            aux_dsl_dict[aux_dsl] = score.item()

    return aux_dsl_dict


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
        self.num_requests = 0
        logger.info(
            "VisionModelWorker init done: agent_kind=%s model_device=%s",
            agent_kind,
            next(self.model.parameters()).device,
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
        }

    @torch.no_grad()
    def generate_one(self, request: dict[str, Any]) -> dict[str, Any]:
        logger.debug(
            "VisionModelWorker generate_one start: agent_kind=%s request_id=%s",
            self.agent_kind,
            request.get("request_id", "<missing>"),
        )
        logger.debug(
            "VisionModelWorker request start: request_id=%s depth=%s img_path=%s",
            request.get("request_id"),
            request.get("depth"),
            request.get("img_path"),
        )
        inference_start = time.time()
        aux_dsl_dict = generate_visual_aux_dsl_dict(
            self.model,
            self.processor,
            query=request["query"],
            img_path=request["img_path"],
            new_point_name=request["new_point_name"],
            decoding_size=request["decoding_size"],
            agent_kind=self.agent_kind,
            response_prefix=request.get("response_prefix", "<aux> x00"),
            with_predicate=request.get("with_predicate", False),
        )
        inference_time_s = time.time() - inference_start
        self.num_requests += 1
        logger.debug(
            "VisionModelWorker generate_one done: agent_kind=%s request_id=%s candidates=%d total_requests=%d",
            self.agent_kind,
            request.get("request_id"),
            len(aux_dsl_dict),
            self.num_requests,
        )
        return {
            "request_id": request["request_id"],
            "aux_dsl_dict": aux_dsl_dict,
            "inference_time_s": inference_time_s,
        }

    def stats(self) -> dict[str, Any]:
        return {
            "model_path": self.model_path,
            "agent_kind": self.agent_kind,
            "num_requests": self.num_requests,
        }
