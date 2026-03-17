from __future__ import annotations
import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"
import logging
from pathlib import Path
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from transformers.utils import logging as hf_logging

from newclid.agent.lm import LMAgent, AUX_PREDICATES


logger = logging.getLogger(__name__)
hf_logging.disable_progress_bar()
hf_logging.set_verbosity_error()

DEBUG_QWEN35_TEXT_INPUT = os.environ.get("NEWCLID_DEBUG_QWEN35_TEXT_INPUT", "").lower() in {
    "1",
    "true",
    "yes",
    "on",
}


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

    def _log_input_snapshot(
        self,
        *,
        query: str,
        messages: list[dict[str, Any]],
        text_prompt: str,
        final_text: str,
        model_inputs,
        prompt_len: int,
    ) -> None:
        if not DEBUG_QWEN35_TEXT_INPUT:
            return

        logger.info("Qwen35Text input snapshot: query=%s", query)
        logger.info("Qwen35Text input snapshot: messages=%s", messages)
        logger.info("Qwen35Text input snapshot: text_prompt=%s", text_prompt)
        logger.info("Qwen35Text input snapshot: final_text=%s", final_text)
        logger.info("Qwen35Text input snapshot: model_input_keys=%s", list(model_inputs.keys()))
        if "input_ids" in model_inputs:
            logger.info("Qwen35Text input snapshot: input_ids.shape=%s", tuple(model_inputs["input_ids"].shape))
        if "attention_mask" in model_inputs:
            logger.info("Qwen35Text input snapshot: attention_mask.shape=%s", tuple(model_inputs["attention_mask"].shape))
        logger.info("Qwen35Text input snapshot: prompt_len=%s", prompt_len)

    def _log_model_output(
        self,
        *,
        queue_type: str,
        aux_dsl: str | None = None,
        score: float | None = None,
        aux: str | None = None,
    ) -> None:
        if score is not None:
            logger.info("Qwen35Text output [%s]: score=%s", queue_type, score)
        if aux_dsl is not None:
            logger.info("Qwen35Text output [%s]: aux_dsl=%s", queue_type, aux_dsl)
        if aux is not None:
            logger.info("Qwen35Text output [%s]: aux=%s", queue_type, aux)

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
        eos_token_id = tokenizer.encode(' ;', add_special_tokens=False)[0]

        if with_predicate and len(AUX_PREDICATES) > 0:
            beams_per_predicate = self.decoding_size // len(AUX_PREDICATES)
            if beams_per_predicate:
                for aux_predicate_str in AUX_PREDICATES:
                    prompt_with_predicate = text + response_prefix + ' ' + new_point_name + ' : ' + aux_predicate_str
                    model_inputs = tokenizer([prompt_with_predicate], return_tensors="pt")
                    self._log_input_snapshot(
                        query=query,
                        messages=messages,
                        text_prompt=text,
                        final_text=prompt_with_predicate,
                        model_inputs=model_inputs,
                        prompt_len=prompt_len,
                    )
                    model_inputs = model_inputs.to(model.device)
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
                        score = score.item()
                        aux_dsl_dict[aux_dsl] = score

        if not with_predicate:
            prompt_no_predicate = text + response_prefix + ' ' + new_point_name
            model_inputs = tokenizer([prompt_no_predicate], return_tensors="pt")
            self._log_input_snapshot(
                query=query,
                messages=messages,
                text_prompt=text,
                final_text=prompt_no_predicate,
                model_inputs=model_inputs,
                prompt_len=prompt_len,
            )
            model_inputs = model_inputs.to(model.device)
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
                score = score.item()
                aux_dsl_dict[aux_dsl] = score

        return aux_dsl_dict
