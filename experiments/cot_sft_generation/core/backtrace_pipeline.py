#!/usr/bin/env python3
"""
Prompt and hard-check helpers for backtrace_text_v1.
"""

from __future__ import annotations

import json
import re

try:
    from .geometry_text import (
        build_aux_direct_consequences,
        build_public_problem_text,
        extract_aux_new_points,
        extract_point_mentions,
        normalize_relation_surface,
        relations_semantically_match,
    )
except ImportError:  # pragma: no cover - script execution path
    from geometry_text import (  # type: ignore
        build_aux_direct_consequences,
        build_public_problem_text,
        extract_aux_new_points,
        extract_point_mentions,
        normalize_relation_surface,
        relations_semantically_match,
    )


_RULE_LEAK_RE = re.compile(r"(?:\[\d{3}\]|\bAR\b|\br\d+\b|\bproof\b|\brule\s+id\b|\btheorem\b|\bcatalog\b)", re.IGNORECASE)
_HIDDEN_META_RE = re.compile(
    r"\b(?:hidden|supervisor|planner|writer|handoff|artifact|proof dag|step id|frontier node|v_core|c1|c2|c3)\b",
    re.IGNORECASE,
)
_TEXT_ONLY_BOUNDARY_RE = re.compile(
    r"(?:<coord>|\bcoordinate(?:s| table)?\b|\bimage\b|\bdiagram\b|\bfigure scan\b|\bgrid\b|\b[a-z]\w*\s*=\s*\(\s*-?\d+\s*,\s*-?\d+\s*\))",
    re.IGNORECASE,
)
_AUX_CONSTRUCTION_RE = re.compile(r"\bconstruct\s+point\s+([a-z]\w*)\b", re.IGNORECASE)
_INSUFFICIENCY_RE = re.compile(
    r"\b(?:still|not enough|not yet|alone|by itself|cannot|can't|without|so we need|need a|need to|this is why)\b",
    re.IGNORECASE,
)
_POINT_RE = re.compile(r"\b([a-z][a-z0-9]*)\b", re.IGNORECASE)


def _split_into_sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", str(text or "").strip()) if part.strip()]


def _relation_mentioned_in_text(text: str, relation: str, point_names: list[str]) -> bool:
    normalized_text = normalize_relation_surface(text or "")
    normalized_relation = normalize_relation_surface(relation or "")
    if not normalized_text or not normalized_relation:
        return False
    if normalized_relation.lower() in normalized_text.lower():
        return True
    if relations_semantically_match(text, relation, point_names):
        return True
    return any(
        relations_semantically_match(sentence, relation, point_names)
        or normalize_relation_surface(sentence).lower().find(normalized_relation.lower()) >= 0
        for sentence in _split_into_sentences(text)
    )


def build_backtrace_write_prompt(record, writer_handoff: dict[str, object]) -> str:
    public_problem = build_public_problem_text(record)
    return (
        "Write one text-only geometry thinking trace for SFT.\n\n"
        "[Visible Problem]\n"
        f"{public_problem}\n\n"
        "[Writer Handoff]\n"
        f"{json.dumps(writer_handoff, ensure_ascii=False, indent=2)}\n\n"
        "[Writing Contract]\n"
        "- Output plain text only, without tags.\n"
        "- Follow this order: goal -> backtrace -> frontier -> support insufficiency -> aux.\n"
        "- Stay text-only: do not mention any image, diagram, coordinates, or coordinate table.\n"
        "- Do not mention proof step ids, rule ids, theorem catalogs, hidden proofs, or internal schema names.\n"
        "- Before the auxiliary construction appears, do not reveal later hidden-route conclusions.\n"
        "- Keep the auxiliary construction geometrically faithful to the approved construction.\n"
        "- The body should motivate why the visible goal is not already reachable, where the backtrace gets stuck, why the current C1 support is insufficient, and then introduce the auxiliary construction.\n"
    )


def build_backtrace_writer_retry_feedback(message: str, writer_handoff: dict | None = None) -> str:
    del writer_handoff
    return (
        "Rewrite the body so it follows goal -> backtrace -> frontier -> support insufficiency -> aux.\n"
        f"Validator feedback: {message}\n"
        "Keep it text-only, do not leak proof metadata, and keep the auxiliary construction faithful."
    )


def collect_backtrace_writer_issues(
    output_text: str,
    *,
    writer_handoff: dict[str, object] | None = None,
    backtrace_slots: dict[str, object] | None = None,
    aux_part: str = "",
) -> list[str]:
    body = str(output_text or "").strip()
    if not body:
        return ["empty_body"]
    if body.startswith("<thinking>") or body.endswith("</thinking>"):
        return ["thinking_tags_not_allowed_in_writer_body"]

    issues: list[str] = []
    if _RULE_LEAK_RE.search(body):
        issues.append("proof_marker_leak")
    if _HIDDEN_META_RE.search(body):
        issues.append("hidden_meta_language")
    if _TEXT_ONLY_BOUNDARY_RE.search(body):
        issues.append("text_only_boundary_violation")

    handoff = writer_handoff or {}
    slots = backtrace_slots or {}
    aux_points = [
        str(point).lower()
        for point in extract_aux_new_points(aux_part or "")
        if isinstance(point, str) and point.strip()
    ]
    point_pool = sorted(
        set(match.lower() for match in _POINT_RE.findall(json.dumps(handoff, ensure_ascii=False)))
        | set(aux_points)
    )
    point_pool = point_pool or aux_points

    aux_construction_nl = str(handoff.get("aux_construction_nl") or "")
    aux_direct_relations = [
        normalize_relation_surface(item)
        for item in build_aux_direct_consequences(aux_part or "")
        if isinstance(item, str) and item.strip()
    ]
    if aux_construction_nl:
        aux_ok = _relation_mentioned_in_text(body, aux_construction_nl, point_pool)
        if not aux_ok and aux_direct_relations:
            aux_ok = any(_relation_mentioned_in_text(body, relation, point_pool) for relation in aux_direct_relations)
        if not aux_ok:
            issues.append("aux_construction_misaligned")

    sentences = _split_into_sentences(body)
    goal_nl = str(handoff.get("goal_nl") or "")
    backtrace_chain_nl = [
        str(item).strip()
        for item in (handoff.get("backtrace_chain_nl") or [])
        if isinstance(item, str) and item.strip()
    ]
    frontier_nodes_nl = [
        str(item).strip()
        for item in (handoff.get("frontier_nodes_nl") or [])
        if isinstance(item, str) and item.strip()
    ]
    goal_idx = next(
        (idx for idx, sentence in enumerate(sentences) if _relation_mentioned_in_text(sentence, goal_nl, point_pool)),
        None,
    )
    backtrace_candidates = [
        relation
        for relation in backtrace_chain_nl
        if relation and not relations_semantically_match(relation, goal_nl, point_pool)
    ]
    backtrace_idx = next(
        (
            idx
            for idx, sentence in enumerate(sentences)
            if any(_relation_mentioned_in_text(sentence, relation, point_pool) for relation in backtrace_candidates)
        ),
        None,
    )
    frontier_idx = next(
        (
            idx
            for idx, sentence in enumerate(sentences)
            if any(_relation_mentioned_in_text(sentence, relation, point_pool) for relation in frontier_nodes_nl)
        ),
        None,
    )
    aux_idx = next(
        (
            idx
            for idx, sentence in enumerate(sentences)
            if _AUX_CONSTRUCTION_RE.search(sentence)
            or any(point in sentence.lower() and "construct" in sentence.lower() for point in aux_points)
            or (aux_construction_nl and _relation_mentioned_in_text(sentence, aux_construction_nl, point_pool))
        ),
        None,
    )
    insufficiency_idx = next(
        (idx for idx, sentence in enumerate(sentences) if _INSUFFICIENCY_RE.search(sentence)),
        None,
    )

    if goal_nl and goal_idx is None:
        issues.append("missing_goal_reference")
    if backtrace_candidates and backtrace_idx is None:
        issues.append("missing_backtrace_reference")
    if frontier_nodes_nl and frontier_idx is None:
        issues.append("missing_frontier_reference")
    if aux_construction_nl and aux_idx is None:
        issues.append("missing_aux_reference")

    if goal_idx is not None and backtrace_idx is not None and backtrace_idx < goal_idx:
        issues.append("narrative_order_violation")
    if backtrace_idx is not None and frontier_idx is not None and frontier_idx < backtrace_idx:
        issues.append("narrative_order_violation")
    if frontier_idx is not None and aux_idx is not None and aux_idx < frontier_idx:
        issues.append("narrative_order_violation")
    if frontier_idx is not None and aux_idx is not None:
        insufficiency_window = " ".join(sentences[frontier_idx:aux_idx + 1])
        if not _INSUFFICIENCY_RE.search(insufficiency_window):
            issues.append("support_insufficiency_missing")
    elif insufficiency_idx is not None and aux_idx is not None and insufficiency_idx > aux_idx:
        issues.append("narrative_order_violation")

    pre_aux_text = body if aux_idx is None else " ".join(sentences[:aux_idx])
    hidden_relations = [
        str(item).strip()
        for item in (slots.get("H_relations_nl") or [])
        if isinstance(item, str) and item.strip()
    ]
    hidden_relations = [normalize_relation_surface(relation) for relation in hidden_relations if relation]
    for relation in hidden_relations:
        relation_aux_points = sorted(extract_point_mentions(relation, aux_points))
        pre_aux_points = sorted(extract_point_mentions(pre_aux_text, aux_points))
        if relation_aux_points and not set(relation_aux_points).intersection(pre_aux_points):
            continue
        if aux_construction_nl and relations_semantically_match(relation, aux_construction_nl, point_pool):
            continue
        if _relation_mentioned_in_text(pre_aux_text, relation, point_pool):
            issues.append("early_hidden_relation")
            break

    deduped_issues = []
    seen = set()
    for issue in issues:
        if issue not in seen:
            deduped_issues.append(issue)
            seen.add(issue)
    return deduped_issues


def validate_backtrace_writer_body(
    output_text: str,
    visible_goal: str = "",
    injected_prefix: str = "",
    plan: dict | None = None,
    writer_handoff: dict[str, object] | None = None,
    backtrace_slots: dict[str, object] | None = None,
    aux_part: str = "",
):
    del visible_goal, injected_prefix, plan
    issues = collect_backtrace_writer_issues(
        output_text,
        writer_handoff=writer_handoff,
        backtrace_slots=backtrace_slots,
        aux_part=aux_part,
    )
    if issues:
        return False, "; ".join(issues)
    return True, "Valid backtrace writer body"


__all__ = [
    "build_backtrace_write_prompt",
    "build_backtrace_writer_retry_feedback",
    "collect_backtrace_writer_issues",
    "validate_backtrace_writer_body",
]
