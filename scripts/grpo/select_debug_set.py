#!/usr/bin/env python3
"""Select a GRPO debug set from difficulty-labeled candidate rows."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from scripts._tqdm import tqdm


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


def _matches_pass_stage(
    row: dict[str, Any], pass_key: str, stage: tuple[str, float, float]
) -> bool:
    _, min_pass, max_pass = stage
    pass_value = float(row.get(pass_key, 0.0))
    return min_pass <= pass_value <= max_pass


def _build_pass_histogram(
    rows: list[dict[str, Any]], pass_key: str
) -> dict[str, int]:
    return dict(
        sorted(
            Counter(f"{float(row.get(pass_key, 0.0)):.4f}" for row in rows).items(),
            key=lambda item: float(item[0]),
        )
    )


def filter_goldilocks(
    rows: list[dict[str, Any]],
    *,
    preferred_min_pass: float,
    preferred_max_pass: float,
    fallback_min_pass: float,
    fallback_max_pass: float,
    relaxed_min_pass: float,
    relaxed_max_pass: float,
    mastered_pass_min: float,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    pass_key = _resolve_pass_key(rows)
    stages = [
        ("preferred", preferred_min_pass, preferred_max_pass),
        ("fallback", fallback_min_pass, fallback_max_pass),
        ("relaxed", relaxed_min_pass, relaxed_max_pass),
    ]
    stage_rows = {
        "preferred": [],
        "fallback": [],
        "relaxed": [],
        "non_dead": [],
        "capped_mastered": [],
    }
    stats = {
        "pass_key": pass_key,
        "removed_mastered": 0,
        "removed_all_invalid": 0,
        "stage_available_rows": {},
        "mastered_pass_threshold": mastered_pass_min,
    }
    for row in tqdm(rows, desc="Filtering goldilocks rows"):
        pass_value = float(row.get(pass_key, 0.0))
        if row.get("greedy_success") and pass_value >= mastered_pass_min:
            stats["removed_mastered"] += 1
            stage_rows["capped_mastered"].append(
                {**row, "_selection_stage": "capped_mastered"}
            )
            continue
        if row.get("all_invalid"):
            stats["removed_all_invalid"] += 1
            continue

        assigned_stage = "non_dead"
        for stage in stages:
            if _matches_pass_stage(row, pass_key, stage):
                assigned_stage = stage[0]
                break
        stage_rows[assigned_stage].append({**row, "_selection_stage": assigned_stage})

    stats["stage_available_rows"] = {
        stage_name: len(candidates) for stage_name, candidates in stage_rows.items()
    }
    return stage_rows, stats


def _selected_mastered_count(selected: list[dict[str, Any]]) -> int:
    return sum(1 for row in selected if row.get("_selection_stage") == "capped_mastered")


def _take_matching(
    selected: list[dict[str, Any]],
    used_ids: set[str],
    source: list[dict[str, Any]],
    predicate,
    limit: int,
    mastered_cap: int,
) -> list[dict[str, Any]]:
    taken = []
    for row in source:
        if len(taken) >= limit:
            break
        if _row_id(row) in used_ids:
            continue
        if (
            row.get("_selection_stage") == "capped_mastered"
            and _selected_mastered_count(selected) >= mastered_cap
        ):
            continue
        if predicate(row):
            used_ids.add(_row_id(row))
            selected.append(row)
            taken.append(row)
    return taken


def select_debug_rows(
    rows: list[dict[str, Any]],
    target_size: int,
    *,
    preferred_min_pass: float = 0.15,
    preferred_max_pass: float = 0.60,
    fallback_min_pass: float = 0.10,
    fallback_max_pass: float = 0.80,
    relaxed_min_pass: float = 0.05,
    relaxed_max_pass: float = 0.90,
    mastered_pass_min: float = 0.90,
    mastered_max_fraction: float = 0.20,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    stage_rows, filter_stats = filter_goldilocks(
        rows,
        preferred_min_pass=preferred_min_pass,
        preferred_max_pass=preferred_max_pass,
        fallback_min_pass=fallback_min_pass,
        fallback_max_pass=fallback_max_pass,
        relaxed_min_pass=relaxed_min_pass,
        relaxed_max_pass=relaxed_max_pass,
        mastered_pass_min=mastered_pass_min,
    )
    source = (
        stage_rows["preferred"]
        + stage_rows["fallback"]
        + stage_rows["relaxed"]
        + stage_rows["non_dead"]
        + stage_rows["capped_mastered"]
    )
    selected: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    shortages: dict[str, int] = {}
    pass_key = filter_stats["pass_key"]
    mastered_cap = max(0, int(target_size * mastered_max_fraction))

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
        mastered_cap,
    )
    shortages["multi_segment_shortage"] = max(0, multi_segment_target - len(taken))

    taken = _take_matching(
        selected,
        used_ids,
        source,
        lambda row: row.get("aux_points_total", 0) >= 2,
        multi_point_target,
        mastered_cap,
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
            mastered_cap,
        )
        shortages[f"{family}_shortage"] = max(0, need - len(taken))
        for row in taken:
            for tag in row.get("predicate_family_tags", []):
                family_counter[tag] += 1

    goal_counter = Counter(
        row.get("goal_predicate") for row in selected if row.get("goal_predicate")
    )
    for row in tqdm(source, desc="Filling remaining selected rows"):
        if len(selected) >= target_size:
            break
        if _row_id(row) in used_ids:
            continue
        if (
            row.get("_selection_stage") == "capped_mastered"
            and _selected_mastered_count(selected) >= mastered_cap
        ):
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

    selected_full_rows = selected[:target_size]
    selected_goal_counter = Counter(
        row.get("goal_predicate") for row in selected_full_rows if row.get("goal_predicate")
    )
    selected_family_counter = Counter()
    for row in selected_full_rows:
        for tag in row.get("predicate_family_tags", []):
            selected_family_counter[tag] += 1
    selected_stage_counts = Counter(
        row.get("_selection_stage", "unknown") for row in selected_full_rows
    )
    selected_mastered = _selected_mastered_count(selected_full_rows)
    shortage_reasons = []
    if len(final_rows) < target_size:
        shortage_reasons.append("eligible_pool_exhausted_before_target")
        if (
            selected_stage_counts.get("capped_mastered", 0) >= mastered_cap
            and len(stage_rows["capped_mastered"]) > mastered_cap
        ):
            shortage_reasons.append("mastered_cap_reached")
        if filter_stats["removed_all_invalid"] > 0:
            shortage_reasons.append("dead_rows_removed")
        if filter_stats["removed_mastered"] > 0:
            shortage_reasons.append("mastered_rows_limited")

    report = {
        **filter_stats,
        "target_size": target_size,
        "selected_rows": len(final_rows),
        "stage_order": [
            "preferred",
            "fallback",
            "relaxed",
            "non_dead",
            "capped_mastered",
        ],
        "stage_selected_rows": dict(selected_stage_counts),
        "pass_windows": {
            "preferred": [preferred_min_pass, preferred_max_pass],
            "fallback": [fallback_min_pass, fallback_max_pass],
            "relaxed": [relaxed_min_pass, relaxed_max_pass],
        },
        "mastered_max_fraction": mastered_max_fraction,
        "mastered_cap_rows": mastered_cap,
        "selected_mastered_rows": selected_mastered,
        "selected_mastered_ratio": (
            selected_mastered / len(final_rows) if final_rows else 0.0
        ),
        "selected_pass_histogram": _build_pass_histogram(selected_full_rows, pass_key),
        "selected_goal_predicate_distribution": dict(selected_goal_counter.most_common()),
        "selected_predicate_family_distribution": dict(
            selected_family_counter.most_common()
        ),
        "selected_aux_segment_count_distribution": dict(
            sorted(
                Counter(
                    row.get("aux_segment_count", 0) for row in selected_full_rows
                ).items()
            )
        ),
        "selected_aux_points_total_distribution": dict(
            sorted(
                Counter(
                    row.get("aux_points_total", 0) for row in selected_full_rows
                ).items()
            )
        ),
        "shortages": shortages,
        "shortage_reasons": shortage_reasons,
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
    parser.add_argument("--preferred-pass-min", type=float, default=0.15)
    parser.add_argument("--preferred-pass-max", type=float, default=0.60)
    parser.add_argument("--fallback-pass-min", type=float, default=0.10)
    parser.add_argument("--fallback-pass-max", type=float, default=0.80)
    parser.add_argument("--relaxed-pass-min", type=float, default=0.05)
    parser.add_argument("--relaxed-pass-max", type=float, default=0.90)
    parser.add_argument("--mastered-pass-min", type=float, default=0.90)
    parser.add_argument("--mastered-max-fraction", type=float, default=0.20)
    args = parser.parse_args()

    rows = load_jsonl(args.input)
    final_rows, report = select_debug_rows(
        rows,
        args.target_size,
        preferred_min_pass=args.preferred_pass_min,
        preferred_max_pass=args.preferred_pass_max,
        fallback_min_pass=args.fallback_pass_min,
        fallback_max_pass=args.fallback_pass_max,
        relaxed_min_pass=args.relaxed_pass_min,
        relaxed_max_pass=args.relaxed_pass_max,
        mastered_pass_min=args.mastered_pass_min,
        mastered_max_fraction=args.mastered_max_fraction,
    )
    write_jsonl(args.output, final_rows)
    write_json(args.report_output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
