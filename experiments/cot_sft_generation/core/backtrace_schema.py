#!/usr/bin/env python3
"""
Structured schemas for the backtrace_text_v1 generation style.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


BACKTRACE_TEXT_V1 = "backtrace_text_v1"


@dataclass
class BacktraceSlots:
    C1_step_ids: list[str] = field(default_factory=list)
    C2_step_ids: list[str] = field(default_factory=list)
    C3_step_ids: list[str] = field(default_factory=list)
    V_step_ids: list[str] = field(default_factory=list)
    H_step_ids: list[str] = field(default_factory=list)
    V_core_step_ids: list[str] = field(default_factory=list)
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
    backtrace_chain_nl: list[str] = field(default_factory=list)
    frontier_nodes_nl: list[str] = field(default_factory=list)
    supporting_c1_facts_nl: dict[str, list[str]] = field(default_factory=dict)
    aux_construction_nl: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


__all__ = [
    "BACKTRACE_TEXT_V1",
    "BacktraceSlots",
    "WriterHandoff",
]
