#!/usr/bin/env python3
"""Offline difficulty labeling for GRPO candidate pools."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from newclid.training.grpo_rewards import AuxEvaluationResult, AuxRewardEvaluator


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


class CompletionGenerator:
    def __init__(self, model_path: str, max_new_tokens: int = 160) -> None:
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path,
            torch_dtype="auto",
            device_map="auto",
            attn_implementation="flash_attention_2",
        )
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        self.max_new_tokens = max_new_tokens

    def _build_prompt(self, query: str) -> str:
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": query},
        ]
        prompt = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        return prompt + "<think>\n\n</think>\n\n"

    @torch.no_grad()
    def generate_greedy(self, query: str) -> str:
        prompt = self._build_prompt(query)
        inputs = self.tokenizer([prompt], return_tensors="pt").to(self.model.device)
        output = self.model.generate(
            **inputs,
            max_new_tokens=self.max_new_tokens,
            do_sample=False,
            pad_token_id=self.tokenizer.pad_token_id,
        )
        generated = output[:, inputs.input_ids.shape[1] :]
        return self.tokenizer.batch_decode(generated, skip_special_tokens=True)[0]

    @torch.no_grad()
    def generate_sample(self, query: str, num_samples: int, temperature: float, top_p: float) -> list[str]:
        prompt = self._build_prompt(query)
        inputs = self.tokenizer([prompt], return_tensors="pt").to(self.model.device)
        output = self.model.generate(
            **inputs,
            max_new_tokens=self.max_new_tokens,
            do_sample=True,
            temperature=temperature,
            top_p=top_p,
            num_return_sequences=num_samples,
            pad_token_id=self.tokenizer.pad_token_id,
        )
        generated = output[:, inputs.input_ids.shape[1] :]
        return self.tokenizer.batch_decode(generated, skip_special_tokens=True)


def aggregate_difficulty_metrics(
    sample: dict[str, Any],
    greedy_completion: str,
    sampled_completions: list[str],
    evaluator: AuxRewardEvaluator,
) -> dict[str, Any]:
    greedy_result = evaluator.evaluate(greedy_completion, sample["fl_problem"])
    sampled_results = [evaluator.evaluate(completion, sample["fl_problem"]) for completion in sampled_completions]

    ddar_valid_count = sum(1 for result in sampled_results if result.build_ok)
    ddar_solved_count = sum(1 for result in sampled_results if result.ddar_status == "solved")
    format_valid_count = sum(1 for result in sampled_results if result.format_ok)
    normalized_aux_values = [result.normalized_aux for result in sampled_results if result.normalized_aux]
    unique_aux_count = len(set(normalized_aux_values))
    duplicate_aux_ratio = 0.0
    if sampled_results:
        duplicate_aux_ratio = 1.0 - (unique_aux_count / len(sampled_results))

    return {
        **sample,
        "greedy_success": greedy_result.ddar_status == "solved",
        "greedy_status": greedy_result.ddar_status,
        "pass_at_16": ddar_solved_count / len(sampled_results) if sampled_results else 0.0,
        "ddar_valid_count": ddar_valid_count,
        "ddar_solved_count": ddar_solved_count,
        "format_valid_count": format_valid_count,
        "unique_aux_count": unique_aux_count,
        "duplicate_aux_ratio": duplicate_aux_ratio,
        "all_invalid": ddar_valid_count == 0,
    }


def label_difficulty(
    rows: list[dict[str, Any]],
    generator: CompletionGenerator,
    evaluator: AuxRewardEvaluator,
    num_samples: int,
    temperature: float,
    top_p: float,
) -> list[dict[str, Any]]:
    labeled_rows = []
    for row in rows:
        started = time.time()
        greedy_completion = generator.generate_greedy(row["query"])
        sampled_completions = generator.generate_sample(
            row["query"],
            num_samples=num_samples,
            temperature=temperature,
            top_p=top_p,
        )
        labeled = aggregate_difficulty_metrics(row, greedy_completion, sampled_completions, evaluator)
        labeled["avg_eval_time"] = (time.time() - started) / (1 + len(sampled_completions))
        labeled_rows.append(labeled)
    return labeled_rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Candidate pool JSONL")
    parser.add_argument("output", type=Path, help="Difficulty labels JSONL")
    parser.add_argument(
        "--model-path",
        type=str,
        default="models/auxsweep02/checkpoint-39184",
        help="Model checkpoint to use for offline labeling",
    )
    parser.add_argument("--num-samples", type=int, default=16, help="Number of sampled completions per prompt")
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--top-p", type=float, default=0.95)
    args = parser.parse_args()

    rows = load_jsonl(args.input)
    generator = CompletionGenerator(args.model_path)
    evaluator = AuxRewardEvaluator()
    labeled = label_difficulty(
        rows,
        generator=generator,
        evaluator=evaluator,
        num_samples=args.num_samples,
        temperature=args.temperature,
        top_p=args.top_p,
    )
    write_jsonl(args.output, labeled)
    print(f"wrote {len(labeled)} labeled rows to {args.output}")


if __name__ == "__main__":
    main()
