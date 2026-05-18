#!/usr/bin/env python3
"""
Shared geometry-text parsing and normalization helpers for CoT SFT generation.
"""

from __future__ import annotations

import re


AUX_NEW_POINT_RE = re.compile(r"\bx00\s+([a-z]\w*)\b", re.IGNORECASE)
PROBLEM_BODY_RE = re.compile(r"<problem>\s*(.*?)\s*</problem>", re.DOTALL | re.IGNORECASE)
FORMAL_RELATION_STARTERS = {
    "cong",
    "perp",
    "para",
    "coll",
    "cyclic",
    "midp",
    "eqratio",
    "eqangle",
    "simtri",
    "simtrir",
    "contri",
    "contrir",
    "eqpoint",
}


def build_aux_keyword_expectations(aux_part):
    expectations = []
    inner = aux_part.replace("<aux>", "").replace("</aux>", "").lower()
    if "midp" in inner:
        expectations.append(("midpoint", ["midpoint"]))
    if "cyclic" in inner:
        expectations.append(("cyclic/circle", ["cyclic", "circle", "circumcircle", "concyclic"]))
    if "cong" in inner:
        expectations.append(
            (
                "equal-length",
                [
                    "equal",
                    "congruent",
                    "same distance",
                    "equidistant",
                    "perpendicular bisector",
                ],
            )
        )
    if "perp" in inner:
        expectations.append(("perpendicular", ["perpendicular", "right angle"]))
    if "para" in inner:
        expectations.append(("parallel", ["parallel"]))
    if "coll" in inner:
        expectations.append(
            (
                "collinear/line",
                ["collinear", "line through", "passing through", "on line", "on the line", "intersection"],
            )
        )
    return expectations


def extract_visible_point_names(point_coords):
    return sorted(point_coords.keys())


def extract_point_mentions(text, visible_points):
    mentioned = set()
    lowered = text.lower()
    for point_name in visible_points:
        if re.search(rf"\b{re.escape(point_name.lower())}\b", lowered):
            mentioned.add(point_name.lower())

    single_letter_points = {point.lower() for point in visible_points if len(point) == 1}
    compound_matches = re.findall(
        r"\b(?:segment|triangle|line|angle|side|midpoint(?:\s+of)?|points?)\s+([a-z]{2,6})\b",
        lowered,
    )
    for token in compound_matches:
        if not single_letter_points:
            break
        if all(char in single_letter_points for char in token):
            mentioned.update(token)
    if single_letter_points:
        bare_compounds = re.findall(r"\b([a-z]{2,6})\b", lowered)
        for token in bare_compounds:
            if all(char in single_letter_points for char in token):
                mentioned.update(token)
    return mentioned


def relation_keyword_present(text):
    keywords = [
        "parallel",
        "perpendicular",
        "equal",
        "congruent",
        "ratio",
        "proportion",
        "similar",
        "angle",
        "midpoint",
        "collinear",
        "isosceles",
        "equilateral",
        "circle",
        "cyclic",
        "symmetric",
        "symmetry",
        "diameter",
        "bisect",
        "aligned",
        "alignment",
        "right angle",
        "right-angled",
    ]
    lowered = text.lower()
    if any(keyword in lowered for keyword in keywords):
        return True
    if re.search(r"\b[a-z]{2}\s*=\s*[a-z]{2}\b", lowered):
        return True
    if re.search(r"\bangle\s+[a-z]{2}/[a-z]{2}\s+equals\s+angle\s+[a-z]{2}/[a-z]{2}\b", lowered):
        return True
    return False


def summarize_aux_clause(clause):
    clause = re.sub(r"\[\d{3}\]", "", clause).strip()
    ratio_clause_match = re.fullmatch(
        r"([a-z]{2})\s*:\s*([a-z]{2})\s*=\s*([a-z]{2})\s*:\s*([a-z]{2})",
        clause,
        flags=re.IGNORECASE,
    )
    if ratio_clause_match:
        left_num, left_den, right_num, right_den = [group.lower() for group in ratio_clause_match.groups()]
        return f"ratio {left_num} to {left_den} equals ratio {right_num} to {right_den}"
    tokens = clause.split()
    if not tokens:
        return None

    pred = tokens[0]
    args = tokens[1:]
    if pred == "cong" and len(args) >= 4:
        return f"{args[0]}{args[1]} equals {args[2]}{args[3]}"
    if pred == "perp" and len(args) >= 4:
        return f"line {args[0]}{args[1]} is perpendicular to line {args[2]}{args[3]}"
    if pred == "para" and len(args) >= 4:
        return f"line {args[0]}{args[1]} is parallel to line {args[2]}{args[3]}"
    if pred == "coll" and len(args) >= 3:
        return f"{args[0]}, {args[1]}, {args[2]} are collinear"
    if pred == "cyclic" and len(args) >= 4:
        return f"{args[0]}, {args[1]}, {args[2]}, {args[3]} are concyclic"
    if pred == "midp" and len(args) >= 3:
        return f"{args[0]} is the midpoint of {args[1]}{args[2]}"
    if pred == "eqpoint" and len(args) >= 2:
        return f"{args[0]} equals {args[1]}"
    if pred == "eqratio" and len(args) >= 8:
        return (
            f"ratio {args[0]}{args[1]} to {args[2]}{args[3]} "
            f"equals ratio {args[4]}{args[5]} to {args[6]}{args[7]}"
        )
    if pred == "eqangle" and len(args) >= 8:
        return f"angle {args[0]}{args[1]}/{args[2]}{args[3]} equals angle {args[4]}{args[5]}/{args[6]}{args[7]}"
    if pred in {"simtri", "simtrir"} and len(args) >= 6:
        return f"triangles {args[0]}{args[1]}{args[2]} and {args[3]}{args[4]}{args[5]} are similar"
    if pred in {"contri", "contrir"} and len(args) >= 6:
        return f"triangles {args[0]}{args[1]}{args[2]} and {args[3]}{args[4]}{args[5]} are congruent"
    return clause


def normalize_relation_surface(text):
    cleaned = (text or "").strip()
    if not cleaned:
        return cleaned
    normalized = re.sub(r"\[\d{3}\]", "", cleaned).strip(" ;")
    normalized = re.sub(r"^(?:then|thus|therefore|hence|so)\s+", "", normalized, flags=re.IGNORECASE)
    coincide_match = re.fullmatch(
        r"(?:point\s+)?([a-z]\w*)\s+coincides\s+with\s+(?:point\s+)?([a-z]\w*)\.?",
        normalized,
        flags=re.IGNORECASE,
    )
    if coincide_match:
        point_a = coincide_match.group(1).lower()
        point_b = coincide_match.group(2).lower()
        return f"{point_a} equals {point_b}"
    line_match = re.fullmatch(
        r"(?:point\s+)?([a-z]\w*)\s+lies\s+on\s+(?:the\s+)?(?:line|segment)\s+([a-z]\w*)([a-z]\w*)\.?",
        normalized,
        flags=re.IGNORECASE,
    )
    if line_match:
        point_name = line_match.group(1).lower()
        line_p1 = line_match.group(2).lower()
        line_p2 = line_match.group(3).lower()
        return f"{line_p1}, {line_p2}, {point_name} are collinear"
    ratio_match = re.fullmatch(
        r"([a-z]{2})\s*:\s*([a-z]{2})\s*=\s*([a-z]{2})\s*:\s*([a-z]{2})",
        normalized,
        flags=re.IGNORECASE,
    )
    if ratio_match:
        left_num, left_den, right_num, right_den = [group.lower() for group in ratio_match.groups()]
        return f"ratio {left_num} to {left_den} equals ratio {right_num} to {right_den}"
    equality_match = re.fullmatch(
        r"([a-z]{2})\s*=\s*([a-z]{2})\.?",
        normalized,
        flags=re.IGNORECASE,
    )
    if equality_match:
        left_seg, right_seg = [group.lower() for group in equality_match.groups()]
        return f"{left_seg} equals {right_seg}"
    triangle_binary_match = re.search(
        r"triangles?\s+([a-z]{3})\s+and\s+([a-z]{3})\s+are\s+(similar|congruent)\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if triangle_binary_match:
        tri_a = triangle_binary_match.group(1).lower()
        tri_b = triangle_binary_match.group(2).lower()
        relation = triangle_binary_match.group(3).lower()
        return f"triangles {tri_a} and {tri_b} are {relation}"
    triangle_unary_match = re.search(
        r"triangle\s+([a-z]{3})\s+is\s+(similar|congruent)\s+to\s+triangle\s+([a-z]{3})\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if triangle_unary_match:
        tri_a = triangle_unary_match.group(1).lower()
        relation = triangle_unary_match.group(2).lower()
        tri_b = triangle_unary_match.group(3).lower()
        return f"triangles {tri_a} and {tri_b} are {relation}"
    tokens = normalized.split()
    if tokens and tokens[0].lower() in FORMAL_RELATION_STARTERS:
        summary = summarize_aux_clause(normalized)
        if summary:
            return summary
    return cleaned


def relation_text_keywords(text):
    lowered = (text or "").lower()
    keywords = set()
    keyword_groups = {
        "parallel": ["parallel"],
        "perpendicular": ["perpendicular", "right angle", "right-angled"],
        "equal": ["equal", "equals", "congruent", "equidistant"],
        "ratio": ["ratio", "proportion"],
        "similar": ["similar"],
        "angle": ["angle"],
        "midpoint": ["midpoint"],
        "collinear": ["collinear", "aligned", "alignment"],
        "circle": ["circle", "cyclic", "concyclic"],
        "bisect": ["bisect"],
        "isosceles": ["isosceles"],
    }
    for label, variants in keyword_groups.items():
        if any(variant in lowered for variant in variants):
            keywords.add(label)
    if re.search(r"\b[a-z]{2}\s*:\s*[a-z]{2}\s*=\s*[a-z]{2}\s*:\s*[a-z]{2}\b", lowered):
        keywords.add("ratio")
    if re.search(r"\b[a-z]{2}\s*=\s*[a-z]{2}\b", lowered):
        keywords.add("equal")
    return keywords


def extract_high_level_structure_markers(text):
    lowered = (text or "").lower()
    marker_groups = {
        "triangle": ["triangle", "triangles"],
        "similar": ["similar"],
        "cyclic": ["cyclic", "concyclic", "circle"],
        "parallelogram": ["parallelogram"],
        "midpoint": ["midpoint"],
    }
    markers = set()
    for label, variants in marker_groups.items():
        if any(variant in lowered for variant in variants):
            markers.add(label)
    return markers


def normalize_point_case(text, point_names):
    if not isinstance(text, str) or not point_names:
        return text

    normalized = text
    point_names = [str(point).lower() for point in point_names]
    single_letter_points = {point for point in point_names if len(point) == 1}

    for point in sorted(point_names, key=len, reverse=True):
        normalized = re.sub(
            rf"\b{re.escape(point)}\b",
            point,
            normalized,
            flags=re.IGNORECASE,
        )

    def lower_compound(match):
        token = match.group(0)
        lowered = token.lower()
        if single_letter_points and all(char in single_letter_points for char in lowered):
            return lowered
        return token

    normalized = re.sub(r"\b[A-Za-z]{2,6}\b", lower_compound, normalized)
    return normalized


def relations_semantically_match(text_a, text_b, point_names):
    normalized_a = normalize_relation_surface(normalize_point_case(text_a or "", point_names)).lower()
    normalized_b = normalize_relation_surface(normalize_point_case(text_b or "", point_names)).lower()
    if not normalized_a or not normalized_b:
        return False
    if normalized_a == normalized_b:
        return True
    if normalized_a in normalized_b or normalized_b in normalized_a:
        return True
    points_a = extract_point_mentions(normalized_a, point_names)
    points_b = extract_point_mentions(normalized_b, point_names)
    keyword_a = relation_text_keywords(normalized_a)
    keyword_b = relation_text_keywords(normalized_b)
    structure_a = extract_high_level_structure_markers(normalized_a)
    structure_b = extract_high_level_structure_markers(normalized_b)
    if not (points_a and points_b and keyword_a and keyword_b):
        return False
    exclusive_modalities = [
        "angle",
        "ratio",
        "similar",
        "parallel",
        "perpendicular",
        "collinear",
        "midpoint",
        "circle",
        "isosceles",
    ]
    for label in exclusive_modalities:
        if (label in keyword_a) != (label in keyword_b):
            return False
    if ("triangle" in structure_a) != ("triangle" in structure_b):
        return False
    shared_points = points_a & points_b
    shared_keywords = keyword_a & keyword_b
    if "angle" in shared_keywords and len(shared_points) >= 4:
        return True
    if "ratio" in shared_keywords and len(shared_points) >= 4:
        return True
    if {"parallel", "perpendicular"} & shared_keywords and len(shared_points) >= 4:
        return True
    if {"collinear", "midpoint", "circle"} & shared_keywords and len(shared_points) >= 3:
        return True
    if "similar" in shared_keywords and len(shared_points) >= 4:
        return True
    if "equal" in shared_keywords and len(shared_points) >= 3 and "angle" not in keyword_a and "ratio" not in keyword_a:
        return True
    return False


def align_bridge_steps_to_hidden_route(bridge_steps, hidden_route_relations, point_names):
    matches = []
    unmatched = []
    cursor = -1
    for step in bridge_steps:
        relation_text = step.get("relation", "") if isinstance(step, dict) else ""
        matched_index = None
        for idx in range(cursor + 1, len(hidden_route_relations)):
            if relations_semantically_match(relation_text, hidden_route_relations[idx], point_names):
                matched_index = idx
                break
        if matched_index is None:
            matches.append(None)
            unmatched.append(relation_text)
            continue
        matches.append(
            {
                "index": matched_index,
                "relation": hidden_route_relations[matched_index],
            }
        )
        cursor = matched_index
    return {
        "matches": matches,
        "unmatched": unmatched,
    }


def score_support_relation(support, relation_text, point_names, next_target_relation=""):
    support_points = extract_point_mentions(support, point_names)
    relation_points = extract_point_mentions(relation_text, point_names)
    support_keywords = relation_text_keywords(support)
    relation_keywords = relation_text_keywords(relation_text)
    score = 0
    score += 5 * len(support_points & relation_points)
    score += 3 * len(support_keywords & relation_keywords)

    if next_target_relation:
        next_points = extract_point_mentions(next_target_relation, point_names)
        next_keywords = relation_text_keywords(next_target_relation)
        score += 2 * len(support_points & next_points)
        score += 1 * len(support_keywords & next_keywords)

    if "midpoint" in support_keywords and "equal" in relation_keywords and len(support_points & relation_points) >= 2:
        score += 4
    if "collinear" in support_keywords and "collinear" in relation_keywords and len(support_points & relation_points) >= 2:
        score += 4
    if relations_semantically_match(support, relation_text, point_names):
        score += 2
    return score


def select_support_relations_for_step(relation_text, available_supports, point_names, next_target_relation="", max_supports=2):
    ranked = []
    for support in available_supports:
        if not isinstance(support, str) or not support.strip():
            continue
        score = score_support_relation(
            support,
            relation_text,
            point_names,
            next_target_relation=next_target_relation,
        )
        if score <= 0:
            continue
        ranked.append((score, support))
    ranked.sort(key=lambda item: (-item[0], len(item[1]), item[1].lower()))

    selected = []
    for _, support in ranked:
        if support not in selected:
            selected.append(support)
        if len(selected) >= max_supports:
            break
    return selected


def score_visible_relation_candidate(relation_text, route_relations_text, visible_points):
    relation_points = extract_point_mentions(relation_text, visible_points)
    relation_keywords = relation_text_keywords(relation_text)
    route_points = extract_point_mentions(route_relations_text, visible_points)
    route_keywords = relation_text_keywords(route_relations_text)
    score = 0
    score += 5 * len(relation_points & route_points)
    score += 2 * len(relation_keywords & route_keywords)
    if "equal" in relation_keywords and any(keyword in route_keywords for keyword in {"similar", "ratio", "equal"}):
        score += 2
    if "collinear" in relation_keywords and any(keyword in route_keywords for keyword in {"angle", "ratio", "similar"}):
        score += 2
    if "circle" in relation_keywords and any(keyword in route_keywords for keyword in {"angle", "similar"}):
        score += 1
    return score


def prioritize_visible_relations_for_route(existing_relations, fallback_summaries, route_relations, visible_points, min_len=2, max_len=4):
    cleaned_existing = [
        normalize_relation_surface(relation.strip())
        for relation in (existing_relations or [])
        if isinstance(relation, str) and relation.strip()
    ]
    route_relations_text = " ".join(
        relation.strip()
        for relation in (route_relations or [])
        if isinstance(relation, str) and relation.strip()
    )
    if not route_relations_text:
        return cleaned_existing[:max_len]

    candidates = []
    seen = set()
    for origin_rank, relation in enumerate(cleaned_existing + list(fallback_summaries or [])):
        if not isinstance(relation, str) or not relation.strip():
            continue
        cleaned_relation = normalize_relation_surface(relation.strip())
        lowered = cleaned_relation.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        candidates.append(
            (
                score_visible_relation_candidate(cleaned_relation, route_relations_text, visible_points),
                origin_rank,
                cleaned_relation,
            )
        )

    current_score = sum(
        score_visible_relation_candidate(relation, route_relations_text, visible_points)
        for relation in cleaned_existing[:max_len]
    )
    ranked = sorted(
        candidates,
        key=lambda item: (-item[0], item[1], len(item[2]), item[2].lower()),
    )

    selected = []
    for score, _, relation in ranked:
        if score <= 0:
            continue
        if relation not in selected:
            selected.append(relation)
        if len(selected) >= max_len:
            break
    for relation in cleaned_existing:
        if relation not in selected:
            selected.append(relation)
        if len(selected) >= max_len:
            break
    for _, _, relation in ranked:
        if relation not in selected:
            selected.append(relation)
        if len(selected) >= max_len:
            break

    selected = selected[:max_len]
    proposed_score = sum(
        score_visible_relation_candidate(relation, route_relations_text, visible_points)
        for relation in selected
    )
    if len(selected) >= min_len and proposed_score > current_score:
        return selected
    return cleaned_existing[:max_len]


def relation_duplicates_earlier_support(relation_text, available_supports, point_names):
    normalized_relation = normalize_relation_surface(relation_text).lower()
    relation_points = extract_point_mentions(normalized_relation, point_names)
    relation_keywords = relation_text_keywords(normalized_relation)
    for support in available_supports:
        normalized_support = normalize_relation_surface(support).lower()
        if not normalized_support:
            continue
        if normalized_relation == normalized_support:
            return True
        support_points = extract_point_mentions(normalized_support, point_names)
        support_keywords = relation_text_keywords(normalized_support)
        if (
            relation_points == support_points
            and relation_keywords & support_keywords
            and relations_semantically_match(relation_text, support, point_names)
        ):
            return True
    return False


def parse_goal_expression(visible_goal):
    tokens = [token.strip().lower() for token in (visible_goal or "").split() if token.strip()]
    if not tokens:
        return {"predicate": "", "points": []}
    predicate = tokens[0]
    points = [token for token in tokens[1:] if re.fullmatch(r"[a-z]\w*", token)]
    return {"predicate": predicate, "points": points}


def goal_keyword_hints(visible_goal):
    predicate = parse_goal_expression(visible_goal)["predicate"]
    mapping = {
        "eqratio": ["ratio", "proportion", "similar"],
        "eqangle": ["angle", "parallel", "cyclic"],
        "cong": ["equal", "congruent"],
        "contri": ["congruent", "equal", "matching"],
        "simtri": ["similar", "ratio"],
        "simtrir": ["similar", "ratio"],
        "perp": ["perpendicular", "right angle"],
        "para": ["parallel"],
        "coll": ["collinear", "line"],
        "cyclic": ["cyclic", "circle", "concyclic"],
        "midp": ["midpoint", "equal"],
    }
    return mapping.get(predicate, ["angle", "ratio", "equal"])


def parse_aux_clauses(aux_part):
    inner = aux_part.replace("<aux>", "").replace("</aux>", "").strip()
    clauses = []
    for raw_clause in [part.strip() for part in inner.split(";") if part.strip()]:
        point_match = re.match(r"x00\s+([a-z]\w*)\s*:\s*(.*)", raw_clause, re.IGNORECASE)
        if point_match:
            clauses.append(
                {
                    "new_point": point_match.group(1).lower(),
                    "body": point_match.group(2).strip(),
                }
            )
        else:
            clauses.append({"new_point": None, "body": raw_clause})
    return clauses


def split_formal_relation_chain(text):
    cleaned = re.sub(r"\[\d+\]", "|", text or "")
    raw_parts = [part.strip(" ;") for part in cleaned.split("|") if part.strip(" ;")]
    facts = []
    for part in raw_parts:
        starter = part.split()[0].lower() if part.split() else ""
        if starter in FORMAL_RELATION_STARTERS:
            facts.append(part)
        elif facts:
            facts[-1] = f"{facts[-1]} {part}".strip()
    return facts or ([text.strip()] if text and text.strip() else [])


def extract_aux_point_scope(aux_part):
    scope = set()
    for clause in parse_aux_clauses(aux_part):
        for fact in split_formal_relation_chain(clause["body"]):
            tokens = fact.split()
            for token in tokens[1:]:
                token = token.strip().lower()
                if re.fullmatch(r"[a-z]\w*", token):
                    scope.add(token)
        if clause["new_point"]:
            scope.add(clause["new_point"])
    return scope


def infer_relation_type_from_text(text):
    lowered = (text or "").lower()
    if "midpoint" in lowered:
        return "midpoint"
    if "concyclic" in lowered or "circumcircle" in lowered or "cyclic" in lowered or "circle" in lowered:
        return "cyclic"
    if "collinear" in lowered or " on line " in f" {lowered} " or "line through" in lowered:
        return "collinear"
    if "right angle" in lowered or "right-angled" in lowered:
        return "right_triangle"
    if "perpendicular" in lowered:
        return "perpendicular"
    if "parallel" in lowered:
        return "parallel"
    if "equilateral" in lowered:
        return "equilateral"
    if "isosceles" in lowered:
        return "isosceles"
    if "equal in length" in lowered or "same length" in lowered or "equidistant" in lowered:
        return "equal_length"
    if "congruent" in lowered or re.search(r"\b[a-z]{2}\s*=\s*[a-z]{2}\b", lowered):
        return "equal_length"
    return ""


def build_aux_direct_consequences(aux_part):
    consequences = []
    for clause in parse_aux_clauses(aux_part):
        for fact in split_formal_relation_chain(clause["body"]):
            summary = summarize_aux_clause(fact)
            if summary:
                consequences.append(summary)
    return consequences


def build_public_problem_text(record):
    nl_problem = (record.get("nl_problem") or "").strip()
    formal_problem = (record.get("llm_input_renamed") or "").strip()
    if nl_problem:
        return f"<nl_problem>{nl_problem}</nl_problem>\n{formal_problem}"
    return formal_problem


def extract_problem_goal(record):
    problem_text = build_public_problem_text(record)
    body_match = PROBLEM_BODY_RE.search(problem_text)
    body = body_match.group(1).strip() if body_match else problem_text.strip()
    if "?" in body:
        return body.split("?", 1)[1].strip()
    return ""


def extract_problem_context(record):
    problem_text = build_public_problem_text(record)
    body_match = PROBLEM_BODY_RE.search(problem_text)
    body = body_match.group(1).strip() if body_match else problem_text.strip()
    if "?" in body:
        return body.split("?", 1)[0].strip()
    return body


def extract_aux_new_points(aux_part):
    return AUX_NEW_POINT_RE.findall(aux_part)


def build_hidden_aux_brief(aux_part):
    inner = aux_part.replace("<aux>", "").replace("</aux>", "").strip()
    clauses = [part.strip() for part in inner.split(";") if part.strip()]
    summaries = []
    for clause in clauses:
        summary = summarize_aux_clause(clause)
        if summary:
            summaries.append(summary)
    if not summaries:
        return inner
    return "; ".join(summaries)


def build_canonical_construction(aux_part):
    clauses = parse_aux_clauses(aux_part or "")
    if not clauses:
        return ""
    sentences = []
    for clause in clauses:
        point_name = clause.get("new_point")
        fact_summaries = []
        for fact in split_formal_relation_chain(clause.get("body", "")):
            summary = summarize_aux_clause(fact)
            if summary:
                fact_summaries.append(summary)
        if not point_name or not fact_summaries:
            continue
        if len(fact_summaries) == 1:
            fact_text = fact_summaries[0]
        elif len(fact_summaries) == 2:
            fact_text = f"{fact_summaries[0]} and {fact_summaries[1]}"
        else:
            fact_text = ", ".join(fact_summaries[:-1]) + f", and {fact_summaries[-1]}"
        lead = "construct" if not sentences else "then construct"
        sentences.append(f"{lead} point {point_name} such that {fact_text}")
    return ". ".join(sentences).strip()


def build_multi_aux_instruction(aux_part):
    new_points = extract_aux_new_points(aux_part)
    if len(new_points) <= 1:
        return ""

    point_steps = []
    inner = aux_part.replace("<aux>", "").replace("</aux>", "").strip()
    clauses = [part.strip() for part in inner.split(";") if part.strip()]
    for clause in clauses:
        match = re.match(r"x00\s+([a-z]\w*)\s*:\s*(.*)", clause, re.IGNORECASE)
        if not match:
            continue
        point_name = match.group(1).lower()
        summary = summarize_aux_clause(match.group(2).strip()) or match.group(2).strip()
        point_steps.append(f"{point_name}: {summary}")

    steps_text = "; ".join(point_steps) if point_steps else ", ".join(new_points)
    return (
        "[Multi-Point Construction Requirement]\n"
        "This target introduces multiple new points. Your construction field must use explicit stage markers such as "
        "'first', 'then', and 'finally', or say that some points are introduced together before a later step.\n"
        f"Target point-by-point outline: {steps_text}\n\n"
    )


__all__ = [
    "FORMAL_RELATION_STARTERS",
    "PROBLEM_BODY_RE",
    "AUX_NEW_POINT_RE",
    "align_bridge_steps_to_hidden_route",
    "build_aux_direct_consequences",
    "build_aux_keyword_expectations",
    "build_canonical_construction",
    "build_hidden_aux_brief",
    "build_multi_aux_instruction",
    "build_public_problem_text",
    "extract_aux_new_points",
    "extract_aux_point_scope",
    "extract_high_level_structure_markers",
    "extract_point_mentions",
    "extract_problem_context",
    "extract_problem_goal",
    "extract_visible_point_names",
    "goal_keyword_hints",
    "infer_relation_type_from_text",
    "normalize_point_case",
    "normalize_relation_surface",
    "parse_aux_clauses",
    "parse_goal_expression",
    "prioritize_visible_relations_for_route",
    "relation_duplicates_earlier_support",
    "relation_keyword_present",
    "relation_text_keywords",
    "relations_semantically_match",
    "score_support_relation",
    "score_visible_relation_candidate",
    "select_support_relations_for_step",
    "split_formal_relation_chain",
    "summarize_aux_clause",
]
