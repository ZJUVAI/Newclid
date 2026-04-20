#!/usr/bin/env python3
"""Compare GRPO smoke-train windows against historical baselines."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.grpo.summarize_training_log import load_metric_rows, summarize_rows


METRIC_KEYS = (
    "num_metric_rows",
    "first_n_avg_frac_reward_zero_std",
    "first_n_median_reward_std",
    "first_n_avg_reward",
    "first_n_avg_completions_mean_length",
    "last_n_avg_frac_reward_zero_std",
    "last_n_median_reward_std",
    "last_n_avg_reward",
    "last_n_avg_completions_mean_length",
    "all_avg_frac_reward_zero_std",
    "all_avg_step_time",
    "max_consecutive_full_zero_std_steps",
)


def _parse_baseline(spec: str) -> tuple[str, Path]:
    if "=" not in spec:
        raise argparse.ArgumentTypeError(
            f"Invalid --baseline '{spec}', expected LABEL=PATH"
        )
    label, path = spec.split("=", 1)
    return label, Path(path)


def _parse_range(spec: str) -> tuple[int, int]:
    if ":" not in spec:
        raise argparse.ArgumentTypeError(
            f"Invalid --range '{spec}', expected START:END"
        )
    start, end = spec.split(":", 1)
    return int(start), int(end)


def _window_summary(
    rows: list[dict[str, Any]],
    *,
    first_n: int,
    last_n: int,
    range_start: int | None,
    range_end: int | None,
) -> dict[str, Any]:
    summary = summarize_rows(
        rows,
        first_n=first_n,
        last_n=last_n,
        range_start=range_start,
        range_end=range_end,
    )
    range_key = None
    if range_start is not None or range_end is not None:
        range_key = (
            f"range_{range_start if range_start is not None else 'start'}_"
            f"{range_end if range_end is not None else 'end'}"
        )
    metrics = {
        "first_n": {
            "avg_frac_reward_zero_std": summary["first_n_avg_frac_reward_zero_std"],
            "median_reward_std": summary["first_n_median_reward_std"],
            "avg_reward": summary["first_n_avg_reward"],
            "avg_completions_mean_length": summary[
                "first_n_avg_completions_mean_length"
            ],
        },
        "all": {
            "avg_frac_reward_zero_std": summary["all_avg_frac_reward_zero_std"],
            "avg_step_time": summary["all_avg_step_time"],
            "max_consecutive_full_zero_std_steps": summary[
                "max_consecutive_full_zero_std_steps"
            ],
        },
    }
    if last_n > 0:
        metrics["last_n"] = {
            "avg_frac_reward_zero_std": summary["last_n_avg_frac_reward_zero_std"],
            "median_reward_std": summary["last_n_median_reward_std"],
            "avg_reward": summary["last_n_avg_reward"],
            "avg_completions_mean_length": summary[
                "last_n_avg_completions_mean_length"
            ],
        }
    if range_key is not None:
        metrics[range_key] = {
            "num_metric_rows": summary[f"{range_key}_num_metric_rows"],
            "avg_frac_reward_zero_std": summary[
                f"{range_key}_avg_frac_reward_zero_std"
            ],
            "median_reward_std": summary[f"{range_key}_median_reward_std"],
            "avg_reward": summary[f"{range_key}_avg_reward"],
            "avg_completions_mean_length": summary[
                f"{range_key}_avg_completions_mean_length"
            ],
        }
    return {
        "num_metric_rows": summary["num_metric_rows"],
        "first_step": summary.get("first_step"),
        "last_step": summary.get("last_step"),
        "first_n": first_n,
        "last_n": last_n,
        "range_start": range_start,
        "range_end": range_end,
        "metrics": metrics,
    }


def _delta_metrics(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for section, section_metrics in candidate["metrics"].items():
        if section not in baseline["metrics"]:
            continue
        out[section] = {}
        for key, value in section_metrics.items():
            baseline_value = baseline["metrics"][section].get(key)
            if not isinstance(value, (int, float)) or not isinstance(
                baseline_value, (int, float)
            ):
                continue
            out[section][key] = value - baseline_value
    return out


def _run_summary(
    label: str,
    path: Path,
    *,
    first_n: int,
    last_n: int,
    range_start: int | None,
    range_end: int | None,
) -> dict[str, Any]:
    rows = load_metric_rows(path)
    return {
        "run_dir": str(path.parent),
        "logging_path": str(path),
        **_window_summary(
            rows,
            first_n=first_n,
            last_n=last_n,
            range_start=range_start,
            range_end=range_end,
        ),
        "label": label,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path, help="Candidate logging.jsonl path")
    parser.add_argument(
        "--candidate-label", default="candidate", help="Label for candidate run"
    )
    parser.add_argument(
        "--baseline",
        action="append",
        default=[],
        help="Baseline in LABEL=PATH form",
    )
    parser.add_argument("--first-n", type=int, default=50)
    parser.add_argument("--last-n", type=int, default=0)
    parser.add_argument(
        "--range",
        dest="step_range",
        default=None,
        help="Optional inclusive START:END step range",
    )
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    range_start = range_end = None
    if args.step_range:
        range_start, range_end = _parse_range(args.step_range)

    candidate = _run_summary(
        args.candidate_label,
        args.candidate,
        first_n=args.first_n,
        last_n=args.last_n,
        range_start=range_start,
        range_end=range_end,
    )
    baselines = {}
    deltas = {}
    for spec in args.baseline:
        label, path = _parse_baseline(spec)
        baseline = _run_summary(
            label,
            path,
            first_n=args.first_n,
            last_n=args.last_n,
            range_start=range_start,
            range_end=range_end,
        )
        baselines[label] = baseline
        deltas[f"{args.candidate_label}_vs_{label}"] = _delta_metrics(
            candidate, baseline
        )

    payload = {
        "candidate": candidate,
        "baselines": baselines,
        "deltas": deltas,
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
