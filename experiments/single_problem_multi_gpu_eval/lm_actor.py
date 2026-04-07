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


def generate_aux_dsl_dict(
    model,
    tokenizer,
    *,
    query: str,
    new_point_name: str,
    decoding_size: int,
    response_prefix: str = "<aux> x00",
    with_predicate: bool = False,
) -> dict[str, float]:
    # The experiment asks the model to continue from a fixed auxiliary prefix,
    # then treats each returned completion as one candidate construction DSL.
    aux_dsl_dict: dict[str, float] = {}
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
    prompt_inputs = tokenizer([text], return_tensors="pt")
    prompt_len = prompt_inputs.input_ids.shape[1]
    pad_token_id = tokenizer.pad_token_id
    eos_token_id = tokenizer.encode(" ;", add_special_tokens=False)[0]

    if with_predicate and AUX_PREDICATES:
        beams_per_predicate = decoding_size // len(AUX_PREDICATES)
        if beams_per_predicate:
            for aux_predicate_str in AUX_PREDICATES:
                prompt = text + response_prefix + " " + new_point_name + " : " + aux_predicate_str
                model_inputs = tokenizer([prompt], return_tensors="pt").to(model.device)
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
                generated_sequences = generated_output.sequences[:, prompt_len:]
                aux_dsls = tokenizer.batch_decode(generated_sequences, skip_special_tokens=True)
                for aux_dsl, score in zip(aux_dsls, scores):
                    aux_dsl_dict[aux_dsl] = score.item()

    if not with_predicate:
        prompt = text + response_prefix + " " + new_point_name
        model_inputs = tokenizer([prompt], return_tensors="pt").to(model.device)
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
        generated_sequences = generated_output.sequences[:, prompt_len:]
        aux_dsls = tokenizer.batch_decode(generated_sequences, skip_special_tokens=True)
        for aux_dsl, score in zip(aux_dsls, scores):
            aux_dsl_dict[aux_dsl] = score.item()

    return aux_dsl_dict


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

    def warmup(self) -> dict[str, Any]:
        device = str(next(self.model.parameters()).device)
        return {
            "model_path": self.model_path,
            "device": device,
        }

    @torch.no_grad()
    def generate_batch(self, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for request in requests:
            # Requests are still decoded one by one inside a worker; batching here
            # mainly amortizes Ray scheduling and actor-call overhead.
            inference_start = time.time()
            aux_dsl_dict = generate_aux_dsl_dict(
                self.model,
                self.tokenizer,
                query=request["query"],
                new_point_name=request["new_point_name"],
                decoding_size=request["decoding_size"],
                response_prefix=request.get("response_prefix", "<aux> x00"),
                with_predicate=request.get("with_predicate", False),
            )
            inference_time_s = time.time() - inference_start
            self.num_requests += 1
            results.append(
                {
                    "request_id": request["request_id"],
                    "aux_dsl_dict": aux_dsl_dict,
                    "inference_time_s": inference_time_s,
                }
            )
        return results

    def stats(self) -> dict[str, Any]:
        return {
            "model_path": self.model_path,
            "num_requests": self.num_requests,
        }
