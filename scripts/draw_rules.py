#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
draw_rules.py — Standalone script to render geometry images for extracted rules.

Reads rules from a rules.txt file and the original JSONL (with pid field),
then draws the proof graph for each rule using FilterAndPruneEngine's render logic.

Usage:
    python scripts/draw_rules.py \\
        --rules outputs/experiments/.../part2/xxx_pruned_rules.txt \\
        --source outputs/experiments/.../part1/filtered.jsonl \\
        --output-dir outputs/experiments/.../images

    # Only draw specific rules
    python scripts/draw_rules.py \\
        --rules .../rules.txt \\
        --source .../filtered.jsonl \\
        --output-dir .../images \\
        --rule-ids r000001,r000002
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


def _load_rules_txt(rules_path: Path) -> List[tuple]:
    """Load (rule_id, rule_text) pairs from rules.txt."""
    pairs = []
    with open(rules_path, "r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    for i in range(0, len(lines), 2):
        if i + 1 >= len(lines):
            break
        pairs.append((lines[i], lines[i + 1]))
    return pairs


def _load_source_jsonl(source_path: Path) -> Dict[str, Dict[str, Any]]:
    """Load pid → record mapping from a JSONL file."""
    pid_map: Dict[str, Dict[str, Any]] = {}
    with open(source_path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict):
                continue
            pid = str(rec.get("pid") or rec.get("problem_id") or f"line:{idx:06d}")
            pid_map[pid] = rec
    return pid_map


def _extract_pid_from_rule_id(rule_id: str) -> Optional[str]:
    """Extract the source pid from a rule_id like 'r000001 pid=abc:000123'."""
    # Rule id format from _dump_rules: e.g. 'r000001 pid=filtered:000042'
    # or just 'r000001' with pid stored elsewhere
    if " pid=" in rule_id:
        pid_part = rule_id.split(" pid=", 1)[1].split(" ")[0]
        return pid_part
    return None


def draw_rules(
    rules_path: Path,
    source_path: Path,
    output_dir: Path,
    rule_ids: Optional[Set[str]] = None,
    max_workers: int = 4,
) -> Dict[str, Any]:
    """Draw geometry images for rules.

    For each rule in rules_path, find the corresponding source record in source_path
    and render the proof graph to output_dir/{rule_id}.png.
    """
    from newclid.proof_scout.core.filter_and_prune_engine import (
        FilterAndPruneEngine,
        _worker_prune,
        _build_proposition_no_aux,
        _to_rule_text,
        _convert_llm_record,
        _has_llm_format,
        _sanitize_basename,
        _worker_render_combined,
    )
    from concurrent.futures import ProcessPoolExecutor, as_completed

    output_dir.mkdir(parents=True, exist_ok=True)

    # Load rules
    rule_pairs = _load_rules_txt(rules_path)
    print(f"Loaded {len(rule_pairs)} rules from {rules_path}")

    # Filter by rule_ids if specified
    if rule_ids:
        rule_pairs = [(rid, rtxt) for rid, rtxt in rule_pairs if rid in rule_ids]
        print(f"Filtered to {len(rule_pairs)} rules matching --rule-ids")

    # Load source records
    pid_map = _load_source_jsonl(source_path)
    base = _sanitize_basename(source_path)
    print(f"Loaded {len(pid_map)} source records from {source_path}")

    # Build a set of pids we need
    engine = FilterAndPruneEngine(
        max_workers=max_workers,
        render_by_rule=True,
        keep_pid_images=False,
    )

    n_done = 0
    n_skipped = 0
    n_failed = 0

    for rule_id, rule_text in rule_pairs:
        out_png = output_dir / f"{rule_id}.png"
        if out_png.exists():
            n_skipped += 1
            continue

        # Find source pid from rule_id
        pid = _extract_pid_from_rule_id(rule_id)
        if pid is None:
            # Try matching by rule text: find record whose proposition matches
            n_skipped += 1
            print(f"  [skip] {rule_id}: cannot extract pid from rule_id")
            continue

        rec = pid_map.get(pid)
        if rec is None:
            n_skipped += 1
            print(f"  [skip] {rule_id}: pid={pid} not found in source")
            continue

        # Ensure record is in internal format
        if _has_llm_format(rec) and "proof" not in rec:
            idx = int(pid.split(":")[-1]) if ":" in pid else 0
            rec = _convert_llm_record(rec, base, idx)

        # Prune proof graph
        try:
            pid_val, rendered_list = _worker_prune(rec)
            if not rendered_list:
                n_skipped += 1
                print(f"  [skip] {rule_id}: graph pruning produced no subgraphs")
                continue
            rendered = rendered_list[0]  # use first subgraph
        except Exception as e:
            n_failed += 1
            print(f"  [fail] {rule_id}: graph pruning failed: {e}")
            continue

        # Render image
        try:
            pid_out, status = _worker_render_combined(
                rec,
                rendered,
                str(out_png),
                engine.label_mode,
                engine.figsize_single,
                engine.ranksep,
                engine.nodesep,
                engine.font_size,
            )
            if status == "ok":
                n_done += 1
            else:
                n_failed += 1
                print(f"  [fail] {rule_id}: render returned status={status}")
        except Exception as e:
            n_failed += 1
            print(f"  [fail] {rule_id}: render failed: {e}")

    print(f"\nDone: {n_done} rendered, {n_skipped} skipped, {n_failed} failed")
    print(f"Output: {output_dir}")
    return {"done": n_done, "skipped": n_skipped, "failed": n_failed}


def main():
    parser = argparse.ArgumentParser(
        description="Draw geometry proof graph images for extracted rules",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--rules", "-r", type=Path, required=True,
        help="Path to rules.txt (rule_id\\nrule_text\\n... format)",
    )
    parser.add_argument(
        "--source", "-s", type=Path, required=True,
        help="Path to source JSONL file containing original problem records",
    )
    parser.add_argument(
        "--output-dir", "-o", type=Path, required=True,
        help="Directory to write PNG images",
    )
    parser.add_argument(
        "--rule-ids", type=str, default=None,
        help="Comma-separated rule IDs to draw (default: draw all)",
    )
    parser.add_argument(
        "--max-workers", type=int, default=4,
        help="Parallel workers for rendering (default: 4)",
    )

    args = parser.parse_args()

    if not args.rules.exists():
        print(f"Error: rules file not found: {args.rules}", file=sys.stderr)
        sys.exit(1)
    if not args.source.exists():
        print(f"Error: source file not found: {args.source}", file=sys.stderr)
        sys.exit(1)

    rule_ids: Optional[Set[str]] = None
    if args.rule_ids:
        rule_ids = {r.strip() for r in args.rule_ids.split(",") if r.strip()}

    draw_rules(
        rules_path=args.rules,
        source_path=args.source,
        output_dir=args.output_dir,
        rule_ids=rule_ids,
        max_workers=args.max_workers,
    )


if __name__ == "__main__":
    main()
