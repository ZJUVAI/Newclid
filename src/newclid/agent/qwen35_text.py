from __future__ import annotations
import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"
import logging
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from transformers.utils import logging as hf_logging

from newclid.agent.lm import LMAgent, AUX_PREDICATES


logger = logging.getLogger(__name__)
hf_logging.disable_progress_bar()
hf_logging.set_verbosity_error()


def _resolve_model_path(path: str) -> str:
    candidate = Path(path).expanduser()
    if candidate.exists():
        resolved = str(candidate.resolve())
        logger.info("Loading Qwen3.5 text model from local path: %s", resolved)
        return resolved

    try:
        from modelscope import snapshot_download
    except ImportError as exc:
        raise ImportError(
            "modelscope is required to load remote model ids like "
            f"'{path}'. Install it or pass a local model path."
        ) from exc

    logger.info("Downloading/loading Qwen3.5 text model via ModelScope: %s", path)
    resolved = snapshot_download(path)
    logger.info("Resolved ModelScope model id %s to local path: %s", path, resolved)
    return resolved


class Qwen35TextAgent(LMAgent):
    def __init__(self, model_path: list[str], decoding_size: int, beam_size: int, search_depth: int):
        self.any_new_statement_has_been_added = True
        self.problemJGEX = None
        self.decoding_size = decoding_size
        self.beam_size = beam_size
        self.search_depth = search_depth
        self.model_path = model_path
        self.models = []
        self.tokenizers = []

        for path in self.model_path:
            resolved_path = _resolve_model_path(path)
            model = AutoModelForCausalLM.from_pretrained(
                resolved_path,
                torch_dtype="auto",
                device_map="auto",
                attn_implementation="flash_attention_2",
                trust_remote_code=True,
            )
            tokenizer = AutoTokenizer.from_pretrained(
                resolved_path,
                trust_remote_code=True,
            )
            self.models.append(model)
            self.tokenizers.append(tokenizer)

    @torch.no_grad()
    def inference(self, model, tokenizer, query: str, new_point_name: str, response_prefix: str = '<aux>', with_predicate: bool = True):
        aux_dsl_dict = {}
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": query},
        ]
        text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        prompt_inputs = tokenizer([text], return_tensors="pt")
        prompt_len = prompt_inputs.input_ids.shape[1]
        pad_token_id = tokenizer.pad_token_id
        if pad_token_id is None:
            pad_token_id = tokenizer.eos_token_id
        eos_token_id = tokenizer.encode(';', add_special_tokens=False)[0]

        if with_predicate and len(AUX_PREDICATES) > 0:
            beams_per_predicate = self.decoding_size // len(AUX_PREDICATES)
            if beams_per_predicate:
                for aux_predicate_str in AUX_PREDICATES:
                    prompt_with_predicate = text + response_prefix + ' ' + new_point_name + ' : ' + aux_predicate_str
                    model_inputs = tokenizer([prompt_with_predicate], return_tensors="pt").to(model.device)
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
                    output_sequences = generated_output.sequences[:, prompt_len:]
                    aux_dsls = tokenizer.batch_decode(output_sequences, skip_special_tokens=True)
                    for aux_dsl, score in zip(aux_dsls, scores):
                        aux_dsl_dict[aux_dsl] = score.item()
                        logger.info("aux_dsl (with_predicate): %s", aux_dsl)

        if not with_predicate:
            prompt_no_predicate = text + response_prefix + ' ' + new_point_name
            model_inputs = tokenizer([prompt_no_predicate], return_tensors="pt").to(model.device)
            generated_output = model.generate(
                **model_inputs,
                max_new_tokens=100,
                num_beams=self.decoding_size,
                num_return_sequences=self.decoding_size,
                pad_token_id=pad_token_id,
                eos_token_id=eos_token_id,
                return_dict_in_generate=True,
                output_scores=True,
            )
            scores = generated_output.sequences_scores
            output_sequences = generated_output.sequences[:, prompt_len:]
            aux_dsls = tokenizer.batch_decode(output_sequences, skip_special_tokens=True)
            for aux_dsl, score in zip(aux_dsls, scores):
                aux_dsl_dict[aux_dsl] = score.item()
                logger.info("aux_dsl (no_predicate): %s", aux_dsl)

        return aux_dsl_dict
