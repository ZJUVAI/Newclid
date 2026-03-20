#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run 10k rule extraction with eqpoint/constline filtering.

Filters out records where llm_output_renamed contains 'eqpoint' or 'constline'
before graph pruning and rule extraction.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from newclid.proof_scout.core.filter_and_prune_engine import FilterAndPruneEngine  # noqa: E402


INPUT_JSON = str(PROJECT_ROOT / "outputs/datasets/synthetic_10k_aux_only/geometry_clauses15_samples10k.jsonl")
OUTPUT_DIR = str(PROJECT_ROOT / "outputs/experiments/20260309_10k_rule_extraction_no_eqpoint_constline")


def main() -> int:
    engine = FilterAndPruneEngine(
        label_mode="legend",
        figsize_single=(15, 20),
        figsize_combined=(30, 20),
        font_size=9,
        ranksep=2.8,
        nodesep=1.2,
        overwrite=True,
        progress_every=50,
        max_workers=50,
        render_by_rule=False,     # Skip image rendering for speed
        keep_pid_images=False,
        skip_predicates=["eqpoint", "constline"],
    )

    try:
        stats = engine.run(INPUT_JSON, OUTPUT_DIR, save_intermediates=True)
        print("=" * 60)
        print("FINAL SUMMARY")
        print("=" * 60)
        print(f"Total records:      {stats.get('total', 0)}")
        print(f"Kept after filters: {stats.get('kept', 0)}")
        print(f"Dropped:            {stats.get('dropped', 0)}")
        print(f"Rules extracted:    {stats.get('rules', 0)}")
        print(f"Skipped rules:      {stats.get('skipped_rules', 0)}")
        print(f"JSON saved:         {stats.get('json', '')}")
        return 0
    except Exception as exc:
        print(f"[ERROR] {exc}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
