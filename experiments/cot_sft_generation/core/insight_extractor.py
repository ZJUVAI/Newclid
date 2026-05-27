#!/usr/bin/env python3
"""
Script-side DAG extraction for the insight_v1 mainline.
"""

from __future__ import annotations

import re
from collections import defaultdict, deque

try:
    from .geometry_text import (
        build_aux_direct_consequences,
        extract_aux_new_points,
        normalize_relation_surface,
        parse_aux_clauses,
        parse_goal_expression,
        relations_semantically_match,
        split_formal_relation_chain,
    )
    from .insight_schema import (
        INSIGHT_GAP_TYPES,
        InsightEvidenceWindow,
        InsightSlots,
    )
    from .proof_dag import ProofDAG, ProofStep
except ImportError:  # pragma: no cover - script execution path
    from geometry_text import (  # type: ignore
        build_aux_direct_consequences,
        extract_aux_new_points,
        normalize_relation_surface,
        parse_aux_clauses,
        parse_goal_expression,
        relations_semantically_match,
        split_formal_relation_chain,
    )
    from insight_schema import INSIGHT_GAP_TYPES, InsightEvidenceWindow, InsightSlots  # type: ignore
    from proof_dag import ProofDAG, ProofStep  # type: ignore


_AUX_STEP_ID_RE = re.compile(r"\[(\d{3})\]")
_POINT_RE = re.compile(r"[a-z]\w*")


def _step_points(step: ProofStep | None) -> list[str]:
    if step is None:
        return []
    points = []
    for token in step.args:
        token_text = str(token or "").strip().lower()
        if _POINT_RE.fullmatch(token_text):
            points.append(token_text)
    return list(dict.fromkeys(points))


def _step_relation(step: ProofStep | None) -> str:
    if step is None:
        return ""
    return normalize_relation_surface(step.natural_language or step.raw_line)


def _relation_matches(text_a: str, text_b: str, point_names: list[str]) -> bool:
    normalized_a = normalize_relation_surface(text_a)
    normalized_b = normalize_relation_surface(text_b)
    if not normalized_a or not normalized_b:
        return False
    if normalized_a.lower() == normalized_b.lower():
        return True
    return relations_semantically_match(normalized_a, normalized_b, point_names)


def _build_children_index(dag: ProofDAG, ancestors: set[str]) -> dict[str, set[str]]:
    children_by_dep: dict[str, set[str]] = defaultdict(set)
    for step_id in ancestors:
        step = dag.get(step_id)
        if step is None:
            continue
        for dep_id in step.deps:
            if dep_id in ancestors:
                children_by_dep[dep_id].add(step_id)
    return children_by_dep


def _descendants_from(
    children_by_dep: dict[str, set[str]],
    seed_ids: set[str],
    allowed_step_ids: set[str],
) -> set[str]:
    descendants: set[str] = set()
    queue = deque(seed_ids)
    while queue:
        step_id = queue.popleft()
        if step_id in descendants or step_id not in allowed_step_ids:
            continue
        descendants.add(step_id)
        for child_id in children_by_dep.get(step_id, ()):
            if child_id not in descendants:
                queue.append(child_id)
    return descendants


def _extract_aux_relation_entries(aux_part: str) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for clause in parse_aux_clauses(aux_part or ""):
        body = str(clause.get("body") or "")
        relation_facts = split_formal_relation_chain(body)
        step_ids = _AUX_STEP_ID_RE.findall(body)
        for relation_index, fact in enumerate(relation_facts):
            tokens = fact.split()
            predicate = tokens[0].lower() if tokens else "aux"
            points = [
                token.lower()
                for token in tokens[1:]
                if _POINT_RE.fullmatch(token.lower())
            ]
            entries.append(
                {
                    "step_id": step_ids[relation_index] if relation_index < len(step_ids) else f"aux_{len(entries):03d}",
                    "relation": normalize_relation_surface(fact),
                    "rule_id": "AUX",
                    "predicate": predicate,
                    "points": list(dict.fromkeys(points)),
                }
            )
    return entries


def _ancestor_subgraph(dag: ProofDAG, goal_step_id: str) -> set[str]:
    ancestors: set[str] = set()
    queue = deque([goal_step_id])
    while queue:
        step_id = queue.popleft()
        if step_id in ancestors:
            continue
        ancestors.add(step_id)
        step = dag.get(step_id)
        if step is None:
            continue
        for dep_id in step.deps:
            if dep_id in dag.steps_by_id:
                queue.append(dep_id)
    return ancestors


def _reachable_to_aux(
    dag: ProofDAG,
    ancestors: set[str],
    aux_step_ids: set[str],
    aux_points: set[str],
) -> set[str]:
    reachable: set[str] = set()
    for step_id in dag.ordered_step_ids:
        if step_id not in ancestors:
            continue
        step = dag.get(step_id)
        if step is None:
            continue
        step_points = set(_step_points(step))
        if step.step_id in aux_step_ids or step_points & aux_points:
            reachable.add(step_id)
            continue
        if any(dep_id in reachable or dep_id in aux_step_ids for dep_id in step.deps):
            reachable.add(step_id)
    return reachable


def _classify_goal_gap_type(
    chain: list[ProofStep],
    goal_family: str,
) -> str:
    predicates = {step.predicate.lower() for step in chain if step is not None}
    if goal_family == "eqangle":
        if "eqangle" in predicates:
            return "angle_transfer"
        if "cyclic" in predicates:
            return "cyclic_trigger"
    if goal_family == "eqratio":
        if "eqratio" in predicates:
            return "ratio_transfer"
    if goal_family in {"simtri", "simtrir"} and {"simtri", "simtrir"} & predicates:
        return "similarity_bridge"
    if goal_family in {"contri", "contrir"} and {"contri", "contrir"} & predicates:
        return "congruence_bridge"
    if {"simtri", "simtrir"} & predicates:
        return "similarity_bridge"
    if {"contri", "contrir"} & predicates:
        return "congruence_bridge"
    if "cyclic" in predicates:
        return "cyclic_trigger"
    if "eqratio" in predicates:
        return "ratio_transfer"
    if "eqangle" in predicates:
        return "angle_transfer"
    if {"midp", "para", "perp"} & predicates:
        return "midpoint_parallel_trigger"

    family_fallback = {
        "eqangle": "angle_transfer",
        "eqratio": "ratio_transfer",
        "simtri": "similarity_bridge",
        "simtrir": "similarity_bridge",
        "contri": "congruence_bridge",
        "contrir": "congruence_bridge",
        "cyclic": "cyclic_trigger",
    }.get(goal_family or "")
    if family_fallback in INSIGHT_GAP_TYPES:
        return family_fallback
    return "midpoint_parallel_trigger"


def _predicate_priority_for_goal(goal_family: str, predicate: str) -> int:
    family_preferences = {
        "eqangle": ["eqangle", "cyclic", "simtri", "simtrir", "coll", "para", "perp", "cong", "eqratio"],
        "eqratio": ["eqratio", "simtri", "simtrir", "midp", "para", "perp", "coll", "cong", "eqangle"],
        "simtri": ["simtri", "simtrir", "eqangle", "eqratio", "para", "perp", "cyclic", "coll", "cong"],
        "simtrir": ["simtri", "simtrir", "eqangle", "eqratio", "para", "perp", "cyclic", "coll", "cong"],
        "contri": ["contri", "contrir", "cong", "eqangle", "eqratio", "midp", "para", "perp", "coll"],
        "contrir": ["contri", "contrir", "cong", "eqangle", "eqratio", "midp", "para", "perp", "coll"],
    }
    ranked = family_preferences.get(goal_family or "", [])
    lowered_predicate = (predicate or "").lower()
    try:
        return ranked.index(lowered_predicate)
    except ValueError:
        return len(ranked) + 1


def _window_from_step(role: str, step: ProofStep | None) -> InsightEvidenceWindow | None:
    if step is None:
        return None
    return InsightEvidenceWindow(
        role=role,
        step_id=step.step_id,
        relation=normalize_relation_surface(step.natural_language or step.raw_line),
        rule_id=step.rule_id,
        predicate=step.predicate,
        points=_step_points(step),
    )


def _window_from_aux_entry(role: str, entry: dict[str, object] | None) -> InsightEvidenceWindow | None:
    if not isinstance(entry, dict):
        return None
    relation = normalize_relation_surface(str(entry.get("relation") or ""))
    if not relation:
        return None
    return InsightEvidenceWindow(
        role=role,
        step_id=str(entry.get("step_id") or ""),
        relation=relation,
        rule_id=str(entry.get("rule_id") or "AUX"),
        predicate=str(entry.get("predicate") or "aux"),
        points=[str(point).lower() for point in (entry.get("points") or []) if str(point).strip()],
    )


def extract_insight_slots(
    dag: ProofDAG,
    visible_goal: str,
    aux_part: str,
) -> dict[str, object] | None:
    if not isinstance(dag, ProofDAG) or not dag.steps_by_id or not dag.goal_step_id:
        return None

    goal_spec = parse_goal_expression(visible_goal or "")
    goal_family = str(goal_spec.get("predicate") or "").lower()
    goal_points = {
        str(point).lower()
        for point in (goal_spec.get("points") or [])
        if isinstance(point, str) and point.strip()
    }
    aux_points = {
        str(point).lower()
        for point in extract_aux_new_points(aux_part or "")
        if isinstance(point, str) and point.strip()
    }
    aux_relation_entries = _extract_aux_relation_entries(aux_part or "")
    aux_step_ids = set(_AUX_STEP_ID_RE.findall(aux_part or ""))
    aux_direct_relations = [
        normalize_relation_surface(relation)
        for relation in build_aux_direct_consequences(aux_part or "")
        if isinstance(relation, str) and relation.strip()
    ]

    ancestors = _ancestor_subgraph(dag, dag.goal_step_id)
    aux_reachable = _reachable_to_aux(dag, ancestors, aux_step_ids, aux_points)

    ordered_ancestors = [
        dag.get(step_id)
        for step_id in dag.ordered_step_ids
        if step_id in ancestors and dag.get(step_id) is not None
    ]
    if not aux_relation_entries and not aux_direct_relations:
        return None

    all_point_names = sorted(
        {
            point
            for step in ordered_ancestors
            for point in _step_points(step)
        }
        | goal_points
        | aux_points
    )
    index_by_step = {step.step_id: index for index, step in enumerate(ordered_ancestors)}
    children_by_dep = _build_children_index(dag, ancestors)

    matched_steps_by_entry: list[list[ProofStep]] = []
    for entry in aux_relation_entries:
        relation = str(entry.get("relation") or "")
        matched_steps = [
            step
            for step in ordered_ancestors
            if step is not None
            and step.step_id in aux_reachable
            and _relation_matches(relation, _step_relation(step), all_point_names)
        ]
        matched_steps_by_entry.append(matched_steps)

    required_entry_index = next(
        (
            entry_index
            for entry_index, matched_steps in enumerate(matched_steps_by_entry)
            if matched_steps
        ),
        0,
    )
    required_aux_entry = (
        aux_relation_entries[required_entry_index]
        if aux_relation_entries
        else {
            "step_id": next(iter(aux_step_ids), "aux_000"),
            "relation": aux_direct_relations[0],
            "rule_id": "AUX",
            "predicate": "aux",
            "points": sorted(aux_points),
        }
    )
    required_aux_effect = normalize_relation_surface(str(required_aux_entry.get("relation") or ""))
    required_effect_points = {
        str(point).lower()
        for point in (required_aux_entry.get("points") or [])
        if str(point).strip()
    }

    required_support_steps = matched_steps_by_entry[required_entry_index] if matched_steps_by_entry else []
    fallback_support_steps = [
        step
        for step in ordered_ancestors
        if step is not None
        and step.step_id in aux_reachable
        and set(_step_points(step)) & aux_points
    ]
    if not required_support_steps and required_effect_points:
        best_overlap = max(
            (
                len(set(_step_points(step)) & required_effect_points)
                for step in fallback_support_steps
            ),
            default=0,
        )
        if best_overlap > 0:
            fallback_support_steps = [
                step
                for step in fallback_support_steps
                if len(set(_step_points(step)) & required_effect_points) == best_overlap
            ]
    if not required_support_steps and not fallback_support_steps:
        return None

    required_support_ids = {step.step_id for step in required_support_steps}
    descendant_ids = (
        _descendants_from(children_by_dep, required_support_ids, ancestors)
        if required_support_ids
        else set(aux_reachable)
    )

    old_visible_points = {
        point
        for step in ordered_ancestors
        for point in _step_points(step)
        if point not in aux_points
    }

    def _bridge_rank(step: ProofStep):
        step_points = set(_step_points(step))
        new_old_points = (step_points & old_visible_points) - required_effect_points
        goal_overlap = len(step_points & goal_points)
        return (
            0 if new_old_points else 1,
            _predicate_priority_for_goal(goal_family, step.predicate),
            0 if step.rule_id.upper() != "AR" else 1,
            0 if step.predicate.lower() != "coll" else 1,
            -len(new_old_points),
            -goal_overlap,
            index_by_step.get(step.step_id, 10**6),
        )

    bridge_candidates = [
        step
        for step in ordered_ancestors
        if step is not None
        and step.step_id in descendant_ids
        and step.step_id not in required_support_ids
        and set(_step_points(step)) & aux_points
        and ((set(_step_points(step)) & old_visible_points) - required_effect_points)
        and not _relation_matches(required_aux_effect, _step_relation(step), all_point_names)
    ]
    first_bridge_step = min(bridge_candidates, key=_bridge_rank) if bridge_candidates else None
    if first_bridge_step is None:
        fallback_bridge_candidates = [
            step
            for step in ordered_ancestors
            if step is not None
            and step.step_id in descendant_ids
            and step.step_id not in required_support_ids
            and set(_step_points(step)) & aux_points
            and set(_step_points(step)) & old_visible_points
        ]
        first_bridge_step = (
            min(fallback_bridge_candidates, key=_bridge_rank)
            if fallback_bridge_candidates
            else (required_support_steps or fallback_support_steps)[0]
        )

    pre_goal_step = None
    first_bridge_index = index_by_step.get(first_bridge_step.step_id, 0)
    pre_goal_candidates = [
        step
        for step in ordered_ancestors
        if step is not None
        and step.step_id in aux_reachable
        and index_by_step.get(step.step_id, -1) >= first_bridge_index
        and step.step_id != dag.goal_step_id
        and step.rule_id.upper() != "AR"
    ]
    if pre_goal_candidates:
        def _pre_goal_rank(step: ProofStep):
            step_points = set(_step_points(step))
            goal_overlap = len(step_points & goal_points)
            aux_overlap = len(step_points & aux_points)
            return (
                1 if goal_points and goal_overlap >= min(2, len(goal_points)) else 0,
                goal_overlap,
                index_by_step.get(step.step_id, -1),
                -_predicate_priority_for_goal(goal_family, step.predicate),
                aux_overlap,
            )

        pre_goal_step = max(pre_goal_candidates, key=_pre_goal_rank)
    if pre_goal_step is None:
        fallback_pre_goal_candidates = [
            step
            for step in ordered_ancestors
            if step is not None
            and step.step_id in aux_reachable
            and index_by_step.get(step.step_id, -1) >= first_bridge_index
            and step.step_id != dag.goal_step_id
        ]
        pre_goal_step = fallback_pre_goal_candidates[-1] if fallback_pre_goal_candidates else first_bridge_step

    pre_goal_index = index_by_step.get(pre_goal_step.step_id, first_bridge_index)
    start_index = min(first_bridge_index, pre_goal_index)
    end_index = max(first_bridge_index, pre_goal_index)
    bridge_chain = ordered_ancestors[start_index : end_index + 1]
    goal_gap_type = _classify_goal_gap_type(bridge_chain or required_support_steps, goal_family)

    evidence_windows = []
    for role, window_source in (
        ("required_aux_effect", required_aux_entry),
        ("first_bridge_checkpoint", first_bridge_step),
        ("pre_goal_checkpoint", pre_goal_step),
    ):
        window = (
            _window_from_aux_entry(role, window_source)
            if role == "required_aux_effect"
            else _window_from_step(role, window_source)
        )
        if window is None:
            continue
        if any(existing.step_id == window.step_id for existing in evidence_windows):
            continue
        evidence_windows.append(window)

    stage_order = None
    if len(aux_points) > 1:
        stage_order = aux_direct_relations[: max(2, min(3, len(aux_direct_relations)))] or sorted(aux_points)

    slots = InsightSlots(
        goal_family=goal_family,
        goal_gap_type=goal_gap_type,
        required_aux_effect=required_aux_effect,
        first_bridge_checkpoint=normalize_relation_surface(
            first_bridge_step.natural_language if first_bridge_step is not None else ""
        ),
        pre_goal_checkpoint=normalize_relation_surface(
            pre_goal_step.natural_language if pre_goal_step is not None else ""
        ),
        stage_order=stage_order,
        evidence_windows=evidence_windows[:3],
    )
    return slots.to_dict()


__all__ = ["extract_insight_slots"]
