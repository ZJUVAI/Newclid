#!/usr/bin/env python3
"""Shared utilities for geometry problem annotation and analysis."""

from __future__ import annotations

import re
from typing import Any

PREDICATE_FAMILIES = {
    "circle_family": {"cyclic", "on_circle", "on_circum", "secant"},
    "ratio_family": {"eqratio", "cong"},
    "angle_family": {"eqangle", "angle_bisector", "angle_mirror"},
    "triangle_family": {"simtri", "simtrir"},
    "parallel_perp_family": {"para", "perp"},
}

PREDICATE_PATTERN = re.compile(r"\b([a-z_]+)\b")
PROBLEM_BLOCK_PATTERN = re.compile(
    r"<problem>\s*(.*?)\s*</problem>", re.DOTALL | re.IGNORECASE
)


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


def extract_problem_predicate_count(problem_text: str) -> int:
    return len(tokenize_predicates(problem_text))


def extract_problem_clause_count(fl_problem: str) -> int:
    if not fl_problem:
        return 0
    construction_part = fl_problem.split("?", 1)[0].strip()
    if not construction_part:
        return 0
    return sum(1 for clause in construction_part.split(";") if clause.strip())


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
