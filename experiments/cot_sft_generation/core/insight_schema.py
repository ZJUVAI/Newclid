#!/usr/bin/env python3
"""
Structured schemas for the insight_v1 CoT SFT mainline.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


INSIGHT_V1 = "insight_v1"
INSIGHT_GAP_TYPES = {
    "angle_transfer",
    "ratio_transfer",
    "similarity_bridge",
    "congruence_bridge",
    "cyclic_trigger",
    "midpoint_parallel_trigger",
}


@dataclass
class InsightEvidenceWindow:
    role: str
    step_id: str
    relation: str
    rule_id: str
    predicate: str
    points: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InsightSlots:
    goal_family: str
    goal_gap_type: str
    required_aux_effect: str
    first_bridge_checkpoint: str
    pre_goal_checkpoint: str
    stage_order: list[str] | None = None
    evidence_windows: list[InsightEvidenceWindow] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["evidence_windows"] = [window.to_dict() for window in self.evidence_windows]
        return payload


@dataclass
class InsightPlan:
    visible_facts: list[str]
    image_scan: list[str]
    goal_gap_type: str
    goal_gap_text: str
    required_aux_effect: str
    aux_construction: str
    aux_selection_reason: str
    stage_order: list[str] | None = None
    bonus_post_aux_tail: list[str] | None = None
    generation_style: str = INSIGHT_V1
    insight_version: str = INSIGHT_V1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


__all__ = [
    "INSIGHT_GAP_TYPES",
    "INSIGHT_V1",
    "InsightEvidenceWindow",
    "InsightPlan",
    "InsightSlots",
]
