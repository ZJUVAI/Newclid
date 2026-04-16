#!/usr/bin/env python3
"""Offline difficulty labeling for GRPO candidate pools (VLM version)."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

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


class VLMCompletionGenerator:
    """VLM-compatible completion generator using SWIFT inference."""

    def __init__(self, model_path: str, model_type: str = "qwen3_vl", max_new_tokens: int = 160) -> None:
        from swift.infer_engine import InferRequest, RequestConfig, TransformersEngine

        self.engine = TransformersEngine(model=model_path, model_type=model_type)
        self.max_new_tokens = max_new_tokens
        self._InferRequest = InferRequest
        self._RequestConfig = RequestConfig

    def _build_messages(self, query: str) -> list[dict]:
        return [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": query},
        ]

    def generate_greedy(self, query: str) -> str:
        messages = self._build_messages(query)
        req = self._InferRequest(messages=messages)
        cfg = self._RequestConfig(temperature=0.0, n=1, max_tokens=self.max_new_tokens)
        result = self.engine.infer([req], cfg)
        if result and result[0].choices:
            return result[0].choices[0].message.content
        return ""

    def generate_sample(self, query: str, num_samples: int, temperature: float, top_p: float) -> list[str]:
        messages = self._build_messages(query)
        req = self._InferRequest(messages=messages)
        cfg = self._RequestConfig(temperature=temperature, top_p=top_p, n=num_samples, max_tokens=self.max_new_tokens)
        result = self.engine.infer([req], cfg)
        if result and result[0].choices:
            return [c.message.content for c in result[0].choices]
        return []


def label_difficulty(
    rows: list[dict[str, Any]],
    generator: VLMCompletionGenerator,
    evaluator: AuxRewardEvaluator,
    num_samples: int,
    temperature: float,
    top_p: float,
) -> list[dict[str, Any]]:
    labeled_rows = []
    start_time = time.perf_counter()

    for idx, row in enumerate(rows, start=1):
        query = row["query"]
        fl_problem = row["fl_problem"]

        # Greedy@1
        greedy_completion = generator.generate_greedy(query)
        greedy_result = evaluator.evaluate(greedy_completion, fl_problem)

        # Sample@N
        sampled_completions = generator.generate_sample(query, num_samples, temperature, top_p)
        sampled_results = [evaluator.evaluate(c, fl_problem) for c in sampled_completions]

        # Aggregate metrics
        valid_count = sum(1 for r in sampled_results if r.build_ok)
        solved_count = sum(1 for r in sampled_results if r.ddar_status == "solved")
        format_valid_count = sum(1 for r in sampled_results if r.format_ok)

        labeled_row = {
            **row,
            "greedy_success": greedy_result.ddar_status == "solved",
            "greedy_build_ok": greedy_result.build_ok,
            "greedy_format_ok": greedy_result.format_ok,
            "pass_at_16": solved_count / num_samples,
            "valid_at_16": valid_count / num_samples,
            "format_valid_at_16": format_valid_count / num_samples,
            "all_invalid": valid_count == 0,
        }
        labeled_rows.append(labeled_row)

        elapsed = time.perf_counter() - start_time
        avg_time = elapsed / idx
        eta = avg_time * (len(rows) - idx)
        print(
            f"[{idx}/{len(rows)}] greedy={greedy_result.ddar_status} "
            f"pass@{num_samples}={solved_count}/{num_samples} "
            f"elapsed={elapsed:.1f}s eta={eta:.1f}s"
        )

    return labeled_rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Candidate pool JSONL")
    parser.add_argument("output", type=Path, help="Difficulty labels JSONL")
    parser.add_argument(
        "--model-path",
        type=str,
        required=True,
        help="Model checkpoint to use for offline labeling",
    )
    parser.add_argument(
        "--model-type",
        type=str,
        default="qwen3_vl",
        help="SWIFT model type",
    )
    parser.add_argument("--num-samples", type=int, default=16, help="Number of sampled completions per prompt")
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--top-p", type=float, default=0.95)
    args = parser.parse_args()

    rows = load_jsonl(args.input)
    generator = VLMCompletionGenerator(args.model_path, args.model_type)
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
