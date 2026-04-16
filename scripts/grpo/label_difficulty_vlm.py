#!/usr/bin/env python3
"""Offline difficulty labeling for GRPO candidate pools (VLM version)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from newclid.training.grpo_rewards import AuxRewardEvaluator


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

    def __init__(
        self,
        model_path: str,
        model_type: str = "qwen3_vl",
        max_new_tokens: int = 160,
        max_batch_size: int = 16,
    ) -> None:
        from swift.infer_engine import InferRequest, RequestConfig, TransformersEngine

        self.engine = TransformersEngine(
            model=model_path,
            model_type=model_type,
            max_batch_size=max_batch_size,
        )
        self.max_new_tokens = max_new_tokens
        self._InferRequest = InferRequest
        self._RequestConfig = RequestConfig

    def _build_messages(self, query: str) -> list[dict]:
        return [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": query},
        ]

    def generate_batch(
        self,
        queries: list[str],
        num_samples: int,
        temperature: float,
        top_p: float,
    ) -> tuple[list[str], list[list[str]]]:
        """Batch inference: returns (greedy_outputs, sampled_outputs_per_query)."""
        reqs = [self._InferRequest(messages=self._build_messages(q)) for q in queries]

        greedy_cfg = self._RequestConfig(temperature=0.0, n=1, max_tokens=self.max_new_tokens)
        greedy_results = self.engine.infer(reqs, greedy_cfg)
        greedy_outputs = [
            r.choices[0].message.content if r and r.choices else ""
            for r in greedy_results
        ]

        sample_cfg = self._RequestConfig(
            temperature=temperature, top_p=top_p, n=num_samples, max_tokens=self.max_new_tokens
        )
        sample_results = self.engine.infer(reqs, sample_cfg)
        sampled_outputs = [
            [c.message.content for c in r.choices] if r and r.choices else []
            for r in sample_results
        ]

        return greedy_outputs, sampled_outputs


def label_difficulty(
    rows: list[dict[str, Any]],
    generator: VLMCompletionGenerator,
    evaluator: AuxRewardEvaluator,
    num_samples: int,
    temperature: float,
    top_p: float,
    batch_size: int = 8,
) -> list[dict[str, Any]]:
    labeled_rows = []
    start_time = time.perf_counter()
    pass_key = f"pass_at_{num_samples}"
    valid_key = f"valid_at_{num_samples}"
    fmt_key = f"format_valid_at_{num_samples}"

    for batch_start in range(0, len(rows), batch_size):
        batch = rows[batch_start : batch_start + batch_size]
        queries = [r["query"] for r in batch]
        fl_problems = [r["fl_problem"] for r in batch]

        greedy_outputs, sampled_outputs = generator.generate_batch(
            queries, num_samples, temperature, top_p
        )

        for i, row in enumerate(batch):
            greedy_result = evaluator.evaluate(greedy_outputs[i], fl_problems[i])
            sampled_results = [evaluator.evaluate(c, fl_problems[i]) for c in sampled_outputs[i]]

            n = len(sampled_results) or 1
            valid_count = sum(1 for r in sampled_results if r.build_ok)
            solved_count = sum(1 for r in sampled_results if r.ddar_status == "solved")
            fmt_count = sum(1 for r in sampled_results if r.format_ok)

            labeled_rows.append({
                **row,
                "greedy_success": greedy_result.ddar_status == "solved",
                "greedy_build_ok": greedy_result.build_ok,
                "greedy_format_ok": greedy_result.format_ok,
                pass_key: solved_count / n,
                valid_key: valid_count / n,
                fmt_key: fmt_count / n,
                "all_invalid": valid_count == 0,
            })

        idx = batch_start + len(batch)
        elapsed = time.perf_counter() - start_time
        avg_time = elapsed / idx
        eta = avg_time * (len(rows) - idx)
        last = labeled_rows[-1]
        print(
            f"[{idx}/{len(rows)}] greedy={greedy_result.ddar_status} "
            f"pass@{num_samples}={last[pass_key]:.2f} "
            f"elapsed={elapsed:.1f}s eta={eta:.1f}s"
        )

    return labeled_rows


def _shard_rows(rows: list[dict[str, Any]], shard_index: int, num_shards: int) -> list[dict[str, Any]]:
    return [r for i, r in enumerate(rows) if i % num_shards == shard_index]


def _merge_shards(shard_paths: list[Path]) -> list[dict[str, Any]]:
    """Merge shard outputs preserving original order via _shard_index field."""
    all_rows: list[dict[str, Any]] = []
    for p in shard_paths:
        all_rows.extend(load_jsonl(p))
    all_rows.sort(key=lambda r: r.pop("_shard_index"))
    return all_rows


def run_workers(args: argparse.Namespace) -> None:
    """Launch --workers subprocesses, each handling one GPU shard, then merge."""
    num_workers = args.workers
    rows = load_jsonl(args.input)
    total = len(rows)

    # Write per-shard input files
    shard_inputs: list[Path] = []
    shard_outputs: list[Path] = []
    for i in range(num_workers):
        shard_rows = _shard_rows(rows, i, num_workers)
        # Tag each row with its original index for merge ordering
        for j, r in enumerate(shard_rows):
            r["_shard_index"] = i + j * num_workers
        p = Path(f"/tmp/_label_shard_{i}_of_{num_workers}.jsonl")
        write_jsonl(p, shard_rows)
        shard_inputs.append(p)
        shard_outputs.append(Path(f"/tmp/_label_shard_{i}_of_{num_workers}_out.jsonl"))

    procs = []
    for i in range(num_workers):
        env = os.environ.copy()
        env["CUDA_VISIBLE_DEVICES"] = str(i)
        cmd = [
            sys.executable, __file__,
            str(shard_inputs[i]), str(shard_outputs[i]),
            "--model-path", args.model_path,
            "--model-type", args.model_type,
            "--num-samples", str(args.num_samples),
            "--temperature", str(args.temperature),
            "--top-p", str(args.top_p),
            "--batch-size", str(args.batch_size),
            "--shard-index", str(i),
            "--num-shards", "1",  # already pre-sharded
        ]
        print(f"[worker {i}] CUDA_VISIBLE_DEVICES={i} launching ({len(load_jsonl(shard_inputs[i]))} rows)")
        procs.append(subprocess.Popen(cmd, env=env))

    for i, p in enumerate(procs):
        ret = p.wait()
        if ret != 0:
            raise RuntimeError(f"Worker {i} exited with code {ret}")
        print(f"[worker {i}] done")

    merged = _merge_shards(shard_outputs)
    write_jsonl(args.output, merged)
    print(f"wrote {len(merged)} labeled rows to {args.output}")

    # Cleanup temp files
    for p in shard_inputs + shard_outputs:
        p.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Candidate pool JSONL")
    parser.add_argument("output", type=Path, help="Difficulty labels JSONL")
    parser.add_argument("--model-path", type=str, required=True)
    parser.add_argument("--model-type", type=str, default="qwen3_vl")
    parser.add_argument("--num-samples", type=int, default=16, help="Sampled completions per prompt")
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--top-p", type=float, default=0.95)
    parser.add_argument("--batch-size", type=int, default=8, help="Rows per inference batch")
    parser.add_argument("--workers", type=int, default=1, help="Number of GPU workers (one per GPU)")
    # Internal sharding args used by worker subprocesses
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--num-shards", type=int, default=1)
    args = parser.parse_args()

    if args.workers > 1:
        run_workers(args)
        return

    rows = load_jsonl(args.input)
    if args.num_shards > 1:
        rows = _shard_rows(rows, args.shard_index, args.num_shards)

    generator = VLMCompletionGenerator(
        args.model_path,
        args.model_type,
        max_batch_size=args.batch_size,
    )
    evaluator = AuxRewardEvaluator()
    labeled = label_difficulty(
        rows,
        generator=generator,
        evaluator=evaluator,
        num_samples=args.num_samples,
        temperature=args.temperature,
        top_p=args.top_p,
        batch_size=args.batch_size,
    )
    write_jsonl(args.output, labeled)
    print(f"wrote {len(labeled)} labeled rows to {args.output}")


if __name__ == "__main__":
    main()
