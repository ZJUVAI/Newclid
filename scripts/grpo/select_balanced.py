#!/usr/bin/env python3
"""Select a balanced GRPO training set from difficulty-labeled candidate rows.

Selection goals (in priority order):
1. Predicate combination distribution as uniform as possible
2. 50% aux_segment_count == 1, 50% aux_segment_count > 1 (best-effort)
3. Within each cell, prefer higher aux_points_total
4. Goal predicate distribution recorded in report (not a hard constraint)
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from tqdm import tqdm

from select_debug_set import (
    _classify_bucket_unified,
    _resolve_pass_key,
    load_jsonl,
    write_json,
    write_jsonl,
)


def _combination_key(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(sorted(row.get("predicate_family_tags") or []))


def _classify_rows(
    rows: list[dict[str, Any]],
    *,
    core_min_pass: float,
    core_max_pass: float,
    mastered_pass_min: float,
    zero_pass_reward_std_min: float,
) -> list[dict[str, Any]]:
    pass_key = _resolve_pass_key(rows)
    candidates = []
    for row in tqdm(rows, desc="Classifying"):
        bucket = _classify_bucket_unified(
            row,
            pass_key,
            core_min_pass=core_min_pass,
            core_max_pass=core_max_pass,
            mastered_pass_min=mastered_pass_min,
            zero_pass_reward_std_min=zero_pass_reward_std_min,
        )
        if bucket in ("core", "reward_mixed_zero"):
            candidates.append({**row, "_bucket": bucket})
    return candidates


def select_balanced(
    rows: list[dict[str, Any]],
    target_size: int,
    *,
    core_min_pass: float = 0.0625,
    core_max_pass: float = 0.75,
    mastered_pass_min: float = 0.90,
    zero_pass_reward_std_min: float = 0.15,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    candidates = _classify_rows(
        rows,
        core_min_pass=core_min_pass,
        core_max_pass=core_max_pass,
        mastered_pass_min=mastered_pass_min,
        zero_pass_reward_std_min=zero_pass_reward_std_min,
    )

    # Build cells: combination -> seg_layer -> rows sorted by aux_points_total desc
    # seg_layer: "seg1" (==1) or "seg_gt1" (>1)
    cells: dict[tuple[str, ...], dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: {"seg1": [], "seg_gt1": []}
    )
    for row in candidates:
        combo = _combination_key(row)
        seg = row.get("aux_segment_count", 0)
        layer = "seg1" if seg == 1 else "seg_gt1"
        cells[combo][layer].append(row)

    for combo in cells:
        for layer in ("seg1", "seg_gt1"):
            cells[combo][layer].sort(
                key=lambda r: int(r.get("aux_points_total", 0)), reverse=True
            )

    combinations = sorted(cells.keys())
    n_combos = len(combinations)
    if n_combos == 0:
        return [], {"selected_rows": 0, "error": "no eligible candidates"}

    # Allocate quota per combination: equal share, remainder goes to largest combos
    base_quota = target_size // n_combos
    remainder = target_size - base_quota * n_combos
    # Give remainder slots to combinations with most candidates
    combo_total = {
        c: len(cells[c]["seg1"]) + len(cells[c]["seg_gt1"]) for c in combinations
    }
    combos_by_size = sorted(combinations, key=lambda c: combo_total[c], reverse=True)
    combo_quota = {c: base_quota for c in combinations}
    for c in combos_by_size[:remainder]:
        combo_quota[c] += 1

    selected: list[dict[str, Any]] = []
    seg_gt1_shortage = 0
    cursors: dict[tuple[str, ...], dict[str, int]] = {
        c: {"seg1": 0, "seg_gt1": 0} for c in combinations
    }
    leftover_quota = 0

    for combo in combinations:
        quota = combo_quota[combo] + leftover_quota
        leftover_quota = 0
        half = quota // 2
        want_gt1 = half
        want_seg1 = quota - half

        avail_gt1 = len(cells[combo]["seg_gt1"])
        avail_seg1 = len(cells[combo]["seg1"])

        got_gt1 = min(want_gt1, avail_gt1)
        shortage = want_gt1 - got_gt1
        seg_gt1_shortage += shortage
        # fill shortage from seg1
        got_seg1 = min(want_seg1 + shortage, avail_seg1)

        total_got = got_gt1 + got_seg1
        leftover_quota = quota - total_got

        for row in cells[combo]["seg_gt1"][:got_gt1]:
            selected.append(row)
        for row in cells[combo]["seg1"][:got_seg1]:
            selected.append(row)

    # Distribute any leftover quota from exhausted combos
    if leftover_quota > 0:
        for combo in combos_by_size:
            if leftover_quota <= 0:
                break
            already_gt1 = min(combo_quota[combo] // 2, len(cells[combo]["seg_gt1"]))
            already_seg1 = min(
                combo_quota[combo] - already_gt1 + (combo_quota[combo] // 2 - already_gt1),
                len(cells[combo]["seg1"]),
            )
            used = already_gt1 + already_seg1
            extra = min(leftover_quota, combo_total[combo] - used)
            # take from seg_gt1 first, then seg1
            extra_gt1 = min(extra, len(cells[combo]["seg_gt1"]) - already_gt1)
            extra_seg1 = min(extra - extra_gt1, len(cells[combo]["seg1"]) - already_seg1)
            for row in cells[combo]["seg_gt1"][already_gt1: already_gt1 + extra_gt1]:
                selected.append(row)
            for row in cells[combo]["seg1"][already_seg1: already_seg1 + extra_seg1]:
                selected.append(row)
            leftover_quota -= extra_gt1 + extra_seg1

    final_rows = [
        {"query": r["query"], "fl_problem": r["fl_problem"], "response": r["response"]}
        for r in selected[:target_size]
    ]

    # Build report
    bucket_counter: Counter[str] = Counter(r["_bucket"] for r in selected[:target_size])
    goal_counter: Counter[str] = Counter(
        r.get("goal_predicate") for r in selected[:target_size] if r.get("goal_predicate")
    )
    combo_counter: Counter[str] = Counter(
        str(_combination_key(r)) for r in selected[:target_size]
    )
    seg_counter: Counter[int] = Counter(
        r.get("aux_segment_count", 0) for r in selected[:target_size]
    )
    pts_counter: Counter[int] = Counter(
        r.get("aux_points_total", 0) for r in selected[:target_size]
    )

    total_sel = len(final_rows)
    seg_gt1_count = sum(v for k, v in seg_counter.items() if k > 1)

    report = {
        "target_size": target_size,
        "selected_rows": total_sel,
        "candidate_rows": len(candidates),
        "core_selected": bucket_counter.get("core", 0),
        "reward_mixed_zero_selected": bucket_counter.get("reward_mixed_zero", 0),
        "seg1_count": seg_counter.get(1, 0),
        "seg1_ratio": seg_counter.get(1, 0) / total_sel if total_sel else 0.0,
        "seg_gt1_count": seg_gt1_count,
        "seg_gt1_ratio": seg_gt1_count / total_sel if total_sel else 0.0,
        "seg_gt1_shortage": seg_gt1_shortage,
        "n_combinations": n_combos,
        "goal_predicate_distribution": dict(goal_counter.most_common()),
        "predicate_combination_distribution": dict(combo_counter.most_common()),
        "aux_segment_count_distribution": dict(sorted(seg_counter.items())),
        "aux_points_total_distribution": dict(sorted(pts_counter.items())),
        "thresholds": {
            "core_pass_window": [core_min_pass, core_max_pass],
            "mastered_pass_min": mastered_pass_min,
            "zero_pass_reward_std_min": zero_pass_reward_std_min,
        },
    }
    return final_rows, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Difficulty-labeled JSONL")
    parser.add_argument("output", type=Path, help="Selected JSONL")
    parser.add_argument("--report-output", type=Path, help="JSON report path")
    parser.add_argument("--target-size", type=int, default=2000)
    parser.add_argument("--core-pass-min", type=float, default=0.0625)
    parser.add_argument("--core-pass-max", type=float, default=0.75)
    parser.add_argument("--mastered-pass-min", type=float, default=0.90)
    parser.add_argument("--zero-pass-reward-std-min", type=float, default=0.15)
    args = parser.parse_args()

    rows = load_jsonl(args.input)
    final_rows, report = select_balanced(
        rows,
        args.target_size,
        core_min_pass=args.core_pass_min,
        core_max_pass=args.core_pass_max,
        mastered_pass_min=args.mastered_pass_min,
        zero_pass_reward_std_min=args.zero_pass_reward_std_min,
    )
    write_jsonl(args.output, final_rows)
    if args.report_output:
        write_json(args.report_output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
