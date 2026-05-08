#!/usr/bin/env python3
"""Select a GRPO training set by sampling equally from core and reward_mixed_zero buckets."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

from tqdm import tqdm

from select_debug_set import (
    _classify_bucket_unified,
    _resolve_pass_key,
    load_jsonl,
    write_jsonl,
    write_json,
)


def _classify_rows(
    rows: list[dict[str, Any]],
    *,
    core_min_pass: float,
    core_max_pass: float,
    mastered_pass_min: float,
    zero_pass_reward_std_min: float,
) -> dict[str, list[dict[str, Any]]]:
    pass_key = _resolve_pass_key(rows)
    buckets: dict[str, list[dict[str, Any]]] = {"core": [], "reward_mixed_zero": [], "other": []}
    for row in tqdm(rows, desc="Classifying"):
        bucket = _classify_bucket_unified(
            row,
            pass_key,
            core_min_pass=core_min_pass,
            core_max_pass=core_max_pass,
            mastered_pass_min=mastered_pass_min,
            zero_pass_reward_std_min=zero_pass_reward_std_min,
        )
        buckets.setdefault(bucket, []).append(row)
    return buckets


def select_simple(
    rows: list[dict[str, Any]],
    target_size: int,
    *,
    core_min_pass: float = 0.0625,
    core_max_pass: float = 0.75,
    mastered_pass_min: float = 0.90,
    zero_pass_reward_std_min: float = 0.15,
    seed: int = 42,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rng = random.Random(seed)
    buckets = _classify_rows(
        rows,
        core_min_pass=core_min_pass,
        core_max_pass=core_max_pass,
        mastered_pass_min=mastered_pass_min,
        zero_pass_reward_std_min=zero_pass_reward_std_min,
    )

    core_pool = buckets.get("core", [])
    mixed_pool = buckets.get("reward_mixed_zero", [])

    half = target_size // 2
    core_n = min(half, len(core_pool))
    mixed_n = min(target_size - core_n, len(mixed_pool))
    # fill any shortfall from the other bucket
    if core_n < half:
        mixed_n = min(len(mixed_pool), target_size - core_n)
    if mixed_n < target_size - core_n:
        core_n = min(len(core_pool), target_size - mixed_n)

    core_selected = rng.sample(core_pool, core_n)
    mixed_selected = rng.sample(mixed_pool, mixed_n)
    selected = core_selected + mixed_selected
    rng.shuffle(selected)

    final_rows = [
        {"query": row["query"], "fl_problem": row["fl_problem"], "response": row["response"]}
        for row in selected
    ]

    report = {
        "target_size": target_size,
        "selected_rows": len(final_rows),
        "core_available": len(core_pool),
        "reward_mixed_zero_available": len(mixed_pool),
        "core_selected": core_n,
        "reward_mixed_zero_selected": mixed_n,
        "seed": seed,
        "thresholds": {
            "core_pass_window": [core_min_pass, core_max_pass],
            "mastered_pass_min": mastered_pass_min,
            "zero_pass_reward_std_min": zero_pass_reward_std_min,
        },
        "bucket_counts": {k: len(v) for k, v in buckets.items()},
    }
    return final_rows, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Difficulty labels JSONL")
    parser.add_argument("output", type=Path, help="Selected JSONL")
    parser.add_argument("--report-output", type=Path, help="JSON report path")
    parser.add_argument("--target-size", type=int, default=2000)
    parser.add_argument("--core-pass-min", type=float, default=0.0625)
    parser.add_argument("--core-pass-max", type=float, default=0.75)
    parser.add_argument("--mastered-pass-min", type=float, default=0.90)
    parser.add_argument("--zero-pass-reward-std-min", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rows = load_jsonl(args.input)
    final_rows, report = select_simple(
        rows,
        args.target_size,
        core_min_pass=args.core_pass_min,
        core_max_pass=args.core_pass_max,
        mastered_pass_min=args.mastered_pass_min,
        zero_pass_reward_std_min=args.zero_pass_reward_std_min,
        seed=args.seed,
    )
    write_jsonl(args.output, final_rows)
    if args.report_output:
        write_json(args.report_output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
