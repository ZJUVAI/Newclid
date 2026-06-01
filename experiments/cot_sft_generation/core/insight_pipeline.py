#!/usr/bin/env python3
"""
Planner and writer contracts for the insight_v1 CoT SFT mainline.
"""

from __future__ import annotations

import json
import re

try:
    from .geometry_text import (
        build_aux_direct_consequences,
        build_canonical_construction,
        build_public_problem_text,
        extract_aux_new_points,
        extract_point_mentions,
        extract_problem_goal,
        extract_visible_point_names,
        infer_relation_type_from_text,
        normalize_relation_surface,
        parse_goal_expression,
        relation_keyword_present,
        relations_semantically_match,
    )
    from .insight_schema import INSIGHT_GAP_TYPES, INSIGHT_V1, InsightPlan
except ImportError:  # pragma: no cover - script execution path
    from geometry_text import (  # type: ignore
        build_aux_direct_consequences,
        build_canonical_construction,
        build_public_problem_text,
        extract_aux_new_points,
        extract_point_mentions,
        extract_problem_goal,
        extract_visible_point_names,
        infer_relation_type_from_text,
        normalize_relation_surface,
        parse_goal_expression,
        relation_keyword_present,
        relations_semantically_match,
    )
    from insight_schema import INSIGHT_GAP_TYPES, INSIGHT_V1, InsightPlan  # type: ignore


_RULE_LEAK_RE = re.compile(r"(?:\[\d{3}\]|\bAR\b|\br\d+\b|\bproof\b|\bhidden\b)", re.IGNORECASE)
_INTERNAL_REF_RE = re.compile(
    r"\b(?:visible_facts|image_scan|aux_immediate_effects|evidence_windows|slots|plan|bridge_chain)\[\d+\]"
)
_AUX_POINT_TEXT_RE = re.compile(r"\bconstruct\s+point\s+([a-z]\w*)\b", re.IGNORECASE)


def _extract_json_object(output_text: str):
    if not output_text:
        return None
    text = output_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\})", text, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None


def _extract_aux_point_names_from_text(*texts: str) -> list[str]:
    point_names = []
    for text in texts:
        if not isinstance(text, str) or not text.strip():
            continue
        point_names.extend(match.lower() for match in _AUX_POINT_TEXT_RE.findall(text))
    return list(dict.fromkeys(point_names))


def _normalize_geometry_math_text(text: str) -> str:
    normalized = str(text or "")
    normalized = re.sub(r"\\\((.*?)\\\)", r" \1 ", normalized)
    normalized = normalized.replace("$", " ")
    normalized = re.sub(r"\\overline\s*\{([^}]+)\}", r" \1 ", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\\triangle\b", " triangle ", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\\perp\b", " perpendicular ", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\\parallel\b", " parallel ", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"[{}]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip().lower()
    return normalized


def _text_semantically_mentions_relation(text: str, relation: str, point_names: list[str]) -> bool:
    normalized_text = normalize_relation_surface(text or "").lower()
    normalized_relation = normalize_relation_surface(relation or "").lower()
    math_text = _normalize_geometry_math_text(text or "")
    math_relation = _normalize_geometry_math_text(relation or "")
    if not normalized_text or not normalized_relation:
        return False
    if normalized_relation in normalized_text:
        return True
    if math_relation and math_relation in math_text:
        return True
    if relations_semantically_match(text, relation, point_names):
        return True
    for sentence in re.split(r"[.!?]+", text):
        sentence = sentence.strip()
        if not sentence:
            continue
        normalized_sentence = normalize_relation_surface(sentence).lower()
        math_sentence = _normalize_geometry_math_text(sentence)
        if normalized_relation in normalized_sentence:
            return True
        if math_relation and math_relation in math_sentence:
            return True
        if relations_semantically_match(sentence, relation, point_names):
            return True
        relation_type = infer_relation_type_from_text(relation)
        if relation_type:
            sentence_lower = sentence.lower()
            relation_points = extract_point_mentions(relation, point_names)
            sentence_points = extract_point_mentions(sentence, point_names)
            if relation_points and relation_points.issubset(sentence_points):
                keyword_variants = {
                    "midpoint": ["midpoint", "equal parts", "divide", "divides", "split", "splits"],
                    "parallel": ["parallel"],
                    "perpendicular": ["perpendicular", "right angle", "right angles"],
                    "cyclic": ["cyclic", "concyclic", "circle", "same circle", "circle through"],
                    "collinear": ["collinear", "straight line", "line through"],
                }
                if any(
                    keyword in sentence_lower
                    for keyword in keyword_variants.get(relation_type, [])
                ):
                    return True
        equality_match = re.fullmatch(r"([a-z]{2}) equals ([a-z]{2})", normalized_relation)
        if equality_match:
            seg_a, seg_b = equality_match.groups()
            if f"{seg_a} = {seg_b}" in math_sentence or f"{seg_b} = {seg_a}" in math_sentence:
                return True
        perpendicular_match = re.fullmatch(r"line ([a-z]{2}) is perpendicular to line ([a-z]{2})", normalized_relation)
        if perpendicular_match:
            seg_a, seg_b = perpendicular_match.groups()
            if (
                f"{seg_a} perpendicular {seg_b}" in math_sentence
                or f"{seg_b} perpendicular {seg_a}" in math_sentence
            ):
                return True
        parallel_match = re.fullmatch(r"line ([a-z]{2}) is parallel to line ([a-z]{2})", normalized_relation)
        if parallel_match:
            seg_a, seg_b = parallel_match.groups()
            if (
                f"{seg_a} parallel {seg_b}" in math_sentence
                or f"{seg_b} parallel {seg_a}" in math_sentence
            ):
                return True
    return False


def _clean_text(
    value,
    field_name: str,
    min_chars: int = 6,
    max_chars: int = 320,
):
    text = str(value or "").strip()
    if len(text) < min_chars:
        return False, f"{field_name} is too short", None
    if len(text) > max_chars:
        return False, f"{field_name} is too long", None
    if _RULE_LEAK_RE.search(text):
        return False, f"{field_name} leaks hidden proof markers", None
    if _INTERNAL_REF_RE.search(text):
        return False, f"{field_name} contains internal reference syntax", None
    return True, "ok", normalize_relation_surface(text)


def _gap_type_matches_goal_family(goal_gap_type: str, visible_goal: str) -> bool:
    goal_family = str(parse_goal_expression(visible_goal or "").get("predicate") or "").lower()
    compatible = {
        "eqangle": {"angle_transfer", "cyclic_trigger", "similarity_bridge", "congruence_bridge"},
        "eqratio": {"ratio_transfer", "similarity_bridge", "midpoint_parallel_trigger"},
        "simtri": {"similarity_bridge", "ratio_transfer", "angle_transfer"},
        "simtrir": {"similarity_bridge", "ratio_transfer", "angle_transfer"},
        "contri": {"congruence_bridge", "midpoint_parallel_trigger", "cyclic_trigger"},
        "contrir": {"congruence_bridge", "midpoint_parallel_trigger", "cyclic_trigger"},
        "cyclic": {"cyclic_trigger", "angle_transfer"},
    }
    return goal_gap_type in compatible.get(goal_family, INSIGHT_GAP_TYPES)


def build_insight_plan_json_example():
    return json.dumps(
        {
            "visible_facts": [
                "ab equals ac",
                "angle ab/bc equals angle bc/ac",
            ],
            "image_scan": [
                "points b, d, and f appear nearly collinear",
                "line ac and line df look like they can transfer one angle",
            ],
            "goal_gap_type": "angle_transfer",
            "goal_gap_text": "the visible givens still do not transfer the angle at the b-side onto the d-side and e-side in one local frame",
            "required_aux_effect": "a, c, d, f are concyclic",
            "aux_construction": "construct point f such that a, c, d, f are concyclic and b, d, f are collinear",
            "aux_selection_reason": "this helper is appropriate because the cyclic effect creates the missing angle carrier that the slot requires before the old b-d side can be reused",
            "stage_order": [
                "first create the cyclic angle carrier through a, c, d, and f",
                "then use the collinearity through b, d, and f to reconnect that carrier to the old figure",
            ],
            "bonus_post_aux_tail": [
                "Once that carrier exists, the last transfer back to the target angle becomes short.",
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


def build_insight_plan_prompt(
    record,
    aux_part: str,
    visible_fact_relations: list[str],
    image_scan_candidates: list[str],
    insight_slots: dict,
):
    public_problem = build_public_problem_text(record)
    visible_goal = extract_problem_goal(record)
    canonical_aux_construction = build_canonical_construction(aux_part or "")
    return (
        "You are planning an insight-first geometry CoT sample.\n\n"
        "[Visible Inputs]\n"
        "The final student will only see the image and the public problem text.\n"
        f"{public_problem}\n\n"
        "[Visible Goal]\n"
        f"{visible_goal}\n\n"
        "[Visible Facts]\n"
        f"{json.dumps(visible_fact_relations, ensure_ascii=False, indent=2)}\n\n"
        "[Visible Image Cues]\n"
        f"{json.dumps(image_scan_candidates, ensure_ascii=False, indent=2)}\n\n"
        "[Approved Auxiliary Construction]\n"
        "This is the canonical auxiliary construction already chosen in the teacher record. Keep the geometry consistent with it.\n"
        f"{canonical_aux_construction}\n\n"
        "[Insight Slots]\n"
        "These slots come from the hidden proof DAG. Reuse them as internal anchors, but do not quote proof ids, rule names, or hidden-route language.\n"
        f"{json.dumps(insight_slots, ensure_ascii=False, indent=2)}\n\n"
        "[Task]\n"
        "Return exactly one JSON object describing only the visible setup, the gap, the helper effect that is missing, and why the given auxiliary construction is the right move.\n\n"
        "[Critical Requirements]\n"
        "- Keep the plan insight-first. Do not write a full closure route.\n"
        "- `required_aux_effect` must stay aligned with the slot-derived effect.\n"
        "- `aux_construction` should describe the approved auxiliary construction naturally, without changing the geometry.\n"
        "- `aux_selection_reason` must explain only why this helper is appropriate; it must reuse the slot information instead of inventing a different hidden relation or expanding into a proof route.\n"
        "- If the auxiliary construction introduces multiple new points or multiple staged facts, include `stage_order`.\n"
        "- `bonus_post_aux_tail` is optional; if you include it, keep it local to what the helper opens after construction.\n"
        "- Do not list the construction's direct consequences one by one; keep them script-local.\n"
        "- Do not mention proof ids, rule names, hidden hints, or theorem catalogs.\n\n"
        "[Output Schema Example]\n"
        f"{build_insight_plan_json_example()}\n"
    )


def build_insight_write_prompt(record, plan: dict):
    public_problem = build_public_problem_text(record)
    visible_goal = extract_problem_goal(record)
    visible_plan = {
        "visible_facts": plan.get("visible_facts", []),
        "image_scan": plan.get("image_scan", []),
        "goal_gap_text": plan.get("goal_gap_text", ""),
        "canonical_aux_construction": plan.get("canonical_aux_construction") or plan.get("aux_construction", ""),
        "aux_construction": plan.get("aux_construction", ""),
        "aux_selection_reason": plan.get("aux_selection_reason", ""),
        "stage_order": plan.get("stage_order"),
        "bonus_post_aux_tail": plan.get("bonus_post_aux_tail"),
    }
    return (
        "Write one insight-first geometry thinking trace.\n\n"
        "[Visible Problem]\n"
        f"{public_problem}\n\n"
        "[Visible Goal]\n"
        f"{visible_goal}\n\n"
        "[Approved Insight Plan]\n"
        f"{json.dumps(visible_plan, ensure_ascii=False, indent=2)}\n\n"
        "[Writing Rules]\n"
        "- Output plain text only, without tags.\n"
        "- Focus on what is visible, what is missing, what effect the helper must create, and therefore which auxiliary construction to choose.\n"
        "- Keep the post-construction boundary explicit: the body may describe the visible gap, the approved auxiliary construction, the construction's direct local effect, and cautious local unlock statements that stay near that helper effect.\n"
        "- Do not claim that a remote goal-side object is already connected, transferable, comparable, or resolved unless that supporting relation is explicitly stated in the body itself.\n"
        "- You do not need to quote `required_aux_effect` verbatim; describing the approved helper relation or its immediate geometric payoff is enough.\n"
        "- You may continue after the construction to explain what the helper unlocks locally, but do not turn that into a full hidden proof retelling.\n"
        "- Do not enumerate direct construction consequences one by one.\n"
        "- Do not retell the full proof. Do not list theorems. Do not mention proof ids or rule names.\n"
        "- Keep the tone impersonal and visible-only.\n"
        "- Allowed example: \"this creates a cyclic angle carrier around a, c, d, and f.\"\n"
        "- Allowed example: \"this gives one local frame that can be reused later.\"\n"
        "- Forbidden example: \"so the angle at e can now be transferred\" when e is only reachable through a later hidden bridge not stated in the body.\n"
    )


def build_insight_plan_retry_feedback(message: str, aux_part: str | None = None) -> str:
    del aux_part
    return (
        "Revise the JSON so it stays insight-first and slot-grounded.\n"
        f"Validator feedback: {message}\n"
        "Keep the same auxiliary construction, keep required_aux_effect aligned with the slots, and do not turn bridge checkpoints into a full proof."
    )


def build_insight_writer_retry_feedback(message: str, plan: dict | None = None) -> str:
    del plan
    return (
        "Rewrite the body so it stays visible-only and insight-first.\n"
        f"Validator feedback: {message}\n"
        "Explain the gap and the helper choice, but do not retell the full hidden route."
    )


def build_scripted_insight_plan(
    record,
    aux_part: str,
    insight_slots: dict,
    visible_text_facts,
    image_scan_candidates: list[str],
):
    aux_points = {
        str(point).lower()
        for point in extract_aux_new_points(aux_part or "")
        if isinstance(point, str) and point.strip()
    }
    visible_facts = []
    for item in visible_text_facts or []:
        relation = item.get("relation") if isinstance(item, dict) else item
        if isinstance(relation, str) and relation.strip() and relation not in visible_facts:
            visible_facts.append(relation.strip())
        if len(visible_facts) >= 4:
            break

    image_scan = [
        item
        for item in image_scan_candidates
        if isinstance(item, str) and item.strip() and not extract_point_mentions(item, list(aux_points))
    ][:3]
    visible_goal = extract_problem_goal(record)
    goal_points = parse_goal_expression(visible_goal).get("points", [])
    goal_point_text = ", ".join(goal_points[:4]) if goal_points else "the target"
    required_aux_effect = normalize_relation_surface(insight_slots.get("required_aux_effect", ""))
    first_bridge = normalize_relation_surface(insight_slots.get("first_bridge_checkpoint", ""))
    pre_goal = normalize_relation_surface(insight_slots.get("pre_goal_checkpoint", ""))
    construction = build_canonical_construction(aux_part or "")
    direct_consequences = [
        normalize_relation_surface(item)
        for item in build_aux_direct_consequences(aux_part or "")
        if isinstance(item, str) and item.strip()
    ]
    if not required_aux_effect and direct_consequences:
        required_aux_effect = direct_consequences[0]

    goal_gap_type = insight_slots.get("goal_gap_type") or "midpoint_parallel_trigger"
    goal_gap_text = (
        f"the visible givens still do not create the right {goal_gap_type.replace('_', ' ')} "
        f"around {goal_point_text}"
    )
    aux_selection_reason = (
        f"the helper is chosen because {required_aux_effect} is the first effect that matters, "
        f"then {first_bridge} reconnects that effect before {pre_goal} prepares the goal side"
    ).strip()
    stage_order = insight_slots.get("stage_order")
    bonus_tail = None
    if first_bridge and pre_goal and first_bridge != pre_goal:
        bonus_tail = [
            f"After that, {first_bridge} is enough to reopen the last move toward {pre_goal}.",
        ]

    return InsightPlan(
        visible_facts=visible_facts,
        image_scan=image_scan,
        goal_gap_type=goal_gap_type,
        goal_gap_text=goal_gap_text,
        required_aux_effect=required_aux_effect,
        aux_construction=construction,
        aux_selection_reason=aux_selection_reason,
        stage_order=stage_order,
        bonus_post_aux_tail=bonus_tail,
    ).to_dict()


def _canonical_relation_list(values, min_items: int, field_name: str):
    if not isinstance(values, list):
        return False, f"{field_name} must be a list", None
    cleaned = []
    for idx, item in enumerate(values):
        ok, message, text = _clean_text(item, f"{field_name}[{idx}]", min_chars=4, max_chars=220)
        if not ok:
            return False, message, None
        cleaned.append(text)
    if len(cleaned) < min_items:
        return False, f"{field_name} must contain at least {min_items} items", None
    return True, "ok", cleaned


def validate_insight_plan_response(
    output_text,
    point_coords,
    visible_goal="",
    aux_part=None,
    coordinate_candidates=None,
    sanitized_rest=None,
    visible_premise_summaries=None,
    visible_text_facts=None,
    insight_slots=None,
):
    del coordinate_candidates, sanitized_rest, visible_premise_summaries
    plan = output_text if isinstance(output_text, dict) else _extract_json_object(output_text)
    if not isinstance(plan, dict):
        return False, "Planner must return a single JSON object", None
    if not isinstance(insight_slots, dict):
        return False, "Insight slots are required for insight_v1 validation", None

    required_keys = [
        "visible_facts",
        "image_scan",
        "goal_gap_type",
        "goal_gap_text",
        "required_aux_effect",
        "aux_construction",
        "aux_selection_reason",
    ]
    missing = [key for key in required_keys if key not in plan]
    if missing:
        return False, f"Insight plan missing keys: {missing}", None

    visible_points = extract_visible_point_names(point_coords or {})
    aux_points = {
        str(point).lower()
        for point in extract_aux_new_points(aux_part or "")
        if isinstance(point, str) and point.strip()
    }
    goal_points = {
        str(point).lower()
        for point in (parse_goal_expression(visible_goal or "").get("points") or [])
        if isinstance(point, str) and point.strip()
    }
    reference_visible_relations = []
    for item in visible_text_facts or []:
        relation = item.get("relation") if isinstance(item, dict) else item
        if isinstance(relation, str) and relation.strip():
            reference_visible_relations.append(normalize_relation_surface(relation))

    ok, message, cleaned_visible_facts = _canonical_relation_list(
        plan.get("visible_facts"),
        min_items=1,
        field_name="visible_facts",
    )
    if not ok:
        return False, message, None
    if reference_visible_relations and any(
        not any(relations_semantically_match(item, candidate, visible_points) for candidate in reference_visible_relations)
        for item in cleaned_visible_facts
    ):
        return False, "visible_facts must stay grounded in the public visible facts", None

    ok, message, cleaned_image_scan = _canonical_relation_list(
        plan.get("image_scan"),
        min_items=1,
        field_name="image_scan",
    )
    if not ok:
        return False, message, None
    for item in cleaned_image_scan:
        if extract_point_mentions(item, list(aux_points)):
            return False, "image_scan must not mention auxiliary points before construction", None

    slot_gap_type = str(insight_slots.get("goal_gap_type") or "").strip()
    goal_gap_type = str(plan.get("goal_gap_type") or "").strip() or slot_gap_type or "midpoint_parallel_trigger"
    goal_gap_type_diagnostics = []
    if goal_gap_type not in INSIGHT_GAP_TYPES:
        goal_gap_type_diagnostics.append("unsupported")
    elif not _gap_type_matches_goal_family(goal_gap_type, visible_goal):
        goal_gap_type_diagnostics.append("goal_family_conflict")
    if slot_gap_type and goal_gap_type != slot_gap_type:
        goal_gap_type_diagnostics.append("slot_mismatch")

    ok, message, goal_gap_text = _clean_text(plan.get("goal_gap_text"), "goal_gap_text", min_chars=18, max_chars=320)
    if not ok:
        return False, message, None
    if goal_points and len(extract_point_mentions(goal_gap_text, list(goal_points))) < min(2, len(goal_points)):
        return False, "goal_gap_text must mention the concrete goal-side objects", None

    ok, message, required_aux_effect = _clean_text(
        plan.get("required_aux_effect"),
        "required_aux_effect",
        min_chars=6,
        max_chars=220,
    )
    if not ok:
        return False, message, None
    slot_effect = normalize_relation_surface(insight_slots.get("required_aux_effect", ""))
    if slot_effect and not relations_semantically_match(required_aux_effect, slot_effect, visible_points + list(aux_points)):
        return False, "required_aux_effect must stay aligned with the slot-derived effect", None
    expected_effects = [
        normalize_relation_surface(item)
        for item in build_aux_direct_consequences(aux_part or "")
        if isinstance(item, str) and item.strip()
    ]
    if expected_effects and not any(
        relations_semantically_match(required_aux_effect, candidate, visible_points + list(aux_points))
        for candidate in expected_effects
    ):
        return False, "required_aux_effect must match a direct consequence of the construction", None

    ok, message, aux_construction = _clean_text(
        plan.get("aux_construction"),
        "aux_construction",
        min_chars=12,
        max_chars=320,
    )
    if not ok:
        return False, message, None
    canonical_construction = normalize_relation_surface(build_canonical_construction(aux_part or ""))
    if canonical_construction:
        for point_name in aux_points:
            if point_name not in aux_construction.lower():
                return False, f"aux_construction must mention auxiliary point '{point_name}'", None
    aux_point_scope = visible_points + list(aux_points)
    aux_construction_matches_canonical = True
    if canonical_construction:
        aux_construction_matches_canonical = relations_semantically_match(
            aux_construction,
            canonical_construction,
            aux_point_scope,
        )
        if not aux_construction_matches_canonical and expected_effects:
            aux_construction_matches_canonical = all(
                relations_semantically_match(aux_construction, candidate, aux_point_scope)
                for candidate in expected_effects
            )

    ok, message, aux_selection_reason = _clean_text(
        plan.get("aux_selection_reason"),
        "aux_selection_reason",
        min_chars=24,
        max_chars=360,
    )
    if not ok:
        return False, message, None
    slot_reference_text = " ".join(
        str(insight_slots.get(key) or "")
        for key in ("required_aux_effect", "first_bridge_checkpoint", "pre_goal_checkpoint")
    )
    slot_reference_points = extract_point_mentions(slot_reference_text, visible_points + list(aux_points))
    if slot_reference_points and not extract_point_mentions(aux_selection_reason, list(slot_reference_points)):
        return False, "aux_selection_reason must reuse the slot checkpoints instead of inventing a new hidden relation", None

    cleaned_stage_order = None
    raw_stage_order = plan.get("stage_order")
    if raw_stage_order is not None:
        ok, message, cleaned_stage_order = _canonical_relation_list(
            raw_stage_order,
            min_items=1,
            field_name="stage_order",
        )
        if not ok:
            return False, message, None
    if len(aux_points) > 1 and not cleaned_stage_order:
        return False, "multi-point auxiliary plans must include stage_order", None

    cleaned_bonus_tail = None
    raw_bonus_tail = plan.get("bonus_post_aux_tail")
    if raw_bonus_tail is not None:
        ok, message, cleaned_bonus_tail = _canonical_relation_list(
            raw_bonus_tail,
            min_items=1,
            field_name="bonus_post_aux_tail",
        )
        if not ok:
            return False, message, None

    cleaned_plan = InsightPlan(
        visible_facts=cleaned_visible_facts,
        image_scan=cleaned_image_scan,
        goal_gap_type=goal_gap_type,
        goal_gap_text=goal_gap_text,
        required_aux_effect=required_aux_effect,
        aux_construction=aux_construction,
        aux_selection_reason=aux_selection_reason,
        stage_order=cleaned_stage_order,
        bonus_post_aux_tail=cleaned_bonus_tail,
    ).to_dict()
    cleaned_plan["goal_family"] = parse_goal_expression(visible_goal or "").get("predicate") or ""
    cleaned_plan["insight_slots"] = insight_slots
    cleaned_plan["canonical_aux_construction"] = canonical_construction
    cleaned_plan["canonical_aux_direct_consequences"] = expected_effects
    cleaned_plan["aux_construction_matches_canonical"] = aux_construction_matches_canonical
    if not aux_construction_matches_canonical:
        cleaned_plan["aux_construction_audit_signal"] = "aux_construction_mismatch"
    if goal_gap_type_diagnostics:
        cleaned_plan["goal_gap_type_diagnostics"] = goal_gap_type_diagnostics
    return True, "Valid insight plan", cleaned_plan


def build_scripted_insight_writer_body(plan: dict):
    sentences = []
    image_scan = [item for item in (plan.get("image_scan") or []) if isinstance(item, str) and item.strip()]
    visible_facts = [item for item in (plan.get("visible_facts") or []) if isinstance(item, str) and item.strip()]
    if image_scan:
        lead = image_scan[0]
        if visible_facts:
            lead = f"{lead}, and {visible_facts[0]} remains one stable visible fact."
        sentences.append(f"From the visible figure, {lead}")
    elif visible_facts:
        sentences.append(f"One usable visible fact is that {visible_facts[0]}")

    sentences.append(f"The real gap is that {plan.get('goal_gap_text', '')}")
    sentences.append(f"So the helper should first create {plan.get('required_aux_effect', '')}")
    sentences.append(f"{plan.get('aux_construction', '').capitalize()}.")

    reason = str(plan.get("aux_selection_reason") or "").strip()
    if reason:
        sentences.append(reason[0].upper() + reason[1:] if len(reason) > 1 else reason.upper())

    for tail in (plan.get("bonus_post_aux_tail") or [])[:2]:
        if isinstance(tail, str) and tail.strip():
            sentences.append(tail.strip())
    return " ".join(sentence.strip().rstrip(".") + "." for sentence in sentences if sentence and sentence.strip())


def validate_insight_writer_body(output_text: str, visible_goal="", injected_prefix="", plan=None):
    del injected_prefix, visible_goal
    body = str(output_text or "").strip()
    if not body:
        return False, "Writer body is empty"
    if body.startswith("<thinking>") or body.endswith("</thinking>"):
        return False, "Writer body must be plain text only"
    if _RULE_LEAK_RE.search(body):
        return False, "Writer body must not mention proof ids, rule names, or hidden proof language"
    if _INTERNAL_REF_RE.search(body):
        return False, "Writer body must not mention internal plan references"
    if re.search(r"\b(I|we|We|I'll|we'll)\b", body):
        return False, "Writer body must stay impersonal"

    if isinstance(plan, dict):
        required_effect = str(plan.get("required_aux_effect") or "").strip()
        construction = str(plan.get("aux_construction") or "").strip()
        canonical_construction = str(plan.get("canonical_aux_construction") or construction).strip()
        canonical_effects = [
            str(item).strip()
            for item in (plan.get("canonical_aux_direct_consequences") or [])
            if isinstance(item, str) and item.strip()
        ]
        if required_effect and not relation_keyword_present(required_effect):
            required_effect = ""
        aux_point_names = _extract_aux_point_names_from_text(canonical_construction, construction)
        plan_points = sorted(
            set(aux_point_names)
            | set(re.findall(r"\b[a-z]\b", " ".join([required_effect, construction, canonical_construction, str(plan.get("goal_gap_text") or "")]).lower()))
        )
        for point_name in aux_point_names:
            if point_name.lower() not in body.lower():
                return False, f"Writer body must mention auxiliary point '{point_name.lower()}'"
        helper_anchor_candidates = [candidate for candidate in [canonical_construction, required_effect] + canonical_effects if candidate]
        helper_match = any(
            _text_semantically_mentions_relation(body, candidate, plan_points)
            for candidate in helper_anchor_candidates
        )
        if not helper_match:
            return False, "Writer body must describe the approved helper relation or one immediate geometric effect of it"
        if str(plan.get("goal_gap_text") or "").strip():
            goal_points = sorted(
                set(re.findall(r"\b[a-z]\w*\b", str(plan.get("goal_gap_text") or "").lower()))
            )
            if goal_points and not any(point in body.lower() for point in goal_points):
                return False, "Writer body must stay anchored on the stated gap objects"
    return True, "Valid insight writer body"


__all__ = [
    "INSIGHT_V1",
    "build_insight_plan_prompt",
    "build_insight_plan_retry_feedback",
    "build_insight_write_prompt",
    "build_insight_writer_retry_feedback",
    "build_scripted_insight_plan",
    "build_scripted_insight_writer_body",
    "validate_insight_plan_response",
    "validate_insight_writer_body",
]
