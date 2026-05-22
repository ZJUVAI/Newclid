#!/usr/bin/env python3
"""
Audit and relation-matching helpers for CoT SFT generation.

This module keeps source-audit, generation-audit, and sentence-level relation
matching logic separate from the main generation pipeline so maintenance work on
audits does not keep inflating the orchestration script.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable

try:
    from .geometry_text import (
        PROBLEM_BODY_RE,
        build_aux_direct_consequences,
        extract_relation_signatures,
        extract_aux_new_points,
        extract_aux_point_scope,
        extract_point_mentions,
        extract_visible_point_names,
        infer_relation_type_from_text,
        parse_aux_clauses,
        parse_goal_expression,
        relation_text_keywords,
        relations_semantically_match,
        split_formal_relation_chain,
        summarize_aux_clause,
    )
except ImportError:  # pragma: no cover - script execution path
    from geometry_text import (
        PROBLEM_BODY_RE,
        build_aux_direct_consequences,
        extract_relation_signatures,
        extract_aux_new_points,
        extract_aux_point_scope,
        extract_point_mentions,
        extract_visible_point_names,
        infer_relation_type_from_text,
        parse_aux_clauses,
        parse_goal_expression,
        relation_text_keywords,
        relations_semantically_match,
        split_formal_relation_chain,
        summarize_aux_clause,
    )


def get_point_coords(record: Dict[str, Any]) -> Dict[str, tuple[int, int]]:
    coords = record.get("grid_coord") or record.get("point_coords_grid") or {}
    normalized: Dict[str, tuple[int, int]] = {}
    for point_name, pair in coords.items():
        if isinstance(pair, (list, tuple)) and len(pair) == 2:
            normalized[str(point_name)] = (int(pair[0]), int(pair[1]))
    return normalized


def extract_visible_formal_facts(record: Dict[str, Any]) -> list[Dict[str, Any]]:
    formal_problem = (
        record.get("llm_input_renamed")
        or record.get("public_problem")
        or record.get("input")
        or ""
    ).strip()
    body_match = PROBLEM_BODY_RE.search(formal_problem)
    body = body_match.group(1).strip() if body_match else formal_problem
    if "?" in body:
        body = body.split("?", 1)[0].strip()

    facts = []
    for clause in [part.strip() for part in body.split(";") if part.strip()]:
        if ":" not in clause:
            continue
        _, relation_text = clause.split(":", 1)
        for fact in split_formal_relation_chain(relation_text):
            tokens = fact.split()
            if not tokens:
                continue
            facts.append(
                {
                    "raw": fact.strip(),
                    "predicate": tokens[0].lower(),
                    "args": [token.lower() for token in tokens[1:]],
                    "summary": summarize_aux_clause(fact),
                }
            )
    return facts


def build_visible_premise_summaries(record: Dict[str, Any], max_items: int = 12) -> list[str]:
    summaries = []
    seen = set()
    for fact in extract_visible_formal_facts(record):
        summary = fact.get("summary")
        if not summary:
            continue
        normalized = summary.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        summaries.append(summary)
        if len(summaries) >= max_items:
            break
    return summaries


def _canonical_line_key(p1: str, p2: str) -> tuple[str, str]:
    a, b = sorted([p1.lower(), p2.lower()])
    return (a, b)


def visible_parallelogram_supported(record: Dict[str, Any], vertex_word: str) -> bool:
    if not isinstance(vertex_word, str) or len(vertex_word) != 4:
        return False
    a, b, c, d = [char.lower() for char in vertex_word]
    visible_facts = extract_visible_formal_facts(record)
    parallel_pairs = set()
    for fact in visible_facts:
        if fact.get("predicate") != "para":
            continue
        args = fact.get("args", [])
        if len(args) < 4:
            continue
        line_1 = _canonical_line_key(args[0], args[1])
        line_2 = _canonical_line_key(args[2], args[3])
        parallel_pairs.add(frozenset([line_1, line_2]))

    needed_pairs = [
        frozenset([
            _canonical_line_key(a, b),
            _canonical_line_key(c, d),
        ]),
        frozenset([
            _canonical_line_key(a, d),
            _canonical_line_key(b, c),
        ]),
    ]
    return all(pair in parallel_pairs for pair in needed_pairs)


def iter_supported_parallelogram_mentions(record: Dict[str, Any], text: str):
    if not isinstance(text, str) or not text:
        return
    patterns = [
        r"\bparallelogram\s+([a-z]{4})\b",
        r"\b([a-z]{4})\s+forms?\s+(?:an?\s+)?parallelogram\b",
        r"\b([a-z]{4})\s+is\s+(?:an?\s+)?parallelogram\b",
        r"\bquadrilateral\s+([a-z]{4})\s+is\s+(?:an?\s+)?parallelogram\b",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            vertex_word = match.group(1).lower()
            if visible_parallelogram_supported(record, vertex_word):
                yield match.span()


def aux_constructs_parallelogram(aux_part: str) -> bool:
    if not isinstance(aux_part, str) or not aux_part.strip():
        return False
    new_points = {point.lower() for point in extract_aux_new_points(aux_part)}
    if not new_points:
        return False
    para_counts = {point: 0 for point in new_points}
    old_point_unions = {point: set() for point in new_points}
    for clause in parse_aux_clauses(aux_part):
        for fact in split_formal_relation_chain(clause["body"]):
            tokens = fact.split()
            if not tokens or tokens[0].lower() != "para":
                continue
            args = [token.lower() for token in tokens[1:]]
            if len(args) < 4:
                continue
            arg_set = set(args[:4])
            touched_new_points = arg_set & new_points
            if not touched_new_points:
                continue
            for point in touched_new_points:
                para_counts[point] += 1
                old_point_unions[point].update(arg_set - {point})
    return any(para_counts[point] >= 2 and len(old_point_unions[point]) >= 3 for point in new_points)


def iter_aux_constructed_parallelogram_mentions(text: str, aux_part: str):
    if not isinstance(text, str) or not text or not aux_constructs_parallelogram(aux_part):
        return
    patterns = [
        r"\bcreate(?:s|d|ing)?\s+(?:an?\s+)?parallelogram\b",
        r"\bform(?:s|ed|ing)?\s+(?:an?\s+)?parallelogram\b",
        r"\bcomplete(?:s|d|ing)?\s+(?:an?\s+)?parallelogram\b",
        r"\bmake(?:s|d|ing)?\s+(?:an?\s+)?parallelogram\b",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            yield match.span()


def extract_midpoint_relation_signature(text: str):
    if not isinstance(text, str):
        return None
    lowered = text.lower().strip()
    midpoint_patterns = [
        r"(?:point\s+)?([a-z])\s+looks\s+like\s+the\s+midpoint\s+of\s+(?:segment\s+)?([a-z])([a-z])\b",
        r"(?:point\s+)?([a-z])\s+is\s+the\s+midpoint\s+of\s+(?:segment\s+)?([a-z])([a-z])\b",
        r"(?:point\s+)?([a-z])\s+appears\s+to\s+be\s+the\s+midpoint\s+of\s+(?:segment\s+)?([a-z])([a-z])\b",
    ]
    for pattern in midpoint_patterns:
        match = re.search(pattern, lowered)
        if not match:
            continue
        midpoint = match.group(1).lower()
        endpoint_a = match.group(2).lower()
        endpoint_b = match.group(3).lower()
        return midpoint, tuple(sorted([endpoint_a, endpoint_b]))
    return None


def coordinate_hints_support_parallelogram(plan: Dict[str, Any]) -> bool:
    if not isinstance(plan, dict):
        return False
    midpoint_map = {}
    for relation in plan.get("coordinate_relations", []):
        signature = extract_midpoint_relation_signature(relation)
        if not signature:
            continue
        midpoint, segment = signature
        midpoint_map.setdefault(midpoint, set()).add(segment)
    for segments in midpoint_map.values():
        if len(segments) < 2:
            continue
        segment_points = set()
        for segment in segments:
            segment_points.update(segment)
        if len(segment_points) >= 4:
            return True
    return False


def iter_coordinate_supported_parallelogram_mentions(text: str, plan: Dict[str, Any]):
    if not isinstance(text, str) or not text or not coordinate_hints_support_parallelogram(plan):
        return
    patterns = [
        r"\bparallelogram\s+structure\b",
        r"\bsuggests?\s+(?:a|the)\s+parallelogram\b",
        r"\bsuggests?\s+(?:a|the)\s+parallelogram\s+structure\b",
        r"\bparallelogram-like\s+structure\b",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            yield match.span()


def _coord_line_metrics(point_coords: Dict[str, tuple[int, int]], p1: str, p2: str):
    x1, y1 = point_coords[p1]
    x2, y2 = point_coords[p2]
    dx = x2 - x1
    dy = y2 - y1
    length_sq = dx * dx + dy * dy
    return x1, y1, x2, y2, dx, dy, length_sq


def _visible_fact_coordinate_conflict(
    fact: Dict[str, Any],
    point_coords: Dict[str, tuple[int, int]],
) -> str | None:
    predicate = fact.get("predicate", "")
    args = fact.get("args", [])
    summary = fact.get("summary") or fact.get("raw") or ""
    if predicate == "cong" and len(args) >= 4 and all(point in point_coords for point in args[:4]):
        _, _, _, _, _, _, len1 = _coord_line_metrics(point_coords, args[0], args[1])
        _, _, _, _, _, _, len2 = _coord_line_metrics(point_coords, args[2], args[3])
        if min(len1, len2) == 0:
            return None
        rel_gap = abs(len1 - len2) / max(len1, len2)
        if rel_gap > 0.18:
            return f"visible_premise_coordinate_conflict:{summary}"
    if predicate == "perp" and len(args) >= 4 and all(point in point_coords for point in args[:4]):
        _, _, _, _, dx1, dy1, len1 = _coord_line_metrics(point_coords, args[0], args[1])
        _, _, _, _, dx2, dy2, len2 = _coord_line_metrics(point_coords, args[2], args[3])
        if min(len1, len2) == 0:
            return None
        perp_score = abs(dx1 * dx2 + dy1 * dy2) / ((len1 * len2) ** 0.5)
        if perp_score > 0.18:
            return f"visible_premise_coordinate_conflict:{summary}"
    if predicate == "para" and len(args) >= 4 and all(point in point_coords for point in args[:4]):
        _, _, _, _, dx1, dy1, len1 = _coord_line_metrics(point_coords, args[0], args[1])
        _, _, _, _, dx2, dy2, len2 = _coord_line_metrics(point_coords, args[2], args[3])
        if min(len1, len2) == 0:
            return None
        parallel_score = abs(dx1 * dy2 - dy1 * dx2) / ((len1 * len2) ** 0.5)
        if parallel_score > 0.14:
            return f"visible_premise_coordinate_conflict:{summary}"
    if predicate == "coll" and len(args) >= 3 and all(point in point_coords for point in args[:3]):
        x1, y1 = point_coords[args[0]]
        x2, y2 = point_coords[args[1]]
        x3, y3 = point_coords[args[2]]
        len12 = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        len23 = ((x3 - x2) ** 2 + (y3 - y2) ** 2) ** 0.5
        len13 = ((x3 - x1) ** 2 + (y3 - y1) ** 2) ** 0.5
        longest_side = max(len12, len23, len13, 1.0)
        area_score = abs((x2 - x1) * (y3 - y1) - (y2 - y1) * (x3 - x1)) / longest_side
        if area_score > 3.0:
            return f"visible_premise_coordinate_conflict:{summary}"
    if predicate == "midp" and len(args) >= 3 and all(point in point_coords for point in args[:3]):
        xm, ym = point_coords[args[0]]
        x1, y1 = point_coords[args[1]]
        x2, y2 = point_coords[args[2]]
        seg_len = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        if seg_len == 0:
            return None
        area_score = abs((x2 - x1) * (ym - y1) - (y2 - y1) * (xm - x1)) / seg_len
        midpoint_gap = ((xm - (x1 + x2) / 2) ** 2 + (ym - (y1 + y2) / 2) ** 2) ** 0.5
        if area_score > 3.0 or midpoint_gap > 4.0:
            return f"visible_premise_coordinate_conflict:{summary}"
    return None


def coordinate_relation_matches_candidate(relation_text: str, candidate: Dict[str, Any]) -> bool:
    relation_type = infer_relation_type_from_text(relation_text)
    if not relation_type:
        lowered_relation = (relation_text or "").lower()
        if (
            candidate.get("relation_type") == "equal_length"
            and "angle" not in lowered_relation
            and "ratio" not in lowered_relation
            and re.search(r"\b[a-z]{2}\s+equals\s+[a-z]{2}\b", lowered_relation)
        ):
            relation_type = "equal_length"
    if not relation_type:
        return False

    candidate_type = candidate.get("relation_type", "")
    candidate_points = {str(point).lower() for point in candidate.get("points", [])}
    relation_points = extract_point_mentions(relation_text, sorted(candidate_points))

    equivalent_types = {
        ("perpendicular", "right_triangle"),
        ("equal_length", "isosceles"),
        ("equal_length", "equilateral"),
    }
    if relation_type == candidate_type:
        return candidate_points.issubset(relation_points)
    if (relation_type, candidate_type) in equivalent_types:
        return relation_points.issubset(candidate_points) and len(relation_points) >= 2
    return False


def validate_aux_step_scope(step_text: str, aux_part: str, visible_points: Iterable[str]):
    allowed_points = {point.lower() for point in extract_aux_point_scope(aux_part)}
    candidate_points = sorted(set(visible_points) | allowed_points)
    step_points = extract_point_mentions(step_text, candidate_points)
    if not (step_points & allowed_points):
        return False, "the direct auxiliary relation must mention the auxiliary-point relation explicitly"
    extra_points = step_points - allowed_points
    if extra_points:
        return False, (
            "the direct auxiliary relation should stay on the direct aux consequence and must not "
            f"introduce extra old-figure points yet: {sorted(extra_points)}"
        )
    return True, None


def _normalize_overlap_words(text: str):
    lowered = re.sub(r"<[^>]+>", " ", text or "")
    lowered = re.sub(r"[^a-z0-9/ ]+", " ", lowered.lower())
    return [token for token in lowered.split() if token]


def has_long_ngram_overlap(source_text: str, target_text: str, ngram_size: int = 7) -> bool:
    source_words = _normalize_overlap_words(source_text)
    target_words = _normalize_overlap_words(target_text)
    if len(source_words) < ngram_size or len(target_words) < ngram_size:
        return False
    source_ngrams = {
        tuple(source_words[idx:idx + ngram_size])
        for idx in range(len(source_words) - ngram_size + 1)
    }
    target_ngrams = {
        tuple(target_words[idx:idx + ngram_size])
        for idx in range(len(target_words) - ngram_size + 1)
    }
    return bool(source_ngrams & target_ngrams)


def flatten_bridge_relations(plan: Dict[str, Any]) -> list[str]:
    if not isinstance(plan, dict):
        return []
    if isinstance(plan.get("bridge_steps"), list):
        relations = []
        for step in plan["bridge_steps"]:
            if isinstance(step, dict):
                relation = step.get("relation")
                if isinstance(relation, str) and relation.strip():
                    relations.append(relation.strip())
        if relations:
            return relations
    relations = plan.get("bridge_relations")
    if isinstance(relations, list):
        return [relation.strip() for relation in relations if isinstance(relation, str) and relation.strip()]
    return []


def split_into_sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text or "") if part.strip()]


def _normalize_relation_surface_for_mention_match(text: str) -> str:
    lowered = (text or "").lower()
    lowered = re.sub(r"\bequaling\b", "equals", lowered)
    lowered = re.sub(r"\bratio of ([a-z]{2}) to ([a-z]{2})\b", r"ratio \1 to \2", lowered)
    lowered = re.sub(
        r"\b(?:construct\s+)?point\s+([a-z])\s+as\s+the midpoint of\s+([a-z]{2})\b",
        r"\1 is the midpoint of \2",
        lowered,
    )
    lowered = re.sub(
        r"\b([a-z])\s*,\s*([a-z])\s*,\s*and\s*([a-z])\s+are collinear\b",
        r"\1, \2, \3 are collinear",
        lowered,
    )
    lowered = re.sub(
        r"\bthe\s+(ratio|angle|line|segment|segments|triangle|triangles|point|points)\b",
        r"\1",
        lowered,
    )
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered.strip()


def relation_mentioned_in_text(text: str, relation: str) -> bool:
    lowered_text = _normalize_relation_surface_for_mention_match(text)
    lowered_relation = _normalize_relation_surface_for_mention_match(relation)
    if not lowered_relation:
        return False
    if lowered_relation in lowered_text:
        return True
    if {"parallel", "perpendicular", "collinear", "midpoint", "equal"} & relation_text_keywords(relation):
        return False
    return has_long_ngram_overlap(lowered_relation, lowered_text, ngram_size=4)


def extract_relation_point_names(text: str, point_names=None) -> list[str]:
    if point_names:
        explicit_points = extract_point_mentions(text, point_names)
        if explicit_points:
            return sorted(explicit_points)
    lowered = (text or "").lower()
    stopwords = {
        "a",
        "i",
        "is",
        "to",
        "of",
        "on",
        "in",
        "by",
        "at",
        "as",
        "are",
        "and",
        "the",
        "line",
        "ratio",
    }
    point_names = set(re.findall(r"\b([a-z])\b", lowered))
    for token in re.findall(r"\b[a-z]{2,4}\b", lowered):
        if token in stopwords:
            continue
        if token in {"line", "ratio"}:
            continue
        if len(token) <= 4:
            point_names.update(char for char in token if char.isalpha())
    return sorted(point_names)


def relation_semantically_mentioned_in_sentence(sentence: str, relation: str, point_names=None) -> bool:
    lowered_sentence = (sentence or "").lower()
    relation_points = extract_relation_point_names(relation, point_names=point_names)
    if not relation_points or not all(point in lowered_sentence for point in relation_points):
        return False
    keywords = relation_text_keywords(relation)
    sentence_signatures = extract_relation_signatures(sentence)
    relation_signatures = extract_relation_signatures(relation)
    structured_signature_required = False
    for family in ["parallel", "perpendicular", "collinear", "midpoint", "equal"]:
        if family not in keywords:
            continue
        if relation_signatures[family]:
            structured_signature_required = True
        if relation_signatures[family] and sentence_signatures[family] & relation_signatures[family]:
            return True
    if structured_signature_required:
        return False
    if "parallel" in keywords and "parallel" in lowered_sentence:
        return True
    if "perpendicular" in keywords and ("perpendicular" in lowered_sentence or "right angle" in lowered_sentence):
        return True
    if "collinear" in keywords and any(
        phrase in lowered_sentence for phrase in ["collinear", "same line", "one line", "on one line", "on the same line"]
    ):
        return True
    if "circle" in keywords and any(
        phrase in lowered_sentence for phrase in ["cyclic", "concyclic", "circle", "circumcircle"]
    ):
        return True
    if "midpoint" in keywords and ("midpoint" in lowered_sentence or "bisect" in lowered_sentence or "bisects" in lowered_sentence):
        return True
    if "similar" in keywords and "similar" in lowered_sentence:
        return True
    if "ratio" in keywords and "ratio" in lowered_sentence:
        return True
    if "angle" in keywords and "angle" in lowered_sentence:
        return True
    if "equal" in keywords and any(
        phrase in lowered_sentence for phrase in [" equal", " equals", "congruent", "same length", "same distance", "equidistant"]
    ):
        return True
    return False


def count_relation_mentions(text: str, relations: Iterable[str], point_names=None) -> int:
    mentions = 0
    for relation in relations:
        if relation_mentioned_in_text(text, relation):
            mentions += 1
            continue
        if relation_semantically_mentioned_in_sentence(text, relation, point_names=point_names):
            mentions += 1
            continue
        relation_keywords = relation_text_keywords(relation)
        if {"parallel", "perpendicular", "collinear", "midpoint", "equal"} & relation_keywords:
            continue
        local_points = extract_relation_point_names(relation, point_names=point_names)
        if local_points and relations_semantically_match(text, relation, local_points):
            mentions += 1
    return mentions


def _support_requires_distinct_grounding_phrase(
    support: str,
    target_relation: str,
    point_names=None,
) -> bool:
    if not isinstance(support, str) or not support.strip():
        return False
    if not isinstance(target_relation, str) or not target_relation.strip():
        return False
    local_points = point_names or extract_relation_point_names(support)
    if not local_points:
        return False
    if not relations_semantically_match(support, target_relation, local_points):
        return False
    lowered_support = support.lower()
    return any(
        marker in lowered_support
        for marker in [
            "look",
            "looks",
            "appear",
            "appears",
            "seem",
            "seems",
            "nearly",
            "split",
            "splits",
            "evenly",
            "divides",
            "aligned",
            "same line",
            "one line",
            "line through",
        ]
    )


def _sentence_has_distinct_support_grounding_phrase(sentence: str, support: str) -> bool:
    lowered_sentence = (sentence or "").lower()
    support_keywords = relation_text_keywords(support)
    grounding_phrases = []
    if "collinear" in support_keywords:
        grounding_phrases.extend([
            "nearly collinear",
            "same line",
            "one line",
            "line through",
            "aligned",
        ])
    if "midpoint" in support_keywords:
        grounding_phrases.extend([
            "looks like the midpoint",
            "appears to be the midpoint",
            "split",
            "splits",
            "evenly",
            "equal parts",
            "divides",
        ])
    if "parallel" in support_keywords:
        grounding_phrases.extend(["looks parallel", "appear parallel", "seem parallel"])
    if "perpendicular" in support_keywords:
        grounding_phrases.extend(["looks perpendicular", "appear perpendicular", "seem perpendicular"])
    if "equal" in support_keywords:
        grounding_phrases.extend(["equal in length", "same length", "looks equal", "appear equal"])
    if any(phrase in lowered_sentence for phrase in grounding_phrases):
        return True
    return any(
        marker in lowered_sentence
        for marker in [
            "look",
            "looks",
            "appear",
            "appears",
            "seem",
            "seems",
            "nearly",
            "split",
            "splits",
            "evenly",
            "divides",
            "aligned",
            "same line",
            "one line",
            "line through",
        ]
    )


def support_relation_grounded_in_sentence(
    sentence: str,
    support: str,
    point_names=None,
    target_relation: str = "",
) -> bool:
    if not isinstance(support, str) or not support.strip():
        return False
    mentioned = False
    if relation_mentioned_in_text(sentence, support):
        mentioned = True
    elif relation_semantically_mentioned_in_sentence(sentence, support, point_names=point_names):
        mentioned = True
    else:
        keywords = relation_text_keywords(support)
        if not {"parallel", "perpendicular", "collinear", "midpoint", "equal"} & keywords:
            local_points = extract_relation_point_names(support, point_names=point_names)
            if local_points and relations_semantically_match(sentence, support, local_points):
                mentioned = True
    if not mentioned:
        return False
    if _support_requires_distinct_grounding_phrase(support, target_relation, point_names=point_names):
        return _sentence_has_distinct_support_grounding_phrase(sentence, support)
    return True


def count_support_relation_mentions(
    sentence: str,
    relations: Iterable[str],
    point_names=None,
    target_relation: str = "",
) -> int:
    mentions = 0
    for relation in relations:
        if support_relation_grounded_in_sentence(
            sentence,
            relation,
            point_names=point_names,
            target_relation=target_relation,
        ):
            mentions += 1
    return mentions


def relation_only_appears_in_preparation_clause(sentence: str, relation: str, point_names=None) -> bool:
    lowered_sentence = (sentence or "").lower()
    local_points = point_names or extract_relation_point_names(relation)
    preparation_markers = [
        "which prepares",
        "this prepares",
        "which is required to prove",
        "required to prove",
        "to prove",
    ]
    for marker in preparation_markers:
        marker_idx = lowered_sentence.find(marker)
        if marker_idx < 0:
            continue
        prefix = sentence[:marker_idx]
        suffix = sentence[marker_idx:]
        if not relation_mentioned_in_text(suffix, relation):
            if not (local_points and relations_semantically_match(suffix, relation, local_points)):
                continue
        if relation_mentioned_in_text(prefix, relation) and relation_has_sufficient_point_coverage(prefix, relation, point_names=local_points):
            return False
        if (
            local_points
            and relations_semantically_match(prefix, relation, local_points)
            and relation_has_sufficient_point_coverage(prefix, relation, point_names=local_points)
        ):
            return False
        return True
    return False


def relation_has_sufficient_point_coverage(sentence: str, relation: str, point_names=None) -> bool:
    local_points = point_names or extract_relation_point_names(relation)
    if not local_points:
        return False
    mentioned_points = extract_point_mentions(sentence, local_points)
    keywords = relation_text_keywords(relation)
    if {"collinear", "midpoint", "circle"} & keywords:
        return len(mentioned_points) >= 3
    if {"parallel", "perpendicular", "angle", "ratio", "similar"} & keywords:
        return len(mentioned_points) >= 4
    if "equal" in keywords:
        return len(mentioned_points) >= 3
    return len(mentioned_points) >= min(3, len(local_points))


def bridge_step_relation_realized(sentence: str, step: Dict[str, Any]) -> bool:
    if not isinstance(step, dict):
        return False
    relation_candidates = []
    for key in ["relation", "approved_route_relation"]:
        relation = step.get(key, "")
        if isinstance(relation, str) and relation.strip() and relation not in relation_candidates:
            relation_candidates.append(relation)
    for relation in relation_candidates:
        local_points = extract_relation_point_names(relation)
        if relation_mentioned_in_text(sentence, relation):
            if relation_only_appears_in_preparation_clause(sentence, relation, point_names=local_points):
                continue
            if not relation_has_sufficient_point_coverage(sentence, relation, point_names=local_points):
                continue
            return True
        if local_points and relations_semantically_match(sentence, relation, local_points):
            if relation_only_appears_in_preparation_clause(sentence, relation, point_names=local_points):
                continue
            if not relation_has_sufficient_point_coverage(sentence, relation, point_names=local_points):
                continue
            return True
    return False


def detect_visible_premise_relation_conflicts(record: Dict[str, Any]) -> list[str]:
    issues = []
    visible_facts = extract_visible_formal_facts(record)
    line_pair_predicates = {}
    midpoint_claims = {}

    for fact in visible_facts:
        predicate = fact.get("predicate", "")
        args = fact.get("args", [])
        if predicate in {"para", "perp"} and len(args) >= 4:
            line_pair = frozenset([
                _canonical_line_key(args[0], args[1]),
                _canonical_line_key(args[2], args[3]),
            ])
            line_pair_predicates.setdefault(line_pair, set()).add(predicate)
        elif predicate == "midp" and len(args) >= 3:
            segment_key = _canonical_line_key(args[1], args[2])
            midpoint_claims.setdefault(segment_key, set()).add(args[0])

    for line_pair, predicates in line_pair_predicates.items():
        if {"para", "perp"}.issubset(predicates):
            lines = sorted("".join(points) for points in line_pair)
            issues.append(
                "visible_premise_relation_conflict:"
                f"{'/'.join(lines)} both parallel and perpendicular"
            )
    for segment_key, midpoints in midpoint_claims.items():
        if len(midpoints) > 1:
            issues.append(
                "visible_premise_midpoint_conflict:"
                f"{''.join(segment_key)} has multiple midpoints {','.join(sorted(midpoints))}"
            )
    return issues


def audit_source_record(
    record: Dict[str, Any],
    image_path: Path,
    aux_part: str,
    visible_goal: str,
    proof_guidance: Dict[str, Any],
) -> Dict[str, Any]:
    issues = []
    point_coords = get_point_coords(record)
    goal_spec = parse_goal_expression(visible_goal)
    goal_points = set(goal_spec["points"])
    visible_points = set(extract_visible_point_names(point_coords))
    aux_scope = extract_aux_point_scope(aux_part)
    aux_direct = build_aux_direct_consequences(aux_part)

    if not image_path.exists():
        issues.append("missing_image")
    if not point_coords:
        issues.append("missing_point_coords")
    if not visible_goal:
        issues.append("missing_visible_goal")
    if goal_points and not goal_points.issubset(visible_points | aux_scope):
        issues.append("goal_references_unknown_points")
    if not aux_direct:
        issues.append("aux_has_no_parseable_direct_consequences")
    if not proof_guidance.get("goal_finish_relations"):
        issues.append("proof_guidance_missing_goal_finish_relations")
    relation_conflicts = detect_visible_premise_relation_conflicts(record)
    if relation_conflicts:
        issues.extend(relation_conflicts[:8])
    if point_coords:
        visible_fact_conflicts = []
        for fact in extract_visible_formal_facts(record):
            conflict = _visible_fact_coordinate_conflict(fact, point_coords)
            if conflict and conflict not in visible_fact_conflicts:
                visible_fact_conflicts.append(conflict)
            if len(visible_fact_conflicts) >= 8:
                break
        issues.extend(visible_fact_conflicts)

    return {
        "issues": issues,
        "has_issue": bool(issues),
    }


def audit_generation_quality(
    record: Dict[str, Any],
    generation: Dict[str, Any],
    aux_part: str,
    coordinate_candidates: list[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    issues = []
    point_coords = get_point_coords(record)
    visible_points = extract_visible_point_names(point_coords)
    plan = generation.get("plan_parsed") or {}
    suspicious_markers = [
        "rotational symmetry",
        "common center",
        "reference center",
        "circumcenter",
        "square-like",
        "square structure",
        "square structures",
        "square configuration",
        "square configurations",
        "parallelogram",
        "crucial center",
        "midpoint property",
        "midpoint properties",
        "similarity or angle equality",
        "specific angle conditions",
    ]
    generic_bridge_markers = [
        "midpoint property",
        "midpoint properties",
        "specific angle conditions",
        "similarity or angle equality",
    ]

    if plan:
        if plan.get("dossier_version") == "dossier_v1":
            coordinate_candidates = coordinate_candidates or []
            unmatched_relations = [
                relation
                for relation in plan.get("coordinate_relations", [])
                if not any(coordinate_relation_matches_candidate(relation, candidate) for candidate in coordinate_candidates)
            ]
            if unmatched_relations:
                issues.append("coordinate_relations_unmatched:" + " | ".join(unmatched_relations))
            direct_relations = plan.get("aux_immediate_effects") or plan.get("aux_direct_relations") or [""]
            ok, message = validate_aux_step_scope(direct_relations[0], aux_part, visible_points)
            if not ok:
                issues.append(message)
            if not isinstance(plan.get("bridge_chain"), list) or not plan.get("bridge_chain"):
                issues.append("missing_bridge_chain")
            if not isinstance(plan.get("goal_closure"), list) or not plan.get("goal_closure"):
                issues.append("missing_goal_closure")
            write_output = generation.get("write_output") or ""
            coordinate_relations = [
                relation
                for relation in plan.get("coordinate_relations", [])
                if isinstance(relation, str) and relation.strip()
            ]
            observation_focus_relations = [
                relation
                for relation in (plan.get("image_scan") or [])
                if isinstance(relation, str) and relation.strip()
            ]
            if write_output:
                if observation_focus_relations:
                    observation_relation_mentions = count_relation_mentions(
                        write_output,
                        observation_focus_relations,
                        point_names=visible_points,
                    )
                    if observation_relation_mentions == 0:
                        issues.append("observation_cues_not_reused_in_body")
                if coordinate_relations:
                    coordinate_relation_mentions = count_relation_mentions(
                        write_output,
                        coordinate_relations,
                        point_names=visible_points,
                    )
                    if coordinate_relation_mentions == 0:
                        issues.append("coordinate_cues_not_reused_in_body")
                sentences = split_into_sentences(write_output)
                search_start = 0
                for idx, step in enumerate(plan.get("bridge_chain", [])):
                    match_idx = None
                    for sentence_idx in range(search_start, len(sentences)):
                        if relation_mentioned_in_text(sentences[sentence_idx], step.get("claim", "")):
                            match_idx = sentence_idx
                            break
                    if match_idx is None:
                        issues.append(f"bridge_claim_missing_in_body:{idx}")
                        continue
                    sentence = sentences[match_idx].lower()
                    if any(marker in sentence for marker in generic_bridge_markers):
                        issues.append(f"generic_bridge_phrase:{idx}")
                    search_start = match_idx + 1
                for idx, step in enumerate(plan.get("goal_closure", [])):
                    match_idx = None
                    for sentence_idx in range(search_start, len(sentences)):
                        if relation_mentioned_in_text(sentences[sentence_idx], step.get("claim", "")):
                            match_idx = sentence_idx
                            break
                    if match_idx is None:
                        issues.append(f"goal_closure_missing_in_body:{idx}")
                        continue
                    search_start = match_idx + 1
        else:
            coordinate_candidates = coordinate_candidates or []
            unmatched_relations = [
                relation
                for relation in plan.get("coordinate_relations", [])
                if not any(coordinate_relation_matches_candidate(relation, candidate) for candidate in coordinate_candidates)
            ]
            if unmatched_relations:
                issues.append("coordinate_relations_unmatched:" + " | ".join(unmatched_relations))
            direct_relations = plan.get("aux_direct_relations") or plan.get("verification_chain") or [""]
            ok, message = validate_aux_step_scope(direct_relations[0], aux_part, visible_points)
            if not ok:
                issues.append(message)
            bridge_relations = flatten_bridge_relations(plan)
            if not bridge_relations:
                issues.append("missing_bridge_relations")
            write_output = generation.get("write_output") or ""
            coordinate_relations = [
                relation
                for relation in plan.get("coordinate_relations", [])
                if isinstance(relation, str) and relation.strip()
            ]
            coverage_targets = plan.get("coverage_targets", {}) if isinstance(plan.get("coverage_targets"), dict) else {}
            anchor_points = {
                point.lower()
                for point in (plan.get("anchor_points") or [])
                if isinstance(point, str) and point.strip()
            }
            non_anchor_coordinate_points = []
            for relation in coordinate_relations:
                for point in extract_point_mentions(relation, visible_points):
                    point = point.lower()
                    if point in anchor_points or point in non_anchor_coordinate_points:
                        continue
                    non_anchor_coordinate_points.append(point)
            coordinate_focus_relations = [
                relation
                for relation in (coverage_targets.get("coordinate_focus_relations") or coordinate_relations)
                if isinstance(relation, str) and relation.strip()
            ]
            observation_focus_relations = [
                relation
                for relation in (coverage_targets.get("observation_focus_relations") or [])
                if isinstance(relation, str) and relation.strip()
            ]
            if not observation_focus_relations:
                for observation in plan.get("observation_relations", []) or []:
                    if not isinstance(observation, dict):
                        continue
                    relation = observation.get("relation")
                    if isinstance(relation, str) and relation.strip() and relation not in observation_focus_relations:
                        observation_focus_relations.append(relation.strip())
            coordinate_reuse_min = int(coverage_targets.get("coordinate_reuse_min") or (1 if coordinate_relations else 0))
            early_coordinate_reuse_min = int(coverage_targets.get("early_coordinate_reuse_min") or 0)
            observation_relation_mentions = (
                count_relation_mentions(write_output, observation_focus_relations, point_names=visible_points)
                if write_output and observation_focus_relations else 0
            )
            coordinate_relation_mentions = (
                count_relation_mentions(write_output, coordinate_relations, point_names=visible_points)
                if write_output and coordinate_relations else 0
            )
            mentioned_coordinate_points = (
                extract_point_mentions(write_output, non_anchor_coordinate_points)
                if write_output and non_anchor_coordinate_points else set()
            )
            if observation_focus_relations and observation_relation_mentions == 0:
                issues.append("observation_cues_not_reused_in_body")
            if coordinate_relations and coordinate_relation_mentions == 0:
                issues.append("coordinate_cues_not_reused_in_body")
            elif coordinate_relations and coordinate_relation_mentions < coordinate_reuse_min:
                issues.append(
                    f"coordinate_cue_reuse_too_shallow:{coordinate_relation_mentions}/{coordinate_reuse_min}"
                )
            if non_anchor_coordinate_points and not mentioned_coordinate_points:
                issues.append("non_anchor_coordinate_cues_unused")
            if write_output and isinstance(plan.get("bridge_steps"), list):
                sentences = split_into_sentences(write_output)
                if observation_focus_relations:
                    early_body = " ".join(sentences[: min(3, len(sentences))])
                    early_observation_mentions = count_relation_mentions(
                        early_body,
                        observation_focus_relations,
                        point_names=visible_points,
                    )
                    if early_observation_mentions < 1:
                        issues.append("early_observation_cue_missing")
                if early_coordinate_reuse_min and coordinate_focus_relations:
                    early_body = " ".join(sentences[: min(3, len(sentences))])
                    early_coordinate_mentions = count_relation_mentions(
                        early_body,
                        coordinate_focus_relations,
                        point_names=visible_points,
                    )
                    if early_coordinate_mentions < early_coordinate_reuse_min:
                        issues.append("early_non_anchor_coordinate_cue_missing")
                search_start = 0
                for idx, step in enumerate(plan["bridge_steps"]):
                    match_idx = None
                    for sentence_idx in range(search_start, len(sentences)):
                        if bridge_step_relation_realized(sentences[sentence_idx], step):
                            match_idx = sentence_idx
                            break
                    if match_idx is None:
                        issues.append(f"bridge_relation_missing_in_body:{idx}")
                        continue
                    sentence = sentences[match_idx].lower()
                    sentence_text = sentences[match_idx]
                    if any(marker in sentence for marker in generic_bridge_markers):
                        issues.append(f"generic_bridge_phrase:{idx}")
                    required_supports = step.get("required_supports") or step.get("depends_on", [])
                    min_support_mentions = step.get("min_support_mentions", 1 if required_supports else 0)
                    mentioned_dependencies = count_support_relation_mentions(
                        sentence_text,
                        required_supports,
                        point_names=visible_points,
                        target_relation=step.get("approved_route_relation") or step.get("relation", ""),
                    )
                    if mentioned_dependencies < min_support_mentions:
                        issues.append(f"bridge_supports_missing_in_body:{idx}")
                    search_start = match_idx + 1
            if isinstance(plan.get("bridge_steps"), list) and plan.get("goal_finish"):
                last_step = plan["bridge_steps"][-1] if plan["bridge_steps"] else None
                if isinstance(last_step, dict):
                    last_relation = last_step.get("approved_route_relation") or last_step.get("relation", "")
                    if relations_semantically_match(last_relation, plan.get("goal_finish", ""), visible_points):
                        issues.append("bridge_goal_finish_duplicate")

    text_to_scan = " ".join(
        part for part in [generation.get("write_output"), generation.get("thinking")] if part
    ).lower()
    for marker in suspicious_markers:
        if marker == "parallelogram":
            supported_spans = list(iter_supported_parallelogram_mentions(record, text_to_scan))
            supported_spans.extend(iter_aux_constructed_parallelogram_mentions(text_to_scan, aux_part))
            supported_spans.extend(iter_coordinate_supported_parallelogram_mentions(text_to_scan, plan))
            marker_hits = [match.span() for match in re.finditer(r"\bparallelogram\b", text_to_scan)]
            unsupported_hits = [
                hit
                for hit in marker_hits
                if not any(supported_start <= hit[0] and hit[1] <= supported_end for supported_start, supported_end in supported_spans)
            ]
            if unsupported_hits:
                issues.append(f"suspicious_phrase:{marker}")
            continue
        if marker in text_to_scan:
            issues.append(f"suspicious_phrase:{marker}")

    return {
        "issues": issues,
        "has_issue": bool(issues),
    }
