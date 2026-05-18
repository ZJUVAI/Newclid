#!/usr/bin/env python3
"""
Validate and summarize semantic-review artifacts for CoT SFT runs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


def read_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


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
    normalized.setdefault("review_status", "pending")
    normalized.setdefault("reviewer", None)
    normalized.setdefault("issues", [])
    normalized.setdefault("notes", "")
    if normalized["semantic_pass"] is None and normalized["review_status"] != "pending":
        normalized["review_status"] = "pending"
    if normalized["semantic_pass"] is not None:
        normalized["review_status"] = "reviewed"
    if not isinstance(normalized["issues"], list):
        raise ValueError("semantic audit field 'issues' must be a list")
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = refresh_run_summary(args.run_dir.resolve(), write_summary=args.write_summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
