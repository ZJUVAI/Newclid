#!/usr/bin/env python3
"""Cheap streaming prefilter for large GRPO candidate pools."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any


AUX_BUCKET_WEIGHTS = {
    "multi_aux": 0.60,
    "single_aux": 0.40,
}

PREMISE_BUCKET_WEIGHTS = {
    "p8_plus": 0.40,
    "p5_7": 0.40,
    "p0_4": 0.20,
}

GOAL_CAP_RATIO = 0.20

KNOWN_FAMILY_BY_GOAL = {
    "cyclic": "circle_family",
    "secant": "circle_family",
    "cong": "ratio_family",
    "eqratio": "ratio_family",
    "eqangle": "angle_family",
    "angle_bisector": "angle_family",
    "angle_mirror": "angle_family",
    "simtri": "triangle_family",
    "simtrir": "triangle_family",
    "para": "parallel_perp_family",
    "perp": "parallel_perp_family",
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


def query_hash(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()


def aux_shape_bucket(row: dict[str, Any]) -> str:
    if row.get("aux_segment_count", 0) >= 2 or row.get("aux_points_total", 0) >= 2:
        return "multi_aux"
    return "single_aux"


def complexity_source_value(row: dict[str, Any]) -> int:
    n_premises = row.get("n_premises")
    if isinstance(n_premises, int):
        return n_premises
    if isinstance(n_premises, float):
        return int(n_premises)
    return int(row.get("problem_clause_count", 0) or 0)


def premise_bucket(row: dict[str, Any]) -> str:
    value = complexity_source_value(row)
    if value >= 8:
        return "p8_plus"
    if value >= 5:
        return "p5_7"
    return "p0_4"


def primary_family(row: dict[str, Any]) -> str:
    goal_predicate = row.get("goal_predicate")
    if goal_predicate in KNOWN_FAMILY_BY_GOAL:
        return KNOWN_FAMILY_BY_GOAL[goal_predicate]
    tags = row.get("predicate_family_tags") or []
    if tags:
        return tags[0]
    return "other_family"


def prefilter_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (aux_shape_bucket(row), premise_bucket(row), primary_family(row))


def _safe_round(value: float) -> int:
    return max(0, int(round(value)))


def compute_bucket_quotas(
    bucket_counts: Counter[tuple[str, str, str]],
    target_size: int,
) -> dict[tuple[str, str, str], int]:
    quotas: dict[tuple[str, str, str], int] = {}
    aux_totals: dict[str, int] = {}
    for aux_bucket, weight in AUX_BUCKET_WEIGHTS.items():
        aux_totals[aux_bucket] = _safe_round(target_size * weight)

    assigned = sum(aux_totals.values())
    if assigned != target_size:
        aux_totals["multi_aux"] += target_size - assigned

    for aux_bucket, aux_target in aux_totals.items():
        premise_totals: dict[str, int] = {}
        for prem_bucket, weight in PREMISE_BUCKET_WEIGHTS.items():
            premise_totals[prem_bucket] = _safe_round(aux_target * weight)
        assigned = sum(premise_totals.values())
        if assigned != aux_target:
            premise_totals["p8_plus"] += aux_target - assigned

        for prem_bucket, prem_target in premise_totals.items():
            family_keys = sorted(
                key for key, count in bucket_counts.items()
                if count > 0 and key[0] == aux_bucket and key[1] == prem_bucket
            )
            if not family_keys or prem_target <= 0:
                continue
            base = prem_target // len(family_keys)
            remainder = prem_target % len(family_keys)
            for index, key in enumerate(family_keys):
                quotas[key] = base + (1 if index < remainder else 0)
    return quotas


def _reservoir_insert(
    reservoirs: dict[tuple[str, str, str], list[dict[str, Any]]],
    seen_counts: Counter[tuple[str, str, str]],
    quotas: dict[tuple[str, str, str], int],
    row: dict[str, Any],
    rng: random.Random,
) -> None:
    key = prefilter_key(row)
    quota = quotas.get(key, 0)
    if quota <= 0:
        return
    seen_counts[key] += 1
    bucket = reservoirs.setdefault(key, [])
    if len(bucket) < quota:
        bucket.append(row)
        return
    replace_index = rng.randrange(seen_counts[key])
    if replace_index < quota:
        bucket[replace_index] = row


def _fill_with_cap(
    selected: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    target_size: int,
    used_queries: set[str],
) -> tuple[list[dict[str, Any]], int]:
    goal_cap = max(1, int(target_size * GOAL_CAP_RATIO))
    goal_counts = Counter(row.get("goal_predicate") for row in selected if row.get("goal_predicate"))
    skipped_for_cap = 0
    for row in candidates:
        if len(selected) >= target_size:
            break
        qhash = query_hash(row["query"])
        if qhash in used_queries:
            continue
        goal = row.get("goal_predicate")
        if goal and goal_counts[goal] >= goal_cap:
            skipped_for_cap += 1
            continue
        selected.append(row)
        used_queries.add(qhash)
        if goal:
            goal_counts[goal] += 1
    return selected, skipped_for_cap


def prefilter_candidate_pool(
    rows: list[dict[str, Any]],
    *,
    target_size: int,
    seed: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rng = random.Random(seed)
    query_counts = Counter()
    bucket_counts: Counter[tuple[str, str, str]] = Counter()
    distinct_rows = 0
    duplicate_rows = 0

    for row in rows:
        qhash = query_hash(row["query"])
        query_counts[qhash] += 1
        if query_counts[qhash] == 1:
            distinct_rows += 1
            bucket_counts[prefilter_key(row)] += 1
        else:
            duplicate_rows += 1

    quotas = compute_bucket_quotas(bucket_counts, min(target_size, distinct_rows))
    reservoirs: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    seen_counts: Counter[tuple[str, str, str]] = Counter()
    used_queries: set[str] = set()

    for row in rows:
        qhash = query_hash(row["query"])
        if qhash in used_queries:
            continue
        used_queries.add(qhash)
        _reservoir_insert(reservoirs, seen_counts, quotas, row, rng)

    selected: list[dict[str, Any]] = []
    selected_queries: set[str] = set()
    shortages = {}
    for key in sorted(quotas):
        bucket_rows = reservoirs.get(key, [])
        selected.extend(bucket_rows)
        selected_queries.update(query_hash(row["query"]) for row in bucket_rows)
        shortages["|".join(key)] = max(0, quotas[key] - len(bucket_rows))

    if len(selected) > target_size:
        selected = selected[:target_size]
        selected_queries = {query_hash(row["query"]) for row in selected}

    selected_hashes = {query_hash(row["query"]) for row in selected}
    fallback_candidates = []
    for row in rows:
        qhash = query_hash(row["query"])
        if qhash in selected_hashes:
            continue
        if query_counts[qhash] > 1:
            # Keep only the first occurrence of an exact duplicate query.
            query_counts[qhash] = 1
        fallback_candidates.append(row)
        selected_hashes.add(qhash)

    selected, skipped_for_cap = _fill_with_cap(
        selected,
        fallback_candidates,
        min(target_size, distinct_rows),
        selected_queries,
    )

    selected = selected[: min(target_size, distinct_rows)]

    final_bucket_counts = Counter(prefilter_key(row) for row in selected)
    final_goal_counts = Counter(row.get("goal_predicate") for row in selected if row.get("goal_predicate"))

    report = {
        "input_rows": len(rows),
        "distinct_queries": distinct_rows,
        "exact_duplicate_queries_removed": duplicate_rows,
        "target_size": target_size,
        "selected_rows": len(selected),
        "bucket_counts_before": {"|".join(key): count for key, count in sorted(bucket_counts.items())},
        "bucket_quota_targets": {"|".join(key): count for key, count in sorted(quotas.items())},
        "bucket_counts_after": {"|".join(key): count for key, count in sorted(final_bucket_counts.items())},
        "bucket_shortages": shortages,
        "selected_goal_predicate_distribution": dict(final_goal_counts.most_common()),
        "skipped_for_goal_cap": skipped_for_cap,
    }
    return selected, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Candidate pool JSONL")
    parser.add_argument("output", type=Path, help="Prefiltered candidate pool JSONL")
    parser.add_argument("--report-output", type=Path, default=None, help="Optional JSON report path")
    parser.add_argument("--target-size", type=int, default=50000)
    parser.add_argument("--seed", type=int, default=998244353)
    args = parser.parse_args()

    rows = load_jsonl(args.input)
    selected, report = prefilter_candidate_pool(rows, target_size=args.target_size, seed=args.seed)
    write_jsonl(args.output, selected)
    if args.report_output is not None:
        write_json(args.report_output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
