#!/usr/bin/env python3
"""Summarize GRPO training logs for smoke-train gate checks."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any


def load_metric_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if "frac_reward_zero_std" not in row:
                continue
            rows.append(row)
    return rows


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _median(values: list[float]) -> float:
    return statistics.median(values) if values else 0.0


def _max_consecutive_zero_std(rows: list[dict[str, Any]]) -> int:
    best = 0
    current = 0
    for row in rows:
        value = float(row.get("frac_reward_zero_std", 0.0))
        if value >= 0.999999:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def summarize_rows(rows: list[dict[str, Any]], *, first_n: int) -> dict[str, Any]:
    head = rows[:first_n]

    def collect(metric: str, bucket: list[dict[str, Any]]) -> list[float]:
        values = []
        for row in bucket:
            value = row.get(metric)
            if isinstance(value, (int, float)):
                values.append(float(value))
        return values

    summary = {
        "num_metric_rows": len(rows),
        "first_n": first_n,
        "first_n_avg_frac_reward_zero_std": _avg(collect("frac_reward_zero_std", head)),
        "first_n_median_reward_std": _median(collect("reward_std", head)),
        "first_n_avg_reward": _avg(collect("reward", head)),
        "first_n_avg_completions_mean_length": _avg(
            collect("completions/mean_length", head)
        ),
        "all_avg_step_time": _avg(collect("step_time", rows)),
        "all_avg_frac_reward_zero_std": _avg(collect("frac_reward_zero_std", rows)),
        "max_consecutive_full_zero_std_steps": _max_consecutive_zero_std(rows),
    }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Path to logging.jsonl")
    parser.add_argument(
        "--first-n",
        type=int,
        default=100,
        help="How many leading steps to use for smoke summary metrics",
    )
    args = parser.parse_args()

    rows = load_metric_rows(args.input)
    summary = summarize_rows(rows, first_n=args.first_n)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
