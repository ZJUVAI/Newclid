#!/usr/bin/env python3
"""
Helpers for CoT SFT run artifacts.

This module keeps run-output schema logic separate from the main generation
pipeline so artifact evolution does not further bloat the generation script.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Iterable, Optional


SEMANTIC_REVIEW_CHECKLIST_VERSION = "cot_sft_semantic_review_v1"
SEMANTIC_REVIEW_ISSUE_CODE_DESCRIPTIONS = {
    "not_visible_only": "The thinking reads like hidden-proof supervision rather than visible-input reasoning.",
    "full_figure_coverage_missing": "The text stays on a narrow anchor frame and misses needed visible substructures.",
    "coordinate_cue_unused": "Coordinate or visual cues are named but never actually enter the reasoning chain.",
    "aux_direct_not_grounded": "The immediate aux consequences are misstated or not direct consequences of the construction.",
    "bridge_unsupported": "A bridge relation is not actually supported by the cited earlier relations.",
    "route_drift": "The route drifts away from the approved or plausible goal-side chain.",
    "goal_finish_unclosed": "The final 2-4 steps do not genuinely close to the target goal relation.",
    "goal_type_mismatch": "The reasoning closes toward the wrong goal modality or wrong target relation family.",
    "staged_strategy_missing": "A multi-point auxiliary construction is not explained as a staged strategy.",
    "high_level_shorthand_without_support": "High-level geometry language replaces concrete supporting relations.",
    "other": "Fallback code for issues that do not fit the current structured taxonomy.",
}


def _safe_rate(numerator: int, denominator: int) -> Optional[float]:
    if denominator <= 0:
        return None
    return numerator / denominator


def _safe_average(values: Iterable[Any]) -> Optional[float]:
    numeric_values = [value for value in values if isinstance(value, (int, float))]
    if not numeric_values:
        return None
    return sum(numeric_values) / len(numeric_values)


def build_dataset_output_record(
    sample_order: int,
    instruction: str,
    public_problem: str,
    thinking: str,
    aux_part: str,
    image_path: str,
) -> Dict[str, Any]:
    output = f"{thinking}\n{aux_part}"
    return {
        "instruction": instruction,
        "input": public_problem,
        "thinking": thinking,
        "aux": aux_part,
        "output": output,
        "image_path": image_path,
        "_order": sample_order,
    }


def build_missing_image_item_record(
    sample_order: int,
    input_index: int,
    image_path: str,
    source_audit: Dict[str, Any],
    error: str,
) -> Dict[str, Any]:
    return {
        "sample_order": sample_order,
        "input_index": input_index,
        "image_path": image_path,
        "goal_type": None,
        "aux_type": None,
        "source_audit": source_audit,
        "generation_audit": {"issues": [], "has_issue": False},
        "surface_pass": False,
        "success": False,
        "attempts_used": 0,
        "elapsed_seconds": None,
        "error": error,
    }


def build_item_record(
    sample_order: int,
    input_index: int,
    image_path: str,
    public_problem: str,
    aux_part: str,
    goal_type: Optional[str],
    aux_type: Optional[str],
    hidden_rest_sanitized: str,
    point_coords_grid: Dict[str, Any],
    source_audit: Dict[str, Any],
    generation_audit: Dict[str, Any],
    generation: Dict[str, Any],
) -> Dict[str, Any]:
    surface_pass = bool(generation.get("success"))
    return {
        "sample_order": sample_order,
        "input_index": input_index,
        "image_path": image_path,
        "public_problem": public_problem,
        "aux": aux_part,
        "goal_type": goal_type,
        "aux_type": aux_type,
        "hidden_rest_sanitized": hidden_rest_sanitized,
        "point_coords_grid": point_coords_grid,
        "source_audit": source_audit,
        "generation_audit": generation_audit,
        "plan_prompt": generation.get("plan_prompt"),
        "write_prompt": generation.get("write_prompt"),
        "plan_output": generation.get("plan_output"),
        "plan_parsed": generation.get("plan_parsed"),
        "write_output": generation.get("write_output"),
        "thinking": generation.get("thinking"),
        "surface_pass": surface_pass,
        "success": surface_pass,
        "attempts_used": generation.get("attempts_used"),
        "elapsed_seconds": generation.get("elapsed_seconds"),
        "error": generation.get("error"),
    }


def build_item_audit_record(item_record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "sample_order": item_record["sample_order"],
        "input_index": item_record["input_index"],
        "goal_type": item_record.get("goal_type"),
        "aux_type": item_record.get("aux_type"),
        "source_audit": item_record.get("source_audit", {}),
        "generation_audit": item_record.get("generation_audit", {}),
        "surface_pass": item_record.get("surface_pass", item_record.get("success", False)),
        "success": item_record.get("success", False),
    }


def build_semantic_audit_stub(item_record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "sample_order": item_record["sample_order"],
        "input_index": item_record["input_index"],
        "image_path": item_record.get("image_path", ""),
        "goal_type": item_record.get("goal_type"),
        "aux_type": item_record.get("aux_type"),
        "surface_pass": item_record.get("surface_pass", item_record.get("success", False)),
        "semantic_pass": None,
        "manual_critical_error": None,
        "review_status": "pending",
        "review_checklist_version": SEMANTIC_REVIEW_CHECKLIST_VERSION,
        "reviewer": None,
        "issue_codes": [],
        "issues": [],
        "notes": "",
    }


def build_run_summary(
    input_jsonl: str,
    total_candidates_with_aux: int,
    sampled_items: int,
    item_records: Iterable[Dict[str, Any]],
    semantic_audit_records: Iterable[Dict[str, Any]],
    source_audit_issue_items: int,
    generation_audit_issue_items: int,
    num_workers: int,
    max_retries_per_stage: int,
    model_name: str,
    output_jsonl: str,
    artifacts_dir: str,
    runtime_seconds: float,
) -> Dict[str, Any]:
    item_records = list(item_records)
    semantic_audit_records = list(semantic_audit_records)

    surface_pass_items = sum(
        1 for item in item_records if item.get("surface_pass", item.get("success", False))
    )
    surface_fail_items = sampled_items - surface_pass_items

    reviewed_items = sum(1 for item in semantic_audit_records if item.get("semantic_pass") is not None)
    semantic_pass_items = sum(1 for item in semantic_audit_records if item.get("semantic_pass") is True)
    semantic_fail_items = sum(1 for item in semantic_audit_records if item.get("semantic_pass") is False)
    manual_critical_error_items = sum(
        1 for item in semantic_audit_records if item.get("manual_critical_error") is True
    )
    avg_attempts_used = _safe_average(item.get("attempts_used") for item in item_records)

    if reviewed_items == 0:
        semantic_review_status = "not_reviewed"
    elif reviewed_items < sampled_items:
        semantic_review_status = "partially_reviewed"
    else:
        semantic_review_status = "fully_reviewed"

    return {
        "input_jsonl": input_jsonl,
        "total_candidates_with_aux": total_candidates_with_aux,
        "sampled_items": sampled_items,
        "successful_items": surface_pass_items,
        "failed_items": surface_fail_items,
        "surface_pass_items": surface_pass_items,
        "surface_fail_items": surface_fail_items,
        "surface_pass_rate": _safe_rate(surface_pass_items, sampled_items),
        "semantic_reviewed_items": reviewed_items,
        "semantic_pass_items": semantic_pass_items,
        "semantic_fail_items": semantic_fail_items,
        "semantic_pass_rate": _safe_rate(semantic_pass_items, reviewed_items),
        "manual_critical_error_items": manual_critical_error_items,
        "manual_critical_error_rate": _safe_rate(manual_critical_error_items, reviewed_items),
        "semantic_review_status": semantic_review_status,
        "avg_attempts_used": avg_attempts_used,
        "source_audit_issue_items": source_audit_issue_items,
        "generation_audit_issue_items": generation_audit_issue_items,
        "num_workers": num_workers,
        "max_retries_per_stage": max_retries_per_stage,
        "model_name": model_name,
        "output_jsonl": os.path.abspath(output_jsonl),
        "artifacts_dir": os.path.abspath(artifacts_dir),
        "runtime_seconds": runtime_seconds,
    }
