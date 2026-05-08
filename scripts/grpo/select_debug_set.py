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

from tqdm import tqdm

BUCKET_UNIFIED_POLICY = "bucket_unified"
UNIFIED_BUCKETS = (
    "all_invalid",
    "mastered",
    "core",
    "low",
    "high",
    "high_pass_non_greedy",
    "zero_valid_low",
    "zero_valid_high",
    "zero_reward_std_low",
    "reward_mixed_zero",
)
UNIFIED_MAIN_BUCKET_ORDER = (
    "core",
    "low",
    "reward_mixed_zero",
    "high",
)
UNIFIED_FALLBACK_BUCKET_ORDER = ("mastered",)
ALL_SELECTION_POLICIES = (BUCKET_UNIFIED_POLICY,)
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


def _pass_distance_rank(row: dict[str, Any], pass_key: str) -> float:
    return abs(_pass_value(row, pass_key) - 0.375)


def _tier_rank(row: dict[str, Any], pass_key: str) -> tuple[Any, ...]:
    return (
        -int(row.get("aux_points_total", 0) >= 2),
        -int(row.get("aux_segment_count", 0) >= 2),
        -int(row.get("unique_aux_count", 0)),
        -_proxy_reward_std(row),
        _pass_distance_rank(row, pass_key),
        float(row.get("duplicate_aux_ratio", 1.0)),
        int(row.get("build_invalid_count", 0)),
        int(row.get("format_invalid_count", 0)),
        -int(row.get("aux_segment_count", 0)),
        -int(row.get("aux_points_total", 0)),
        -int(row.get("n_premises", 0)),
        -int(row.get("problem_predicate_count", 0)),
        -int(row.get("problem_clause_count", 0)),
        _row_id(row),
    )


def _classify_bucket_unified(
    row: dict[str, Any],
    pass_key: str,
    *,
    core_min_pass: float,
    core_max_pass: float,
    mastered_pass_min: float,
    zero_valid_min: float,
    zero_valid_max: float,
    zero_pass_reward_std_min: float,
) -> str:
    pass_value = _pass_value(row, pass_key)
    if row.get("all_invalid"):
        return "all_invalid"
    if row.get("greedy_success") and pass_value >= mastered_pass_min:
        return "mastered"
    if core_min_pass <= pass_value <= core_max_pass:
        return "core"
    if 0.0 < pass_value < core_min_pass:
        return "low"
    if core_max_pass < pass_value < 1.0:
        return "high"
    if pass_value >= mastered_pass_min:
        return "high_pass_non_greedy"

    # For pass=0, prioritize reward-based classification
    if _proxy_reward_std(row) >= zero_pass_reward_std_min:
        return "reward_mixed_zero"

    valid_ratio = _valid_ratio(row, pass_key)
    if valid_ratio < zero_valid_min:
        return "zero_valid_low"
    if valid_ratio > zero_valid_max:
        return "zero_valid_high"
    return "zero_reward_std_low"


def filter_candidate_buckets(
    rows: list[dict[str, Any]],
    *,
    selection_policy: str,
    core_min_pass: float,
    core_max_pass: float,
    mastered_pass_min: float,
    zero_valid_min: float,
    zero_valid_max: float,
    zero_pass_reward_std_min: float,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    pass_key = _resolve_pass_key(rows)
    bucket_rows = {bucket_name: [] for bucket_name in UNIFIED_BUCKETS}

    for row in tqdm(rows, desc="Classifying candidate buckets"):
        bucket = _classify_bucket_unified(
            row,
            pass_key,
            core_min_pass=core_min_pass,
            core_max_pass=core_max_pass,
            mastered_pass_min=mastered_pass_min,
            zero_valid_min=zero_valid_min,
            zero_valid_max=zero_valid_max,
            zero_pass_reward_std_min=zero_pass_reward_std_min,
        )
        bucket_rows[bucket].append({**row, "_selection_bucket": bucket})

    for bucket_name in UNIFIED_BUCKETS:
        bucket_rows[bucket_name].sort(
            key=lambda row: _tier_rank(row, pass_key)
        )

    stats = {
        "pass_key": pass_key,
        "selection_policy": selection_policy,
        "bucket_order": list(UNIFIED_MAIN_BUCKET_ORDER),
        "bucket_available_rows": {
            bucket_name: len(bucket_rows[bucket_name]) for bucket_name in UNIFIED_BUCKETS
        },
        "bucket_pass_histogram": {
            bucket_name: _build_pass_histogram(bucket_rows[bucket_name], pass_key)
            for bucket_name in UNIFIED_BUCKETS
        },
    }
    return bucket_rows, stats


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
    pass_key: str,
    tier_caps: dict[str, int],
    goal_cap: int,
    easy_tail_counter: Counter[str],
    easy_tail_caps: dict[str, int],
    high_pass_min: float,
    pass_one_value: float,
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
            pass_value = _pass_value(row, pass_key)
            if bool(row.get("greedy_success")) and (
                easy_tail_counter["greedy_success"] >= easy_tail_caps["greedy_success"]
            ):
                continue
            if pass_value >= pass_one_value and (
                easy_tail_counter["pass_one"] >= easy_tail_caps["pass_one"]
            ):
                continue
            if pass_value >= high_pass_min and (
                easy_tail_counter["high_pass"] >= easy_tail_caps["high_pass"]
            ):
                continue
            if not predicate(row):
                continue
            used_ids.add(row_id)
            selected.append(row)
            taken.append(row)
            tier_selected_counter[tier_name] += 1
            if bool(row.get("greedy_success")):
                easy_tail_counter["greedy_success"] += 1
            if pass_value >= pass_one_value:
                easy_tail_counter["pass_one"] += 1
            if pass_value >= high_pass_min:
                easy_tail_counter["high_pass"] += 1
            if goal_predicate:
                goal_counter[goal_predicate] += 1
            for tag in row.get("predicate_family_tags", []):
                family_counter[tag] += 1
    return taken


def _selected_rows_summary(rows: list[dict[str, Any]], pass_key: str) -> dict[str, Any]:
    total_rows = len(rows)
    nonzero_pass_rows = sum(1 for row in rows if _pass_value(row, pass_key) > 0.0)
    zero_pass_rows = total_rows - nonzero_pass_rows
    greedy_success_rows = sum(1 for row in rows if bool(row.get("greedy_success")))
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
    valid_eq_1_rows = sum(1 for row in rows if _valid_ratio(row, pass_key) == 1.0)
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
        "selected_greedy_success_rows": greedy_success_rows,
        "selected_greedy_success_ratio": (
            greedy_success_rows / total_rows if total_rows else 0.0
        ),
        "selected_valid_eq_1_rows": valid_eq_1_rows,
        "selected_valid_eq_1_ratio": (
            valid_eq_1_rows / total_rows if total_rows else 0.0
        ),
    }


def _build_pass_histogram_by_group(
    rows: list[dict[str, Any]], pass_key: str, group_key: str
) -> dict[str, dict[str, int]]:
    by_group: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_group.setdefault(row.get(group_key, "unknown"), []).append(row)
    return {
        group_name: _build_pass_histogram(group_rows, pass_key)
        for group_name, group_rows in sorted(by_group.items())
    }


def _build_pass_histogram_by_tier(
    rows: list[dict[str, Any]], pass_key: str
) -> dict[str, dict[str, int]]:
    return _build_pass_histogram_by_group(rows, pass_key, "_selection_tier")


def _select_debug_rows_bucket_unified(
    rows: list[dict[str, Any]],
    target_size: int,
    *,
    selection_policy: str,
    core_min_pass: float,
    core_max_pass: float,
    mastered_pass_min: float,
    low_max_fraction: float,
    high_max_fraction: float,
    mastered_max_fraction: float,
    mastered_fallback_min_fill_fraction: float,
    multi_segment_min_fraction: float,
    multi_point_min_fraction: float,
    family_min_fraction: float,
    goal_max_fraction: float,
    zero_valid_min: float,
    zero_valid_max: float,
    zero_pass_reward_std_min: float,
    reward_mixed_zero_max_fraction: float,
    low_min_fraction: float,
    reward_mixed_zero_min_fraction: float,
    high_min_fraction: float,
    greedy_success_max_fraction: float,
    pass_one_max_fraction: float,
    high_pass_min: float,
    high_pass_max_fraction: float,
    pass_one_value: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    bucket_rows, bucket_stats = filter_candidate_buckets(
        rows,
        selection_policy=selection_policy,
        core_min_pass=core_min_pass,
        core_max_pass=core_max_pass,
        mastered_pass_min=mastered_pass_min,
        zero_valid_min=zero_valid_min,
        zero_valid_max=zero_valid_max,
        zero_pass_reward_std_min=zero_pass_reward_std_min,
    )

    selected: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    shortages: dict[str, int] = {}
    pass_key = bucket_stats["pass_key"]
    bucket_selected_counter: Counter[str] = Counter()
    family_counter: Counter[str] = Counter()
    goal_counter: Counter[str] = Counter()
    easy_tail_counter: Counter[str] = Counter()

    bucket_min_fraction = {
        "low": low_min_fraction,
        "reward_mixed_zero": reward_mixed_zero_min_fraction,
        "high": high_min_fraction,
    }
    bucket_max_fraction = {
        "all_invalid": 0.0,
        "mastered": mastered_max_fraction,
        "low": low_max_fraction,
        "high": high_max_fraction,
        "high_pass_non_greedy": 0.0,
        "zero_valid_low": 0.0,
        "zero_valid_high": 0.0,
        "zero_reward_std_low": 0.0,
        "reward_mixed_zero": reward_mixed_zero_max_fraction,
    }
    bucket_min_rows = {
        bucket_name: max(0, int(target_size * bucket_min_fraction.get(bucket_name, 0.0)))
        for bucket_name in UNIFIED_BUCKETS
    }
    bucket_max_rows = {
        bucket_name: (
            max(0, int(target_size * bucket_max_fraction[bucket_name]))
            if bucket_name in bucket_max_fraction
            else target_size
        )
        for bucket_name in UNIFIED_BUCKETS
    }
    bucket_caps = dict(bucket_max_rows)

    easy_tail_caps = {
        "greedy_success": max(0, int(target_size * greedy_success_max_fraction)),
        "pass_one": max(0, int(target_size * pass_one_max_fraction)),
        "high_pass": max(0, int(target_size * high_pass_max_fraction)),
    }
    fallback_trigger_min_rows = max(
        0, int(target_size * mastered_fallback_min_fill_fraction)
    )
    multi_segment_target = max(0, int(target_size * multi_segment_min_fraction))
    multi_point_target = max(0, int(target_size * multi_point_min_fraction))
    family_target = max(0, int(target_size * family_min_fraction))
    goal_cap = max(1, int(target_size * goal_max_fraction))

    taken = _take_matching_from_tiers(
        selected,
        bucket_selected_counter,
        used_ids,
        family_counter,
        goal_counter,
        bucket_rows,
        UNIFIED_MAIN_BUCKET_ORDER,
        lambda row: row.get("aux_segment_count", 0) >= 2,
        multi_segment_target,
        pass_key=pass_key,
        tier_caps=bucket_caps,
        goal_cap=goal_cap,
        easy_tail_counter=easy_tail_counter,
        easy_tail_caps=easy_tail_caps,
        high_pass_min=high_pass_min,
        pass_one_value=pass_one_value,
    )
    shortages["multi_segment_shortage"] = max(0, multi_segment_target - len(taken))

    taken = _take_matching_from_tiers(
        selected,
        bucket_selected_counter,
        used_ids,
        family_counter,
        goal_counter,
        bucket_rows,
        UNIFIED_MAIN_BUCKET_ORDER,
        lambda row: row.get("aux_points_total", 0) >= 2,
        multi_point_target,
        pass_key=pass_key,
        tier_caps=bucket_caps,
        goal_cap=goal_cap,
        easy_tail_counter=easy_tail_counter,
        easy_tail_caps=easy_tail_caps,
        high_pass_min=high_pass_min,
        pass_one_value=pass_one_value,
    )
    shortages["multi_point_shortage"] = max(0, multi_point_target - len(taken))

    all_families = sorted(
        {
            tag
            for bucket_name in UNIFIED_BUCKETS
            for row in bucket_rows[bucket_name]
            for tag in row.get("predicate_family_tags", [])
        }
    )
    for family in tqdm(all_families, desc="Balancing predicate families"):
        need = max(0, family_target - family_counter[family])
        taken = _take_matching_from_tiers(
            selected,
            bucket_selected_counter,
            used_ids,
            family_counter,
            goal_counter,
            bucket_rows,
            UNIFIED_MAIN_BUCKET_ORDER,
            lambda row, family=family: family in row.get("predicate_family_tags", []),
            need,
            pass_key=pass_key,
            tier_caps=bucket_caps,
            goal_cap=goal_cap,
            easy_tail_counter=easy_tail_counter,
            easy_tail_caps=easy_tail_caps,
            high_pass_min=high_pass_min,
            pass_one_value=pass_one_value,
        )
        shortages[f"{family}_shortage"] = max(0, need - len(taken))

    bucket_floor_shortages = {}
    for bucket_name in ("low", "reward_mixed_zero", "high"):
        needed = max(0, bucket_min_rows[bucket_name] - bucket_selected_counter[bucket_name])
        taken = _take_matching_from_tiers(
            selected,
            bucket_selected_counter,
            used_ids,
            family_counter,
            goal_counter,
            bucket_rows,
            (bucket_name,),
            lambda row: True,
            needed,
            pass_key=pass_key,
            tier_caps=bucket_caps,
            goal_cap=goal_cap,
            easy_tail_counter=easy_tail_counter,
            easy_tail_caps=easy_tail_caps,
            high_pass_min=high_pass_min,
            pass_one_value=pass_one_value,
        )
        bucket_floor_shortages[bucket_name] = max(0, needed - len(taken))

    _take_matching_from_tiers(
        selected,
        bucket_selected_counter,
        used_ids,
        family_counter,
        goal_counter,
        bucket_rows,
        UNIFIED_MAIN_BUCKET_ORDER,
        lambda row: True,
        target_size - len(selected),
        pass_key=pass_key,
        tier_caps=bucket_caps,
        goal_cap=goal_cap,
        easy_tail_counter=easy_tail_counter,
        easy_tail_caps=easy_tail_caps,
        high_pass_min=high_pass_min,
        pass_one_value=pass_one_value,
    )

    fallback_triggered = len(selected) < fallback_trigger_min_rows
    if fallback_triggered:
        _take_matching_from_tiers(
            selected,
            bucket_selected_counter,
            used_ids,
            family_counter,
            goal_counter,
            bucket_rows,
            UNIFIED_FALLBACK_BUCKET_ORDER,
            lambda row: True,
            target_size - len(selected),
            pass_key=pass_key,
            tier_caps=bucket_caps,
            goal_cap=goal_cap,
            easy_tail_counter=easy_tail_counter,
            easy_tail_caps=easy_tail_caps,
            high_pass_min=high_pass_min,
            pass_one_value=pass_one_value,
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

    bucket_selected_rows = {
        bucket_name: bucket_selected_counter[bucket_name] for bucket_name in UNIFIED_BUCKETS
    }
    shortage_reasons = []
    if len(final_rows) < target_size:
        shortage_reasons.append("eligible_pool_exhausted_before_target")
        if sum(bucket_stats["bucket_available_rows"].values()) > len(final_rows):
            shortage_reasons.append("bucket_caps_or_goal_caps_limited_fill")
        if not fallback_triggered:
            shortage_reasons.append("fallback_bucket_not_triggered")

    report = {
        "pass_key": pass_key,
        "selection_policy": selection_policy,
        "target_size": target_size,
        "selected_rows": len(final_rows),
        "bucket_order": list(UNIFIED_MAIN_BUCKET_ORDER),
        "fallback_bucket_order": list(UNIFIED_FALLBACK_BUCKET_ORDER),
        "fallback_trigger_fill_fraction": mastered_fallback_min_fill_fraction,
        "fallback_trigger_min_rows": fallback_trigger_min_rows,
        "fallback_triggered": fallback_triggered,
        "bucket_available_rows": bucket_stats["bucket_available_rows"],
        "bucket_selected_rows": bucket_selected_rows,
        "bucket_min_rows": bucket_min_rows,
        "bucket_max_rows": bucket_max_rows,
        "bucket_floor_shortages": bucket_floor_shortages,
        "bucket_pass_histogram": bucket_stats["bucket_pass_histogram"],
        "bucket_pass_histogram_selected": _build_pass_histogram_by_group(
            selected_full_rows, pass_key, "_selection_bucket"
        ),
        "selection_thresholds": {
            "selection_policy": selection_policy,
            "core_pass_window": [core_min_pass, core_max_pass],
            "mastered_pass_min": mastered_pass_min,
            "zero_valid_min": zero_valid_min,
            "zero_valid_max": zero_valid_max,
            "zero_pass_reward_std_min": zero_pass_reward_std_min,
            "bucket_min_fraction": bucket_min_fraction,
            "bucket_max_fraction": bucket_max_fraction,
            "multi_segment_min_fraction": multi_segment_min_fraction,
            "multi_point_min_fraction": multi_point_min_fraction,
            "family_min_fraction": family_min_fraction,
            "goal_max_fraction": goal_max_fraction,
            "greedy_success_max_fraction": greedy_success_max_fraction,
            "pass_one_max_fraction": pass_one_max_fraction,
            "high_pass_min": high_pass_min,
            "high_pass_max_fraction": high_pass_max_fraction,
            "pass_one_value": pass_one_value,
        },
        "easy_tail_caps": easy_tail_caps,
        "goal_cap_rows": goal_cap,
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


def select_debug_rows(
    rows: list[dict[str, Any]],
    target_size: int,
    *,
    selection_policy: str = "bucket_unified",
    core_min_pass: float = 0.0625,
    core_max_pass: float = 0.75,
    mastered_pass_min: float = 0.90,
    low_max_fraction: float = 0.20,
    high_max_fraction: float = 0.08,
    mastered_max_fraction: float = 0.05,
    mastered_fallback_min_fill_fraction: float = 0.90,
    multi_segment_min_fraction: float = 0.45,
    multi_point_min_fraction: float = 0.40,
    family_min_fraction: float = 0.10,
    goal_max_fraction: float = 0.18,
    zero_valid_min: float = 0.25,
    zero_valid_max: float = 0.875,
    zero_pass_reward_std_min: float = 0.15,
    reward_mixed_zero_max_fraction: float = 0.20,
    low_min_fraction: float = 0.05,
    reward_mixed_zero_min_fraction: float = 0.05,
    high_min_fraction: float = 0.03,
    greedy_success_max_fraction: float = 1.0,
    pass_one_max_fraction: float = 1.0,
    high_pass_min: float = 0.75,
    high_pass_max_fraction: float = 1.0,
    pass_one_value: float = 1.0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return _select_debug_rows_bucket_unified(
        rows,
        target_size,
        selection_policy=selection_policy,
        core_min_pass=core_min_pass,
        core_max_pass=core_max_pass,
        mastered_pass_min=mastered_pass_min,
        low_max_fraction=low_max_fraction,
        high_max_fraction=high_max_fraction,
        mastered_max_fraction=mastered_max_fraction,
        mastered_fallback_min_fill_fraction=mastered_fallback_min_fill_fraction,
        multi_segment_min_fraction=multi_segment_min_fraction,
        multi_point_min_fraction=multi_point_min_fraction,
        family_min_fraction=family_min_fraction,
        goal_max_fraction=goal_max_fraction,
        zero_valid_min=zero_valid_min,
        zero_valid_max=zero_valid_max,
        zero_pass_reward_std_min=zero_pass_reward_std_min,
        reward_mixed_zero_max_fraction=reward_mixed_zero_max_fraction,
        low_min_fraction=low_min_fraction,
        reward_mixed_zero_min_fraction=reward_mixed_zero_min_fraction,
        high_min_fraction=high_min_fraction,
        greedy_success_max_fraction=greedy_success_max_fraction,
        pass_one_max_fraction=pass_one_max_fraction,
        high_pass_min=high_pass_min,
        high_pass_max_fraction=high_pass_max_fraction,
        pass_one_value=pass_one_value,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Difficulty labels JSONL")
    parser.add_argument("output", type=Path, nargs="?", help="Selected debug-set JSONL")
    parser.add_argument(
        "--report-output",
        type=Path,
        help="JSON report path",
    )
    parser.add_argument("--target-size", type=int, default=2000)
    parser.add_argument(
        "--selection-policy",
        choices=ALL_SELECTION_POLICIES,
        default=BUCKET_UNIFIED_POLICY,
    )
    parser.add_argument("--core-pass-min", type=float, default=0.0625)
    parser.add_argument("--core-pass-max", type=float, default=0.75)
    parser.add_argument("--mastered-pass-min", type=float, default=0.90)
    parser.add_argument("--low-max-fraction", type=float, default=0.20)
    parser.add_argument("--high-max-fraction", type=float, default=0.08)
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
    parser.add_argument("--reward-mixed-zero-max-fraction", type=float, default=0.20)
    parser.add_argument("--low-min-fraction", type=float, default=0.05)
    parser.add_argument("--reward-mixed-zero-min-fraction", type=float, default=0.05)
    parser.add_argument("--high-min-fraction", type=float, default=0.03)
    parser.add_argument("--greedy-success-max-fraction", type=float, default=1.0)
    parser.add_argument("--pass-one-max-fraction", type=float, default=1.0)
    parser.add_argument("--high-pass-min", type=float, default=0.75)
    parser.add_argument("--high-pass-max-fraction", type=float, default=1.0)
    parser.add_argument("--pass-one-value", type=float, default=1.0)
    parser.add_argument(
        "--stats-only",
        action="store_true",
        help="Only show bucket statistics without performing selection",
    )
    args = parser.parse_args()

    rows = load_jsonl(args.input)

    if args.stats_only:
        _, stats = filter_candidate_buckets(
            rows,
            selection_policy=args.selection_policy,
            core_min_pass=args.core_pass_min,
            core_max_pass=args.core_pass_max,
            mastered_pass_min=args.mastered_pass_min,
            zero_valid_min=args.zero_valid_min,
            zero_valid_max=args.zero_valid_max,
            zero_pass_reward_std_min=args.zero_pass_reward_std_min,
        )
        total_rows = sum(stats["bucket_available_rows"].values())
        bucket_percentages = {
            bucket: {
                "count": count,
                "percentage": (count / total_rows * 100) if total_rows > 0 else 0.0,
            }
            for bucket, count in stats["bucket_available_rows"].items()
        }
        stats["bucket_statistics"] = bucket_percentages
        stats["total_rows"] = total_rows
        print(json.dumps(stats, ensure_ascii=False, indent=2, sort_keys=True))
        return

    if not args.output or not args.report_output:
        parser.error("output and --report-output are required when not using --stats-only")

    final_rows, report = select_debug_rows(
        rows,
        args.target_size,
        selection_policy=args.selection_policy,
        core_min_pass=args.core_pass_min,
        core_max_pass=args.core_pass_max,
        mastered_pass_min=args.mastered_pass_min,
        low_max_fraction=args.low_max_fraction,
        high_max_fraction=args.high_max_fraction,
        mastered_max_fraction=args.mastered_max_fraction,
        mastered_fallback_min_fill_fraction=args.mastered_fallback_min_fill_fraction,
        multi_segment_min_fraction=args.multi_segment_min_fraction,
        multi_point_min_fraction=args.multi_point_min_fraction,
        family_min_fraction=args.family_min_fraction,
        goal_max_fraction=args.goal_max_fraction,
        zero_valid_min=args.zero_valid_min,
        zero_valid_max=args.zero_valid_max,
        zero_pass_reward_std_min=args.zero_pass_reward_std_min,
        reward_mixed_zero_max_fraction=args.reward_mixed_zero_max_fraction,
        low_min_fraction=args.low_min_fraction,
        reward_mixed_zero_min_fraction=args.reward_mixed_zero_min_fraction,
        high_min_fraction=args.high_min_fraction,
        greedy_success_max_fraction=args.greedy_success_max_fraction,
        pass_one_max_fraction=args.pass_one_max_fraction,
        high_pass_min=args.high_pass_min,
        high_pass_max_fraction=args.high_pass_max_fraction,
        pass_one_value=args.pass_one_value,
    )
    write_jsonl(args.output, final_rows)
    write_json(args.report_output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

