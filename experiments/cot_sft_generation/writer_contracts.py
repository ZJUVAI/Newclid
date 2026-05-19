#!/usr/bin/env python3
"""
Writer-contract and prompt-adjacent coverage helpers for CoT SFT generation.
"""

from __future__ import annotations

import json
import re

try:
    from .geometry_text import (
        extract_point_mentions,
        normalize_relation_surface,
        parse_goal_expression,
        relation_keyword_present,
        relation_text_keywords,
    )
except ImportError:  # pragma: no cover - script execution path
    from geometry_text import (
        extract_point_mentions,
        normalize_relation_surface,
        parse_goal_expression,
        relation_keyword_present,
        relation_text_keywords,
    )


def build_instruction_text():
    return (
        "Given the geometry image and the formal problem text, write a forward-thinking "
        "trace that motivates the auxiliary construction. Output the thinking trace and "
        "the final aux block."
    )


def enrich_bridge_steps_with_targets(plan):
    if not isinstance(plan, dict) or not isinstance(plan.get("bridge_steps"), list):
        return plan
    enriched_steps = []
    total_steps = len(plan["bridge_steps"])
    for idx, step in enumerate(plan["bridge_steps"]):
        if not isinstance(step, dict):
            enriched_steps.append(step)
            continue
        enriched = dict(step)
        if idx < total_steps - 1:
            enriched["next_target_relation"] = plan["bridge_steps"][idx + 1].get("relation", "")
        else:
            enriched["next_target_relation"] = plan.get("goal_finish", "")
        enriched["next_target_purpose"] = build_step_unlock_purpose(
            enriched.get("approved_route_relation") or enriched.get("relation", ""),
            enriched.get("next_target_relation", ""),
            final_step=(idx == total_steps - 1),
        )
        dependencies = [
            dep for dep in enriched.get("depends_on", [])
            if isinstance(dep, str) and dep.strip()
        ]
        enriched["required_supports"] = dependencies[: min(2, len(dependencies))]
        enriched["min_support_mentions"] = 1 if dependencies else 0
        enriched_steps.append(enriched)
    enriched_plan = dict(plan)
    enriched_plan["bridge_steps"] = enriched_steps
    return enriched_plan


def anonymize_new_point_mentions(text, new_points):
    if not isinstance(text, str) or not new_points:
        return text
    anonymized = text
    for point_name in sorted({point.lower() for point in new_points}, key=len, reverse=True):
        anonymized = re.sub(rf"\b{re.escape(point_name)}\b", "a point", anonymized, flags=re.IGNORECASE)
    anonymized = re.sub(r"\ba point(?:\s+a point)+\b", "a point", anonymized, flags=re.IGNORECASE)
    anonymized = re.sub(r"\ba point point\b", "a point", anonymized, flags=re.IGNORECASE)
    return anonymized


def build_canonical_bridge_unlock(next_target_relation, final_step=False):
    target_text = normalize_relation_surface(next_target_relation or "").strip().rstrip(".")
    if not target_text:
        return "this prepares the next approved bridge relation."
    target_text = re.sub(r"^(then|therefore|thus)\s+", "", target_text, flags=re.IGNORECASE)
    if final_step:
        return f"this prepares the final goal-side relation {target_text}."
    return f"this is required to prove {target_text} next."


def build_step_unlock_purpose(relation_text, next_target_relation, final_step=False):
    current_keywords = relation_text_keywords(relation_text or "")
    next_keywords = relation_text_keywords(next_target_relation or "")
    if final_step:
        if "perpendicular" in next_keywords:
            return "this fixes the final angle configuration needed for the perpendicular conclusion."
        if "parallel" in next_keywords:
            return "this fixes the final direction comparison needed for the parallel conclusion."
        if "similar" in next_keywords:
            return "this supplies the last correspondence needed for the final similarity conclusion."
        if "ratio" in next_keywords:
            return "this supplies the last proportional comparison needed for the final ratio conclusion."
        if "angle" in next_keywords:
            return "this supplies the last angle comparison needed for the final angle conclusion."
        if "equal" in next_keywords:
            return "this supplies the last equality needed for the final conclusion."
        return "this prepares the final goal-side conclusion."
    if "similar" in next_keywords:
        if {"angle", "collinear", "parallel", "perpendicular", "circle"} & current_keywords:
            return "this fixes the angle alignment needed for the upcoming similarity step."
        if {"ratio", "equal"} & current_keywords:
            return "this fixes the side correspondence needed for the upcoming similarity step."
        return "this supplies one of the correspondences needed for the upcoming similarity step."
    if "ratio" in next_keywords:
        if "similar" in current_keywords:
            return "this lets the needed proportional comparison be read off next."
        if {"equal", "collinear"} & current_keywords:
            return "this transfers the needed length comparison into the next ratio step."
        return "this supplies the proportional comparison needed next."
    if "angle" in next_keywords:
        if "similar" in current_keywords:
            return "this lets the needed angle correspondence be read off next."
        if {"collinear", "parallel", "perpendicular", "circle"} & current_keywords:
            return "this fixes the angle alignment needed in the next step."
        return "this supplies the angle comparison needed next."
    if "equal" in next_keywords:
        return "this supplies the equality needed next."
    if "collinear" in next_keywords:
        return "this places the needed points on one line for the next step."
    if "parallel" in next_keywords:
        return "this fixes the direction comparison needed next."
    if "perpendicular" in next_keywords:
        return "this fixes the right-angle configuration needed next."
    return build_canonical_bridge_unlock(next_target_relation, final_step=False)


def format_tagged_point(point_name, point_coords):
    x_val, y_val = point_coords[point_name]
    return f"<point>{point_name}</point><coord>({x_val},{y_val})</coord>"


def join_natural_list(items):
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def build_anchor_sentence(plan, point_coords):
    tagged_points = [format_tagged_point(point_name, point_coords) for point_name in plan["anchor_points"]]
    anchor_list = join_natural_list(tagged_points)
    relation = plan["anchor_relation"].strip().rstrip(".")
    return f"From the diagram, the key visible anchors are {anchor_list}; visually, {relation}."


def build_overview_sentence(plan):
    overview = plan["figure_overview"].strip().rstrip(".")
    return f"{overview}."


def build_coordinate_hint_sentence(plan):
    hints = plan["coordinate_hints"].strip().rstrip(".")
    relation_text = "; ".join(plan.get("coordinate_relations", [])).strip().rstrip(".")
    if relation_text:
        return f"{relation_text}. {hints}."
    return f"{hints}."


def build_visible_relation_sentence(plan):
    relation_text = "; ".join(plan.get("visible_relations", [])).strip().rstrip(".")
    if not relation_text:
        return ""
    return f"The visible givens also show that {relation_text}."


def build_prefix_coverage_notes(plan):
    if not isinstance(plan, dict):
        return "[]"
    notes = []
    figure_overview = plan.get("figure_overview")
    if isinstance(figure_overview, str) and figure_overview.strip():
        notes.append(f"overview already covered: {figure_overview.strip().rstrip('.')}")
    for relation in plan.get("coordinate_relations", []) or []:
        if isinstance(relation, str) and relation.strip():
            notes.append(f"coordinate cue already covered: {relation.strip().rstrip('.')}")
    for relation in plan.get("visible_relations", []) or []:
        if isinstance(relation, str) and relation.strip():
            notes.append(f"visible relation already covered: {relation.strip().rstrip('.')}")
    return json.dumps(notes, ensure_ascii=False, indent=2) if notes else "[]"


def build_relation_reuse_hint(relation_text):
    if not isinstance(relation_text, str):
        return ""
    relation = normalize_relation_surface(relation_text).strip().rstrip(".")
    lowered = relation.lower()
    midpoint_match = re.fullmatch(
        r"point\s+([a-z]\w*)\s+looks\s+like\s+the\s+midpoint\s+of\s+(?:segment\s+)?([a-z]\w*)([a-z]\w*)",
        lowered,
    )
    if midpoint_match:
        midpoint = midpoint_match.group(1)
        end_a = midpoint_match.group(2)
        end_b = midpoint_match.group(3)
        return (
            f"say 'the midpoint-looking point {midpoint} on {end_a}{end_b}' or "
            f"'{midpoint} appears to split {end_a}{end_b} evenly' instead of repeating it verbatim"
        )
    right_triangle_match = re.fullmatch(
        r"triangle\s+([a-z]\w*)([a-z]\w*)([a-z]\w*)\s+looks\s+right-angled\s+at\s+([a-z]\w*)",
        lowered,
    )
    if right_triangle_match:
        tri_a, tri_b, tri_c, right_vertex = right_triangle_match.groups()
        return (
            f"say 'the sides through {right_vertex} meet at a right angle in triangle {tri_a}{tri_b}{tri_c}' "
            "instead of repeating it verbatim"
        )
    concyclic_match = re.fullmatch(
        r"([a-z]\w*)(?:,\s*([a-z]\w*))(?:,\s*([a-z]\w*))(?:,\s*([a-z]\w*)) are concyclic",
        lowered,
    )
    if concyclic_match:
        points = [point for point in concyclic_match.groups() if point]
        if len(points) >= 4:
            base = ", ".join(points[:-1])
            return f"say '{points[-1]} lies on the same circle through {base}' instead of repeating it verbatim"
    collinear_match = re.fullmatch(
        r"([a-z]\w*),\s*([a-z]\w*),\s*([a-z]\w*) are collinear",
        lowered,
    )
    if collinear_match:
        p1, p2, p3 = collinear_match.groups()
        return f"say 'point {p3} lies on line {p1}{p2}' instead of repeating it verbatim"
    parallel_match = re.fullmatch(
        r"line ([a-z]\w*[a-z]\w*) is parallel to line ([a-z]\w*[a-z]\w*)",
        lowered,
    )
    if parallel_match:
        left, right = parallel_match.groups()
        return f"say 'line {left} runs parallel to line {right}' instead of repeating it verbatim"
    perpendicular_match = re.fullmatch(
        r"line ([a-z]\w*[a-z]\w*) is perpendicular to line ([a-z]\w*[a-z]\w*)",
        lowered,
    )
    if perpendicular_match:
        left, right = perpendicular_match.groups()
        return f"say 'line {left} meets line {right} at a right angle' instead of repeating it verbatim"
    equality_match = re.fullmatch(r"([a-z]\w*) equals ([a-z]\w*)", lowered)
    if equality_match:
        left, right = equality_match.groups()
        return f"say '{left} and {right} have the same length' instead of repeating it verbatim"
    return f"paraphrase '{relation}' rather than copying the same wording from the prefix"


def build_prefix_reuse_guidance(plan):
    if not isinstance(plan, dict):
        return "[]"
    guidance = []
    seen = set()
    for field_name in ["coordinate_relations", "visible_relations"]:
        for relation in plan.get(field_name, []) or []:
            if not isinstance(relation, str) or not relation.strip():
                continue
            normalized = normalize_relation_surface(relation).strip().rstrip(".")
            lowered = normalized.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            guidance.append(
                {
                    "already_in_prefix": normalized,
                    "reuse_hint": build_relation_reuse_hint(normalized),
                }
            )
    return json.dumps(guidance, ensure_ascii=False, indent=2) if guidance else "[]"


def _uses_extended_coverage_budget(plan):
    if not isinstance(plan, dict):
        return False
    return (
        len(plan.get("anchor_points") or []) >= 5
        or len(plan.get("bridge_steps") or []) >= 5
        or len(plan.get("coordinate_relations") or []) >= 4
        or len(plan.get("aux_direct_relations") or []) >= 4
    )


def build_plan_coverage_targets(plan, visible_goal="", visible_points=None, max_points=None, max_relations=None):
    if not isinstance(plan, dict):
        return {}
    extended_budget = _uses_extended_coverage_budget(plan)
    if max_points is None:
        max_points = 7 if extended_budget else 6
    if max_relations is None:
        max_relations = 5 if extended_budget else 4
    visible_points = [point.lower() for point in (visible_points or []) if isinstance(point, str) and point.strip()]
    anchor_points = [point.lower() for point in (plan.get("anchor_points") or []) if isinstance(point, str) and point.strip()]
    anchor_set = set(anchor_points)
    goal_points = [
        point.lower()
        for point in parse_goal_expression(visible_goal or "").get("points", [])
        if isinstance(point, str) and point.strip()
    ]
    seen_goal_points = set()
    ordered_goal_points = []
    for point in goal_points:
        if point in seen_goal_points:
            continue
        seen_goal_points.add(point)
        ordered_goal_points.append(point)

    relation_sources = []
    overview = plan.get("figure_overview")
    if isinstance(overview, str) and overview.strip():
        relation_sources.append(("figure_overview", overview.strip(), False))
    for relation in plan.get("visible_relations", []) or []:
        if isinstance(relation, str) and relation.strip():
            relation_sources.append(("visible_relation", relation.strip(), True))
    for relation in plan.get("coordinate_relations", []) or []:
        if isinstance(relation, str) and relation.strip():
            relation_sources.append(("coordinate_relation", relation.strip(), True))
    for step in plan.get("bridge_steps", []) or []:
        if isinstance(step, dict):
            relation = step.get("approved_route_relation") or step.get("relation", "")
            if isinstance(relation, str) and relation.strip():
                relation_sources.append(("bridge_relation", relation.strip(), True))
    goal_finish = plan.get("goal_finish")
    if isinstance(goal_finish, str) and goal_finish.strip():
        relation_sources.append(("goal_finish", goal_finish.strip(), True))

    point_counts = {}
    point_first_seen = {}
    focus_relations = []
    seen_relations = set()
    coordinate_point_counts = {}
    coordinate_point_first_seen = {}
    coordinate_focus_relations = []
    seen_coordinate_relations = set()
    for source_label, relation_text, include_in_focus in relation_sources:
        mentioned_points = [
            point for point in extract_point_mentions(relation_text, visible_points)
            if point not in anchor_set
        ]
        for point in mentioned_points:
            point_counts[point] = point_counts.get(point, 0) + 1
            point_first_seen.setdefault(point, len(point_first_seen))
        normalized_relation = normalize_relation_surface(relation_text).strip().rstrip(".")
        lowered_relation = normalized_relation.lower()
        if (
            include_in_focus
            and mentioned_points
            and relation_keyword_present(normalized_relation)
            and lowered_relation not in seen_relations
        ):
            seen_relations.add(lowered_relation)
            focus_relations.append(
                {
                    "source": source_label,
                    "relation": normalized_relation,
                    "points": mentioned_points,
                }
            )
        if source_label != "coordinate_relation":
            continue
        for point in mentioned_points:
            coordinate_point_counts[point] = coordinate_point_counts.get(point, 0) + 1
            coordinate_point_first_seen.setdefault(point, len(coordinate_point_first_seen))
        if mentioned_points and relation_keyword_present(normalized_relation) and lowered_relation not in seen_coordinate_relations:
            seen_coordinate_relations.add(lowered_relation)
            coordinate_focus_relations.append(
                {
                    "relation": normalized_relation,
                    "points": mentioned_points,
                }
            )

    ranked_non_anchor_points = sorted(
        point_counts,
        key=lambda point: (
            point not in ordered_goal_points,
            -point_counts[point],
            point_first_seen.get(point, 0),
            point,
        ),
    )
    primary_points = ranked_non_anchor_points[:max_points]
    goal_points_outside_anchors = [point for point in ordered_goal_points if point not in anchor_set]
    opening_focus_cap = 4 if extended_budget else 3
    bridge_focus_cap = 5 if extended_budget else 4
    opening_focus_points = goal_points_outside_anchors[:opening_focus_cap] or primary_points[:opening_focus_cap]
    bridge_focus_points = primary_points[:bridge_focus_cap]
    ranked_coordinate_points = sorted(
        coordinate_point_counts,
        key=lambda point: (
            point not in ordered_goal_points,
            -coordinate_point_counts[point],
            coordinate_point_first_seen.get(point, 0),
            point,
        ),
    )
    coordinate_focus_cap = 5 if extended_budget else 4
    coordinate_focus_points = ranked_coordinate_points[:coordinate_focus_cap]
    coordinate_focus_relation_cap = 3 if extended_budget else 2
    coordinate_focus_relation_texts = [
        item["relation"]
        for item in coordinate_focus_relations[:coordinate_focus_relation_cap]
    ]
    coordinate_reuse_min = 0
    if coordinate_focus_relation_texts:
        coordinate_reuse_min = 2 if extended_budget and len(coordinate_focus_relation_texts) >= 2 else 1
    early_coordinate_reuse_min = 1 if coordinate_focus_relation_texts else 0

    reminder_parts = []
    if opening_focus_points:
        reminder_parts.append(
            f"frame the bottleneck through {join_natural_list(opening_focus_points)} rather than only the anchor frame"
        )
    if bridge_focus_points:
        reminder_parts.append(
            f"reconnect the auxiliary route to {join_natural_list(bridge_focus_points)} as the body advances"
        )
    if coordinate_focus_points:
        reminder_parts.append(
            f"keep using coordinate-backed cues around {join_natural_list(coordinate_focus_points)} instead of collapsing back to the anchor frame"
        )
    reminder = ". ".join(reminder_parts).strip()
    if reminder:
        reminder += "."

    opening_sentence_hint = ""
    if opening_focus_points:
        opening_sentence_hint = (
            f"name the obstacle through {join_natural_list(opening_focus_points[:opening_focus_cap])} in the first sentence"
        )
    helper_sentence_hint = ""
    if bridge_focus_points:
        helper_sentence_hint = (
            f"name the helper through the local configuration around {join_natural_list(bridge_focus_points[:bridge_focus_cap])} in the second sentence"
        )
    coordinate_sentence_hint = ""
    if coordinate_focus_points:
        coordinate_sentence_hint = (
            f"reuse coordinate-backed cues around {join_natural_list(coordinate_focus_points[:coordinate_focus_cap])} in the helper or first bridge"
        )

    return {
        "goal_points": ordered_goal_points,
        "goal_points_outside_anchors": goal_points_outside_anchors,
        "non_anchor_points": primary_points,
        "opening_focus_points": opening_focus_points,
        "bridge_focus_points": bridge_focus_points,
        "coordinate_focus_points": coordinate_focus_points,
        "coordinate_focus_relations": coordinate_focus_relation_texts,
        "coordinate_reuse_min": coordinate_reuse_min,
        "early_coordinate_reuse_min": early_coordinate_reuse_min,
        "focus_relations": focus_relations[:max_relations],
        "opening_sentence_hint": opening_sentence_hint,
        "helper_sentence_hint": helper_sentence_hint,
        "coordinate_sentence_hint": coordinate_sentence_hint,
        "reminder": reminder,
    }


def build_bridge_step_focus_points(
    step,
    anchor_points,
    goal_points,
    global_non_anchor_points,
    visible_points,
    max_points=4,
):
    if not isinstance(step, dict):
        return []
    anchor_set = {
        point.lower()
        for point in (anchor_points or [])
        if isinstance(point, str) and point.strip()
    }
    goal_set = {
        point.lower()
        for point in (goal_points or [])
        if isinstance(point, str) and point.strip()
    }
    global_non_anchor_set = {
        point.lower()
        for point in (global_non_anchor_points or [])
        if isinstance(point, str) and point.strip()
    }
    point_scores = {}
    point_first_seen = {}
    support_points = []
    support_points_with_anchors = []

    def add_points(relation_text, weight):
        if not isinstance(relation_text, str) or not relation_text.strip():
            return []
        local_points = []
        for point in extract_point_mentions(relation_text, visible_points or []):
            point = point.lower()
            if point in anchor_set:
                continue
            point_scores[point] = point_scores.get(point, 0) + weight
            point_first_seen.setdefault(point, len(point_first_seen))
            if point not in local_points:
                local_points.append(point)
        return local_points

    def extract_points_including_anchors(relation_text):
        if not isinstance(relation_text, str) or not relation_text.strip():
            return []
        local_points = []
        for point in extract_point_mentions(relation_text, visible_points or []):
            point = point.lower()
            if point not in local_points:
                local_points.append(point)
        return local_points

    add_points(step.get("approved_route_relation") or step.get("relation", ""), 4)
    add_points(step.get("next_target_relation", ""), 3)
    for relation in step.get("required_supports", []) or []:
        for point in extract_points_including_anchors(relation):
            if point not in support_points_with_anchors:
                support_points_with_anchors.append(point)
        for point in add_points(relation, 2):
            if point not in support_points:
                support_points.append(point)
    for relation in step.get("depends_on", []) or []:
        for point in extract_points_including_anchors(relation):
            if point not in support_points_with_anchors:
                support_points_with_anchors.append(point)
        for point in add_points(relation, 1):
            if point not in support_points:
                support_points.append(point)

    ranked_points = sorted(
        point_scores,
        key=lambda point: (
            point not in goal_set,
            point not in global_non_anchor_set,
            -point_scores[point],
            point_first_seen.get(point, 0),
            point,
        ),
    )
    selected = ranked_points[:max_points]
    if support_points and not any(point in support_points for point in selected):
        fallback_support = support_points[0]
        selected = [fallback_support] + [point for point in selected if point != fallback_support]
        selected = selected[:max_points]
    if len(selected) < 2:
        for point in support_points_with_anchors:
            if point not in selected:
                selected.append(point)
            if len(selected) >= max_points:
                break
    return selected


def enrich_bridge_steps_with_coverage_targets(plan, visible_points=None):
    if not isinstance(plan, dict) or not isinstance(plan.get("bridge_steps"), list):
        return plan
    max_focus_points = 5 if _uses_extended_coverage_budget(plan) else 4
    coverage_targets = plan.get("coverage_targets", {}) if isinstance(plan.get("coverage_targets"), dict) else {}
    anchor_points = plan.get("anchor_points") or []
    goal_points = coverage_targets.get("goal_points") or []
    global_non_anchor_points = coverage_targets.get("non_anchor_points") or []
    enriched_steps = []
    for step in plan.get("bridge_steps", []):
        if not isinstance(step, dict):
            enriched_steps.append(step)
            continue
        enriched = dict(step)
        focus_points = build_bridge_step_focus_points(
            enriched,
            anchor_points=anchor_points,
            goal_points=goal_points,
            global_non_anchor_points=global_non_anchor_points,
            visible_points=visible_points or [],
            max_points=max_focus_points,
        )
        enriched["focus_points"] = focus_points
        if focus_points:
            enriched["focus_hint"] = (
                f"mention at least one of {join_natural_list(focus_points)} while landing on this bridge relation"
            )
        else:
            enriched["focus_hint"] = ""
        enriched_steps.append(enriched)
    enriched_plan = dict(plan)
    enriched_plan["bridge_steps"] = enriched_steps
    return enriched_plan


def build_writer_sentence_duties(plan):
    if not isinstance(plan, dict):
        return ""
    coverage_targets = plan.get("coverage_targets") if isinstance(plan.get("coverage_targets"), dict) else {}
    opening_focus_points = coverage_targets.get("opening_focus_points", [])
    bridge_focus_points = coverage_targets.get("bridge_focus_points", [])
    coordinate_focus_points = coverage_targets.get("coordinate_focus_points", [])
    coordinate_focus_relations = coverage_targets.get("coordinate_focus_relations", [])
    coordinate_reuse_min = int(coverage_targets.get("coordinate_reuse_min") or 0)
    opening_focus_clause = ""
    if opening_focus_points:
        opening_focus_clause = (
            f" If possible, frame that obstacle through at least one non-anchor focus point such as "
            f"{join_natural_list(opening_focus_points)}."
        )
    helper_focus_clause = ""
    if bridge_focus_points:
        helper_focus_clause = (
            f" Keep the missing helper tied to the broader figure around {join_natural_list(bridge_focus_points)} "
            "rather than only restating the anchor frame."
        )
    helper_sentence_hint = coverage_targets.get("helper_sentence_hint", "")
    coordinate_sentence_hint = coverage_targets.get("coordinate_sentence_hint", "")
    coordinate_clause = ""
    if coordinate_focus_relations:
        cue_label = "cue" if coordinate_reuse_min == 1 else "cues"
        coordinate_clause = (
            f" Reuse at least {coordinate_reuse_min} approved coordinate {cue_label} across the early body, such as "
            f"{join_natural_list(coordinate_focus_relations[:2])}."
        )
        if coordinate_focus_points:
            coordinate_clause += (
                f" Keep those cues tied to non-anchor points like {join_natural_list(coordinate_focus_points)}."
            )
        if coordinate_sentence_hint:
            coordinate_clause += f" Prefer this shape: {coordinate_sentence_hint}."
    lines = [
        "1. Opening sentence: state the goal-side obstacle directly, using the target relation or the target-side points."
        + opening_focus_clause,
        "2. Helper sentence: restate the approved helper idea impersonally, but do not quote the plan wording word-for-word."
        + helper_focus_clause
        + coordinate_clause
        + (f" Prefer this shape: {helper_sentence_hint}." if helper_sentence_hint else ""),
        "3. Construction sentence: introduce the auxiliary point from the approved construction, but keep the wording natural rather than copying the plan string verbatim.",
    ]
    aux_direct_relations = plan.get("aux_direct_relations", [])
    if aux_direct_relations:
        lines.append(
            f"{len(lines) + 1}. Direct-aux sentence: explicitly realize the immediate construction consequences before any bridge step."
        )
    for idx, step in enumerate(plan.get("bridge_steps", []), start=1):
        if not isinstance(step, dict):
            continue
        approved_relation = step.get("approved_route_relation") or step.get("relation", "")
        required_supports = step.get("required_supports", [])
        min_support_mentions = step.get("min_support_mentions", 1 if required_supports else 0)
        support_clause = (
            f" explicitly mention at least {min_support_mentions} of these support relations: {json.dumps(required_supports, ensure_ascii=False)};"
            if required_supports else
            " explicitly mention at least one approved support relation;"
        )
        focus_clause = ""
        if step.get("focus_points"):
            focus_clause = (
                f" keep the sentence tied to {join_natural_list(step.get('focus_points', []))};"
            )
        lines.append(
            f"{len(lines) + 1}. Bridge sentence {idx}: state the approved relation '{approved_relation}',{support_clause}{focus_clause} prefer an aux-direct or previous-bridge support when possible, avoid summary labels like symmetry or midpoint property in place of those supports, paraphrase any visible given that already appears in the prefix, and explain its bridge function as '{step.get('next_target_purpose', '')}' rather than mechanically repeating the next target relation."
        )
    lines.append(
        f"{len(lines) + 1}. Final sentence: after the last bridge sentence, explicitly land on the approved goal-side finish exactly: {plan.get('goal_finish', '')}"
    )
    return "\n".join(lines)


def build_bridge_sentence_shell(step):
    if not isinstance(step, dict):
        return ""
    supports = step.get("required_supports") or step.get("depends_on", [])
    relation = step.get("approved_route_relation") or step.get("relation", "")
    next_target = step.get("next_target_relation", "")
    unlock_purpose = step.get("next_target_purpose", "")
    if supports:
        support_text = supports[0]
        if len(supports) > 1:
            support_text = f"{supports[0]} and {supports[1]}"
        shell = f"Because {support_text}, {relation}"
    else:
        shell = f"State {relation}"
    if unlock_purpose:
        shell += f", and {unlock_purpose.rstrip('.')}"
    elif next_target:
        shell += f", which prepares {next_target}"
    return shell + "."


def build_writer_bridge_contracts(plan):
    if not isinstance(plan, dict):
        return []
    contracts = []
    bridge_steps = plan.get("bridge_steps", [])
    for idx, step in enumerate(bridge_steps, start=1):
        if not isinstance(step, dict):
            continue
        contracts.append(
            {
                "sentence_type": f"bridge_{idx}",
                "relation": step.get("approved_route_relation") or step.get("relation", ""),
                "required_supports": step.get("required_supports", []),
                "min_support_mentions": step.get("min_support_mentions", 1 if step.get("required_supports") else 0),
                "focus_points": step.get("focus_points", []),
                "focus_hint": step.get("focus_hint", ""),
                "next_target_relation": step.get("next_target_relation", ""),
                "next_target_purpose": step.get("next_target_purpose", ""),
                "preferred_sentence_shell": build_bridge_sentence_shell(step),
            }
        )
    contracts.append(
        {
            "sentence_type": "goal_finish",
            "relation": plan.get("goal_finish", ""),
            "must_appear_after_bridge_count": len(bridge_steps),
            "preferred_sentence_shell": f"Therefore, {plan.get('goal_finish', '')}.",
        }
    )
    return contracts


def build_bridge_sentence_checklist(plan):
    if not isinstance(plan, dict):
        return ""
    lines = []
    for idx, step in enumerate(plan.get("bridge_steps", []), start=1):
        if not isinstance(step, dict):
            continue
        relation = step.get("approved_route_relation") or step.get("relation", "")
        required_supports = step.get("required_supports", [])
        line = f"{idx}. State '{relation}' as its own bridge sentence."
        if required_supports:
            line += f" Mention at least one of {json.dumps(required_supports, ensure_ascii=False)}."
        if step.get("focus_points"):
            line += f" Mention at least one of {join_natural_list(step.get('focus_points', []))}."
        next_target_purpose = step.get("next_target_purpose", "")
        if next_target_purpose:
            line += f" Unlock clause: '{next_target_purpose}'."
        lines.append(line)
    if plan.get("goal_finish"):
        lines.append(
            f"{len(lines) + 1}. After the last bridge sentence, end with '{plan.get('goal_finish', '')}'."
        )
    return "\n".join(lines)


def build_writer_handoff(plan):
    if not isinstance(plan, dict):
        return {}
    handoff_steps = []
    for step in plan.get("bridge_steps", []):
        if not isinstance(step, dict):
            continue
        handoff_steps.append(
            {
                "relation": step.get("approved_route_relation") or step.get("relation", ""),
                "required_supports": step.get("required_supports", []),
                "min_support_mentions": step.get("min_support_mentions", 1 if step.get("required_supports") else 0),
                "focus_points": step.get("focus_points", []),
                "unlock_purpose": step.get("next_target_purpose", ""),
                "preferred_sentence_shell": build_bridge_sentence_shell(step),
            }
        )
    coverage_targets = plan.get("coverage_targets", {}) if isinstance(plan.get("coverage_targets"), dict) else {}
    return {
        "goal_bottleneck": plan.get("goal_bottleneck", ""),
        "helper_idea": plan.get("helper_idea", ""),
        "construction": plan.get("construction", ""),
        "aux_direct_relations": plan.get("aux_direct_relations", []),
        "bridge_steps": handoff_steps,
        "goal_finish": plan.get("goal_finish", ""),
        "opening_focus_points": coverage_targets.get("opening_focus_points", []),
        "bridge_focus_points": coverage_targets.get("bridge_focus_points", []),
        "coordinate_focus_points": coverage_targets.get("coordinate_focus_points", []),
        "coordinate_focus_relations": coverage_targets.get("coordinate_focus_relations", []),
        "coordinate_reuse_min": coverage_targets.get("coordinate_reuse_min", 0),
        "opening_sentence_hint": coverage_targets.get("opening_sentence_hint", ""),
        "helper_sentence_hint": coverage_targets.get("helper_sentence_hint", ""),
        "coordinate_sentence_hint": coverage_targets.get("coordinate_sentence_hint", ""),
    }


def build_writer_sentence_blueprints(plan):
    if not isinstance(plan, dict):
        return []
    coverage_targets = plan.get("coverage_targets") if isinstance(plan.get("coverage_targets"), dict) else {}
    blueprints = [
        {
            "sentence_type": "opening",
            "goal_finish": plan.get("goal_finish", ""),
            "coverage_points": coverage_targets.get("opening_focus_points", []),
            "preferred_focus_hint": coverage_targets.get("opening_sentence_hint", ""),
            "instruction": (
                "State the obstacle directly in goal-side terms without re-describing the injected prefix. "
                "When possible, anchor that obstacle in one of the listed non-anchor coverage points instead of narrating only the anchor triangle."
            ),
        },
        {
            "sentence_type": "helper",
            "coverage_points": coverage_targets.get("bridge_focus_points", []),
            "preferred_focus_hint": coverage_targets.get("helper_sentence_hint", ""),
            "coordinate_focus_points": coverage_targets.get("coordinate_focus_points", []),
            "coordinate_focus_relations": coverage_targets.get("coordinate_focus_relations", []),
            "instruction": (
                "State the missing helper mechanism impersonally and concretely, keep it tied to the broader visible figure listed under the coverage points, and start reusing the approved non-anchor coordinate cues instead of dropping back to anchor-only language."
            ),
        },
        {
            "sentence_type": "construction",
            "instruction": "Introduce the approved auxiliary construction in natural language.",
        },
    ]
    if plan.get("aux_direct_relations"):
        blueprints.append(
            {
                "sentence_type": "aux_direct",
                "relation_sequence": plan.get("aux_direct_relations", []),
                "instruction": "Realize the direct auxiliary consequences before any bridge sentence.",
            }
        )
    for idx, step in enumerate(plan.get("bridge_steps", []), start=1):
        if not isinstance(step, dict):
            continue
        support_sequence = step.get("required_supports") or step.get("depends_on", [])
        blueprints.append(
            {
                "sentence_type": f"bridge_{idx}",
                "recommended_order": [
                    "support",
                    "approved_relation",
                    "unlock_purpose",
                ],
                "support_relation": support_sequence[0] if support_sequence else "",
                "fallback_support_relations": support_sequence[1:] if len(support_sequence) > 1 else [],
                "coverage_points": step.get("focus_points", []),
                "preferred_focus_hint": step.get("focus_hint", ""),
                "approved_relation": step.get("approved_route_relation") or step.get("relation", ""),
                "next_target_relation": step.get("next_target_relation", ""),
                "next_target_purpose": step.get("next_target_purpose", ""),
                "preferred_sentence_shell": build_bridge_sentence_shell(step),
                "forbid_new_claims": True,
                "instruction": (
                    "Prefer a sentence of the form 'Because <support>, <approved relation>, and <unlock purpose>'. "
                    "Mention the exact next target relation only when it clarifies the bridge, keep the sentence tied to the listed coverage points when they are non-empty, and do not add a fresh geometric claim outside the approved support/relation/unlock bundle."
                ),
            }
        )
    blueprints.append(
        {
            "sentence_type": "goal_finish",
            "approved_relation": plan.get("goal_finish", ""),
            "instruction": "Use one final sentence that explicitly states the approved goal_finish relation and stops there.",
        }
    )
    return blueprints


def build_prefix_sentences(plan, point_coords):
    sentences = [
        build_anchor_sentence(plan, point_coords),
        build_overview_sentence(plan),
        build_coordinate_hint_sentence(plan),
    ]
    visible_relation_sentence = build_visible_relation_sentence(plan)
    if visible_relation_sentence:
        sentences.append(visible_relation_sentence)
    return sentences


def build_injected_prefix_block(plan, point_coords):
    return " ".join(build_prefix_sentences(plan, point_coords))


__all__ = [
    "anonymize_new_point_mentions",
    "build_anchor_sentence",
    "build_bridge_sentence_checklist",
    "build_bridge_sentence_shell",
    "build_bridge_step_focus_points",
    "build_canonical_bridge_unlock",
    "build_coordinate_hint_sentence",
    "build_injected_prefix_block",
    "build_instruction_text",
    "build_overview_sentence",
    "build_plan_coverage_targets",
    "build_prefix_coverage_notes",
    "build_prefix_reuse_guidance",
    "build_prefix_sentences",
    "build_relation_reuse_hint",
    "build_step_unlock_purpose",
    "build_visible_relation_sentence",
    "build_writer_bridge_contracts",
    "build_writer_handoff",
    "build_writer_sentence_blueprints",
    "build_writer_sentence_duties",
    "enrich_bridge_steps_with_coverage_targets",
    "enrich_bridge_steps_with_targets",
    "format_tagged_point",
    "join_natural_list",
]
