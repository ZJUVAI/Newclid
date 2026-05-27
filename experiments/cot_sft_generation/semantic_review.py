#!/usr/bin/env python3
"""
Validate and summarize semantic-review artifacts for CoT SFT runs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

try:
    from .run_artifacts import (
        SEMANTIC_REVIEW_CHECKLIST_VERSION,
        SEMANTIC_REVIEW_ISSUE_CODE_DESCRIPTIONS,
    )
except ImportError:  # pragma: no cover - script execution path
    from run_artifacts import (
        SEMANTIC_REVIEW_CHECKLIST_VERSION,
        SEMANTIC_REVIEW_ISSUE_CODE_DESCRIPTIONS,
    )


def read_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_jsonl(path: Path, records: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def normalize_semantic_audit_record(record: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(record)
    normalized.setdefault("surface_pass", False)
    normalized.setdefault("semantic_pass", None)
    normalized.setdefault("manual_critical_error", None)
    normalized.setdefault("goal_type", None)
    normalized.setdefault("aux_type", None)
    normalized.setdefault("review_status", "pending")
    normalized.setdefault("review_checklist_version", SEMANTIC_REVIEW_CHECKLIST_VERSION)
    normalized.setdefault("reviewer", None)
    normalized.setdefault("issue_codes", [])
    normalized.setdefault("issues", [])
    normalized.setdefault("notes", "")
    if normalized["semantic_pass"] is None and normalized["review_status"] != "pending":
        normalized["review_status"] = "pending"
    if normalized["semantic_pass"] is not None:
        normalized["review_status"] = "reviewed"
    if normalized["review_checklist_version"] != SEMANTIC_REVIEW_CHECKLIST_VERSION:
        raise ValueError(
            "semantic audit field 'review_checklist_version' must match "
            f"{SEMANTIC_REVIEW_CHECKLIST_VERSION!r}"
        )
    if not isinstance(normalized["issue_codes"], list):
        raise ValueError("semantic audit field 'issue_codes' must be a list")
    for issue_code in normalized["issue_codes"]:
        if issue_code not in SEMANTIC_REVIEW_ISSUE_CODE_DESCRIPTIONS:
            raise ValueError(f"unknown semantic audit issue code: {issue_code!r}")
    if not isinstance(normalized["issues"], list):
        raise ValueError("semantic audit field 'issues' must be a list")
    if normalized["semantic_pass"] is False and not normalized["issue_codes"] and not normalized["issues"]:
        raise ValueError(
            "semantic audit rows marked semantic_pass=false must include at least one issue code or issue note"
        )
    if normalized["semantic_pass"] is True and normalized["manual_critical_error"] is True:
        raise ValueError(
            "semantic audit rows cannot set semantic_pass=true together with manual_critical_error=true"
        )
    return normalized


def validate_semantic_audit_alignment(
    item_audits: List[Dict[str, Any]],
    semantic_audits: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if len(item_audits) != len(semantic_audits):
        raise ValueError(
            "semantic_audits.jsonl must have the same number of rows as item_audits.jsonl"
        )

    normalized: List[Dict[str, Any]] = []
    for idx, (item_audit, semantic_audit) in enumerate(zip(item_audits, semantic_audits)):
        normalized_record = normalize_semantic_audit_record(semantic_audit)
        expected_pair = (item_audit.get("sample_order"), item_audit.get("input_index"))
        actual_pair = (
            normalized_record.get("sample_order"),
            normalized_record.get("input_index"),
        )
        if expected_pair != actual_pair:
            raise ValueError(
                "semantic audit row "
                f"{idx} does not align with item_audits row {idx}: "
                f"expected {expected_pair}, got {actual_pair}"
            )
        expected_goal_type = item_audit.get("goal_type")
        if expected_goal_type is not None and normalized_record.get("goal_type") != expected_goal_type:
            raise ValueError(
                "semantic audit row "
                f"{idx} goal_type mismatch: expected {expected_goal_type!r}, "
                f"got {normalized_record.get('goal_type')!r}"
            )
        expected_aux_type = item_audit.get("aux_type")
        if expected_aux_type is not None and normalized_record.get("aux_type") != expected_aux_type:
            raise ValueError(
                "semantic audit row "
                f"{idx} aux_type mismatch: expected {expected_aux_type!r}, "
                f"got {normalized_record.get('aux_type')!r}"
            )
        normalized.append(normalized_record)
    return normalized


def build_semantic_summary_fields(
    item_audits: List[Dict[str, Any]],
    semantic_audits: List[Dict[str, Any]],
) -> Dict[str, Any]:
    sampled_items = len(item_audits)
    surface_pass_items = sum(1 for item in item_audits if item.get("surface_pass", item.get("success", False)))
    surface_fail_items = sampled_items - surface_pass_items

    reviewed_items = sum(1 for item in semantic_audits if item.get("semantic_pass") is not None)
    semantic_pass_items = sum(1 for item in semantic_audits if item.get("semantic_pass") is True)
    semantic_fail_items = sum(1 for item in semantic_audits if item.get("semantic_pass") is False)
    manual_critical_error_items = sum(
        1 for item in semantic_audits if item.get("manual_critical_error") is True
    )

    if reviewed_items == 0:
        semantic_review_status = "not_reviewed"
        semantic_pass_rate = None
    elif reviewed_items < sampled_items:
        semantic_review_status = "partially_reviewed"
        semantic_pass_rate = semantic_pass_items / reviewed_items
    else:
        semantic_review_status = "fully_reviewed"
        semantic_pass_rate = semantic_pass_items / reviewed_items

    return {
        "sampled_items": sampled_items,
        "successful_items": surface_pass_items,
        "failed_items": surface_fail_items,
        "surface_pass_items": surface_pass_items,
        "surface_fail_items": surface_fail_items,
        "surface_pass_rate": (surface_pass_items / sampled_items) if sampled_items else None,
        "semantic_reviewed_items": reviewed_items,
        "semantic_pass_items": semantic_pass_items,
        "semantic_fail_items": semantic_fail_items,
        "semantic_pass_rate": semantic_pass_rate,
        "manual_critical_error_items": manual_critical_error_items,
        "manual_critical_error_rate": (
            manual_critical_error_items / reviewed_items if reviewed_items else None
        ),
        "semantic_review_status": semantic_review_status,
    }


def build_pending_review_queue(
    item_audits: List[Dict[str, Any]],
    semantic_audits: List[Dict[str, Any]],
    surface_pass_only: bool = False,
    max_items: int | None = None,
) -> List[Dict[str, Any]]:
    normalized = validate_semantic_audit_alignment(item_audits, semantic_audits)
    queue: List[Dict[str, Any]] = []
    for item_audit, semantic_audit in zip(item_audits, normalized):
        if semantic_audit.get("semantic_pass") is not None:
            continue
        surface_pass = item_audit.get("surface_pass", item_audit.get("success", False))
        if surface_pass_only and not surface_pass:
            continue
        queue.append(
            {
                "sample_order": semantic_audit.get("sample_order"),
                "input_index": semantic_audit.get("input_index"),
                "goal_type": semantic_audit.get("goal_type"),
                "aux_type": semantic_audit.get("aux_type"),
                "surface_pass": surface_pass,
                "review_recommendation": "review_now" if surface_pass else "fix_surface_first",
                "source_audit_issues": (item_audit.get("source_audit") or {}).get("issues", []),
                "generation_audit_issues": (item_audit.get("generation_audit") or {}).get("issues", []),
            }
        )
        if max_items is not None and len(queue) >= max_items:
            break
    return queue


def validate_item_record_alignment(
    item_audits: List[Dict[str, Any]],
    item_records: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if len(item_audits) != len(item_records):
        raise ValueError(
            "item_records.jsonl must have the same number of rows as item_audits.jsonl "
            "when building review payloads"
        )
    normalized: List[Dict[str, Any]] = []
    for idx, (item_audit, item_record) in enumerate(zip(item_audits, item_records)):
        expected_pair = (item_audit.get("sample_order"), item_audit.get("input_index"))
        actual_pair = (item_record.get("sample_order"), item_record.get("input_index"))
        if expected_pair != actual_pair:
            raise ValueError(
                "item_records row "
                f"{idx} does not align with item_audits row {idx}: "
                f"expected {expected_pair}, got {actual_pair}"
            )
        normalized.append(item_record)
    return normalized


def build_pending_review_payloads(
    item_records: List[Dict[str, Any]],
    item_audits: List[Dict[str, Any]],
    semantic_audits: List[Dict[str, Any]],
    surface_pass_only: bool = False,
    max_items: int | None = None,
) -> List[Dict[str, Any]]:
    normalized_item_records = validate_item_record_alignment(item_audits, item_records)
    normalized_semantic_audits = validate_semantic_audit_alignment(item_audits, semantic_audits)
    payloads: List[Dict[str, Any]] = []
    for item_record, item_audit, semantic_audit in zip(
        normalized_item_records,
        item_audits,
        normalized_semantic_audits,
    ):
        if semantic_audit.get("semantic_pass") is not None:
            continue
        surface_pass = item_audit.get("surface_pass", item_audit.get("success", False))
        if surface_pass_only and not surface_pass:
            continue
        payloads.append(
            {
                "sample_order": item_record.get("sample_order"),
                "input_index": item_record.get("input_index"),
                "goal_type": item_record.get("goal_type"),
                "aux_type": item_record.get("aux_type"),
                "surface_pass": surface_pass,
                "review_recommendation": "review_now" if surface_pass else "fix_surface_first",
                "context": {
                    "generation_style": item_record.get("generation_style"),
                    "image_path": item_record.get("image_path", ""),
                    "public_problem": item_record.get("public_problem", ""),
                    "aux": item_record.get("aux", ""),
                    "thinking": item_record.get("thinking"),
                    "plan_parsed": item_record.get("plan_parsed"),
                    "insight_slots": item_record.get("insight_slots"),
                    "insight_plan_parsed": item_record.get("insight_plan_parsed"),
                    "write_output": item_record.get("write_output"),
                    "source_audit": item_record.get("source_audit", {}),
                    "generation_audit": item_record.get("generation_audit", {}),
                    "attempts_used": item_record.get("attempts_used"),
                    "error": item_record.get("error"),
                },
                "review_stub": semantic_audit,
            }
        )
        if max_items is not None and len(payloads) >= max_items:
            break
    return payloads


def refresh_run_summary(run_dir: Path, write_summary: bool = False) -> Dict[str, Any]:
    summary_path = run_dir / "summary.json"
    item_audits_path = run_dir / "item_audits.jsonl"
    semantic_audits_path = run_dir / "semantic_audits.jsonl"

    summary = read_json(summary_path)
    item_audits = read_jsonl(item_audits_path)
    semantic_audits = validate_semantic_audit_alignment(
        item_audits,
        read_jsonl(semantic_audits_path),
    )
    summary.update(build_semantic_summary_fields(item_audits, semantic_audits))

    if write_summary:
        write_json(summary_path, summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate semantic review records and refresh CoT SFT run summary metrics."
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        required=True,
        help="Artifacts directory containing summary.json, item_audits.jsonl, and semantic_audits.jsonl.",
    )
    parser.add_argument(
        "--write-summary",
        action="store_true",
        help="Overwrite summary.json with refreshed semantic review metrics.",
    )
    parser.add_argument(
        "--print-pending",
        action="store_true",
        help="Print the pending semantic-review queue for iteration-time Codex review.",
    )
    parser.add_argument(
        "--surface-pass-only",
        action="store_true",
        help="When printing pending reviews, include only rows that already passed surface checks.",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=None,
        help="Optional cap when printing the pending review queue.",
    )
    parser.add_argument(
        "--print-pending-payloads",
        action="store_true",
        help="Print full pending review payloads. Requires item_records.jsonl, which is emitted by verbose runs.",
    )
    parser.add_argument(
        "--export-pending-review-jsonl",
        type=Path,
        default=None,
        help="Write full pending review payloads to a JSONL file. Requires item_records.jsonl from a verbose run.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_dir = args.run_dir.resolve()
    summary = refresh_run_summary(run_dir, write_summary=args.write_summary)
    if not args.print_pending and not args.print_pending_payloads and args.export_pending_review_jsonl is None:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    item_audits = read_jsonl(run_dir / "item_audits.jsonl")
    semantic_audits = read_jsonl(run_dir / "semantic_audits.jsonl")
    pending_reviews = build_pending_review_queue(
        item_audits,
        semantic_audits,
        surface_pass_only=args.surface_pass_only,
        max_items=args.max_items,
    )
    pending_payloads = None
    if args.print_pending_payloads or args.export_pending_review_jsonl is not None:
        item_records_path = run_dir / "item_records.jsonl"
        if not item_records_path.exists():
            raise FileNotFoundError(
                "pending review payload export requires item_records.jsonl; rerun generation with --verbose"
            )
        item_records = read_jsonl(item_records_path)
        pending_payloads = build_pending_review_payloads(
            item_records,
            item_audits,
            semantic_audits,
            surface_pass_only=args.surface_pass_only,
            max_items=args.max_items,
        )
    if args.export_pending_review_jsonl is not None:
        export_path = args.export_pending_review_jsonl.resolve()
        write_jsonl(export_path, pending_payloads or [])
    print(
        json.dumps(
            {
                "summary": summary,
                "pending_review_items": len(pending_reviews),
                "surface_pass_only": args.surface_pass_only,
                "pending_reviews": pending_reviews,
                "pending_review_payload_items": len(pending_payloads or []),
                "pending_review_payloads": pending_payloads if args.print_pending_payloads else None,
                "pending_review_payload_export": (
                    str(args.export_pending_review_jsonl.resolve())
                    if args.export_pending_review_jsonl is not None else None
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
