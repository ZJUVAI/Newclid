#!/usr/bin/env python3
"""Render extracted-rule figures for risos subset in parallel."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

# Import the main rendering function
from render_rule_extractions_parallel import main as render_main
import argparse


def main() -> int:
    # Override sys.argv to pass custom arguments
    exp_dir = PROJECT_ROOT / "outputs/experiments/20260309_01_risos_subset_rule_extraction"

    sys.argv = [
        sys.argv[0],
        "--input-jsonl", str(PROJECT_ROOT / "outputs/datasets/square_case/risos_on_dia_eqdist_subset.jsonl"),
        "--pruned-json", str(PROJECT_ROOT / "outputs/datasets/square_case/risos_on_dia_eqdist_subset_pruned.json"),
        "--rules-stats", str(exp_dir / "intermediates/step1e_rules_stats.json"),
        "--output-dir", str(exp_dir / "risos_subset_figures"),
        "--workers", "30",
        "--progress-every", "10",
        "--dpi", "250",
        "--overwrite",
    ]

    return render_main()


if __name__ == "__main__":
    raise SystemExit(main())
