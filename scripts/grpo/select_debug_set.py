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
    "v6_mid_strict_zero": (
        "core",
        "near_low",
        "reward_mixed_zero",
        "near_high_mid",
        "mastered",
    ),
    "v7_structure_strict_zero": (
        "core",
        "near_low",
        "reward_mixed_zero",
        "near_high_mid",
        "mastered",
    ),
    "v9_stage_balanced": (
        "core",
        "near_low",
        "reward_mixed_zero",
        "near_high_mid",
        "mastered",
    ),
    "v10_auxfix_stage_balanced": (
        "core",
        "near_low",
        "reward_mixed_zero",
        "near_high_mid",
        "mastered",
    ),
}
BUCKET_UNIFIED_POLICY = "bucket_unified"
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
    "v6_mid_strict_zero": (
        "core",
        "near_low",
        "reward_mixed_zero",
        "near_high_mid",
    ),
    "v7_structure_strict_zero": (
        "core",
        "near_low",
        "reward_mixed_zero",
        "near_high_mid",
    ),
    "v9_stage_balanced": (
        "core",
        "near_low",
        "reward_mixed_zero",
        "near_high_mid",
    ),
    "v10_auxfix_stage_balanced": (
        "core",
        "near_low",
        "reward_mixed_zero",
        "near_high_mid",
    ),
}
ALL_TIERS = (
    "core",
    "near",
    "near_low",
    "near_high_mid",
    "hard_valid_high",
    "hard_valid_mid",
    "reward_mixed_zero",
    "mastered",
)
UNIFIED_BUCKETS = (
    "all_invalid",
    "mastered",
    "core",
    "near_low",
    "near_high_mid",
    "easy_tail_nonzero",
    "high_pass_non_greedy",
    "zero_valid_low",
    "zero_valid_high",
    "zero_reward_std_low",
    "zero_unique_aux_low",
    "reward_mixed_zero",
)
UNIFIED_MAIN_BUCKET_ORDER = (
    "core",
    "near_low",
    "reward_mixed_zero",
    "near_high_mid",
)
UNIFIED_FALLBACK_BUCKET_ORDER = ("mastered",)
ALL_SELECTION_POLICIES = tuple(
    sorted((*POLICY_TIER_ORDER.keys(), BUCKET_UNIFIED_POLICY))
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


def _pass_distance_rank(
    row: dict[str, Any], pass_key: str, *, selection_policy: str
) -> float:
    if selection_policy in {
        "v6_mid_strict_zero",
        "v7_structure_strict_zero",
        "v9_stage_balanced",
        "v10_auxfix_stage_balanced",
        BUCKET_UNIFIED_POLICY,
    }:
        return abs(_pass_value(row, pass_key) - 0.375)
    return abs(_valid_ratio(row, pass_key) - 0.5)


def _tier_rank(
    row: dict[str, Any], pass_key: str, *, selection_policy: str
) -> tuple[Any, ...]:
    if selection_policy in {
        "v7_structure_strict_zero",
        "v9_stage_balanced",
        "v10_auxfix_stage_balanced",
        BUCKET_UNIFIED_POLICY,
    }:
        return (
            -int(row.get("aux_points_total", 0) >= 2),
            -int(row.get("aux_segment_count", 0) >= 2),
            -int(row.get("unique_aux_count", 0)),
            -_proxy_reward_std(row),
            _pass_distance_rank(row, pass_key, selection_policy=selection_policy),
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
    return (
        -_proxy_reward_std(row),
        -int(row.get("unique_aux_count", 0)),
        float(row.get("duplicate_aux_ratio", 1.0)),
        _pass_distance_rank(row, pass_key, selection_policy=selection_policy),
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
    near_high_mid_max_pass: float,
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

    if selection_policy in {
        "v6_mid_strict_zero",
        "v7_structure_strict_zero",
        "v9_stage_balanced",
        "v10_auxfix_stage_balanced",
    }:
        if 0.0 < pass_value < core_min_pass:
            return "near_low"
        if core_max_pass < pass_value <= near_high_mid_max_pass:
            return "near_high_mid"
    elif (0.0 < pass_value < core_min_pass) or (
        core_max_pass < pass_value < mastered_pass_min
    ):
        return "near"

    if pass_value != 0.0:
        return "discarded_non_dead"

    if selection_policy in {
        "v4_reward_mixed",
        "v6_mid_strict_zero",
        "v7_structure_strict_zero",
        "v9_stage_balanced",
        "v10_auxfix_stage_balanced",
    }:
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


def _excluded_reason(
    row: dict[str, Any],
    pass_key: str,
    *,
    selection_policy: str,
    core_min_pass: float,
    core_max_pass: float,
    mastered_pass_min: float,
    hard_valid_build_invalid_max: int,
    hard_valid_format_invalid_max: int,
    near_high_mid_max_pass: float,
    zero_valid_min: float,
    zero_valid_max: float,
    zero_pass_reward_std_min: float,
    reward_mixed_zero_unique_aux_min: int,
) -> str:
    pass_value = _pass_value(row, pass_key)
    if pass_value != 0.0:
        if (
            selection_policy
            in {
                "v6_mid_strict_zero",
                "v7_structure_strict_zero",
                "v9_stage_balanced",
                "v10_auxfix_stage_balanced",
            }
            and near_high_mid_max_pass < pass_value < mastered_pass_min
        ):
            return (
                f"nonzero_easy_tail_"
                f"{near_high_mid_max_pass:.2f}_{mastered_pass_min:.2f}"
            )
        if pass_value >= mastered_pass_min:
            return f"nonzero_highpass_ge_{mastered_pass_min:.2f}_without_greedy"
        return "nonzero_other"

    if selection_policy in {
        "v4_reward_mixed",
        "v6_mid_strict_zero",
        "v7_structure_strict_zero",
        "v9_stage_balanced",
        "v10_auxfix_stage_balanced",
    }:
        valid_ratio = _valid_ratio(row, pass_key)
        if valid_ratio < zero_valid_min:
            return "zero_pass_valid_too_low"
        if valid_ratio > zero_valid_max:
            return "zero_pass_valid_too_high"
        if _proxy_reward_std(row) < zero_pass_reward_std_min:
            return "zero_pass_reward_std_too_low"
        if int(row.get("unique_aux_count", 0)) < reward_mixed_zero_unique_aux_min:
            return "zero_pass_unique_aux_too_low"
        return "zero_pass_other"

    build_invalid_count = int(row.get("build_invalid_count", 0))
    if build_invalid_count > hard_valid_build_invalid_max:
        return "zero_pass_build_invalid_too_high"

    format_invalid_count = int(row.get("format_invalid_count", 0))
    if format_invalid_count > hard_valid_format_invalid_max:
        return "zero_pass_format_invalid_too_high"

    return "zero_pass_other"


def _classify_bucket_unified(
    row: dict[str, Any],
    pass_key: str,
    *,
    core_min_pass: float,
    core_max_pass: float,
    mastered_pass_min: float,
    near_high_mid_max_pass: float,
    zero_valid_min: float,
    zero_valid_max: float,
    zero_pass_reward_std_min: float,
    reward_mixed_zero_unique_aux_min: int,
) -> str:
    pass_value = _pass_value(row, pass_key)
    if row.get("all_invalid"):
        return "all_invalid"
    if row.get("greedy_success") and pass_value >= mastered_pass_min:
        return "mastered"
    if core_min_pass <= pass_value <= core_max_pass:
        return "core"
    if 0.0 < pass_value < core_min_pass:
        return "near_low"
    if core_max_pass < pass_value <= near_high_mid_max_pass:
        return "near_high_mid"
    if near_high_mid_max_pass < pass_value < mastered_pass_min:
        return "easy_tail_nonzero"
    if pass_value >= mastered_pass_min:
        return "high_pass_non_greedy"

    valid_ratio = _valid_ratio(row, pass_key)
    if valid_ratio < zero_valid_min:
        return "zero_valid_low"
    if valid_ratio > zero_valid_max:
        return "zero_valid_high"
    if _proxy_reward_std(row) < zero_pass_reward_std_min:
        return "zero_reward_std_low"
    if int(row.get("unique_aux_count", 0)) < reward_mixed_zero_unique_aux_min:
        return "zero_unique_aux_low"
    return "reward_mixed_zero"


def filter_candidate_buckets(
    rows: list[dict[str, Any]],
    *,
    selection_policy: str,
    core_min_pass: float,
    core_max_pass: float,
    mastered_pass_min: float,
    near_high_mid_max_pass: float,
    zero_valid_min: float,
    zero_valid_max: float,
    zero_pass_reward_std_min: float,
    reward_mixed_zero_unique_aux_min: int,
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
            near_high_mid_max_pass=near_high_mid_max_pass,
            zero_valid_min=zero_valid_min,
            zero_valid_max=zero_valid_max,
            zero_pass_reward_std_min=zero_pass_reward_std_min,
            reward_mixed_zero_unique_aux_min=reward_mixed_zero_unique_aux_min,
        )
        bucket_rows[bucket].append({**row, "_selection_bucket": bucket})

    for bucket_name in UNIFIED_BUCKETS:
        bucket_rows[bucket_name].sort(
            key=lambda row: _tier_rank(
                row, pass_key, selection_policy=BUCKET_UNIFIED_POLICY
            )
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
    near_high_mid_max_pass: float,
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
        "excluded_rows_total": 0,
        "excluded_rows_by_reason": {},
        "excluded_pass_histogram_by_reason": {},
        "tier_available_rows": {},
        "selection_policy": selection_policy,
    }
    excluded_rows_by_reason: dict[str, list[dict[str, Any]]] = {}
    excluded_reason_counts: Counter[str] = Counter()

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
            near_high_mid_max_pass=near_high_mid_max_pass,
            zero_valid_min=zero_valid_min,
            zero_valid_max=zero_valid_max,
            zero_pass_reward_std_min=zero_pass_reward_std_min,
            reward_mixed_zero_unique_aux_min=reward_mixed_zero_unique_aux_min,
        )
        if tier == "all_invalid":
            stats["removed_all_invalid"] += 1
            continue
        if tier == "discarded_non_dead":
            reason = _excluded_reason(
                row,
                pass_key,
                selection_policy=selection_policy,
                core_min_pass=core_min_pass,
                core_max_pass=core_max_pass,
                mastered_pass_min=mastered_pass_min,
                hard_valid_build_invalid_max=hard_valid_build_invalid_max,
                hard_valid_format_invalid_max=hard_valid_format_invalid_max,
                near_high_mid_max_pass=near_high_mid_max_pass,
                zero_valid_min=zero_valid_min,
                zero_valid_max=zero_valid_max,
                zero_pass_reward_std_min=zero_pass_reward_std_min,
                reward_mixed_zero_unique_aux_min=reward_mixed_zero_unique_aux_min,
            )
            stats["excluded_rows_total"] += 1
            excluded_reason_counts[reason] += 1
            excluded_rows_by_reason.setdefault(reason, []).append(row)
            continue
        if tier == "mastered":
            stats["removed_mastered"] += 1
        tier_rows[tier].append({**row, "_selection_tier": tier})

    for tier_name in ALL_TIERS:
        tier_rows[tier_name].sort(
            key=lambda row: _tier_rank(
                row, pass_key, selection_policy=selection_policy
            )
        )
    stats["tier_available_rows"] = {
        tier_name: len(tier_rows[tier_name])
        for tier_name in POLICY_TIER_ORDER[selection_policy]
    }
    stats["excluded_rows_by_reason"] = dict(sorted(excluded_reason_counts.items()))
    stats["excluded_pass_histogram_by_reason"] = {
        reason: _build_pass_histogram(reason_rows, pass_key)
        for reason, reason_rows in sorted(excluded_rows_by_reason.items())
    }
    stats["excluded_rows_total"] = sum(
        stats["excluded_rows_by_reason"].values()
    )
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
    near_high_mid_max_pass: float,
    near_high_mid_max_fraction: float,
    mastered_max_fraction: float,
    mastered_fallback_min_fill_fraction: float,
    multi_segment_min_fraction: float,
    multi_point_min_fraction: float,
    family_min_fraction: float,
    goal_max_fraction: float,
    zero_valid_min: float,
    zero_valid_max: float,
    zero_pass_reward_std_min: float,
    reward_mixed_zero_unique_aux_min: int,
    reward_mixed_zero_max_fraction: float,
    near_low_min_fraction: float,
    near_low_max_fraction: float,
    reward_mixed_zero_min_fraction: float,
    near_high_mid_min_fraction: float,
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
        near_high_mid_max_pass=near_high_mid_max_pass,
        zero_valid_min=zero_valid_min,
        zero_valid_max=zero_valid_max,
        zero_pass_reward_std_min=zero_pass_reward_std_min,
        reward_mixed_zero_unique_aux_min=reward_mixed_zero_unique_aux_min,
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
        "near_low": near_low_min_fraction,
        "reward_mixed_zero": reward_mixed_zero_min_fraction,
        "near_high_mid": near_high_mid_min_fraction,
    }
    bucket_max_fraction = {
        "all_invalid": 0.0,
        "mastered": mastered_max_fraction,
        "near_low": near_low_max_fraction,
        "near_high_mid": near_high_mid_max_fraction,
        "easy_tail_nonzero": 0.0,
        "high_pass_non_greedy": 0.0,
        "zero_valid_low": 0.0,
        "zero_valid_high": 0.0,
        "zero_reward_std_low": 0.0,
        "zero_unique_aux_low": 0.0,
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
    for bucket_name in ("near_low", "reward_mixed_zero", "near_high_mid"):
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
            "near_high_mid_max_pass": near_high_mid_max_pass,
            "zero_valid_min": zero_valid_min,
            "zero_valid_max": zero_valid_max,
            "zero_pass_reward_std_min": zero_pass_reward_std_min,
            "reward_mixed_zero_unique_aux_min": reward_mixed_zero_unique_aux_min,
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
    near_high_mid_max_pass: float = 0.75,
    near_high_mid_max_fraction: float = 0.08,
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
    reward_mixed_zero_max_fraction: float = 0.20,
    near_low_min_fraction: float = 0.05,
    near_low_max_fraction: float = 0.20,
    reward_mixed_zero_min_fraction: float = 0.05,
    near_high_mid_min_fraction: float = 0.03,
    greedy_success_max_fraction: float = 1.0,
    pass_one_max_fraction: float = 1.0,
    high_pass_min: float = 0.75,
    high_pass_max_fraction: float = 1.0,
    pass_one_value: float = 1.0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if selection_policy == BUCKET_UNIFIED_POLICY:
        return _select_debug_rows_bucket_unified(
            rows,
            target_size,
            selection_policy=selection_policy,
            core_min_pass=core_min_pass,
            core_max_pass=core_max_pass,
            mastered_pass_min=mastered_pass_min,
            near_high_mid_max_pass=near_high_mid_max_pass,
            near_high_mid_max_fraction=near_high_mid_max_fraction,
            mastered_max_fraction=mastered_max_fraction,
            mastered_fallback_min_fill_fraction=mastered_fallback_min_fill_fraction,
            multi_segment_min_fraction=multi_segment_min_fraction,
            multi_point_min_fraction=multi_point_min_fraction,
            family_min_fraction=family_min_fraction,
            goal_max_fraction=goal_max_fraction,
            zero_valid_min=zero_valid_min,
            zero_valid_max=zero_valid_max,
            zero_pass_reward_std_min=zero_pass_reward_std_min,
            reward_mixed_zero_unique_aux_min=reward_mixed_zero_unique_aux_min,
            reward_mixed_zero_max_fraction=reward_mixed_zero_max_fraction,
            near_low_min_fraction=near_low_min_fraction,
            near_low_max_fraction=near_low_max_fraction,
            reward_mixed_zero_min_fraction=reward_mixed_zero_min_fraction,
            near_high_mid_min_fraction=near_high_mid_min_fraction,
            greedy_success_max_fraction=greedy_success_max_fraction,
            pass_one_max_fraction=pass_one_max_fraction,
            high_pass_min=high_pass_min,
            high_pass_max_fraction=high_pass_max_fraction,
            pass_one_value=pass_one_value,
        )

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
        near_high_mid_max_pass=near_high_mid_max_pass,
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
    easy_tail_counter: Counter[str] = Counter()

    tier_caps = {"mastered": max(0, int(target_size * mastered_max_fraction))}
    easy_tail_caps = {
        "greedy_success": max(0, int(target_size * greedy_success_max_fraction)),
        "pass_one": max(0, int(target_size * pass_one_max_fraction)),
        "high_pass": max(0, int(target_size * high_pass_max_fraction)),
    }
    if selection_policy == "v3_tiered":
        tier_caps["hard_valid_high"] = max(
            0, int(target_size * hard_valid_high_max_fraction)
        )
        tier_caps["hard_valid_mid"] = max(
            0, int(target_size * hard_valid_mid_max_fraction)
        )
    elif selection_policy == "v4_reward_mixed":
        tier_caps["reward_mixed_zero"] = max(
            0, int(target_size * reward_mixed_zero_max_fraction)
        )
    elif selection_policy in {"v6_mid_strict_zero", "v7_structure_strict_zero"}:
        tier_caps["reward_mixed_zero"] = max(
            0, int(target_size * reward_mixed_zero_max_fraction)
        )
        tier_caps["near_high_mid"] = max(
            0, int(target_size * near_high_mid_max_fraction)
        )
    elif selection_policy == "v9_stage_balanced":
        tier_caps["near_low"] = max(0, int(target_size * near_low_max_fraction))
        tier_caps["reward_mixed_zero"] = max(
            0, int(target_size * reward_mixed_zero_max_fraction)
        )
        tier_caps["near_high_mid"] = max(
            0, int(target_size * near_high_mid_max_fraction)
        )
    elif selection_policy == "v10_auxfix_stage_balanced":
        tier_caps["near_low"] = max(0, int(target_size * near_low_max_fraction))
        tier_caps["reward_mixed_zero"] = max(
            0, int(target_size * reward_mixed_zero_max_fraction)
        )
        tier_caps["near_high_mid"] = max(
            0, int(target_size * near_high_mid_max_fraction)
        )
    mastered_fallback_min_rows = max(
        0, int(target_size * mastered_fallback_min_fill_fraction)
    )
    multi_segment_target = max(0, int(target_size * multi_segment_min_fraction))
    multi_point_target = max(0, int(target_size * multi_point_min_fraction))
    family_target = max(1, int(target_size * family_min_fraction))
    goal_cap = max(1, int(target_size * goal_max_fraction))
    tier_min_rows = {}
    if selection_policy in {"v9_stage_balanced", "v10_auxfix_stage_balanced"}:
        tier_min_rows = {
            "near_low": max(0, int(target_size * near_low_min_fraction)),
            "reward_mixed_zero": max(
                0, int(target_size * reward_mixed_zero_min_fraction)
            ),
            "near_high_mid": max(0, int(target_size * near_high_mid_min_fraction)),
        }

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
        pass_key=pass_key,
        tier_caps=tier_caps,
        goal_cap=goal_cap,
        easy_tail_counter=easy_tail_counter,
        easy_tail_caps=easy_tail_caps,
        high_pass_min=high_pass_min,
        pass_one_value=pass_one_value,
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
        pass_key=pass_key,
        tier_caps=tier_caps,
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
            pass_key=pass_key,
            tier_caps=tier_caps,
            goal_cap=goal_cap,
            easy_tail_counter=easy_tail_counter,
            easy_tail_caps=easy_tail_caps,
            high_pass_min=high_pass_min,
            pass_one_value=pass_one_value,
        )
        shortages[f"{family}_shortage"] = max(0, need - len(taken))

    tier_floor_shortages = {}
    if selection_policy in {"v9_stage_balanced", "v10_auxfix_stage_balanced"}:
        for tier_name in ("near_low", "reward_mixed_zero", "near_high_mid"):
            needed = max(0, tier_min_rows.get(tier_name, 0) - tier_selected_counter[tier_name])
            taken = _take_matching_from_tiers(
                selected,
                tier_selected_counter,
                used_ids,
                family_counter,
                goal_counter,
                tier_rows,
                (tier_name,),
                lambda row: True,
                needed,
                pass_key=pass_key,
                tier_caps=tier_caps,
                goal_cap=goal_cap,
                easy_tail_counter=easy_tail_counter,
                easy_tail_caps=easy_tail_caps,
                high_pass_min=high_pass_min,
                pass_one_value=pass_one_value,
            )
            tier_floor_shortages[tier_name] = max(0, needed - len(taken))

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
        pass_key=pass_key,
        tier_caps=tier_caps,
        goal_cap=goal_cap,
        easy_tail_counter=easy_tail_counter,
        easy_tail_caps=easy_tail_caps,
        high_pass_min=high_pass_min,
        pass_one_value=pass_one_value,
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
            pass_key=pass_key,
            tier_caps=tier_caps,
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
    selected_tier_counts = Counter(
        row.get("_selection_tier", "unknown") for row in selected_full_rows
    )
    selected_mastered = selected_tier_counts.get("mastered", 0)
    shortage_reasons = []
    if len(final_rows) < target_size:
        shortage_reasons.append("eligible_pool_exhausted_before_target")
        if filter_stats["excluded_rows_total"] > 0:
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
            "near_high_mid_max_pass": near_high_mid_max_pass,
            "zero_valid_min": zero_valid_min,
            "zero_valid_max": zero_valid_max,
            "zero_pass_reward_std_min": zero_pass_reward_std_min,
            "reward_mixed_zero_unique_aux_min": reward_mixed_zero_unique_aux_min,
            "near_low_min_fraction": near_low_min_fraction,
            "near_low_max_fraction": near_low_max_fraction,
            "reward_mixed_zero_min_fraction": reward_mixed_zero_min_fraction,
            "reward_mixed_zero_max_fraction": reward_mixed_zero_max_fraction,
            "hard_valid_high_max_fraction": hard_valid_high_max_fraction,
            "hard_valid_mid_max_fraction": hard_valid_mid_max_fraction,
            "near_high_mid_max_fraction": near_high_mid_max_fraction,
            "near_high_mid_min_fraction": near_high_mid_min_fraction,
            "mastered_max_fraction": mastered_max_fraction,
            "mastered_fallback_min_fill_fraction": (
                mastered_fallback_min_fill_fraction
            ),
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
        "tier_caps": tier_caps,
        "easy_tail_caps": easy_tail_caps,
        "tier_min_rows": tier_min_rows,
        "tier_max_rows": tier_caps,
        "tier_floor_shortages": tier_floor_shortages,
        "goal_cap_rows": goal_cap,
        "mastered_fallback_min_rows": mastered_fallback_min_rows,
        "mastered_fallback_triggered": mastered_fallback_triggered,
        "selected_mastered_rows": selected_mastered,
        "selected_mastered_ratio": (
            selected_mastered / len(final_rows) if final_rows else 0.0
        ),
        "selected_pass_one_rows": easy_tail_counter["pass_one"],
        "selected_pass_one_ratio": (
            easy_tail_counter["pass_one"] / len(final_rows) if final_rows else 0.0
        ),
        "selected_high_pass_rows": easy_tail_counter["high_pass"],
        "selected_high_pass_ratio": (
            easy_tail_counter["high_pass"] / len(final_rows) if final_rows else 0.0
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
        "selected_near_low_rows": selected_tier_counts.get("near_low", 0),
        "selected_near_low_ratio": (
            selected_tier_counts.get("near_low", 0) / len(final_rows)
            if final_rows
            else 0.0
        ),
        "selected_near_high_mid_rows": selected_tier_counts.get("near_high_mid", 0),
        "selected_near_high_mid_ratio": (
            selected_tier_counts.get("near_high_mid", 0) / len(final_rows)
            if final_rows
            else 0.0
        ),
        "selected_core_rows": selected_tier_counts.get("core", 0),
        "selected_core_ratio": (
            selected_tier_counts.get("core", 0) / len(final_rows)
            if final_rows
            else 0.0
        ),
        "selected_pass_histogram": _build_pass_histogram(selected_full_rows, pass_key),
        "pass_bucket_selected_by_tier": _build_pass_histogram_by_tier(
            selected_full_rows, pass_key
        ),
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
        choices=ALL_SELECTION_POLICIES,
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
    parser.add_argument("--near-high-mid-max-pass", type=float, default=0.75)
    parser.add_argument("--near-high-mid-max-fraction", type=float, default=0.08)
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
    parser.add_argument("--reward-mixed-zero-max-fraction", type=float, default=0.20)
    parser.add_argument("--near-low-min-fraction", type=float, default=0.05)
    parser.add_argument("--near-low-max-fraction", type=float, default=0.20)
    parser.add_argument("--reward-mixed-zero-min-fraction", type=float, default=0.05)
    parser.add_argument("--near-high-mid-min-fraction", type=float, default=0.03)
    parser.add_argument("--greedy-success-max-fraction", type=float, default=1.0)
    parser.add_argument("--pass-one-max-fraction", type=float, default=1.0)
    parser.add_argument("--high-pass-min", type=float, default=0.75)
    parser.add_argument("--high-pass-max-fraction", type=float, default=1.0)
    parser.add_argument("--pass-one-value", type=float, default=1.0)
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
        near_high_mid_max_pass=args.near_high_mid_max_pass,
        near_high_mid_max_fraction=args.near_high_mid_max_fraction,
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
        near_low_min_fraction=args.near_low_min_fraction,
        near_low_max_fraction=args.near_low_max_fraction,
        reward_mixed_zero_min_fraction=args.reward_mixed_zero_min_fraction,
        near_high_mid_min_fraction=args.near_high_mid_min_fraction,
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
