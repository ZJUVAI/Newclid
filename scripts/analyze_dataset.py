#!/usr/bin/env python3
"""Analyze and annotate geometry JSONL datasets for GRPO candidate selection."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from tqdm import tqdm

from newclid.training.aux_dsl import extract_first_tagged_aux_block

PREDICATE_FAMILIES = {
    "circle_family": {"cyclic", "on_circle", "on_circum", "secant"},
    "ratio_family": {"eqratio", "cong"},
    "angle_family": {"eqangle", "angle_bisector", "angle_mirror"},
    "triangle_family": {"simtri", "simtrir"},
    "parallel_perp_family": {"para", "perp"},
}

PREDICATE_PATTERN = re.compile(r"\b([a-z_]+)\b")
PROBLEM_BLOCK_PATTERN = re.compile(r"<problem>\s*(.*?)\s*</problem>", re.DOTALL | re.IGNORECASE)


def extract_problem_text(llm_input: str) -> str:
    match = PROBLEM_BLOCK_PATTERN.search(llm_input or "")
    return match.group(1).strip() if match else (llm_input or "").strip()


def tokenize_predicates(problem_text: str) -> list[str]:
    predicates = []
    for token in PREDICATE_PATTERN.findall(problem_text):
        if token in {"x00"}:
            continue
        if token in {"a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k"}:
            continue
        predicates.append(token)
    return predicates


def extract_goal_predicate(fl_problem: str) -> str | None:
    if not fl_problem or "?" not in fl_problem:
        return None
    goal = fl_problem.split("?", 1)[1].strip()
    if not goal:
        return None
    return goal.split()[0]


def extract_predicate_family_tags(problem_text: str, fl_problem: str) -> list[str]:
    tokens = set(tokenize_predicates(problem_text))
    goal_predicate = extract_goal_predicate(fl_problem)
    if goal_predicate:
        tokens.add(goal_predicate)

    tags = []
    for family, members in PREDICATE_FAMILIES.items():
        if tokens.intersection(members):
            tags.append(family)
    return sorted(tags)


def extract_aux_structure(llm_output: str) -> tuple[bool, str | None, int, int]:
    aux_block = extract_first_tagged_aux_block(llm_output)
    if aux_block is None:
        return False, None, 0, 0

    body = aux_block[len("<aux> ") : -len(" </aux>")].strip()
    points_total = 0
    segment_count = 0
    for segment in body.split(";"):
        segment = segment.strip()
        if not segment or ":" not in segment:
            continue
        before_colon = segment.split(":", 1)[0].strip()
        points = [item for item in before_colon.split() if item and item != "x00"]
        if not points:
            continue
        segment_count += 1
        points_total += len(points)
    return True, aux_block, segment_count, points_total


def annotate_record(record: dict[str, Any], sample_id: str) -> dict[str, Any]:
    query = record.get("llm_input_renamed", "")
    fl_problem = record.get("fl_problem", "")
    problem_text = extract_problem_text(query)
    has_aux, response_aux, aux_segment_count, aux_points_total = extract_aux_structure(
        record.get("llm_output_renamed", "")
    )
    return {
        "sample_id": sample_id,
        "query": query,
        "fl_problem": fl_problem,
        "response_aux": response_aux,
        "has_aux": has_aux,
        "aux_segment_count": aux_segment_count,
        "aux_points_total": aux_points_total,
        "goal_predicate": extract_goal_predicate(fl_problem),
        "predicate_family_tags": extract_predicate_family_tags(problem_text, fl_problem),
    }


def summarize_annotations(annotations: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(annotations)
    aux_rows = sum(1 for item in annotations if item["has_aux"])
    goal_counter = Counter(item["goal_predicate"] for item in annotations if item["goal_predicate"])
    family_counter = Counter()
    segment_counter = Counter()
    points_counter = Counter()
    for item in annotations:
        if item["has_aux"]:
            segment_counter[item["aux_segment_count"]] += 1
            points_counter[item["aux_points_total"]] += 1
        for tag in item["predicate_family_tags"]:
            family_counter[tag] += 1

    return {
        "total_rows": total,
        "aux_rows": aux_rows,
        "aux_ratio": (aux_rows / total) if total else 0.0,
        "goal_predicate_distribution": dict(goal_counter.most_common()),
        "predicate_family_distribution": dict(family_counter.most_common()),
        "aux_segment_count_distribution": dict(sorted(segment_counter.items())),
        "aux_points_total_distribution": dict(sorted(points_counter.items())),
    }


def annotate_jsonl(input_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    annotations: list[dict[str, Any]] = []
    with input_path.open("r", encoding="utf-8") as handle:
        total_lines = sum(1 for _ in handle)
    with input_path.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(tqdm(handle, total=total_lines, desc="Annotating")):
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            sample_id = f"{input_path.stem}:{index}"
            annotations.append(annotate_record(record, sample_id))
    return annotations, summarize_annotations(annotations)


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


def print_summary(summary: dict[str, Any]) -> None:
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Input JSONL dataset")
    parser.add_argument(
        "--annotations-output",
        type=Path,
        default=None,
        help="Optional JSONL path for per-sample annotations",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=None,
        help="Optional JSON path for summary statistics",
    )
    args = parser.parse_args()

    annotations, summary = annotate_jsonl(args.input)
    if args.annotations_output is not None:
        write_jsonl(args.annotations_output, annotations)
    if args.summary_output is not None:
        write_json(args.summary_output, summary)
    print_summary(summary)


if __name__ == "__main__":
    main()
