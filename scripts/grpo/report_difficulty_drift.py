#!/usr/bin/env python3
"""Compare two difficulty-label JSONL files and summarize distribution drift."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def _row_key(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("query", "")), str(row.get("fl_problem", "")))


def _resolve_pass_key(rows: list[dict[str, Any]]) -> str:
    for row in rows:
        pass_keys = sorted(
            (key for key in row if key.startswith("pass_at_")),
            key=lambda key: int(key.split("_")[-1]),
            reverse=True,
        )
        if pass_keys:
            return pass_keys[0]
    raise KeyError("No pass_at_* field found")


def _pass_value(row: dict[str, Any], pass_key: str) -> float:
    return float(row.get(pass_key, 0.0))


def _stats(rows: list[dict[str, Any]], pass_key: str) -> dict[str, Any]:
    if not rows:
        return {
            "avg_pass": 0.0,
            "greedy_success_rate": 0.0,
            "median_pass": 0.0,
            "one_ratio": 0.0,
            "total_rows": 0,
            "zero_ratio": 0.0,
        }
    pass_values = [_pass_value(row, pass_key) for row in rows]
    total = len(rows)
    return {
        "avg_pass": sum(pass_values) / total,
        "median_pass": statistics.median(pass_values),
        "zero_ratio": sum(value == 0.0 for value in pass_values) / total,
        "one_ratio": sum(value == 1.0 for value in pass_values) / total,
        "greedy_success_rate": (
            sum(bool(row.get("greedy_success")) for row in rows) / total
        ),
        "all_invalid_rate": sum(bool(row.get("all_invalid")) for row in rows) / total,
        "total_rows": total,
    }


def _histogram(rows: list[dict[str, Any]], pass_key: str) -> dict[str, int]:
    return dict(
        sorted(
            Counter(f"{_pass_value(row, pass_key):.4f}" for row in rows).items(),
            key=lambda item: float(item[0]),
        )
    )


def build_drift_report(
    old_rows: list[dict[str, Any]], new_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    old_pass_key = _resolve_pass_key(old_rows)
    new_pass_key = _resolve_pass_key(new_rows)
    old_map = {_row_key(row): row for row in old_rows}
    new_map = {_row_key(row): row for row in new_rows}

    shared_keys = sorted(set(old_map) & set(new_map))
    missing_in_new = len(set(old_map) - set(new_map))
    missing_in_old = len(set(new_map) - set(old_map))

    old_matched = [old_map[key] for key in shared_keys]
    new_matched = [new_map[key] for key in shared_keys]
    deltas = [
        _pass_value(new_map[key], new_pass_key) - _pass_value(old_map[key], old_pass_key)
        for key in shared_keys
    ]
    movement = {
        "pass_up": sum(delta > 0.0 for delta in deltas),
        "pass_down": sum(delta < 0.0 for delta in deltas),
        "pass_same": sum(delta == 0.0 for delta in deltas),
        "delta_avg": sum(deltas) / len(deltas) if deltas else 0.0,
        "delta_median": statistics.median(deltas) if deltas else 0.0,
        "delta_ge_0_25_ratio": (
            sum(delta >= 0.25 for delta in deltas) / len(deltas) if deltas else 0.0
        ),
        "delta_ge_0_50_ratio": (
            sum(delta >= 0.50 for delta in deltas) / len(deltas) if deltas else 0.0
        ),
    }

    return {
        "matched_rows": len(shared_keys),
        "missing_in_new": missing_in_new,
        "missing_in_old": missing_in_old,
        "old_pass_key": old_pass_key,
        "new_pass_key": new_pass_key,
        "old_stats": _stats(old_matched, old_pass_key),
        "new_stats": _stats(new_matched, new_pass_key),
        "movement": movement,
        "old_pass_histogram": _histogram(old_matched, old_pass_key),
        "new_pass_histogram": _histogram(new_matched, new_pass_key),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("old", type=Path, help="Old difficulty-label JSONL")
    parser.add_argument("new", type=Path, help="New difficulty-label JSONL")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional JSON summary output path",
    )
    args = parser.parse_args()

    report = build_drift_report(load_jsonl(args.old), load_jsonl(args.new))
    if args.output is not None:
        write_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
