#!/usr/bin/env python3
"""Build a GRPO candidate pool from annotated dataset rows."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from tqdm import tqdm


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def build_candidate_pool(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    kept = []
    dropped_no_aux = 0
    dropped_missing_fields = 0
    goal_counter = Counter()
    family_counter = Counter()
    segment_counter = Counter()
    points_counter = Counter()

    for row in tqdm(rows, desc="Building candidate pool"):
        if not row.get("has_aux"):
            dropped_no_aux += 1
            continue
        if (
            not row.get("query")
            or not row.get("fl_problem")
            or not row.get("response_aux")
        ):
            dropped_missing_fields += 1
            continue
        if row.get("aux_segment_count", 0) < 1 or row.get("aux_points_total", 0) < 1:
            dropped_missing_fields += 1
            continue

        kept_row = {
            "sample_id": row["sample_id"],
            "query": row["query"],
            "fl_problem": row["fl_problem"],
            "response": row["response_aux"],
            "goal_predicate": row.get("goal_predicate"),
            "predicate_family_tags": row.get("predicate_family_tags", []),
            "aux_segment_count": row.get("aux_segment_count", 0),
            "aux_points_total": row.get("aux_points_total", 0),
            "n_premises": row.get("n_premises"),
            "problem_predicate_count": row.get("problem_predicate_count", 0),
            "problem_clause_count": row.get("problem_clause_count", 0),
        }
        kept.append(kept_row)
        if kept_row["goal_predicate"]:
            goal_counter[kept_row["goal_predicate"]] += 1
        for tag in kept_row["predicate_family_tags"]:
            family_counter[tag] += 1
        segment_counter[kept_row["aux_segment_count"]] += 1
        points_counter[kept_row["aux_points_total"]] += 1

    summary = {
        "total_rows": len(rows),
        "kept_rows": len(kept),
        "dropped_no_aux": dropped_no_aux,
        "dropped_missing_fields": dropped_missing_fields,
        "goal_predicate_distribution": dict(goal_counter.most_common()),
        "predicate_family_distribution": dict(family_counter.most_common()),
        "aux_segment_count_distribution": dict(sorted(segment_counter.items())),
        "aux_points_total_distribution": dict(sorted(points_counter.items())),
    }
    return kept, summary


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
    parser.add_argument(
        "input", type=Path, help="Annotated JSONL from analyze_dataset.py"
    )
    parser.add_argument("output", type=Path, help="Candidate pool JSONL output")
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=None,
        help="Optional JSON path for candidate pool summary",
    )
    args = parser.parse_args()

    rows = load_jsonl(args.input)
    pool, summary = build_candidate_pool(rows)
    write_jsonl(args.output, pool)
    if args.summary_output is not None:
        write_json(args.summary_output, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
