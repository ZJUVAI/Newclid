#!/usr/bin/env python3
"""
Statistical analysis for select_simple JSONL datasets.

These datasets use fields: query (problem in predicate format),
fl_problem (construction format with coordinates), response (aux output).
All records contain <aux> but no <proof>.
"""

import argparse
import json
import re
import statistics
from collections import Counter, defaultdict

from tqdm import tqdm


# ============================================================================
# TAG HELPERS (shared with analyze_dataset.py)
# ============================================================================


def extract_tag_content(text: str, tag: str) -> str:
    match = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL)
    return match.group(1).strip() if match else ""


# ============================================================================
# STATS EXTRACTION
# ============================================================================


def extract_points(problem_text: str) -> set[str]:
    """Extract point names from predicate-format problem text (query field)."""
    points = set()
    for segment in problem_text.split(";"):
        segment = segment.strip()
        if ":" not in segment:
            continue
        before_colon = segment.split(":", 1)[0].strip()
        points.update(token for token in before_colon.split() if token)
    return points


def extract_predicates_before_question(problem_text: str) -> list[str]:
    """Extract premise predicates (before ?) from predicate-format problem text."""
    parts = problem_text.split("?")
    if len(parts) < 2:
        return []
    before = parts[0]
    predicates = []
    for segment in before.split(";"):
        segment = segment.strip()
        if not segment or ":" not in segment:
            continue
        after_colon = segment.split(":", 1)[1].strip()
        predicates.extend(re.findall(r"([a-z]+)\s+[a-z\s]+\s*\[\d+\]", after_colon))
    return predicates


def extract_goal_predicate(problem_text: str) -> str | None:
    """Extract the goal predicate name (after ?)."""
    parts = problem_text.split("?")
    if len(parts) < 2:
        return None
    goal = parts[1].strip()
    tokens = goal.split()
    return tokens[0] if tokens else None


def parse_aux_stats(response: str) -> tuple[list[tuple[str, ...]], int, list[int]]:
    """Extract aux predicate combinations and per-segment point counts."""
    aux_content = extract_tag_content(response, "aux")
    if not aux_content:
        return [], 0, []

    combinations: list[tuple[str, ...]] = []
    points_per_segment: list[int] = []

    for segment in aux_content.split(";"):
        segment = segment.strip()
        if not segment or ":" not in segment:
            continue

        before_colon, after_colon = segment.split(":", 1)
        predicates = re.findall(r"([a-z]+)\s+[a-z\s]+\s*\[\d+\]", after_colon.strip())
        if predicates:
            combinations.append(tuple(sorted(predicates)))

        # exclude xNN prefix token when counting new points
        points = [p for p in before_colon.strip().split() if p and not re.match(r"x\d+$", p)]
        points_per_segment.append(len(points))

    return combinations, len(points_per_segment), points_per_segment


def count_aux_segments(response: str) -> int:
    aux_content = extract_tag_content(response, "aux")
    if not aux_content:
        return 0
    return sum(1 for s in aux_content.split(";") if s.strip() and ":" in s)


# ============================================================================
# MAIN ANALYSIS
# ============================================================================


def analyze(file_path: str):
    total_records = 0
    point_counts: Counter = Counter()
    premise_predicates: Counter = Counter()
    goal_predicates: Counter = Counter()
    aux_predicate_combinations: Counter = Counter()
    aux_segment_counts: Counter = Counter()
    aux_points_per_segment: Counter = Counter()
    parse_errors = 0
    processing_errors = 0

    print(f"Analyzing {file_path} ...")
    with open(file_path) as f:
        for i, line in enumerate(tqdm(f, desc="Processing"), 1):
            try:
                total_records += 1
                data = json.loads(line.strip())
                query = data["query"]
                response = data["response"]

                problem_text = extract_tag_content(query, "problem")
                if problem_text:
                    points = extract_points(problem_text)
                    point_counts[len(points)] += 1
                    premise_predicates.update(extract_predicates_before_question(problem_text))
                    goal = extract_goal_predicate(problem_text)
                    if goal:
                        goal_predicates[goal] += 1

                combinations, seg_count, pts_per_seg = parse_aux_stats(response)
                for combo in combinations:
                    aux_predicate_combinations[combo] += 1
                aux_segment_counts[seg_count] += 1
                for pts in pts_per_seg:
                    aux_points_per_segment[pts] += 1

            except json.JSONDecodeError as e:
                parse_errors += 1
                print(f"  JSON error on line {i}: {e}")
            except Exception as e:
                processing_errors += 1
                print(f"  Error on line {i}: {e}")

    _report(
        total_records,
        point_counts,
        premise_predicates,
        goal_predicates,
        aux_predicate_combinations,
        aux_segment_counts,
        aux_points_per_segment,
        parse_errors,
        processing_errors,
    )


# ============================================================================
# REPORTING
# ============================================================================


def _pct(count: int, total: int) -> str:
    return f"{count / total:.2%}" if total > 0 else "n/a"


def _report(
    total_records,
    point_counts,
    premise_predicates,
    goal_predicates,
    aux_predicate_combinations,
    aux_segment_counts,
    aux_points_per_segment,
    parse_errors,
    processing_errors,
):
    W = 80
    print("\n" + "=" * W)
    print("SELECT-SIMPLE DATASET ANALYSIS REPORT")
    print("=" * W)

    print(f"\nTotal records: {total_records:,}")
    if parse_errors or processing_errors:
        print(f"  Parse errors:      {parse_errors:,}")
        print(f"  Processing errors: {processing_errors:,}")

    # ---- 0. Aux content ----
    print("\n0. AUXILIARY CONTENT")
    print("-" * 40)
    total_aux = sum(aux_segment_counts.values())
    print(f"  Records with <aux>: {total_aux:,} ({_pct(total_aux, total_records)})")

    if aux_predicate_combinations:
        print("\n  Predicate combination distribution:")
        total_combos = sum(aux_predicate_combinations.values())
        for combo, cnt in aux_predicate_combinations.most_common():
            combo_str = "[" + ", ".join(combo) + "]"
            print(f"    {combo_str}: {cnt:,} ({_pct(cnt, total_combos)})")

    if aux_segment_counts:
        print("\n  Aux segment count per record:")
        for n in sorted(aux_segment_counts):
            cnt = aux_segment_counts[n]
            print(f"    {n} segment(s): {cnt:,} ({_pct(cnt, total_aux)})")

    if aux_points_per_segment:
        print("\n  New points per aux segment:")
        total_segs = sum(aux_points_per_segment.values())
        for n in sorted(aux_points_per_segment):
            cnt = aux_points_per_segment[n]
            print(f"    {n} point(s): {cnt:,} ({_pct(cnt, total_segs)})")

    # ---- 1. Point distribution ----
    print("\n1. POINT DISTRIBUTION")
    print("-" * 40)
    for n in sorted(point_counts):
        cnt = point_counts[n]
        print(f"  {n} points: {cnt:,} ({_pct(cnt, total_records)})")

    # ---- 2. Premise predicates ----
    print("\n2. PREMISE PREDICATES (before '?')")
    print("-" * 40)
    total_prem = sum(premise_predicates.values())
    for pred, cnt in premise_predicates.most_common():
        print(f"  {pred}: {cnt:,} ({_pct(cnt, total_prem)})")

    # ---- 3. Goal predicates ----
    print("\n3. GOAL PREDICATES (after '?')")
    print("-" * 40)
    total_goal = sum(goal_predicates.values())
    for pred, cnt in goal_predicates.most_common():
        print(f"  {pred}: {cnt:,} ({_pct(cnt, total_goal)})")

    print("\n" + "=" * W)
    print("Analysis complete.")
    print("=" * W)


# ============================================================================
# ENTRY POINT
# ============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Analyze a select_simple geometry JSONL dataset (query/fl_problem/response)."
    )
    parser.add_argument("input_file", help="Path to JSONL dataset file")
    args = parser.parse_args()
    analyze(args.input_file)


if __name__ == "__main__":
    main()
