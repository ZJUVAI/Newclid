#!/usr/bin/env python3
"""Select a GRPO debug set from difficulty-labeled candidate rows."""

from __future__ import annotations

import argparse
import hashlib
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


def _row_id(row: dict[str, Any]) -> str:
    if "sample_id" in row:
        return str(row["sample_id"])
    return hashlib.sha256(row["query"].encode()).hexdigest()


def _resolve_pass_key(rows: list[dict[str, Any]]) -> str:
    for row in rows:
        pass_keys = sorted(
            (key for key in row.keys() if key.startswith("pass_at_")),
            key=lambda key: int(key.split("_")[-1]),
            reverse=True,
        )
        if pass_keys:
            return pass_keys[0]
    raise KeyError("No pass_at_* field found in difficulty-labeled rows")


def _is_preferred(row: dict[str, Any], pass_key: str) -> bool:
    return 0.15 <= row[pass_key] <= 0.60


def _is_fallback(row: dict[str, Any], pass_key: str) -> bool:
    return 0.10 <= row[pass_key] <= 0.80


def filter_goldilocks(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    preferred = []
    fallback = []
    pass_key = _resolve_pass_key(rows)
    stats = {
        "pass_key": pass_key,
        "removed_mastered": 0,
        "removed_all_invalid": 0,
        "preferred_rows": 0,
        "fallback_rows": 0,
    }
    for row in tqdm(rows, desc="Filtering goldilocks rows"):
        if row.get("greedy_success") and row.get(pass_key, 0.0) >= 0.90:
            stats["removed_mastered"] += 1
            continue
        if row.get("all_invalid"):
            stats["removed_all_invalid"] += 1
            continue
        if _is_preferred(row, pass_key):
            preferred.append(row)
        elif _is_fallback(row, pass_key):
            fallback.append(row)
    stats["preferred_rows"] = len(preferred)
    stats["fallback_rows"] = len(fallback)
    return preferred, fallback, stats


def _take_matching(
    selected: list[dict[str, Any]],
    used_ids: set[str],
    source: list[dict[str, Any]],
    predicate,
    limit: int,
) -> list[dict[str, Any]]:
    taken = []
    for row in source:
        if len(taken) >= limit:
            break
        if _row_id(row) in used_ids:
            continue
        if predicate(row):
            used_ids.add(_row_id(row))
            selected.append(row)
            taken.append(row)
    return taken


def select_debug_rows(rows: list[dict[str, Any]], target_size: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    preferred, fallback, filter_stats = filter_goldilocks(rows)
    source = preferred + fallback
    selected: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    shortages: dict[str, int] = {}

    multi_segment_target = int(target_size * 0.50)
    multi_point_target = int(target_size * 0.40)
    family_target = max(1, int(target_size * 0.10))
    goal_cap = max(1, int(target_size * 0.35))

    taken = _take_matching(
        selected,
        used_ids,
        source,
        lambda row: row.get("aux_segment_count", 0) >= 2,
        multi_segment_target,
    )
    shortages["multi_segment_shortage"] = max(0, multi_segment_target - len(taken))

    taken = _take_matching(
        selected,
        used_ids,
        source,
        lambda row: row.get("aux_points_total", 0) >= 2,
        multi_point_target,
    )
    shortages["multi_point_shortage"] = max(0, multi_point_target - len(taken))

    family_counter = Counter()
    for row in selected:
        for tag in row.get("predicate_family_tags", []):
            family_counter[tag] += 1

    all_families = sorted(
        {tag for row in source for tag in row.get("predicate_family_tags", [])}
    )
    for family in tqdm(all_families, desc="Balancing predicate families"):
        need = max(0, family_target - family_counter[family])
        taken = _take_matching(
            selected,
            used_ids,
            source,
            lambda row, family=family: family in row.get("predicate_family_tags", []),
            need,
        )
        shortages[f"{family}_shortage"] = max(0, need - len(taken))
        for row in taken:
            for tag in row.get("predicate_family_tags", []):
                family_counter[tag] += 1

    goal_counter = Counter(row.get("goal_predicate") for row in selected if row.get("goal_predicate"))
    for row in tqdm(source, desc="Filling remaining selected rows"):
        if len(selected) >= target_size:
            break
        if _row_id(row) in used_ids:
            continue
        goal_predicate = row.get("goal_predicate")
        if goal_predicate and goal_counter[goal_predicate] >= goal_cap:
            continue
        used_ids.add(_row_id(row))
        selected.append(row)
        if goal_predicate:
            goal_counter[goal_predicate] += 1
        for tag in row.get("predicate_family_tags", []):
            family_counter[tag] += 1

    final_rows = [
        {
            "query": row["query"],
            "fl_problem": row["fl_problem"],
            "response": row["response"],
        }
        for row in selected[:target_size]
    ]

    report = {
        **filter_stats,
        "target_size": target_size,
        "selected_rows": len(final_rows),
        "selected_goal_predicate_distribution": dict(goal_counter.most_common()),
        "selected_predicate_family_distribution": dict(family_counter.most_common()),
        "selected_aux_segment_count_distribution": dict(
            sorted(Counter(row.get("aux_segment_count", 0) for row in selected).items())
        ),
        "selected_aux_points_total_distribution": dict(
            sorted(Counter(row.get("aux_points_total", 0) for row in selected).items())
        ),
        "shortages": shortages,
    }
    return final_rows, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Difficulty labels JSONL")
    parser.add_argument("output", type=Path, help="Selected debug-set JSONL")
    parser.add_argument(
        "--report-output",
        type=Path,
        required=True,
        help="JSON report path",
    )
    parser.add_argument("--target-size", type=int, default=2000)
    args = parser.parse_args()

    rows = load_jsonl(args.input)
    final_rows, report = select_debug_rows(rows, args.target_size)
    write_jsonl(args.output, final_rows)
    write_json(args.report_output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
