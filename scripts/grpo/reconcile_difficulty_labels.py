#!/usr/bin/env python3
"""Reuse existing difficulty labels and optionally merge newly labeled deltas."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
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


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate_pool", type=Path, help="Target candidate pool JSONL")
    parser.add_argument(
        "existing_labels",
        type=Path,
        help="Previously labeled difficulty JSONL used for reuse by sample_id",
    )
    parser.add_argument(
        "--reused-output",
        type=Path,
        default=None,
        help="Optional JSONL path for labels reused from existing_labels",
    )
    parser.add_argument(
        "--delta-output",
        type=Path,
        default=None,
        help="Optional JSONL path for unlabeled candidate rows missing in existing_labels",
    )
    parser.add_argument(
        "--delta-labeled-input",
        type=Path,
        default=None,
        help="Optional JSONL path with newly labeled delta rows for merge",
    )
    parser.add_argument(
        "--merged-output",
        type=Path,
        default=None,
        help="Optional JSONL path for full merged labels in candidate_pool order",
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=None,
        help="Optional JSON report path",
    )
    args = parser.parse_args()

    existing_by_id = {
        str(row["sample_id"]): row for row in load_jsonl(args.existing_labels)
    }
    delta_by_id: dict[str, dict[str, Any]] = {}
    if args.delta_labeled_input is not None:
        delta_by_id = {
            str(row["sample_id"]): row for row in load_jsonl(args.delta_labeled_input)
        }

    reused_rows: list[dict[str, Any]] = []
    delta_rows: list[dict[str, Any]] = []
    merged_rows: list[dict[str, Any]] = []
    total_rows = 0
    missing_merged_ids: list[str] = []

    for row in load_jsonl(args.candidate_pool):
        total_rows += 1
        sample_id = str(row["sample_id"])
        existing = existing_by_id.get(sample_id)
        if existing is not None:
            reused_rows.append(existing)
            if args.merged_output is not None:
                merged_rows.append(existing)
            continue

        delta_rows.append(row)
        if args.merged_output is None:
            continue
        labeled_delta = delta_by_id.get(sample_id)
        if labeled_delta is None:
            missing_merged_ids.append(sample_id)
            continue
        merged_rows.append(labeled_delta)

    if args.merged_output is not None and missing_merged_ids:
        preview = ", ".join(missing_merged_ids[:5])
        raise ValueError(
            "Missing delta labels for "
            f"{len(missing_merged_ids)} sample_ids; first few: {preview}"
        )

    if args.reused_output is not None:
        write_jsonl(args.reused_output, reused_rows)
    if args.delta_output is not None:
        write_jsonl(args.delta_output, delta_rows)
    if args.merged_output is not None:
        write_jsonl(args.merged_output, merged_rows)

    report = {
        "candidate_pool_path": str(args.candidate_pool),
        "existing_labels_path": str(args.existing_labels),
        "delta_labeled_input_path": (
            str(args.delta_labeled_input) if args.delta_labeled_input is not None else None
        ),
        "total_rows": total_rows,
        "reused_rows": len(reused_rows),
        "reused_ratio": len(reused_rows) / total_rows if total_rows else 0.0,
        "delta_rows": len(delta_rows),
        "delta_ratio": len(delta_rows) / total_rows if total_rows else 0.0,
        "merged_rows": len(merged_rows),
        "reused_output_path": str(args.reused_output) if args.reused_output else None,
        "delta_output_path": str(args.delta_output) if args.delta_output else None,
        "merged_output_path": str(args.merged_output) if args.merged_output else None,
    }
    if args.report_output is not None:
        write_json(args.report_output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
