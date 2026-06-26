#!/usr/bin/env python3
"""
Structured schemas for the backtrace_text_v2 generation style.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


BACKTRACE_TEXT_V1 = "backtrace_text_v1"
BACKTRACE_TEXT_V2 = "backtrace_text_v2"
BACKTRACE_GENERATION_STYLES = {BACKTRACE_TEXT_V1, BACKTRACE_TEXT_V2}


def is_backtrace_generation_style(generation_style: str | None) -> bool:
    return generation_style in BACKTRACE_GENERATION_STYLES


@dataclass
class BacktraceStage:
    step_id: str
    claim_nl: str
    parent_stage_ids: list[str] = field(default_factory=list)
    depth: int = 0
    visible_support_step_ids: list[str] = field(default_factory=list)
    visible_support_nl: list[str] = field(default_factory=list)
    next_v_step_ids: list[str] = field(default_factory=list)
    next_v_nl: list[str] = field(default_factory=list)
    blocking_h_step_ids: list[str] = field(default_factory=list)
    blocking_h_nl: list[str] = field(default_factory=list)
    is_terminal: bool = False
    stop_reason: str = ""


@dataclass
class WriterBacktraceStage:
    claim_nl: str
    depth: int = 0
    visible_support_nl: list[str] = field(default_factory=list)
    subgoal_claims_nl: list[str] = field(default_factory=list)
    stops_at_aux_boundary: bool = False


@dataclass
class BacktraceSlots:
    C1_step_ids: list[str] = field(default_factory=list)
    C2_step_ids: list[str] = field(default_factory=list)
    C3_step_ids: list[str] = field(default_factory=list)
    V_step_ids: list[str] = field(default_factory=list)
    H_step_ids: list[str] = field(default_factory=list)
    V_core_step_ids: list[str] = field(default_factory=list)
    backtrace_root_step_id: str = ""
    backtrace_stage_order_step_ids: list[str] = field(default_factory=list)
    backtrace_stages: list[BacktraceStage] = field(default_factory=list)
    terminal_stage_ids: list[str] = field(default_factory=list)
    backtrace_chain_step_ids: list[str] = field(default_factory=list)
    frontier_node_ids: list[str] = field(default_factory=list)
    supporting_c1_by_frontier: dict[str, list[str]] = field(default_factory=dict)
    aux_construction_formal: str = ""
    aux_construction_nl: str = ""
    goal_nl: str = ""
    backtrace_chain_nl: list[str] = field(default_factory=list)
    frontier_nodes_nl: list[str] = field(default_factory=list)
    supporting_c1_facts_nl: dict[str, list[str]] = field(default_factory=dict)
    H_relations_nl: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WriterHandoff:
    goal_nl: str
    backtrace_stages: list[WriterBacktraceStage] = field(default_factory=list)
    terminal_claims_nl: list[str] = field(default_factory=list)
    aux_construction_nl: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


__all__ = [
    "BACKTRACE_GENERATION_STYLES",
    "BACKTRACE_TEXT_V1",
    "BACKTRACE_TEXT_V2",
    "BacktraceStage",
    "BacktraceSlots",
    "WriterBacktraceStage",
    "WriterHandoff",
    "is_backtrace_generation_style",
]
