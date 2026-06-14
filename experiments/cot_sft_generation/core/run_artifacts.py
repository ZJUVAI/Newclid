#!/usr/bin/env python3
"""
Helpers for CoT SFT run artifacts.

This module keeps run-output schema logic separate from the main generation
pipeline so artifact evolution does not further bloat the generation script.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

try:
    from .insight_schema import INSIGHT_GENERATION_STYLES, INSIGHT_IMAGE_V1
except ImportError:  # pragma: no cover - script execution path
    from insight_schema import INSIGHT_GENERATION_STYLES, INSIGHT_IMAGE_V1  # type: ignore


ARTIFACT_SCHEMA_VERSION = "cot_sft_artifacts_v1"
SEMANTIC_REVIEW_CHECKLIST_VERSION = "cot_sft_semantic_review_v1"
INSIGHT_FAMILY_HARD_GENERATION_AUDIT_ISSUES = {
    "no_proof_echo",
    "visible_only_boundary",
}
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


def _run_git_command(args: list[str], cwd: Path) -> Optional[str]:
    result = subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    text = result.stdout.strip()
    return text or None


def detect_git_context(repo_root: str | Path) -> Dict[str, Any]:
    root = Path(repo_root).resolve()
    commit = _run_git_command(["git", "rev-parse", "HEAD"], root)
    branch = _run_git_command(["git", "rev-parse", "--abbrev-ref", "HEAD"], root)
    dirty_output = _run_git_command(["git", "status", "--short"], root)
    return {
        "git_commit": commit,
        "git_branch": branch,
        "git_dirty": bool(dirty_output) if dirty_output is not None else None,
    }


def compute_file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_input_file_metadata(input_jsonl_path: str | Path) -> Dict[str, Any]:
    input_path = Path(input_jsonl_path).resolve()
    return {
        "resolved_input_jsonl": str(input_path),
        "input_jsonl_sha256": compute_file_sha256(input_path),
        "input_jsonl_bytes": input_path.stat().st_size,
    }


def build_run_config(
    args_dict: Dict[str, Any],
    output_jsonl: str,
    run_dir: str,
    model_name: str,
    script_path: str,
    cwd: str,
    repo_root: str,
    default_input_jsonl: str,
    api_base_url: str,
    api_timeout_seconds: int,
    api_call_retries: int,
    api_retry_backoff_seconds: int,
    fallback_model_names: Optional[list[str]] = None,
) -> Dict[str, Any]:
    run_config = {
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "started_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "script": os.path.abspath(script_path),
        "cwd": cwd,
        "repo_root": os.path.abspath(repo_root),
        "model_name": model_name,
        "fallback_model_names": list(fallback_model_names or []),
        "api_base_url": api_base_url,
        "api_timeout_seconds": api_timeout_seconds,
        "api_call_retries": api_call_retries,
        "api_retry_backoff_seconds": api_retry_backoff_seconds,
        "default_input_jsonl": str(default_input_jsonl),
        "output_jsonl": os.path.abspath(output_jsonl),
        "run_dir": os.path.abspath(run_dir),
        "arguments": args_dict,
    }
    run_config.update(detect_git_context(repo_root))
    return run_config


def build_sampled_input_record(
    sample_order: int,
    input_index: int,
    image_path: str,
    llm_input_renamed: str,
    aux_part: str,
    point_coords_grid: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "sample_order": sample_order,
        "input_index": input_index,
        "image_path": image_path,
        "llm_input_renamed": llm_input_renamed,
        "aux": aux_part,
        "point_coords_grid": point_coords_grid,
    }


def build_dataset_output_record(
    sample_order: int,
    instruction: str,
    public_problem: str,
    thinking: str,
    aux_part: str,
    generation_style: str,
    image_path: str | None = None,
) -> Dict[str, Any]:
    output = f"{thinking}\n{aux_part}"
    record = {
        "instruction": instruction,
        "input": public_problem,
        "thinking": thinking,
        "aux": aux_part,
        "output": output,
        "_order": sample_order,
    }
    if generation_style == INSIGHT_IMAGE_V1 and image_path:
        record["image_path"] = image_path
    return record


def build_missing_image_item_record(
    sample_order: int,
    input_index: int,
    image_path: str,
    source_audit: Dict[str, Any],
    error: str,
    generation_style: str | None = None,
) -> Dict[str, Any]:
    return {
        "sample_order": sample_order,
        "input_index": input_index,
        "image_path": image_path,
        "generation_style": generation_style,
        "goal_type": None,
        "aux_type": None,
        "source_audit": source_audit,
        "generation_audit": {"issues": [], "has_issue": False},
        "surface_pass": False,
        "success": False,
        "exported_to_dataset": False,
        "dataset_filter_reason": "generation_failed",
        "attempts_used": 0,
        "elapsed_seconds": None,
        "error": error,
    }


def build_generation_failure_item_record(
    sample_order: int,
    input_index: int,
    image_path: str,
    error: str,
    source_audit: Optional[Dict[str, Any]] = None,
    generation_style: str | None = None,
    goal_type: str | None = None,
    aux_type: str | None = None,
    public_problem: str | None = None,
    aux_part: str | None = None,
    hidden_rest_sanitized: str | None = None,
    point_coords_grid: Optional[Dict[str, Any]] = None,
    attempts_used: int = 0,
    elapsed_seconds: Optional[float] = None,
) -> Dict[str, Any]:
    return {
        "sample_order": sample_order,
        "input_index": input_index,
        "image_path": image_path,
        "generation_style": generation_style,
        "public_problem": public_problem,
        "aux": aux_part,
        "goal_type": goal_type,
        "aux_type": aux_type,
        "hidden_rest_sanitized": hidden_rest_sanitized,
        "point_coords_grid": point_coords_grid or {},
        "source_audit": source_audit or {"issues": [], "has_issue": False},
        "generation_audit": {"issues": [], "has_issue": False},
        "plan_prompt": None,
        "write_prompt": None,
        "plan_output": None,
        "plan_parsed": None,
        "insight_slots": None,
        "insight_plan_parsed": None,
        "backtrace_slots": None,
        "writer_handoff": None,
        "writer_validation_issues": [],
        "write_output": None,
        "thinking": None,
        "surface_pass": False,
        "success": False,
        "exported_to_dataset": False,
        "dataset_filter_reason": "generation_failed",
        "attempts_used": attempts_used,
        "elapsed_seconds": elapsed_seconds,
        "error": error,
    }


def _insight_family_has_hard_generation_audit_issue(
    generation_style: Optional[str],
    generation_audit: Dict[str, Any],
) -> bool:
    if generation_style not in INSIGHT_GENERATION_STYLES:
        return False
    issues = generation_audit.get("issues") or []
    return any(issue in INSIGHT_FAMILY_HARD_GENERATION_AUDIT_ISSUES for issue in issues)


def resolve_dataset_export_decision(
    generation_style: Optional[str],
    generation: Dict[str, Any],
    generation_audit: Dict[str, Any],
) -> tuple[bool, Optional[str]]:
    if not generation.get("success") or not generation.get("thinking"):
        return False, "generation_failed"
    if _insight_family_has_hard_generation_audit_issue(generation_style, generation_audit):
        return False, "generation_audit_hard_issue"
    return True, None


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
    generation_style: str | None = None,
    exported_to_dataset: bool = False,
    dataset_filter_reason: Optional[str] = None,
) -> Dict[str, Any]:
    surface_pass = bool(generation.get("success"))
    return {
        "sample_order": sample_order,
        "input_index": input_index,
        "image_path": image_path,
        "generation_style": generation_style or generation.get("generation_style"),
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
        "insight_slots": generation.get("insight_slots"),
        "insight_plan_parsed": generation.get("insight_plan_parsed"),
        "backtrace_slots": generation.get("backtrace_slots"),
        "writer_handoff": generation.get("writer_handoff"),
        "writer_validation_issues": list(generation.get("writer_validation_issues") or []),
        "write_output": generation.get("write_output"),
        "thinking": generation.get("thinking"),
        "surface_pass": surface_pass,
        "success": surface_pass,
        "exported_to_dataset": exported_to_dataset,
        "dataset_filter_reason": dataset_filter_reason,
        "attempts_used": generation.get("attempts_used"),
        "elapsed_seconds": generation.get("elapsed_seconds"),
        "error": generation.get("error"),
    }


def build_item_audit_record(item_record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "sample_order": item_record["sample_order"],
        "input_index": item_record["input_index"],
        "generation_style": item_record.get("generation_style"),
        "goal_type": item_record.get("goal_type"),
        "aux_type": item_record.get("aux_type"),
        "source_audit": item_record.get("source_audit", {}),
        "generation_audit": item_record.get("generation_audit", {}),
        "surface_pass": item_record.get("surface_pass", item_record.get("success", False)),
        "success": item_record.get("success", False),
        "exported_to_dataset": item_record.get(
            "exported_to_dataset",
            item_record.get("surface_pass", item_record.get("success", False)),
        ),
        "dataset_filter_reason": item_record.get("dataset_filter_reason"),
    }


def build_semantic_audit_stub(item_record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "sample_order": item_record["sample_order"],
        "input_index": item_record["input_index"],
        "generation_style": item_record.get("generation_style"),
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
    generation_style: str | None,
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
    exported_items = sum(
        1
        for item in item_records
        if item.get(
            "exported_to_dataset",
            item.get("surface_pass", item.get("success", False)),
        )
    )
    filtered_generation_audit_items = sum(
        1
        for item in item_records
        if item.get("dataset_filter_reason") == "generation_audit_hard_issue"
    )

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
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "input_jsonl": input_jsonl,
        "total_candidates_with_aux": total_candidates_with_aux,
        "sampled_items": sampled_items,
        "successful_items": surface_pass_items,
        "failed_items": surface_fail_items,
        "surface_pass_items": surface_pass_items,
        "surface_fail_items": surface_fail_items,
        "surface_pass_rate": _safe_rate(surface_pass_items, sampled_items),
        "exported_items": exported_items,
        "filtered_generation_audit_items": filtered_generation_audit_items,
        "exported_rate": _safe_rate(exported_items, sampled_items),
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
        "generation_style": generation_style,
        "output_jsonl": os.path.abspath(output_jsonl),
        "artifacts_dir": os.path.abspath(artifacts_dir),
        "runtime_seconds": runtime_seconds,
    }
