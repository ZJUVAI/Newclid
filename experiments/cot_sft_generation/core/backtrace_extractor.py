#!/usr/bin/env python3
"""
Script-side DAG extraction for the backtrace_text_v2 mainline.
"""

from __future__ import annotations

import re
from collections import deque

try:
    from .backtrace_schema import BacktraceSlots, BacktraceStage, WriterBacktraceStage, WriterHandoff
    from .geometry_text import (
        build_canonical_construction,
        extract_aux_new_points,
        normalize_relation_surface,
        parse_aux_clauses,
        split_formal_relation_chain,
    )
    from .proof_dag import ProofDAG, ProofStep
except ImportError:  # pragma: no cover - script execution path
    from backtrace_schema import BacktraceSlots, BacktraceStage, WriterBacktraceStage, WriterHandoff  # type: ignore
    from geometry_text import (  # type: ignore
        build_canonical_construction,
        extract_aux_new_points,
        normalize_relation_surface,
        parse_aux_clauses,
        split_formal_relation_chain,
    )
    from proof_dag import ProofDAG, ProofStep  # type: ignore


_STEP_ID_RE = re.compile(r"\[\d{3}\]")
_POINT_RE = re.compile(r"[a-z]\w*")

# backtrace_text_v2 definitions. Do not change these meanings without updating
# the mainline design docs and downstream checks together.
#
# C1
#   premise-only closure
#   一个 proof step 属于 C1，当且仅当：
#   - 该 step 的结论本身不含 aux 点
#   - 且它的所有 proof 前驱要么是 premise，要么已经在 C1 中
# C2
#   结论表面不含 aux 点的所有 step；只看 statement，不看推导过程
# C3
#   ProofDAG \ C1
# V
#   V = C2 ∩ C3
#   结论本身不含 aux 点，但又不是仅靠 premises 就能推出的结论
# H
#   H = C3 \ C2
#   不属于 premise-only，且结论本身含 aux 点的结论
# V_core
#   从 goal 出发，只沿 dep ∈ V 的边反向回溯所能到达的那部分 V
# backtrace_stage
#   writer 会显式叙述的一层 visible claim
#   direct deps 会被分成：
#   - visible_support = deps ∩ C1
#   - next_v = deps ∩ V_core
#   - blocking_h = deps ∩ H
# U
#   U = V \ V_core
#   第一版忽略
# frontier_nodes
#   兼容字段
#   当前等于 direct deps 已触到 H 的 terminal visible stage
# supporting_c1_by_frontier
#   兼容字段
#   每个 terminal visible stage 的直接 C1 支持；只作已有支持，不继续主回溯展开


def _step_points(step: ProofStep | None) -> list[str]:
    if step is None:
        return []
    points = []
    for token in step.args:
        token_text = str(token or "").strip().lower()
        if _POINT_RE.fullmatch(token_text):
            points.append(token_text)
    return list(dict.fromkeys(points))


def _step_nl(step: ProofStep | None) -> str:
    if step is None:
        return ""
    return normalize_relation_surface(step.natural_language or step.raw_line)


def _canonical_aux_construction_formal(aux_part: str) -> str:
    fragments = []
    for clause in parse_aux_clauses(aux_part or ""):
        relation_chain = [
            re.sub(r"\s+", " ", _STEP_ID_RE.sub("", relation)).strip(" ;")
            for relation in split_formal_relation_chain(clause.get("body", ""))
            if relation and relation.strip()
        ]
        if not relation_chain:
            continue
        body = " ; ".join(relation_chain)
        new_point = str(clause.get("new_point") or "").strip().lower()
        if new_point:
            fragments.append(f"x00 {new_point} : {body}")
        else:
            fragments.append(body)
    return " ; ".join(fragments)


def _ordered_subset(ordered_step_ids: list[str], selected: set[str]) -> list[str]:
    return [step_id for step_id in ordered_step_ids if step_id in selected]


def _direct_deps_in(step: ProofStep | None, selected: set[str]) -> list[str]:
    if step is None:
        return []
    return [dep_id for dep_id in step.deps if dep_id in selected]


def _build_backtrace_stage_order(
    dag: ProofDAG,
    root_step_id: str,
    V_core_step_ids: set[str],
    H_step_ids: set[str],
) -> tuple[list[str], dict[str, list[str]], dict[str, int]]:
    stage_order: list[str] = []
    parent_stage_ids: dict[str, list[str]] = {}
    stage_depths: dict[str, int] = {}
    visited: set[str] = set()

    def visit(step_id: str, parent_step_id: str | None = None, depth: int = 0) -> None:
        if step_id not in V_core_step_ids:
            return
        stage_depths[step_id] = min(stage_depths.get(step_id, depth), depth)
        if parent_step_id:
            parent_stage_ids.setdefault(step_id, [])
            if parent_step_id not in parent_stage_ids[step_id]:
                parent_stage_ids[step_id].append(parent_step_id)
        if step_id in visited:
            return
        visited.add(step_id)
        stage_order.append(step_id)

        step = dag.get(step_id)
        if step is None:
            return
        if any(dep_id in H_step_ids for dep_id in step.deps):
            return
        for dep_id in step.deps:
            if dep_id in V_core_step_ids:
                visit(dep_id, parent_step_id=step_id, depth=depth + 1)

    if root_step_id:
        visit(root_step_id)
    return stage_order, parent_stage_ids, stage_depths


def extract_backtrace_slots(
    dag: ProofDAG,
    visible_goal: str,
    aux_part: str,
) -> dict[str, object] | None:
    if not isinstance(dag, ProofDAG) or not dag.steps_by_id or not dag.goal_step_id:
        return None

    aux_points = {
        str(point).lower()
        for point in extract_aux_new_points(aux_part or "")
        if isinstance(point, str) and point.strip()
    }
    ordered_step_ids = list(dag.ordered_step_ids)
    all_step_ids = set(ordered_step_ids)

    C1_step_ids: set[str] = set()
    C2_step_ids: set[str] = set()
    for step_id in ordered_step_ids:
        step = dag.get(step_id)
        if step is None:
            continue
        step_points = set(_step_points(step))
        if not (step_points & aux_points):
            C2_step_ids.add(step_id)
            if all(dep_id not in all_step_ids or dep_id in C1_step_ids for dep_id in step.deps):
                C1_step_ids.add(step_id)

    C3_step_ids = all_step_ids - C1_step_ids
    V_step_ids = C2_step_ids & C3_step_ids
    H_step_ids = C3_step_ids - C2_step_ids

    V_core_step_ids: set[str] = set()
    if dag.goal_step_id in V_step_ids:
        queue = deque([dag.goal_step_id])
        while queue:
            step_id = queue.popleft()
            if step_id in V_core_step_ids or step_id not in V_step_ids:
                continue
            V_core_step_ids.add(step_id)
            step = dag.get(step_id)
            if step is None:
                continue
            for dep_id in step.deps:
                if dep_id in V_step_ids and dep_id not in V_core_step_ids:
                    queue.append(dep_id)

    V_core_ordered = _ordered_subset(ordered_step_ids, V_core_step_ids)
    backtrace_root_step_id = dag.goal_step_id if dag.goal_step_id in V_core_step_ids else ""
    backtrace_stage_order_step_ids, parent_stage_ids, stage_depths = _build_backtrace_stage_order(
        dag,
        backtrace_root_step_id,
        V_core_step_ids,
        H_step_ids,
    )

    backtrace_stages: list[BacktraceStage] = []
    terminal_stage_ids: list[str] = []
    for step_id in backtrace_stage_order_step_ids:
        step = dag.get(step_id)
        visible_support_step_ids = _direct_deps_in(step, C1_step_ids)
        next_v_step_ids = _direct_deps_in(step, V_core_step_ids)
        blocking_h_step_ids = _direct_deps_in(step, H_step_ids)
        is_terminal = bool(blocking_h_step_ids)
        if is_terminal:
            terminal_stage_ids.append(step_id)
        backtrace_stages.append(
            BacktraceStage(
                step_id=step_id,
                claim_nl=_step_nl(step),
                parent_stage_ids=list(parent_stage_ids.get(step_id, [])),
                depth=stage_depths.get(step_id, 0),
                visible_support_step_ids=visible_support_step_ids,
                visible_support_nl=[_step_nl(dag.get(dep_id)) for dep_id in visible_support_step_ids],
                next_v_step_ids=next_v_step_ids,
                next_v_nl=[_step_nl(dag.get(dep_id)) for dep_id in next_v_step_ids],
                blocking_h_step_ids=blocking_h_step_ids,
                blocking_h_nl=[_step_nl(dag.get(dep_id)) for dep_id in blocking_h_step_ids],
                is_terminal=is_terminal,
                stop_reason="has_direct_h_dependency" if is_terminal else "",
            )
        )

    backtrace_chain_step_ids = list(backtrace_stage_order_step_ids)
    frontier_node_ids = list(terminal_stage_ids)
    supporting_c1_by_frontier = {
        stage.step_id: list(stage.visible_support_step_ids)
        for stage in backtrace_stages
        if stage.is_terminal
    }

    frontier_nodes_nl = [_step_nl(dag.get(step_id)) for step_id in frontier_node_ids]
    supporting_c1_facts_nl = {
        _step_nl(dag.get(step_id)): [_step_nl(dag.get(dep_id)) for dep_id in supporting_c1_by_frontier.get(step_id, [])]
        for step_id in frontier_node_ids
    }

    slots = BacktraceSlots(
        C1_step_ids=_ordered_subset(ordered_step_ids, C1_step_ids),
        C2_step_ids=_ordered_subset(ordered_step_ids, C2_step_ids),
        C3_step_ids=_ordered_subset(ordered_step_ids, C3_step_ids),
        V_step_ids=_ordered_subset(ordered_step_ids, V_step_ids),
        H_step_ids=_ordered_subset(ordered_step_ids, H_step_ids),
        V_core_step_ids=V_core_ordered,
        backtrace_root_step_id=backtrace_root_step_id,
        backtrace_stage_order_step_ids=backtrace_stage_order_step_ids,
        backtrace_stages=backtrace_stages,
        terminal_stage_ids=terminal_stage_ids,
        backtrace_chain_step_ids=backtrace_chain_step_ids,
        frontier_node_ids=frontier_node_ids,
        supporting_c1_by_frontier=supporting_c1_by_frontier,
        aux_construction_formal=_canonical_aux_construction_formal(aux_part or ""),
        aux_construction_nl=normalize_relation_surface(build_canonical_construction(aux_part or "")),
        goal_nl=normalize_relation_surface(visible_goal or ""),
        backtrace_chain_nl=[_step_nl(dag.get(step_id)) for step_id in backtrace_chain_step_ids],
        frontier_nodes_nl=frontier_nodes_nl,
        supporting_c1_facts_nl=supporting_c1_facts_nl,
        H_relations_nl=[_step_nl(dag.get(step_id)) for step_id in _ordered_subset(ordered_step_ids, H_step_ids)],
    )
    return slots.to_dict()


def build_backtrace_writer_handoff(backtrace_slots: dict[str, object] | None) -> dict[str, object]:
    if not isinstance(backtrace_slots, dict):
        return {}
    backtrace_stages = []
    terminal_claims_nl = []
    for stage in backtrace_slots.get("backtrace_stages") or []:
        if not isinstance(stage, dict):
            continue
        is_terminal = bool(stage.get("is_terminal"))
        claim_nl = str(stage.get("claim_nl") or "")
        if is_terminal and claim_nl:
            terminal_claims_nl.append(claim_nl)
        backtrace_stages.append(
            WriterBacktraceStage(
                claim_nl=claim_nl,
                depth=int(stage.get("depth") or 0),
                visible_support_nl=list(stage.get("visible_support_nl") or []),
                subgoal_claims_nl=[] if is_terminal else list(stage.get("next_v_nl") or []),
                stops_at_aux_boundary=is_terminal,
            )
        )
    return WriterHandoff(
        goal_nl=str(backtrace_slots.get("goal_nl") or ""),
        backtrace_stages=backtrace_stages,
        terminal_claims_nl=terminal_claims_nl,
        aux_construction_nl=str(backtrace_slots.get("aux_construction_nl") or ""),
    ).to_dict()


__all__ = [
    "build_backtrace_writer_handoff",
    "extract_backtrace_slots",
]
