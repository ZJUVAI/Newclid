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
            global_step = row.get("global_step/max_steps")
            if global_step is not None:
                try:
                    row["_step"] = int(str(global_step).split("/")[0])
                except (TypeError, ValueError):
                    pass
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


def summarize_rows(
    rows: list[dict[str, Any]],
    *,
    first_n: int,
    last_n: int = 0,
    range_start: int | None = None,
    range_end: int | None = None,
) -> dict[str, Any]:
    head = rows[:first_n]
    tail = rows[-last_n:] if last_n > 0 else []
    step_range = []
    if range_start is not None or range_end is not None:
        step_range = [
            row
            for row in rows
            if (range_start is None or row.get("_step", -1) >= range_start)
            and (range_end is None or row.get("_step", -1) <= range_end)
        ]

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
        "first_n_max_consecutive_full_zero_std_steps": _max_consecutive_zero_std(head),
        "all_avg_step_time": _avg(collect("step_time", rows)),
        "all_avg_frac_reward_zero_std": _avg(collect("frac_reward_zero_std", rows)),
        "max_consecutive_full_zero_std_steps": _max_consecutive_zero_std(rows),
    }
    if rows and "_step" in rows[0]:
        summary["first_step"] = rows[0]["_step"]
        summary["last_step"] = rows[-1]["_step"]
    if last_n > 0:
        summary.update(
            {
                "last_n": last_n,
                "last_n_avg_frac_reward_zero_std": _avg(
                    collect("frac_reward_zero_std", tail)
                ),
                "last_n_median_reward_std": _median(collect("reward_std", tail)),
                "last_n_avg_reward": _avg(collect("reward", tail)),
                "last_n_avg_completions_mean_length": _avg(
                    collect("completions/mean_length", tail)
                ),
                "last_n_max_consecutive_full_zero_std_steps": _max_consecutive_zero_std(
                    tail
                ),
            }
        )
    if range_start is not None or range_end is not None:
        range_key = f"range_{range_start if range_start is not None else 'start'}_{range_end if range_end is not None else 'end'}"
        summary.update(
            {
                f"{range_key}_num_metric_rows": len(step_range),
                f"{range_key}_avg_frac_reward_zero_std": _avg(
                    collect("frac_reward_zero_std", step_range)
                ),
                f"{range_key}_median_reward_std": _median(
                    collect("reward_std", step_range)
                ),
                f"{range_key}_avg_reward": _avg(collect("reward", step_range)),
                f"{range_key}_avg_completions_mean_length": _avg(
                    collect("completions/mean_length", step_range)
                ),
                f"{range_key}_max_consecutive_full_zero_std_steps": (
                    _max_consecutive_zero_std(step_range)
                ),
            }
        )
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
    parser.add_argument(
        "--last-n",
        type=int,
        default=0,
        help="How many trailing steps to summarize",
    )
    parser.add_argument(
        "--range-start",
        type=int,
        default=None,
        help="Optional inclusive step-range start for extra summary metrics",
    )
    parser.add_argument(
        "--range-end",
        type=int,
        default=None,
        help="Optional inclusive step-range end for extra summary metrics",
    )
    args = parser.parse_args()

    rows = load_metric_rows(args.input)
    summary = summarize_rows(
        rows,
        first_n=args.first_n,
        last_n=args.last_n,
        range_start=args.range_start,
        range_end=args.range_end,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
