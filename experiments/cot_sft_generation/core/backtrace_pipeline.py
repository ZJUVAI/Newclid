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


_RULE_LEAK_RE = re.compile(r"(?:\[\d{3}\]|\bAR\b|\br\d+\b|\brule\s+id\b)", re.IGNORECASE)
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


def _extract_relation_candidates(text: str) -> list[str]:
    sentence = str(text or "").strip()
    if not sentence:
        return []
    patterns = [
        r"(?:the\s+)?ratio(?:\s+of)?\s+(?:segment\s+)?[a-z]{2}\s+to\s+(?:segment\s+)?[a-z]{2}\s+(?:equals|is\s+equal\s+to)\s+(?:the\s+)?ratio(?:\s+of)?\s+(?:segment\s+)?[a-z]{2}\s+to\s+(?:segment\s+)?[a-z]{2}",
        r"(?:points?\s+)?[a-z]\w*\s*,\s*[a-z]\w*\s*,\s*(?:and\s+)?[a-z]\w*\s+(?:lie\s+on|are\s+on)\s+(?:the\s+)?same\s+line",
        r"(?:points?\s+)?[a-z]\w*\s*,\s*[a-z]\w*\s*,\s*(?:and\s+)?[a-z]\w*\s+are\s+collinear",
        r"line\s+[a-z]{2}\s+is\s+parallel\s+to\s+line\s+[a-z]{2}",
        r"line\s+[a-z]{2}\s+is\s+perpendicular\s+to\s+line\s+[a-z]{2}",
        r"angle\s+[a-z]{2}/[a-z]{2}\s+equals\s+angle\s+[a-z]{2}/[a-z]{2}",
        r"triangles\s+[a-z]{3}\s+and\s+[a-z]{3}\s+are\s+(?:similar|congruent)",
        r"[a-z]{2}\s+equals\s+[a-z]{2}",
        r"equality\s+of\s+[a-z]{2}\s+and\s+[a-z]{2}",
    ]
    candidates = [normalize_relation_surface(sentence)]
    for pattern in patterns:
        for match in re.finditer(pattern, sentence, flags=re.IGNORECASE):
            candidates.append(normalize_relation_surface(match.group(0)))
    # Convert "equality of bf and cf" into the same surface as "bf equals cf".
    for match in re.finditer(r"equality\s+of\s+([a-z]{2})\s+and\s+([a-z]{2})", sentence, flags=re.IGNORECASE):
        candidates.append(f"{match.group(1).lower()} equals {match.group(2).lower()}")
    deduped: list[str] = []
    seen = set()
    for candidate in candidates:
        normalized_candidate = str(candidate or "").strip()
        if not normalized_candidate or normalized_candidate in seen:
            continue
        deduped.append(normalized_candidate)
        seen.add(normalized_candidate)
    return deduped


def _relation_mentioned_in_text(text: str, relation: str, point_names: list[str]) -> bool:
    normalized_text = normalize_relation_surface(text or "")
    normalized_relation = normalize_relation_surface(relation or "")
    if not normalized_text or not normalized_relation:
        return False
    if normalized_relation.lower() in normalized_text.lower():
        return True
    if relations_semantically_match(text, relation, point_names):
        return True
    for candidate in _extract_relation_candidates(text):
        if candidate.lower() == normalized_relation.lower():
            return True
        if normalized_relation.lower() in candidate.lower():
            return True
        if relations_semantically_match(candidate, relation, point_names):
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
        "- Start from the visible goal, then walk through the staged backtrace in order.\n"
        "- For each stage, explain the current claim, which visible support already helps, and which visible subgoal(s) still remain.\n"
        "- When a stage reaches the visible limit, explain that the current visible route is not enough before introducing the auxiliary construction.\n"
        "- Stay text-only: do not mention any image, diagram, coordinates, or coordinate table.\n"
        "- Do not mention proof step ids, rule ids, hidden proofs, or internal schema names.\n"
        "- Avoid theorem-catalog or proof-style phrasing when a direct geometric description is enough.\n"
        "- Before the auxiliary construction appears, do not reveal later hidden-route conclusions.\n"
        "- Keep the auxiliary construction geometrically faithful to the approved construction.\n"
        "- The body should show how each visible claim reduces to deeper visible subgoals until the visible route reaches its limit, and only then introduce the auxiliary construction.\n"
    )


def build_backtrace_writer_retry_feedback(message: str, writer_handoff: dict | None = None) -> str:
    del writer_handoff
    return (
        "Rewrite the body so it follows the staged backtrace: current claim -> visible support -> remaining subgoal(s) -> visible boundary -> aux.\n"
        f"Validator feedback: {message}\n"
        "Keep it text-only, do not leak proof metadata, and keep the auxiliary construction faithful."
    )


def _first_sentence_idx_for_relation(sentences: list[str], relation: str, point_pool: list[str]) -> int | None:
    if not relation:
        return None
    for idx, sentence in enumerate(sentences):
        if _relation_mentioned_in_text(sentence, relation, point_pool):
            return idx
    return None


def _first_sentence_idx_for_any_relation(sentences: list[str], relations: list[str], point_pool: list[str]) -> int | None:
    relation_list = [relation for relation in relations if relation]
    if not relation_list:
        return None
    for idx, sentence in enumerate(sentences):
        if any(_relation_mentioned_in_text(sentence, relation, point_pool) for relation in relation_list):
            return idx
    return None


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
    backtrace_stages = [
        stage for stage in (handoff.get("backtrace_stages") or []) if isinstance(stage, dict)
    ]
    goal_idx = _first_sentence_idx_for_relation(sentences, goal_nl, point_pool)
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
    if aux_construction_nl and aux_idx is None:
        issues.append("missing_aux_reference")

    last_stage_claim_idx = goal_idx if goal_idx is not None else -1
    first_terminal_claim_idx = None
    saw_terminal_boundary = False
    for stage in backtrace_stages:
        claim_nl = str(stage.get("claim_nl") or "").strip()
        visible_support_nl = [
            str(item).strip()
            for item in (stage.get("visible_support_nl") or [])
            if isinstance(item, str) and item.strip()
        ]
        subgoal_claims_nl = [
            str(item).strip()
            for item in (stage.get("subgoal_claims_nl") or [])
            if isinstance(item, str) and item.strip()
        ]
        is_terminal = bool(stage.get("stops_at_aux_boundary"))

        claim_idx = _first_sentence_idx_for_relation(sentences, claim_nl, point_pool)
        if claim_nl and claim_idx is None:
            issues.append("missing_stage_reference")
            continue
        if claim_idx is not None and claim_idx < last_stage_claim_idx:
            issues.append("narrative_order_violation")
        if claim_idx is not None:
            last_stage_claim_idx = claim_idx

        support_idx = _first_sentence_idx_for_any_relation(sentences, visible_support_nl, point_pool)
        if visible_support_nl and support_idx is None:
            issues.append("missing_stage_support_reference")
        if claim_idx is not None and support_idx is not None and support_idx < claim_idx:
            issues.append("narrative_order_violation")

        if is_terminal:
            if first_terminal_claim_idx is None:
                first_terminal_claim_idx = claim_idx
            if claim_idx is not None and aux_idx is not None and aux_idx < claim_idx:
                issues.append("narrative_order_violation")
            window_start = claim_idx if claim_idx is not None else 0
            window_end = aux_idx + 1 if aux_idx is not None else len(sentences)
            insufficiency_window = " ".join(sentences[window_start:window_end])
            if not _INSUFFICIENCY_RE.search(insufficiency_window):
                issues.append("support_insufficiency_missing")
            else:
                saw_terminal_boundary = True
            continue

        for subgoal_nl in subgoal_claims_nl:
            subgoal_idx = _first_sentence_idx_for_relation(sentences, subgoal_nl, point_pool)
            if subgoal_idx is None:
                issues.append("missing_stage_subgoal_reference")
                continue
            if claim_idx is not None and subgoal_idx < claim_idx:
                issues.append("narrative_order_violation")

    if first_terminal_claim_idx is not None and aux_idx is not None and aux_idx < first_terminal_claim_idx:
        issues.append("narrative_order_violation")
    if first_terminal_claim_idx is not None and aux_idx is not None and not saw_terminal_boundary:
        issues.append("missing_terminal_boundary")
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
