#!/usr/bin/env python3
"""
Prompt and hard-check helpers for backtrace_text_v2.
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
        extract_relation_segment_tokens,
        extract_relation_signatures,
        normalize_relation_surface,
        relation_text_keywords,
        relations_semantically_match,
    )
except ImportError:  # pragma: no cover - script execution path
    from geometry_text import (  # type: ignore
        build_aux_direct_consequences,
        build_public_problem_text,
        extract_aux_new_points,
        extract_point_mentions,
        extract_relation_segment_tokens,
        extract_relation_signatures,
        normalize_relation_surface,
        relation_text_keywords,
        relations_semantically_match,
    )


_RULE_LEAK_RE = re.compile(r"(?:\[\d{3}\]|\bAR\b|\br\d+\b|\brule\s+id\b)", re.IGNORECASE)
_HIDDEN_META_RE = re.compile(
    r"(?<!non-)\b(?:hidden|supervisor|planner|writer|handoff|artifact|proof dag|step id|frontier node|v_core|c1|c2|c3)\b",
    re.IGNORECASE,
)
_TEXT_ONLY_BOUNDARY_RE = re.compile(
    r"(?:<coord>|\bcoordinate(?:s| table)?\b|\bimage\b|\bfigure scan\b|\bgrid\b|\b[a-z]\w*\s*=\s*\(\s*-?\d+\s*,\s*-?\d+\s*\))",
    re.IGNORECASE,
)
_AUX_CONSTRUCTION_RE = re.compile(r"\bconstruct\s+(?:a\s+)?point\s+([a-z]\w*)\b", re.IGNORECASE)
_INSUFFICIENCY_RE = re.compile(
    r"\b(?:still|not enough|not yet|alone|by itself|cannot|can't|without|insufficient|insufficiency|visible boundary|visible limit|does not provide enough|doesn't provide enough|do not provide (?:a\s+)?sufficient|does not provide (?:a\s+)?sufficient|not sufficient|so we need|need a|need to|this is why)\b",
    re.IGNORECASE,
)
_POINT_RE = re.compile(r"\b([a-z][a-z0-9]*)\b", re.IGNORECASE)


def _has_hidden_meta_language(text: str) -> bool:
    cleaned = re.sub(r"\bhidden\s+and\s+non-hidden\b", "", str(text or ""), flags=re.IGNORECASE)
    return bool(_HIDDEN_META_RE.search(cleaned))


def _split_into_sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", str(text or "").strip()) if part.strip()]


def _extract_relation_candidates(text: str, *, include_full_sentence: bool = True) -> list[str]:
    sentence = str(text or "").strip()
    if not sentence:
        return []
    loose_equal = r"(?:equals|is\s+equal(?:\s+to)?|are\s+equal(?:\s+to)?|must\s+equal|equall?ing)"
    patterns = [
        rf"(?:the\s+)?ratio(?:\s+of)?\s+(?:side\s+|segment\s+|length\s+)?[a-z]{{2}}\s+to\s+(?:side\s+|segment\s+|length\s+)?[a-z]{{2}}\s+{loose_equal}\s+(?:the\s+)?ratio(?:\s+of)?\s+(?:side\s+|segment\s+|length\s+)?[a-z]{{2}}\s+to\s+(?:side\s+|segment\s+|length\s+)?[a-z]{{2}}",
        rf"(?:the\s+)?ratio\s+of\s+(?:side|segment|length)\s+[a-z]{{2}}\s+to\s+(?:side|segment|length)\s+[a-z]{{2}}\s+{loose_equal}\s+(?:the\s+)?ratio\s+of\s+(?:side|segment|length)\s+[a-z]{{2}}\s+to\s+(?:side|segment|length)\s+[a-z]{{2}}",
        r"(?:points?\s+)?[a-z]\w*\s*,\s*[a-z]\w*\s*,\s*(?:and\s+)?[a-z]\w*\s+(?:lie\s+on|are\s+on)\s+(?:the\s+)?same\s+line",
        r"(?:points?\s+)?[a-z]\w*\s*,\s*[a-z]\w*\s*,\s*(?:and\s+)?[a-z]\w*\s+are\s+collinear",
        r"line\s+[a-z]{2}\s+is\s+parallel\s+to\s+line\s+[a-z]{2}",
        r"line\s+[a-z]{2}\s+is\s+perpendicular\s+to\s+line\s+[a-z]{2}",
        rf"angle\s+[a-z]{{2}}/[a-z]{{2}}\s+{loose_equal}\s+angle\s+[a-z]{{2}}/[a-z]{{2}}",
        rf"(?:the\s+)?angle\s+[a-z]{{2}}/[a-z]{{2}}\s+{loose_equal}\s+(?:the\s+)?angle\s+[a-z]{{2}}/[a-z]{{2}}",
        rf"(?:the\s+)?angle\s+formed\s+by\s+(?:(?:sides?|segments?|lines?)\s+)?[a-z]{{2}}\s+and\s+(?:(?:sides?|segments?|lines?)\s+)?[a-z]{{2}}\s+{loose_equal}\s+(?:the\s+)?angle\s+formed\s+by\s+(?:(?:sides?|segments?|lines?)\s+)?[a-z]{{2}}\s+and\s+(?:(?:sides?|segments?|lines?)\s+)?[a-z]{{2}}",
        rf"(?:the\s+)?angle\s+between\s+(?:(?:sides?|segments?|lines?)\s+)?[a-z]{{2}}\s+and\s+(?:(?:sides?|segments?|lines?)\s+)?[a-z]{{2}}\s+{loose_equal}\s+(?:the\s+)?angle\s+between\s+(?:(?:sides?|segments?|lines?)\s+)?[a-z]{{2}}\s+and\s+(?:(?:sides?|segments?|lines?)\s+)?[a-z]{{2}}",
        rf"(?:the\s+)?angle\s+involving\s+(?:(?:sides?|segments?|lines?)\s+)?[a-z]{{2}}\s+and\s+(?:(?:sides?|segments?|lines?)\s+)?[a-z]{{2}}\s+{loose_equal}\s+(?:the\s+)?angle\s+involving\s+(?:(?:sides?|segments?|lines?)\s+)?[a-z]{{2}}\s+and\s+(?:(?:sides?|segments?|lines?)\s+)?[a-z]{{2}}",
        r"triangles\s+[a-z]{3}\s+and\s+[a-z]{3}\s+are\s+(?:similar|congruent)",
        rf"[a-z]{{2}}\s+{loose_equal}\s+[a-z]{{2}}",
        rf"(?:segment|side)\s+[a-z]{{2}}\s+(?:{loose_equal}|is\s+equal\s+in\s+length\s+to)\s+(?:segment|side)\s+[a-z]{{2}}",
        r"equality\s+of\s+[a-z]{2}\s+and\s+[a-z]{2}",
    ]
    candidates = [normalize_relation_surface(sentence)] if include_full_sentence else []
    for pattern in patterns:
        for match in re.finditer(pattern, sentence, flags=re.IGNORECASE):
            candidates.append(normalize_relation_surface(match.group(0)))
    # Convert "equality of bf and cf" into the same surface as "bf equals cf".
    for match in re.finditer(r"equality\s+of\s+([a-z]{2})\s+and\s+([a-z]{2})", sentence, flags=re.IGNORECASE):
        candidates.append(f"{match.group(1).lower()} equals {match.group(2).lower()}")
    for match in re.finditer(r"\b([a-z]{2})\s+equall?ing\s+([a-z]{2})\b", sentence, flags=re.IGNORECASE):
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


def _relations_strictly_match(text_a: str, text_b: str, point_names: list[str]) -> bool:
    normalized_a = normalize_relation_surface(text_a or "").lower()
    normalized_b = normalize_relation_surface(text_b or "").lower()
    if not normalized_a or not normalized_b:
        return False
    if normalized_a == normalized_b:
        return True

    keywords_a = relation_text_keywords(normalized_a)
    keywords_b = relation_text_keywords(normalized_b)
    if not keywords_a or not keywords_b or keywords_a != keywords_b:
        return False

    signatures_a = extract_relation_signatures(normalized_a)
    signatures_b = extract_relation_signatures(normalized_b)
    for family in ["collinear", "midpoint", "equal", "parallel", "perpendicular"]:
        if family not in keywords_a:
            continue
        if family == "equal" and ({"angle", "ratio"} & keywords_a):
            continue
        if signatures_a[family] or signatures_b[family]:
            return bool(signatures_a[family] & signatures_b[family])

    segments_a = extract_relation_segment_tokens(normalized_a)
    segments_b = extract_relation_segment_tokens(normalized_b)
    if segments_a and segments_b:
        if "angle" in keywords_a or "ratio" in keywords_a:
            return segments_a == segments_b
        return segments_a == segments_b

    return relations_semantically_match(text_a, text_b, point_names)


def _sentence_mentions_aux_points(sentence: str, aux_points: list[str]) -> bool:
    lowered = str(sentence or "").lower()
    for point in aux_points:
        if not point:
            continue
        if re.search(
            rf"\b(?:point|points|line|segment|side|angle|triangle|circle|ratio)\s+[a-z]*{re.escape(point)}[a-z]*\b",
            lowered,
        ):
            return True
        if re.search(rf"\b(?:[a-z]{re.escape(point)}|{re.escape(point)}[a-z])\b", lowered):
            return True
        if re.search(rf"\b{re.escape(point)}\s*,|\b,\s*{re.escape(point)}\s*,|\b,\s*{re.escape(point)}\b", lowered):
            return True
    return False


def _extract_angle_segment_tokens(text: str) -> set[str]:
    normalized = normalize_relation_surface(text or "").lower()
    tokens: set[str] = set()
    angle_patterns = [
        r"angle\s+([a-z]{2})/([a-z]{2})",
        r"angle\s+formed\s+by\s+(?:(?:sides?|segments?|lines?)\s+)?([a-z]{2})\s+and\s+"
        r"(?:(?:sides?|segments?|lines?)\s+)?([a-z]{2})",
        r"angle\s+between\s+(?:(?:sides?|segments?|lines?)\s+)?([a-z]{2})\s+and\s+"
        r"(?:(?:sides?|segments?|lines?)\s+)?([a-z]{2})",
        r"angle\s+involving\s+(?:(?:sides?|segments?|lines?)\s+)?([a-z]{2})\s+and\s+"
        r"(?:(?:sides?|segments?|lines?)\s+)?([a-z]{2})",
    ]
    for pattern in angle_patterns:
        for match in re.finditer(pattern, normalized, flags=re.IGNORECASE):
            for token in match.groups():
                tokens.add("".join(sorted(token.lower())))
    return tokens


def _relation_mentioned_in_text_strict(text: str, relation: str, point_names: list[str]) -> bool:
    normalized_relation = normalize_relation_surface(relation or "")
    if not normalized_relation:
        return False
    for sentence in _split_into_sentences(text):
        candidates = _extract_relation_candidates(sentence, include_full_sentence=False)
        for candidate in candidates:
            if _relations_strictly_match(candidate, normalized_relation, point_names):
                return True
    return False


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
        "- For a visible_backtrace stage, name the current claim, mention at least one listed visible_support_nl item using close wording, then name the listed subgoal_claims_nl item(s).\n"
        "- For visible_backtrace stages only, keep the chain explicit: mention the stage claim and its subgoal_claims_nl with close wording before moving to the next visible stage. Do not apply this subgoal-listing rule to aux_boundary stages.\n"
        "- For each aux_boundary stage, before the auxiliary construction, name only the stage claim_nl and say the visible route is not enough.\n"
        "- For aux_boundary stages, aux_boundary_h_nl items are post-construction auxiliary relations, not pre-construction subgoals. Before the construction, refer to them only generically as 'the remaining link'.\n"
        "- Before the auxiliary construction, never list aux_boundary_h_nl relations and never mention any relation containing a newly constructed point. Do not write sentences like 'we need bf equals bg', 'boundary claim bf equals bi', or 'angle eg/ei equals angle fg/fi' before point f is constructed. Use a generic phrase such as 'the remaining link needs an auxiliary point' instead.\n"
        "- Introduce the auxiliary construction only after the visible route has reached its listed aux_boundary stage claim(s).\n"
        "- The auxiliary construction sentence should only restate aux_construction_nl. Do not add that it creates symmetry, congruence, cyclic structure, or a direct proof.\n"
        "- After introducing the auxiliary construction, group the explanation only by stage claim_nl, never by an aux_boundary_h_nl item. Use this pattern: 'For [exact stage claim_nl], the auxiliary route supplies [aux_boundary_h_nl]. The already-visible relations include [aux_boundary_non_h_nl]. These listed relations reach the boundary claim [exact stage claim_nl].'\n"
        "- After the auxiliary construction, copy at least two aux_boundary_h_nl items with close wording for each aux_boundary stage; if only one is listed, copy that one.\n"
        "- Do not say the auxiliary construction directly establishes, directly implies, proves, or ensures any aux_boundary_h_nl relation. The construction introduces the approved point(s); the auxiliary route supplies the listed aux_boundary_h_nl relations after that construction.\n"
        "- Never call aux_boundary_non_h_nl items auxiliary, new, constructed, or post-construction relations. Name them only as already-visible relations or visible support.\n"
        "- Never call an aux_boundary_h_nl item a boundary claim. The boundary claim is the stage claim_nl; aux_boundary_h_nl items are supporting relations for that boundary claim.\n"
        "- Do not invent theorem explanations such as SAS, cyclic quadrilaterals, reflection, symmetry, circle-centered arguments, or parallelograms unless that exact relation is listed in the handoff.\n"
        "- Stay text-only: do not mention any image, diagram, coordinates, or coordinate table.\n"
        "- Do not mention proof step ids, rule ids, hidden proofs, or internal schema names.\n"
        "- Do not copy formal problem tokens such as 'cong', 'eqangle', 'cyclic', 'para', or bracketed ids into the body; use the normalized natural-language relations from the handoff.\n"
        "- Avoid theorem-catalog or proof-style phrasing when a direct geometric description is enough.\n"
        "- For angle claims, prefer exact wording such as 'angle ab/ac equals angle de/eg' or 'angle formed by ab and ac equals angle formed by de and eg'; avoid vague 'angle involving' wording.\n"
        "- Before the auxiliary construction appears, do not reveal later hidden-route conclusions.\n"
        "- Keep the auxiliary construction geometrically faithful to the approved construction.\n"
        "- The body should show how each visible claim reduces to deeper visible subgoals until the visible route reaches its limit, and only then introduce the auxiliary construction.\n"
    )


def build_backtrace_writer_retry_feedback(message: str, writer_handoff: dict | None = None) -> str:
    del writer_handoff
    return (
        "Rewrite the body so it follows the staged backtrace: current claim -> visible support -> remaining subgoal(s) -> all visible boundary claims -> aux.\n"
        "Before the auxiliary construction, state only the current claim/terminal claim and visible insufficiency; do not name aux_boundary_h_nl relations yet.\n"
        "Do not list aux_boundary_h_nl relations or relations containing newly constructed points until after the auxiliary construction appears. For example, do not write 'bf equals bg', 'bf equals bi', or 'angle eg/ei equals angle fg/fi' before constructing point f.\n"
        "For visible_backtrace stages only, use close wording from the handoff: explicitly name the current claim and its subgoal_claims_nl items before moving to the next visible stage. Do not treat aux_boundary_h_nl items as pre-aux subgoals.\n"
        "Use close wording from visible_support_nl, subgoal_claims_nl, aux_boundary_h_nl, and aux_boundary_non_h_nl instead of only paraphrasing them.\n"
        "After the aux construction, group only by exact stage claim_nl, not by aux_boundary_h_nl items: auxiliary route supplies aux_boundary_h_nl; already-visible relations include aux_boundary_non_h_nl; these listed relations reach stage claim_nl.\n"
        "Do not say the construction directly establishes, implies, proves, or ensures any aux_boundary_h_nl relation; say the auxiliary route supplies those relations after the construction.\n"
        "Do not call aux_boundary_h_nl items boundary claims, and do not invent SAS/cyclic/reflection/symmetry/parallelogram derivations unless that exact relation appears in the handoff.\n"
        f"Validator feedback: {message}\n"
        "Keep it text-only, do not leak proof metadata, and keep the auxiliary construction faithful."
    )


def _first_sentence_idx_for_relation_from(
    sentences: list[str],
    relation: str,
    point_pool: list[str],
    start_idx: int = 0,
) -> int | None:
    if not relation:
        return None
    for idx in range(max(start_idx, 0), len(sentences)):
        sentence = sentences[idx]
        if _relation_mentioned_in_text(sentence, relation, point_pool):
            return idx
    return None


def _first_sentence_idx_for_stage_claim_from(
    sentences: list[str],
    relation: str,
    point_pool: list[str],
    start_idx: int = 0,
) -> int | None:
    if not relation:
        return None
    normalized_relation = normalize_relation_surface(relation).lower()
    relation_segments = extract_relation_segment_tokens(normalized_relation)
    relation_keywords = relation_text_keywords(normalized_relation)
    for idx in range(max(start_idx, 0), len(sentences)):
        sentence = sentences[idx]
        normalized_sentence = normalize_relation_surface(sentence).lower()
        if normalized_relation and normalized_relation in normalized_sentence:
            return idx
        for candidate in _extract_relation_candidates(sentence):
            normalized_candidate = normalize_relation_surface(candidate).lower()
            if normalized_candidate == normalized_relation:
                return idx
            if normalized_relation in normalized_candidate or normalized_candidate in normalized_relation:
                return idx
            candidate_segments = extract_relation_segment_tokens(normalized_candidate)
            candidate_keywords = relation_text_keywords(normalized_candidate)
            if "ratio" in relation_keywords:
                if "ratio" not in candidate_keywords:
                    continue
                if relation_segments and candidate_segments and relation_segments == candidate_segments:
                    return idx
                continue
            if (
                "angle" in relation_keywords
                and "angle" in candidate_keywords
                and _extract_angle_segment_tokens(normalized_relation)
                and _extract_angle_segment_tokens(normalized_candidate) == _extract_angle_segment_tokens(normalized_relation)
            ):
                return idx
            if _relations_strictly_match(candidate, relation, point_pool):
                return idx
    return None


def _first_sentence_idx_for_relation(sentences: list[str], relation: str, point_pool: list[str]) -> int | None:
    return _first_sentence_idx_for_relation_from(sentences, relation, point_pool, start_idx=0)


def _visible_stage_expansion_idx_before_aux(
    sentences: list[str],
    *,
    claim_nl: str,
    visible_support_nl: list[str],
    subgoal_claims_nl: list[str],
    point_pool: list[str],
    aux_idx: int | None,
) -> int | None:
    if aux_idx is None or not claim_nl:
        return None
    claim_idx = _first_sentence_idx_for_stage_claim_from(sentences, claim_nl, point_pool, 0)
    if claim_idx is None or claim_idx >= aux_idx:
        return None
    cursor = claim_idx
    support_idx = _first_sentence_idx_for_any_relation_from(
        sentences[:aux_idx],
        visible_support_nl,
        point_pool,
        cursor,
    )
    if visible_support_nl and support_idx is None:
        return None
    if support_idx is not None:
        cursor = max(cursor, support_idx)
    for subgoal_nl in subgoal_claims_nl:
        subgoal_idx = _first_sentence_idx_for_stage_claim_from(
            sentences[:aux_idx],
            subgoal_nl,
            point_pool,
            cursor,
        )
        if subgoal_idx is None:
            return None
        cursor = max(cursor, subgoal_idx)
    return claim_idx


def _first_sentence_idx_for_any_relation_from(
    sentences: list[str],
    relations: list[str],
    point_pool: list[str],
    start_idx: int = 0,
) -> int | None:
    relation_list = [relation for relation in relations if relation]
    if not relation_list:
        return None
    for idx in range(max(start_idx, 0), len(sentences)):
        sentence = sentences[idx]
        if any(_relation_mentioned_in_text(sentence, relation, point_pool) for relation in relation_list):
            return idx
    return None


def _first_sentence_idx_for_any_relation(sentences: list[str], relations: list[str], point_pool: list[str]) -> int | None:
    return _first_sentence_idx_for_any_relation_from(sentences, relations, point_pool, start_idx=0)


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
    if _has_hidden_meta_language(body):
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
            for sentence_points in [set(point.lower() for point in _POINT_RE.findall(sentence.lower()))]
            if _AUX_CONSTRUCTION_RE.search(sentence)
            or ("construct" in sentence.lower() and any(point in sentence_points for point in aux_points))
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

    stage_cursor = (goal_idx - 1) if goal_idx is not None else -1
    first_terminal_claim_idx = None
    saw_terminal_boundary = False
    aux_has_been_introduced_for_terminal = False
    for stage_index, stage in enumerate(backtrace_stages):
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
        aux_boundary_h_nl = [
            str(item).strip()
            for item in (stage.get("aux_boundary_h_nl") or [])
            if isinstance(item, str) and item.strip()
        ]
        aux_boundary_non_h_nl = [
            str(item).strip()
            for item in (stage.get("aux_boundary_non_h_nl") or [])
            if isinstance(item, str) and item.strip()
        ]
        stage_type = str(stage.get("stage_type") or "visible_backtrace").strip()
        is_terminal = stage_type == "aux_boundary"

        claim_search_start = max(stage_cursor + 1, 0)
        if stage_index == 0 and goal_idx is not None:
            claim_search_start = max(goal_idx, 0)
        claim_matched_as_pre_boundary_sibling = False
        previous_stage = backtrace_stages[stage_index - 1] if stage_index > 0 else None
        previous_is_terminal = (
            isinstance(previous_stage, dict)
            and str(previous_stage.get("stage_type") or "visible_backtrace").strip() == "aux_boundary"
        )
        pre_aux_expansion_idx = None
        if stage_index > 0 and previous_is_terminal and not is_terminal:
            pre_aux_expansion_idx = _visible_stage_expansion_idx_before_aux(
                sentences,
                claim_nl=claim_nl,
                visible_support_nl=visible_support_nl,
                subgoal_claims_nl=subgoal_claims_nl,
                point_pool=point_pool,
                aux_idx=aux_idx,
            )
        claim_idx = _first_sentence_idx_for_stage_claim_from(
            sentences,
            claim_nl,
            point_pool,
            claim_search_start,
        )
        if pre_aux_expansion_idx is not None:
            claim_idx = pre_aux_expansion_idx
            claim_matched_as_pre_boundary_sibling = True
        if claim_idx is None and stage_index > 0 and stage_cursor >= 0:
            fallback_claim_idx = _first_sentence_idx_for_stage_claim_from(
                sentences,
                claim_nl,
                point_pool,
                stage_cursor,
            )
            if fallback_claim_idx == stage_cursor:
                claim_idx = fallback_claim_idx
        if claim_idx is None and stage_index > 0 and not is_terminal:
            sibling_claim_idx = _first_sentence_idx_for_stage_claim_from(
                sentences,
                claim_nl,
                point_pool,
                0,
            )
            if previous_is_terminal and sibling_claim_idx is not None and aux_idx is not None and sibling_claim_idx < aux_idx:
                claim_idx = sibling_claim_idx
                claim_matched_as_pre_boundary_sibling = True
        if claim_nl and claim_idx is None:
            issues.append("missing_stage_reference")
            continue
        if claim_idx is not None and claim_idx < stage_cursor and not claim_matched_as_pre_boundary_sibling:
            issues.append("narrative_order_violation")
        local_cursor = claim_idx if claim_idx is not None else stage_cursor

        if not is_terminal:
            support_idx = _first_sentence_idx_for_any_relation_from(
                sentences,
                visible_support_nl,
                point_pool,
                local_cursor,
            )
            if (
                claim_idx is not None
                and support_idx is not None
                and support_idx < claim_idx
                and not claim_matched_as_pre_boundary_sibling
            ):
                issues.append("narrative_order_violation")
            if support_idx is not None:
                local_cursor = max(local_cursor, support_idx)

        if is_terminal:
            if aux_idx is not None and claim_idx is not None and claim_idx > aux_idx:
                pre_aux_claim_idx = _first_sentence_idx_for_stage_claim_from(
                    sentences[:aux_idx],
                    claim_nl,
                    point_pool,
                    0,
                )
                if pre_aux_claim_idx is not None:
                    claim_idx = pre_aux_claim_idx
                    local_cursor = claim_idx
            if first_terminal_claim_idx is None:
                first_terminal_claim_idx = claim_idx
            allow_reused_aux_boundary = aux_has_been_introduced_for_terminal and aux_idx is not None
            if claim_idx is not None and aux_idx is not None and aux_idx < claim_idx and not allow_reused_aux_boundary:
                issues.append("narrative_order_violation")
            window_start = claim_idx if claim_idx is not None else 0
            next_stage_claim_idx = None
            if stage_index + 1 < len(backtrace_stages):
                next_claim_nl = str(backtrace_stages[stage_index + 1].get("claim_nl") or "").strip()
                next_stage_claim_idx = _first_sentence_idx_for_stage_claim_from(
                    sentences,
                    next_claim_nl,
                    point_pool,
                    window_start + 1,
                )
            window_end = aux_idx + 1 if aux_idx is not None else len(sentences)
            if next_stage_claim_idx is not None and next_stage_claim_idx > window_start:
                window_end = min(window_end, next_stage_claim_idx)
            insufficiency_window = " ".join(sentences[window_start:window_end])
            stage_insufficiency_idx = next(
                (
                    idx
                    for idx in range(window_start, window_end)
                    if _INSUFFICIENCY_RE.search(sentences[idx])
                ),
                None,
            )
            has_boundary_landing = aux_idx is not None and (
                _first_sentence_idx_for_any_relation_from(sentences, aux_boundary_h_nl, point_pool, aux_idx)
                is not None
            )
            if not _INSUFFICIENCY_RE.search(insufficiency_window) and not has_boundary_landing:
                issues.append("support_insufficiency_missing")
            else:
                saw_terminal_boundary = True
            if stage_insufficiency_idx is not None:
                local_cursor = max(local_cursor, stage_insufficiency_idx)
            elif insufficiency_idx is not None and insufficiency_idx >= window_start:
                local_cursor = max(local_cursor, insufficiency_idx)
            aux_h_idx = None
            if aux_idx is not None and aux_boundary_h_nl:
                aux_h_idx = _first_sentence_idx_for_any_relation_from(
                    sentences,
                    aux_boundary_h_nl,
                    point_pool,
                    aux_idx,
                )
                if aux_h_idx is None:
                    issues.append("missing_aux_boundary_h_reference")
            non_h_idx = _first_sentence_idx_for_any_relation_from(
                sentences,
                aux_boundary_non_h_nl,
                point_pool,
                window_start,
            )
            if aux_idx is not None and claim_idx is not None and claim_idx <= aux_idx:
                aux_has_been_introduced_for_terminal = True
            stage_cursor = max(stage_cursor, local_cursor)
            continue

        subgoal_match_indices: dict[str, int] = {}
        subgoal_search_start = local_cursor
        for subgoal_nl in subgoal_claims_nl:
            subgoal_idx = _first_sentence_idx_for_stage_claim_from(
                sentences,
                subgoal_nl,
                point_pool,
                subgoal_search_start,
            )
            if subgoal_idx is None:
                issues.append("missing_stage_subgoal_reference")
                continue
            if claim_idx is not None and subgoal_idx < claim_idx:
                issues.append("narrative_order_violation")
            subgoal_match_indices[normalize_relation_surface(subgoal_nl)] = subgoal_idx
        next_stage_cursor = local_cursor
        if stage_index + 1 < len(backtrace_stages):
            next_claim_nl = normalize_relation_surface(
                str(backtrace_stages[stage_index + 1].get("claim_nl") or "").strip()
            )
            next_stage_cursor = subgoal_match_indices.get(next_claim_nl, local_cursor)
        stage_cursor = max(stage_cursor, next_stage_cursor)

    if first_terminal_claim_idx is not None and aux_idx is not None and aux_idx < first_terminal_claim_idx:
        issues.append("narrative_order_violation")
    if first_terminal_claim_idx is not None and aux_idx is not None and not saw_terminal_boundary:
        issues.append("missing_terminal_boundary")

    hidden_relations = [
        str(item).strip()
        for item in (slots.get("H_relations_nl") or [])
        if isinstance(item, str) and item.strip()
    ]
    hidden_relations = [normalize_relation_surface(relation) for relation in hidden_relations if relation]
    for relation in hidden_relations:
        relation_aux_points = sorted(extract_point_mentions(relation, aux_points))
        if not relation_aux_points:
            continue
        if aux_construction_nl and relations_semantically_match(relation, aux_construction_nl, point_pool):
            continue
        for sentence in sentences[: aux_idx or 0]:
            if not _sentence_mentions_aux_points(sentence, relation_aux_points):
                continue
            if _relation_mentioned_in_text_strict(sentence, relation, point_pool):
                issues.append("early_hidden_relation")
                break
        if issues and issues[-1] == "early_hidden_relation":
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
