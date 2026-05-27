#!/usr/bin/env python3
"""
Script-side DAG extraction for the insight_v1 mainline.
"""

from __future__ import annotations

import re
from collections import deque

try:
    from .geometry_text import (
        build_aux_direct_consequences,
        extract_aux_new_points,
        normalize_relation_surface,
        parse_goal_expression,
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
        parse_goal_expression,
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


def _build_goal_path(
    dag: ProofDAG,
    goal_step_id: str,
    target_step_id: str,
) -> list[ProofStep]:
    if not goal_step_id or not target_step_id or goal_step_id == target_step_id:
        step = dag.get(goal_step_id or target_step_id)
        return [step] if step is not None else []

    index_by_step = {step_id: index for index, step_id in enumerate(dag.ordered_step_ids)}
    path: list[str] = [goal_step_id]
    current_id = goal_step_id
    visited = {goal_step_id}

    while current_id != target_step_id:
        current = dag.get(current_id)
        if current is None:
            break
        candidates = [
            dep_id
            for dep_id in current.deps
            if dep_id in dag.steps_by_id and index_by_step.get(dep_id, -1) >= index_by_step.get(target_step_id, -1)
        ]
        if target_step_id in candidates:
            next_id = target_step_id
        elif candidates:
            ranked = sorted(
                candidates,
                key=lambda dep_id: (
                    dag.get(dep_id).rule_id == "AR" if dag.get(dep_id) else True,
                    -index_by_step.get(dep_id, -1),
                ),
            )
            next_id = ranked[0]
        else:
            break
        if next_id in visited:
            break
        visited.add(next_id)
        path.append(next_id)
        current_id = next_id

    return [dag.get(step_id) for step_id in reversed(path) if dag.get(step_id) is not None]


def _classify_goal_gap_type(
    chain: list[ProofStep],
    goal_family: str,
) -> str:
    predicates = {step.predicate.lower() for step in chain if step is not None}
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
    required_aux_step = next(
        (
            step
            for step in ordered_ancestors
            if step is not None
            and step.step_id in aux_reachable
            and set(_step_points(step)) & aux_points
        ),
        None,
    )
    if required_aux_step is None:
        return None

    chain = _build_goal_path(dag, dag.goal_step_id, required_aux_step.step_id)
    if not chain:
        chain = [required_aux_step]

    old_visible_points = {
        point
        for step in ordered_ancestors
        for point in _step_points(step)
        if point not in aux_points
    }
    first_bridge_step = next(
        (
            step
            for step in chain[1:]
            if step is not None
            and set(_step_points(step)) & aux_points
            and set(_step_points(step)) & old_visible_points
        ),
        required_aux_step,
    )

    pre_goal_step = None
    for step in reversed(chain[:-1] if len(chain) > 1 else chain):
        if step is None or step.rule_id.upper() == "AR":
            continue
        step_points = set(_step_points(step))
        if goal_points and len(step_points & goal_points) >= min(2, len(goal_points)):
            pre_goal_step = step
            break
        if pre_goal_step is None:
            pre_goal_step = step
    if pre_goal_step is None:
        pre_goal_step = chain[-1]

    first_bridge_index = next(
        (idx for idx, step in enumerate(chain) if step is not None and step.step_id == first_bridge_step.step_id),
        0,
    )
    pre_goal_index = next(
        (idx for idx, step in enumerate(chain) if step is not None and step.step_id == pre_goal_step.step_id),
        len(chain) - 1,
    )
    bridge_chain = chain[first_bridge_index: pre_goal_index + 1] if chain else []
    goal_gap_type = _classify_goal_gap_type(bridge_chain or chain, goal_family)

    evidence_windows = []
    for role, step in (
        ("required_aux_effect", required_aux_step),
        ("first_bridge_checkpoint", first_bridge_step),
        ("pre_goal_checkpoint", pre_goal_step),
    ):
        window = _window_from_step(role, step)
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
        required_aux_effect=normalize_relation_surface(
            aux_direct_relations[0] if aux_direct_relations else required_aux_step.natural_language
        ),
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
