#!/usr/bin/env python3
"""Select a GRPO debug set from difficulty-labeled candidate rows."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from scripts._tqdm import tqdm

POLICY_TIER_ORDER = {
    "v3_tiered": (
        "core",
        "near",
        "hard_valid_high",
        "hard_valid_mid",
        "mastered",
    ),
    "v4_reward_mixed": (
        "core",
        "near",
        "reward_mixed_zero",
        "mastered",
    ),
}
NON_MASTERED_TIERS_BY_POLICY = {
    "v3_tiered": (
        "core",
        "near",
        "hard_valid_high",
        "hard_valid_mid",
    ),
    "v4_reward_mixed": (
        "core",
        "near",
        "reward_mixed_zero",
    ),
}
ALL_TIERS = (
    "core",
    "near",
    "hard_valid_high",
    "hard_valid_mid",
    "reward_mixed_zero",
    "mastered",
)
DEFAULT_REWARD_BY_STATUS = {
    "solved": 1.0,
    "unsolved": 0.25,
    "build_invalid": -0.25,
    "format_invalid": -1.0,
    "engine_error": 0.0,
}


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


def _pass_value(row: dict[str, Any], pass_key: str) -> float:
    return float(row.get(pass_key, 0.0))


def _paired_metric_key(row: dict[str, Any], prefix: str, pass_key: str) -> str | None:
    suffix = pass_key.split("_")[-1]
    candidate = f"{prefix}_{suffix}"
    if candidate in row:
        return candidate
    for key in sorted(row.keys(), reverse=True):
        if key.startswith(f"{prefix}_"):
            return key
    return None


def _valid_ratio(row: dict[str, Any], pass_key: str) -> float:
    valid_key = _paired_metric_key(row, "valid_at", pass_key)
    if valid_key is None:
        return 0.0
    return float(row.get(valid_key, 0.0))


def _proxy_reward_values(row: dict[str, Any]) -> list[float]:
    values: list[float] = []
    for status, reward in DEFAULT_REWARD_BY_STATUS.items():
        if status == "solved":
            count = int(row.get("solved_count", 0))
        elif status == "unsolved":
            count = int(row.get("unsolved_count", 0))
        else:
            count = int(row.get(f"{status}_count", 0))
        values.extend([reward] * max(0, count))
    return values


def _proxy_reward_std(row: dict[str, Any]) -> float:
    values = _proxy_reward_values(row)
    return statistics.pstdev(values) if values else 0.0


def _build_pass_histogram(rows: list[dict[str, Any]], pass_key: str) -> dict[str, int]:
    return dict(
        sorted(
            Counter(f"{_pass_value(row, pass_key):.4f}" for row in rows).items(),
            key=lambda item: float(item[0]),
        )
    )


def _tier_rank(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        -_proxy_reward_std(row),
        -int(row.get("unique_aux_count", 0)),
        float(row.get("duplicate_aux_ratio", 1.0)),
        abs(_valid_ratio(row, "pass_at_16") - 0.5),
        int(row.get("build_invalid_count", 0)),
        int(row.get("format_invalid_count", 0)),
        -int(row.get("aux_segment_count", 0)),
        -int(row.get("aux_points_total", 0)),
        -int(row.get("n_premises", 0)),
        -int(row.get("problem_predicate_count", 0)),
        -int(row.get("problem_clause_count", 0)),
        _row_id(row),
    )


def _classify_row(
    row: dict[str, Any],
    pass_key: str,
    *,
    selection_policy: str,
    core_min_pass: float,
    core_max_pass: float,
    mastered_pass_min: float,
    hard_valid_build_invalid_max: int,
    hard_valid_format_invalid_max: int,
    hard_valid_unique_aux_min: int,
    hard_valid_duplicate_aux_max: float,
    zero_valid_min: float,
    zero_valid_max: float,
    zero_pass_reward_std_min: float,
    reward_mixed_zero_unique_aux_min: int,
) -> str:
    pass_value = _pass_value(row, pass_key)
    if row.get("greedy_success") and pass_value >= mastered_pass_min:
        return "mastered"
    if row.get("all_invalid"):
        return "all_invalid"
    if core_min_pass <= pass_value <= core_max_pass:
        return "core"
    if (0.0 < pass_value < core_min_pass) or (
        core_max_pass < pass_value < mastered_pass_min
    ):
        return "near"
    if pass_value != 0.0:
        return "discarded_non_dead"

    if selection_policy == "v4_reward_mixed":
        valid_ratio = _valid_ratio(row, pass_key)
        if valid_ratio < zero_valid_min or valid_ratio > zero_valid_max:
            return "discarded_non_dead"
        if _proxy_reward_std(row) < zero_pass_reward_std_min:
            return "discarded_non_dead"
        if int(row.get("unique_aux_count", 0)) < reward_mixed_zero_unique_aux_min:
            return "discarded_non_dead"
        return "reward_mixed_zero"

    build_invalid_count = int(row.get("build_invalid_count", 0))
    format_invalid_count = int(row.get("format_invalid_count", 0))
    if build_invalid_count > hard_valid_build_invalid_max:
        return "discarded_non_dead"
    if format_invalid_count > hard_valid_format_invalid_max:
        return "discarded_non_dead"

    unique_aux_count = int(row.get("unique_aux_count", 0))
    duplicate_aux_ratio = float(row.get("duplicate_aux_ratio", 1.0))
    if (
        unique_aux_count >= hard_valid_unique_aux_min
        or duplicate_aux_ratio <= hard_valid_duplicate_aux_max
    ):
        return "hard_valid_high"
    return "hard_valid_mid"


def filter_candidate_tiers(
    rows: list[dict[str, Any]],
    *,
    selection_policy: str,
    core_min_pass: float,
    core_max_pass: float,
    mastered_pass_min: float,
    hard_valid_build_invalid_max: int,
    hard_valid_format_invalid_max: int,
    hard_valid_unique_aux_min: int,
    hard_valid_duplicate_aux_max: float,
    zero_valid_min: float,
    zero_valid_max: float,
    zero_pass_reward_std_min: float,
    reward_mixed_zero_unique_aux_min: int,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    pass_key = _resolve_pass_key(rows)
    tier_rows = {tier_name: [] for tier_name in ALL_TIERS}
    stats = {
        "pass_key": pass_key,
        "removed_all_invalid": 0,
        "removed_mastered": 0,
        "discarded_non_dead_rows": 0,
        "tier_available_rows": {},
        "selection_policy": selection_policy,
    }

    for row in tqdm(rows, desc="Classifying candidate tiers"):
        tier = _classify_row(
            row,
            pass_key,
            selection_policy=selection_policy,
            core_min_pass=core_min_pass,
            core_max_pass=core_max_pass,
            mastered_pass_min=mastered_pass_min,
            hard_valid_build_invalid_max=hard_valid_build_invalid_max,
            hard_valid_format_invalid_max=hard_valid_format_invalid_max,
            hard_valid_unique_aux_min=hard_valid_unique_aux_min,
            hard_valid_duplicate_aux_max=hard_valid_duplicate_aux_max,
            zero_valid_min=zero_valid_min,
            zero_valid_max=zero_valid_max,
            zero_pass_reward_std_min=zero_pass_reward_std_min,
            reward_mixed_zero_unique_aux_min=reward_mixed_zero_unique_aux_min,
        )
        if tier == "all_invalid":
            stats["removed_all_invalid"] += 1
            continue
        if tier == "discarded_non_dead":
            stats["discarded_non_dead_rows"] += 1
            continue
        if tier == "mastered":
            stats["removed_mastered"] += 1
        tier_rows[tier].append({**row, "_selection_tier": tier})

    for tier_name in ALL_TIERS:
        tier_rows[tier_name].sort(key=_tier_rank)
    stats["tier_available_rows"] = {
        tier_name: len(tier_rows[tier_name])
        for tier_name in POLICY_TIER_ORDER[selection_policy]
    }
    return tier_rows, stats


def _take_matching_from_tiers(
    selected: list[dict[str, Any]],
    tier_selected_counter: Counter[str],
    used_ids: set[str],
    family_counter: Counter[str],
    goal_counter: Counter[str],
    tier_rows: dict[str, list[dict[str, Any]]],
    tier_order: tuple[str, ...],
    predicate,
    limit: int,
    *,
    tier_caps: dict[str, int],
    goal_cap: int,
) -> list[dict[str, Any]]:
    taken = []
    for tier_name in tier_order:
        for row in tier_rows[tier_name]:
            if len(taken) >= limit:
                return taken
            row_id = _row_id(row)
            if row_id in used_ids:
                continue
            tier_cap = tier_caps.get(tier_name)
            if tier_cap is not None and tier_selected_counter[tier_name] >= tier_cap:
                continue
            goal_predicate = row.get("goal_predicate")
            if goal_predicate and goal_counter[goal_predicate] >= goal_cap:
                continue
            if not predicate(row):
                continue
            used_ids.add(row_id)
            selected.append(row)
            taken.append(row)
            tier_selected_counter[tier_name] += 1
            if goal_predicate:
                goal_counter[goal_predicate] += 1
            for tag in row.get("predicate_family_tags", []):
                family_counter[tag] += 1
    return taken


def _selected_rows_summary(rows: list[dict[str, Any]], pass_key: str) -> dict[str, Any]:
    total_rows = len(rows)
    nonzero_pass_rows = sum(1 for row in rows if _pass_value(row, pass_key) > 0.0)
    zero_pass_rows = total_rows - nonzero_pass_rows
    avg_unique_aux_count = (
        sum(int(row.get("unique_aux_count", 0)) for row in rows) / total_rows
        if total_rows
        else 0.0
    )
    avg_duplicate_aux_ratio = (
        sum(float(row.get("duplicate_aux_ratio", 0.0)) for row in rows) / total_rows
        if total_rows
        else 0.0
    )
    proxy_reward_stds = [_proxy_reward_std(row) for row in rows]
    avg_proxy_reward_std = (
        sum(proxy_reward_stds) / total_rows if proxy_reward_stds else 0.0
    )
    median_proxy_reward_std = (
        statistics.median(proxy_reward_stds) if proxy_reward_stds else 0.0
    )
    avg_valid_ratio = (
        sum(_valid_ratio(row, pass_key) for row in rows) / total_rows
        if total_rows
        else 0.0
    )
    return {
        "selected_nonzero_pass_rows": nonzero_pass_rows,
        "selected_nonzero_pass_ratio": (
            nonzero_pass_rows / total_rows if total_rows else 0.0
        ),
        "selected_zero_pass_rows": zero_pass_rows,
        "selected_zero_pass_ratio": zero_pass_rows / total_rows if total_rows else 0.0,
        "selected_avg_unique_aux_count": avg_unique_aux_count,
        "selected_avg_duplicate_aux_ratio": avg_duplicate_aux_ratio,
        "selected_avg_proxy_reward_std": avg_proxy_reward_std,
        "selected_median_proxy_reward_std": median_proxy_reward_std,
        "selected_avg_valid_ratio": avg_valid_ratio,
    }


def select_debug_rows(
    rows: list[dict[str, Any]],
    target_size: int,
    *,
    selection_policy: str = "v3_tiered",
    core_min_pass: float = 0.0625,
    core_max_pass: float = 0.75,
    mastered_pass_min: float = 0.90,
    hard_valid_build_invalid_max: int = 2,
    hard_valid_format_invalid_max: int = 1,
    hard_valid_unique_aux_min: int = 2,
    hard_valid_duplicate_aux_max: float = 0.875,
    hard_valid_high_max_fraction: float = 0.50,
    hard_valid_mid_max_fraction: float = 0.20,
    mastered_max_fraction: float = 0.05,
    mastered_fallback_min_fill_fraction: float = 0.90,
    multi_segment_min_fraction: float = 0.45,
    multi_point_min_fraction: float = 0.40,
    family_min_fraction: float = 0.10,
    goal_max_fraction: float = 0.18,
    zero_valid_min: float = 0.25,
    zero_valid_max: float = 0.875,
    zero_pass_reward_std_min: float = 0.15,
    reward_mixed_zero_unique_aux_min: int = 2,
    reward_mixed_zero_max_fraction: float = 0.25,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    tier_order = POLICY_TIER_ORDER[selection_policy]
    non_mastered_tiers = NON_MASTERED_TIERS_BY_POLICY[selection_policy]
    tier_rows, filter_stats = filter_candidate_tiers(
        rows,
        selection_policy=selection_policy,
        core_min_pass=core_min_pass,
        core_max_pass=core_max_pass,
        mastered_pass_min=mastered_pass_min,
        hard_valid_build_invalid_max=hard_valid_build_invalid_max,
        hard_valid_format_invalid_max=hard_valid_format_invalid_max,
        hard_valid_unique_aux_min=hard_valid_unique_aux_min,
        hard_valid_duplicate_aux_max=hard_valid_duplicate_aux_max,
        zero_valid_min=zero_valid_min,
        zero_valid_max=zero_valid_max,
        zero_pass_reward_std_min=zero_pass_reward_std_min,
        reward_mixed_zero_unique_aux_min=reward_mixed_zero_unique_aux_min,
    )

    selected: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    shortages: dict[str, int] = {}
    pass_key = filter_stats["pass_key"]
    tier_selected_counter: Counter[str] = Counter()
    family_counter: Counter[str] = Counter()
    goal_counter: Counter[str] = Counter()

    tier_caps = {"mastered": max(0, int(target_size * mastered_max_fraction))}
    if selection_policy == "v3_tiered":
        tier_caps["hard_valid_high"] = max(
            0, int(target_size * hard_valid_high_max_fraction)
        )
        tier_caps["hard_valid_mid"] = max(
            0, int(target_size * hard_valid_mid_max_fraction)
        )
    else:
        tier_caps["reward_mixed_zero"] = max(
            0, int(target_size * reward_mixed_zero_max_fraction)
        )
    mastered_fallback_min_rows = max(
        0, int(target_size * mastered_fallback_min_fill_fraction)
    )
    multi_segment_target = max(0, int(target_size * multi_segment_min_fraction))
    multi_point_target = max(0, int(target_size * multi_point_min_fraction))
    family_target = max(1, int(target_size * family_min_fraction))
    goal_cap = max(1, int(target_size * goal_max_fraction))

    taken = _take_matching_from_tiers(
        selected,
        tier_selected_counter,
        used_ids,
        family_counter,
        goal_counter,
        tier_rows,
        non_mastered_tiers,
        lambda row: row.get("aux_segment_count", 0) >= 2,
        multi_segment_target,
        tier_caps=tier_caps,
        goal_cap=goal_cap,
    )
    shortages["multi_segment_shortage"] = max(0, multi_segment_target - len(taken))

    taken = _take_matching_from_tiers(
        selected,
        tier_selected_counter,
        used_ids,
        family_counter,
        goal_counter,
        tier_rows,
        non_mastered_tiers,
        lambda row: row.get("aux_points_total", 0) >= 2,
        multi_point_target,
        tier_caps=tier_caps,
        goal_cap=goal_cap,
    )
    shortages["multi_point_shortage"] = max(0, multi_point_target - len(taken))

    all_families = sorted(
        {
            tag
            for tier in tier_order
            for row in tier_rows[tier]
            for tag in row.get("predicate_family_tags", [])
        }
    )
    for family in tqdm(all_families, desc="Balancing predicate families"):
        need = max(0, family_target - family_counter[family])
        taken = _take_matching_from_tiers(
            selected,
            tier_selected_counter,
            used_ids,
            family_counter,
            goal_counter,
            tier_rows,
            non_mastered_tiers,
            lambda row, family=family: family in row.get("predicate_family_tags", []),
            need,
            tier_caps=tier_caps,
            goal_cap=goal_cap,
        )
        shortages[f"{family}_shortage"] = max(0, need - len(taken))

    _take_matching_from_tiers(
        selected,
        tier_selected_counter,
        used_ids,
        family_counter,
        goal_counter,
        tier_rows,
        non_mastered_tiers,
        lambda row: True,
        target_size - len(selected),
        tier_caps=tier_caps,
        goal_cap=goal_cap,
    )

    mastered_fallback_triggered = len(selected) < mastered_fallback_min_rows
    if mastered_fallback_triggered:
        _take_matching_from_tiers(
            selected,
            tier_selected_counter,
            used_ids,
            family_counter,
            goal_counter,
            tier_rows,
            ("mastered",),
            lambda row: True,
            target_size - len(selected),
            tier_caps=tier_caps,
            goal_cap=goal_cap,
        )

    selected_full_rows = selected[:target_size]
    final_rows = [
        {
            "query": row["query"],
            "fl_problem": row["fl_problem"],
            "response": row["response"],
        }
        for row in selected_full_rows
    ]

    selected_goal_counter = Counter(
        row.get("goal_predicate")
        for row in selected_full_rows
        if row.get("goal_predicate")
    )
    selected_family_counter = Counter()
    for row in selected_full_rows:
        for tag in row.get("predicate_family_tags", []):
            selected_family_counter[tag] += 1
    selected_tier_counts = Counter(
        row.get("_selection_tier", "unknown") for row in selected_full_rows
    )
    selected_mastered = selected_tier_counts.get("mastered", 0)
    shortage_reasons = []
    if len(final_rows) < target_size:
        shortage_reasons.append("eligible_pool_exhausted_before_target")
        if filter_stats["discarded_non_dead_rows"] > 0:
            shortage_reasons.append("noisy_pass_zero_rows_excluded")
        if sum(filter_stats["tier_available_rows"].values()) > len(final_rows):
            shortage_reasons.append("tier_caps_or_goal_caps_limited_fill")
        if not mastered_fallback_triggered:
            shortage_reasons.append("mastered_fallback_not_enabled")

    report = {
        **filter_stats,
        "target_size": target_size,
        "selected_rows": len(final_rows),
        "tier_order": list(tier_order),
        "tier_selected_rows": dict(selected_tier_counts),
        "stage_order": list(tier_order),
        "stage_available_rows": filter_stats["tier_available_rows"],
        "stage_selected_rows": dict(selected_tier_counts),
        "selection_thresholds": {
            "selection_policy": selection_policy,
            "core_pass_window": [core_min_pass, core_max_pass],
            "mastered_pass_min": mastered_pass_min,
            "hard_valid_build_invalid_max": hard_valid_build_invalid_max,
            "hard_valid_format_invalid_max": hard_valid_format_invalid_max,
            "hard_valid_unique_aux_min": hard_valid_unique_aux_min,
            "hard_valid_duplicate_aux_max": hard_valid_duplicate_aux_max,
            "zero_valid_min": zero_valid_min,
            "zero_valid_max": zero_valid_max,
            "zero_pass_reward_std_min": zero_pass_reward_std_min,
            "reward_mixed_zero_unique_aux_min": reward_mixed_zero_unique_aux_min,
            "reward_mixed_zero_max_fraction": reward_mixed_zero_max_fraction,
            "hard_valid_high_max_fraction": hard_valid_high_max_fraction,
            "hard_valid_mid_max_fraction": hard_valid_mid_max_fraction,
            "mastered_max_fraction": mastered_max_fraction,
            "mastered_fallback_min_fill_fraction": (
                mastered_fallback_min_fill_fraction
            ),
            "multi_segment_min_fraction": multi_segment_min_fraction,
            "multi_point_min_fraction": multi_point_min_fraction,
            "family_min_fraction": family_min_fraction,
            "goal_max_fraction": goal_max_fraction,
        },
        "tier_caps": tier_caps,
        "goal_cap_rows": goal_cap,
        "mastered_fallback_min_rows": mastered_fallback_min_rows,
        "mastered_fallback_triggered": mastered_fallback_triggered,
        "selected_mastered_rows": selected_mastered,
        "selected_mastered_ratio": (
            selected_mastered / len(final_rows) if final_rows else 0.0
        ),
        "selected_hard_valid_mid_rows": selected_tier_counts.get("hard_valid_mid", 0),
        "selected_hard_valid_mid_ratio": (
            selected_tier_counts.get("hard_valid_mid", 0) / len(final_rows)
            if final_rows
            else 0.0
        ),
        "selected_reward_mixed_zero_rows": selected_tier_counts.get(
            "reward_mixed_zero", 0
        ),
        "selected_reward_mixed_zero_ratio": (
            selected_tier_counts.get("reward_mixed_zero", 0) / len(final_rows)
            if final_rows
            else 0.0
        ),
        "selected_pass_histogram": _build_pass_histogram(selected_full_rows, pass_key),
        "selected_goal_predicate_distribution": dict(
            selected_goal_counter.most_common()
        ),
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
        **_selected_rows_summary(selected_full_rows, pass_key),
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
    parser.add_argument(
        "--selection-policy",
        choices=sorted(POLICY_TIER_ORDER),
        default="v3_tiered",
    )
    parser.add_argument("--core-pass-min", type=float, default=0.0625)
    parser.add_argument("--core-pass-max", type=float, default=0.75)
    parser.add_argument("--mastered-pass-min", type=float, default=0.90)
    parser.add_argument("--hard-valid-build-invalid-max", type=int, default=2)
    parser.add_argument("--hard-valid-format-invalid-max", type=int, default=1)
    parser.add_argument("--hard-valid-unique-aux-min", type=int, default=2)
    parser.add_argument("--hard-valid-duplicate-aux-max", type=float, default=0.875)
    parser.add_argument("--hard-valid-high-max-fraction", type=float, default=0.50)
    parser.add_argument("--hard-valid-mid-max-fraction", type=float, default=0.20)
    parser.add_argument("--mastered-max-fraction", type=float, default=0.05)
    parser.add_argument(
        "--mastered-fallback-min-fill-fraction", type=float, default=0.90
    )
    parser.add_argument("--multi-segment-min-fraction", type=float, default=0.45)
    parser.add_argument("--multi-point-min-fraction", type=float, default=0.40)
    parser.add_argument("--family-min-fraction", type=float, default=0.10)
    parser.add_argument("--goal-max-fraction", type=float, default=0.18)
    parser.add_argument("--zero-valid-min", type=float, default=0.25)
    parser.add_argument("--zero-valid-max", type=float, default=0.875)
    parser.add_argument("--zero-pass-reward-std-min", type=float, default=0.15)
    parser.add_argument("--reward-mixed-zero-unique-aux-min", type=int, default=2)
    parser.add_argument("--reward-mixed-zero-max-fraction", type=float, default=0.25)
    args = parser.parse_args()

    rows = load_jsonl(args.input)
    final_rows, report = select_debug_rows(
        rows,
        args.target_size,
        selection_policy=args.selection_policy,
        core_min_pass=args.core_pass_min,
        core_max_pass=args.core_pass_max,
        mastered_pass_min=args.mastered_pass_min,
        hard_valid_build_invalid_max=args.hard_valid_build_invalid_max,
        hard_valid_format_invalid_max=args.hard_valid_format_invalid_max,
        hard_valid_unique_aux_min=args.hard_valid_unique_aux_min,
        hard_valid_duplicate_aux_max=args.hard_valid_duplicate_aux_max,
        hard_valid_high_max_fraction=args.hard_valid_high_max_fraction,
        hard_valid_mid_max_fraction=args.hard_valid_mid_max_fraction,
        mastered_max_fraction=args.mastered_max_fraction,
        mastered_fallback_min_fill_fraction=args.mastered_fallback_min_fill_fraction,
        multi_segment_min_fraction=args.multi_segment_min_fraction,
        multi_point_min_fraction=args.multi_point_min_fraction,
        family_min_fraction=args.family_min_fraction,
        goal_max_fraction=args.goal_max_fraction,
        zero_valid_min=args.zero_valid_min,
        zero_valid_max=args.zero_valid_max,
        zero_pass_reward_std_min=args.zero_pass_reward_std_min,
        reward_mixed_zero_unique_aux_min=args.reward_mixed_zero_unique_aux_min,
        reward_mixed_zero_max_fraction=args.reward_mixed_zero_max_fraction,
    )
    write_jsonl(args.output, final_rows)
    write_json(args.report_output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
