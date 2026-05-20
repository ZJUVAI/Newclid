#!/usr/bin/env python3
"""Replay current CoT SFT checks against an existing verbose artifact run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

try:
    from .audits import (
        audit_generation_quality,
        audit_source_record,
        build_visible_premise_summaries,
        extract_visible_formal_facts,
        get_point_coords,
    )
    from .generate_cot_sft import (
        build_image_coordinate_candidates,
        build_hidden_proof_guidance,
        build_visible_text_facts,
        compute_thinking_total_budget,
        validate_plan_response,
        validate_thinking_response,
        validate_writer_body,
    )
    from .geometry_text import (
        build_hidden_coordinate_candidates,
        extract_problem_goal,
        parse_goal_expression,
    )
except ImportError:  # pragma: no cover - script execution path
    from audits import (
        audit_generation_quality,
        audit_source_record,
        build_visible_premise_summaries,
        extract_visible_formal_facts,
        get_point_coords,
    )
    from generate_cot_sft import (
        build_image_coordinate_candidates,
        build_hidden_proof_guidance,
        build_visible_text_facts,
        compute_thinking_total_budget,
        validate_plan_response,
        validate_thinking_response,
        validate_writer_body,
    )
    from geometry_text import (
        build_hidden_coordinate_candidates,
        extract_problem_goal,
        parse_goal_expression,
    )


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def reconstruct_source_record(item_record: Dict[str, Any]) -> Dict[str, Any]:
    aux_part = item_record.get("aux", "") or ""
    hidden_rest = item_record.get("hidden_rest_sanitized", "") or ""
    output_parts = [part.strip() for part in [aux_part, hidden_rest] if isinstance(part, str) and part.strip()]
    return {
        "nl_problem": "",
        "llm_input_renamed": item_record.get("public_problem", "") or "",
        "llm_output_renamed": " ".join(output_parts),
        "point_coords_grid": item_record.get("point_coords_grid", {}) or {},
        "image_path": item_record.get("image_path", "") or "",
        "_aux_part": aux_part,
        "_sanitized_rest": hidden_rest,
    }


def recheck_item_record(item_record: Dict[str, Any]) -> Dict[str, Any]:
    record = reconstruct_source_record(item_record)
    aux_part = record["_aux_part"]
    sanitized_rest = record["_sanitized_rest"]
    visible_goal = extract_problem_goal(record)
    point_coords = get_point_coords(record)
    point_names = sorted(point_coords)
    visible_text_facts = build_visible_text_facts(record)
    coordinate_candidates = build_image_coordinate_candidates(point_coords, visible_text_facts, max_items=8)
    visible_premise_summaries = build_visible_premise_summaries(record)
    proof_guidance = build_hidden_proof_guidance(sanitized_rest, aux_part, visible_goal)
    image_path = Path(record.get("image_path", "") or "")

    source_audit = audit_source_record(
        record,
        image_path=image_path,
        aux_part=aux_part,
        visible_goal=visible_goal,
        proof_guidance=proof_guidance,
    )

    raw_plan = item_record.get("plan_output")
    if not raw_plan:
        raw_plan = item_record.get("plan_parsed") or {}
    plan_ok, plan_message, revalidated_plan = validate_plan_response(
        raw_plan,
        point_coords,
        visible_goal=visible_goal,
        aux_part=aux_part,
        coordinate_candidates=coordinate_candidates,
        sanitized_rest=sanitized_rest,
        visible_premise_summaries=visible_premise_summaries,
        visible_text_facts=visible_text_facts,
    )

    plan_for_checks = revalidated_plan or item_record.get("plan_parsed") or {}
    write_output = item_record.get("write_output", "") or ""
    thinking = item_record.get("thinking", "") or ""
    writer_ok = False
    writer_message = "missing_write_output"
    if plan_ok and revalidated_plan and write_output:
        writer_ok, writer_message = validate_writer_body(
            write_output,
            visible_goal=visible_goal,
            plan=revalidated_plan,
        )
    elif plan_ok and revalidated_plan:
        writer_message = "missing_write_output"
    else:
        writer_message = "plan_invalid"

    thinking_ok = False
    thinking_message = "missing_thinking"
    if thinking:
        thinking_ok, thinking_message = validate_thinking_response(
            thinking,
            point_coords=point_coords,
            require_coord_tags=False,
            max_total_len=compute_thinking_total_budget(plan_for_checks),
        )

    generation = {
        "success": bool(plan_ok and writer_ok and thinking_ok),
        "plan_parsed": plan_for_checks,
        "write_output": write_output,
        "thinking": thinking,
    }
    generation_audit = audit_generation_quality(
        record,
        generation,
        aux_part,
        coordinate_candidates=coordinate_candidates,
    )

    prior_source_audit = item_record.get("source_audit", {}) or {}
    prior_generation_audit = item_record.get("generation_audit", {}) or {}
    current_all_checks_pass = bool(
        plan_ok
        and writer_ok
        and thinking_ok
        and not generation_audit.get("has_issue")
    )

    return {
        "sample_order": item_record.get("sample_order"),
        "input_index": item_record.get("input_index"),
        "goal_type": parse_goal_expression(visible_goal).get("predicate") or None,
        "prior_surface_pass": bool(item_record.get("surface_pass", item_record.get("success", False))),
        "revalidated_plan_ok": bool(plan_ok),
        "revalidated_plan_message": plan_message,
        "revalidated_plan": revalidated_plan,
        "writer_valid": bool(writer_ok),
        "writer_message": writer_message,
        "thinking_valid": bool(thinking_ok),
        "thinking_message": thinking_message,
        "current_source_audit": source_audit,
        "current_generation_audit": generation_audit,
        "source_audit_changed": source_audit != prior_source_audit,
        "generation_audit_changed": generation_audit != prior_generation_audit,
        "current_all_checks_pass": current_all_checks_pass,
        "coordinate_candidate_count": len(coordinate_candidates),
        "visible_point_count": len(point_names),
    }


def summarize_rechecks(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows = list(rows)
    total_items = len(rows)
    return {
        "total_items": total_items,
        "prior_surface_pass_items": sum(1 for row in rows if row.get("prior_surface_pass")),
        "revalidated_plan_fail_items": sum(1 for row in rows if not row.get("revalidated_plan_ok")),
        "writer_fail_items": sum(1 for row in rows if not row.get("writer_valid")),
        "thinking_fail_items": sum(1 for row in rows if not row.get("thinking_valid")),
        "current_generation_audit_issue_items": sum(
            1 for row in rows if (row.get("current_generation_audit") or {}).get("has_issue")
        ),
        "source_audit_changed_items": sum(1 for row in rows if row.get("source_audit_changed")),
        "generation_audit_changed_items": sum(1 for row in rows if row.get("generation_audit_changed")),
        "current_all_checks_pass_items": sum(1 for row in rows if row.get("current_all_checks_pass")),
    }


def recheck_run_dir(run_dir: Path) -> Dict[str, Any]:
    item_records_path = run_dir / "item_records.jsonl"
    if not item_records_path.exists():
        raise FileNotFoundError(f"Missing item_records.jsonl: {item_records_path}")
    rows = [recheck_item_record(item_record) for item_record in read_jsonl(item_records_path)]
    return {
        "run_dir": str(run_dir),
        "summary": summarize_rechecks(rows),
        "items": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay current CoT SFT checks against an existing verbose artifact run."
    )
    parser.add_argument(
        "--run-dir",
        required=True,
        help="Artifacts directory containing item_records.jsonl from a verbose run.",
    )
    parser.add_argument(
        "--write-json",
        default="",
        help="Optional path to write the full replay payload as JSON.",
    )
    parser.add_argument(
        "--write-jsonl",
        default="",
        help="Optional path to write item-level replay rows as JSONL.",
    )
    args = parser.parse_args()

    payload = recheck_run_dir(Path(args.run_dir))
    if args.write_json:
        write_json(Path(args.write_json), payload)
    if args.write_jsonl:
        write_jsonl(Path(args.write_jsonl), payload["items"])
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
