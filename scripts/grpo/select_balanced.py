#!/usr/bin/env python3
"""Select a balanced GRPO training set from difficulty-labeled candidate rows.

Selection goals (in priority order):
1. Aux predicate combination distribution as uniform as possible
2. 50% aux_segment_count == 1, 50% aux_segment_count > 1 (best-effort)
3. Within each cell, prefer higher problem point count (best-effort)
4. Goal predicate distribution as uniform as possible (best-effort)
"""

from __future__ import annotations

import argparse
import json
import re
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


def _extract_tag(text: str, tag: str) -> str:
    m = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL)
    return m.group(1).strip() if m else ""


def _aux_combination_key(row: dict[str, Any]) -> tuple[str, ...]:
    """Sorted tuple of predicates from the first valid aux segment."""
    response = row.get("response") or ""
    aux = _extract_tag(response, "aux")
    if not aux:
        return ()

    for seg in aux.split(";"):
        seg = seg.strip()
        if ":" not in seg:
            continue
        after = seg.split(":", 1)[1]
        predicates = re.findall(r"([a-z]+)\s+[a-z\s]+\s*\[\d+\]", after)
        if predicates:
            return tuple(sorted(predicates))

    return ()


def _problem_point_count(row: dict[str, Any]) -> int:
    """Count distinct points in the problem statement."""
    query = row.get("query") or ""
    problem = _extract_tag(query, "problem")
    if not problem:
        return 0
    points: set[str] = set()
    for seg in problem.split(";"):
        seg = seg.strip()
        if ":" not in seg:
            continue
        before = seg.split(":", 1)[0].strip()
        points.update(t for t in before.split() if t)
    return len(points)


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


def _take_uniform_goal(
    pool: list[dict[str, Any]], quota: int
) -> list[dict[str, Any]]:
    """Pick `quota` rows from pool, sampling uniformly across goal predicates.
    Within each goal predicate, rows are already sorted by point count desc.
    """
    if quota <= 0 or not pool:
        return []

    by_goal: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in pool:
        by_goal[row.get("goal_predicate") or "_unknown"].append(row)

    goals = sorted(by_goal.keys())
    cursors = {g: 0 for g in goals}
    result: list[dict[str, Any]] = []

    # Round-robin across goal predicates until quota filled or all exhausted
    while len(result) < quota:
        made_progress = False
        for g in goals:
            if len(result) >= quota:
                break
            idx = cursors[g]
            if idx < len(by_goal[g]):
                result.append(by_goal[g][idx])
                cursors[g] += 1
                made_progress = True
        if not made_progress:
            break

    return result


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

    # Annotate each candidate with derived fields used for selection
    for row in tqdm(candidates, desc="Annotating"):
        row["_combo"] = _aux_combination_key(row)
        row["_point_count"] = _problem_point_count(row)

    # Build cells: combination -> seg_layer -> rows sorted by point count desc
    cells: dict[tuple[str, ...], dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: {"seg1": [], "seg_gt1": []}
    )
    for row in candidates:
        seg = row.get("aux_segment_count", 0)
        layer = "seg1" if seg == 1 else "seg_gt1"
        cells[row["_combo"]][layer].append(row)

    for combo in cells:
        for layer in ("seg1", "seg_gt1"):
            cells[combo][layer].sort(key=lambda r: r["_point_count"], reverse=True)

    combinations = sorted(cells.keys())
    n_combos = len(combinations)
    if n_combos == 0:
        return [], {"selected_rows": 0, "error": "no eligible candidates"}

    # Equal quota per combination; remainder to largest combos
    base_quota = target_size // n_combos
    remainder = target_size - base_quota * n_combos
    combo_total = {
        c: len(cells[c]["seg1"]) + len(cells[c]["seg_gt1"]) for c in combinations
    }
    combos_by_size = sorted(combinations, key=lambda c: combo_total[c], reverse=True)
    combo_quota = {c: base_quota for c in combinations}
    for c in combos_by_size[:remainder]:
        combo_quota[c] += 1

    selected: list[dict[str, Any]] = []
    seg_gt1_shortage = 0
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
        got_seg1 = min(want_seg1 + shortage, avail_seg1)

        total_got = got_gt1 + got_seg1
        leftover_quota = quota - total_got

        # Within each seg layer, sample uniformly across goal predicates
        selected.extend(_take_uniform_goal(cells[combo]["seg_gt1"][:avail_gt1], got_gt1))
        selected.extend(_take_uniform_goal(cells[combo]["seg1"][:avail_seg1], got_seg1))

    # Distribute leftover quota from exhausted combos to largest remaining combos
    if leftover_quota > 0:
        already_taken: dict[tuple[str, ...], int] = Counter(
            r["_combo"] for r in selected
        )
        for combo in combos_by_size:
            if leftover_quota <= 0:
                break
            taken = already_taken.get(combo, 0)
            avail = combo_total[combo] - taken
            extra = min(leftover_quota, avail)
            if extra <= 0:
                continue
            all_rows = cells[combo]["seg_gt1"] + cells[combo]["seg1"]
            all_rows.sort(key=lambda r: r["_point_count"], reverse=True)
            pool = [r for r in all_rows if r not in selected]
            selected.extend(_take_uniform_goal(pool, extra))
            leftover_quota -= extra

    selected = selected[:target_size]

    final_rows = [
        {"query": r["query"], "fl_problem": r["fl_problem"], "response": r["response"]}
        for r in selected
    ]

    # Build report
    total_sel = len(final_rows)
    bucket_counter: Counter[str] = Counter(r["_bucket"] for r in selected)
    goal_counter: Counter[str] = Counter(
        r.get("goal_predicate") for r in selected if r.get("goal_predicate")
    )
    combo_counter: Counter[str] = Counter(str(r["_combo"]) for r in selected)
    seg_counter: Counter[int] = Counter(r.get("aux_segment_count", 0) for r in selected)
    pts_counter: Counter[int] = Counter(r["_point_count"] for r in selected)
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
        "problem_point_count_distribution": dict(sorted(pts_counter.items())),
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
