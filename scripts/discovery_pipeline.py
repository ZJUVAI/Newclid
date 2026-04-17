#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Discovery Pipeline — unified config-based rule extraction and reduction.

Replaces the old discovery_pipeline.py (Python solver) and discovery_pipeline_c.py
(CSolver). All stages now use CSolver for subsumption testing.

Usage:
    python scripts/discovery_pipeline.py
    python scripts/discovery_pipeline.py --config scripts/discovery_pipeline_config.json

The pipeline consists of 4 Parts:

    Part 1: Input filter      — drop records without aux_points / matching skip_predicates
    Part 2: Extract rules     — graph prune → proposition → normalization → dedup → dump
    Part 3: max_premises      — filter rules exceeding max_premises (skipped if null)
    Part 4: Reduction         — seed / divide-and-conquer subsumption-based rule reduction

Each Part can be independently enabled/disabled and accepts custom input/output paths.
When a Part is disabled, the next enabled Part inherits the previous Part's output.

Config schema: scripts/discovery_pipeline_config.json (see for full example).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


# ============================================================================
# Config loading and validation
# ============================================================================

def load_config(config_path: Path) -> Dict[str, Any]:
    """Load and validate the pipeline config JSON."""
    with open(config_path, "r", encoding="utf-8") as f:
        raw = f.read()
    # Strip C-style comment lines (lines starting with //) before parsing
    lines = [ln for ln in raw.splitlines() if not ln.strip().startswith("//")]
    cfg = json.loads("\n".join(lines))

    # Strip _comment keys recursively (they are documentation only)
    def strip_comments(obj):
        if isinstance(obj, dict):
            return {k: strip_comments(v) for k, v in obj.items() if not k.startswith("_comment")}
        if isinstance(obj, list):
            return [strip_comments(i) for i in obj]
        return obj

    return strip_comments(cfg)


def _resolve_output(cfg_output: Optional[str], output_dir: Path, subdir: str, filename: str) -> Path:
    """Resolve a Part's output path.

    If cfg_output is specified, use it directly.
    Otherwise default to output_dir/subdir/filename.
    """
    if cfg_output:
        return Path(cfg_output)
    return output_dir / subdir / filename


# ============================================================================
# Pipeline Summary
# ============================================================================

class PipelineSummary:
    """Pipeline execution summary collector."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.start_time = time.time()
        self.parts = {}
        self.initial_seed_count = None

    def record_part(self, part_name: str, enabled: bool, stats: Optional[Dict] = None):
        """Record a Part's execution status and stats."""
        self.parts[part_name] = {
            "enabled": enabled,
            "executed": stats is not None,
            "stats": stats or {}
        }

    def set_initial_seed_count(self, count: int):
        """Record unique seed count from initial data."""
        self.initial_seed_count = count

    def save(self):
        """Write summary to pipeline_summary.json."""
        summary = {
            "pipeline_start": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.start_time)),
            "total_elapsed_seconds": round(time.time() - self.start_time, 1),
            "initial_seed_count": self.initial_seed_count,
            "parts": self.parts
        }
        output_path = self.output_dir / "pipeline_summary.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print(f"\n[Pipeline Summary] → {output_path}")


def _count_unique_seeds(jsonl_path: Path) -> int:
    """Count unique seeds in JSONL file."""
    seeds = set()
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                seed = record.get("seed")
                if seed is not None:
                    seeds.add(seed)
            except json.JSONDecodeError:
                continue
    return len(seeds)


# ============================================================================
# Part 1: Input filter
# ============================================================================

def run_part1(cfg: Dict[str, Any], output_dir: Path) -> tuple:
    """Run Part 1 (input filter).

    Returns:
        (output_path, stats_dict): output path is None if disabled;
        stats_dict is None if disabled, otherwise contains execution stats.
    """
    p1 = cfg.get("part1_filter", {})
    if not p1.get("enabled", True):
        print("[Part 1] Disabled, skipping.")
        return None, None

    start_time = time.time()

    input_path = p1.get("input")
    if not input_path:
        print("Error: part1_filter.input is required when Part 1 is enabled", file=sys.stderr)
        sys.exit(1)
    input_path = Path(input_path)

    output_path = _resolve_output(p1.get("output"), output_dir, "part1", "filtered.jsonl")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    skip_predicates = p1.get("skip_predicates") or []

    print(f"\n{'='*60}")
    print(f"Part 1: Input Filter")
    print(f"{'='*60}")
    print(f"  Input:  {input_path}")
    print(f"  Output: {output_path}")

    from newclid.proof_scout.core.filter_and_prune_engine import FilterAndPruneEngine

    engine = FilterAndPruneEngine(
        skip_predicates=skip_predicates if skip_predicates else None,
        render_by_rule=False,
        keep_pid_images=False,
    )
    engine_stats = engine.run_part1_filter(input_path, output_path)

    elapsed = time.time() - start_time
    print(f"[Part 1] Done — {engine_stats['kept']}/{engine_stats['total']} records kept → {output_path}")

    stats = {
        "input_path": str(input_path),
        "output_path": str(output_path),
        "input_count": engine_stats.get("total", 0),
        "output_count": engine_stats.get("kept", 0),
        "dropped_no_aux": engine_stats.get("dropped_no_aux", 0),
        "dropped_predicate": engine_stats.get("dropped_predicate", 0),
        "elapsed_seconds": round(elapsed, 2),
    }
    return output_path, stats


# ============================================================================
# Part 2: Graph prune + rule extraction
# ============================================================================

def run_part2(
    cfg: Dict[str, Any],
    output_dir: Path,
    prev_output: Optional[Path],
) -> tuple:
    """Run Part 2 (extract rules).

    Returns:
        (output_path, stats_dict): output path is None if disabled;
        stats_dict is None if disabled, otherwise contains execution stats.
    """
    p2 = cfg.get("part2_extract", {})
    if not p2.get("enabled", True):
        print("[Part 2] Disabled, skipping.")
        return None, None

    start_time = time.time()

    # Determine input
    input_path_cfg = p2.get("input")
    if input_path_cfg:
        input_path = Path(input_path_cfg)
    elif prev_output is not None:
        input_path = prev_output
    else:
        print("Error: part2_extract.input is required (no previous Part output available)", file=sys.stderr)
        sys.exit(1)

    part2_dir = _resolve_output(p2.get("output"), output_dir, "part2", ".")
    if part2_dir.suffix:  # user gave a file path; use its parent as dir
        part2_dir = part2_dir.parent
    part2_dir.mkdir(parents=True, exist_ok=True)

    n_workers = cfg.get("global", {}).get("n_workers", 30)
    rule_skip_predicates = p2.get("rule_skip_predicates") or []
    save_intermediates = cfg.get("global", {}).get("save_intermediates", False)

    streaming_cfg = p2.get("streaming", {})
    use_streaming = streaming_cfg.get("enabled", False)

    print(f"\n{'='*60}")
    print(f"Part 2: Rule Extraction {'(STREAMING)' if use_streaming else ''}")
    print(f"{'='*60}")
    print(f"  Input:  {input_path}")
    print(f"  Output: {part2_dir}")
    print(f"  n_workers: {n_workers}")

    from newclid.proof_scout.core.filter_and_prune_engine import FilterAndPruneEngine

    engine = FilterAndPruneEngine(
        max_workers=n_workers,
        rule_skip_predicates=rule_skip_predicates if rule_skip_predicates else None,
        render_by_rule=False,
        keep_pid_images=False,
    )

    if use_streaming:
        chunk_size = streaming_cfg.get("chunk_size", 10000)
        inflight_limit = streaming_cfg.get("inflight_limit", 300)
        result = engine.run_streaming(
            input_path, part2_dir,
            chunk_size=chunk_size,
            inflight_limit=inflight_limit,
            save_intermediates=save_intermediates,
        )
        rules_file_str = result.get("json", "")
        if rules_file_str:
            # streaming output: {stem}_pruned_rules.txt (same dir)
            rules_file = Path(rules_file_str).with_name(
                Path(rules_file_str).stem + "_rules.txt"
            ) if not rules_file_str.endswith("_rules.txt") else Path(rules_file_str)
        else:
            rules_file = None
    else:
        result = engine.run_part2_extract(
            input_path, part2_dir,
            save_intermediates=save_intermediates,
        )
        rules_file_str = result.get("rules_file")
        rules_file = Path(rules_file_str) if rules_file_str else None

    elapsed = time.time() - start_time

    if rules_file and rules_file.exists():
        print(f"[Part 2] Done — {result.get('rules', 0)} rules → {rules_file}")
    else:
        print("[Part 2] Warning: no rules_file produced")

    stats = {
        "input_path": str(input_path),
        "output_path": str(rules_file) if rules_file else None,
        "input_count": result.get("kept", 0),
        "output_count": result.get("rules", 0),
        "skipped_rules": result.get("skipped_rules", 0),
        "elapsed_seconds": round(elapsed, 2),
    }

    # Add step_timing if available
    if "step_timing" in result:
        stats["step_timing"] = result["step_timing"]

    # Add source_data_file if available
    if "source_data_file" in result:
        stats["source_data_file"] = result["source_data_file"]

    return rules_file, stats


# ============================================================================
# Part 3: max_premises filter
# ============================================================================

def run_part3(
    cfg: Dict[str, Any],
    output_dir: Path,
    prev_output: Optional[Path],
) -> tuple:
    """Run Part 3 (max_premises filter).

    Returns:
        (output_path, stats_dict): output path is None if disabled/skipped;
        stats_dict is None if disabled/skipped, otherwise contains execution stats.
    """
    p3 = cfg.get("part3_max_premises", {})

    # If max_premises is null, skip this Part entirely
    max_premises = p3.get("max_premises")
    if not p3.get("enabled", True) or max_premises is None:
        reason = "disabled" if not p3.get("enabled", True) else "max_premises is null"
        print(f"[Part 3] Skipped ({reason}).")
        return None, None

    start_time = time.time()

    # Determine input
    input_path_cfg = p3.get("input")
    if input_path_cfg:
        input_path = Path(input_path_cfg)
    elif prev_output is not None:
        input_path = prev_output
    else:
        print("Error: part3_max_premises.input is required (no previous Part output available)", file=sys.stderr)
        sys.exit(1)

    output_path = _resolve_output(p3.get("output"), output_dir, "part3", "filtered_rules.txt")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"Part 3: max_premises Filter (max_premises={max_premises})")
    print(f"{'='*60}")
    print(f"  Input:  {input_path}")
    print(f"  Output: {output_path}")

    # Load rules
    with open(input_path, "r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip()]

    # Parse rule_id / rule_text pairs and count premises
    kept_lines = []
    skipped = 0
    for i in range(0, len(lines), 2):
        if i + 1 >= len(lines):
            break
        rule_id = lines[i]
        rule_text = lines[i + 1]
        # Count premises: number of comma-separated items before '=>'
        if "=>" in rule_text:
            n_prem = len([c for c in rule_text.split("=>")[0].split(",") if c.strip()])
        else:
            n_prem = 0
        if n_prem <= max_premises:
            kept_lines.append(rule_id)
            kept_lines.append(rule_text)
        else:
            skipped += 1

    n_kept = len(kept_lines) // 2
    elapsed = time.time() - start_time
    print(f"[Part 3] {n_kept} kept, {skipped} skipped (premises > {max_premises})")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(kept_lines))
        if kept_lines:
            f.write("\n")

    print(f"[Part 3] Done → {output_path}")

    stats = {
        "input_path": str(input_path),
        "output_path": str(output_path),
        "input_count": len(lines) // 2,
        "output_count": n_kept,
        "max_premises": max_premises,
        "elapsed_seconds": round(elapsed, 2),
    }
    return output_path, stats


# ============================================================================
# Part 4: Reduction
# ============================================================================

def _load_rules_for_reduction(
    rules_file: Path,
    source_data_file: Optional[Path],
) -> tuple:
    """Load rules from rules_file + optional source_data_file."""
    from newclid.proof_scout.reduction import load_rules_from_discovery_output

    if source_data_file and source_data_file.exists():
        rules, failures = load_rules_from_discovery_output(rules_file, source_data_file)
    else:
        # No source data: load rules without RuleWithSource metadata
        # (points/premises parsed from llm_input_renamed will be empty)
        rules, failures = load_rules_from_discovery_output(
            rules_file,
            source_data_file if source_data_file else rules_file,  # fallback: won't match
        )
    return rules, failures


def run_part4(
    cfg: Dict[str, Any],
    output_dir: Path,
    prev_output: Optional[Path],
    source_data_file: Optional[Path] = None,
) -> tuple:
    """Run Part 4 (reduction).

    Returns:
        (output_path, stats_dict): output path is None if disabled;
        stats_dict is None if disabled, otherwise contains execution stats.
    """
    p4 = cfg.get("part4_reduction", {})
    if not p4.get("enabled", True):
        print("[Part 4] Disabled, skipping.")
        return None, None

    start_time = time.time()
    stage_timing = {}

    # Determine input (rules.txt)
    input_path_cfg = p4.get("input")
    if input_path_cfg:
        input_path = Path(input_path_cfg)
    elif prev_output is not None:
        input_path = prev_output
    else:
        print("Error: part4_reduction.input is required (no previous Part output available)", file=sys.stderr)
        sys.exit(1)

    # Determine source_data (JSONL or step6_rules_stats.json with llm_input_renamed)
    # Priority: config > passed-in argument > auto-detect near rules file
    source_data_cfg = p4.get("source_data")
    if source_data_cfg:
        source_data_file = Path(source_data_cfg)
    elif source_data_file is None:
        # Auto-detect: look for step6_rules_stats.json alongside the rules file
        candidate = input_path.parent / "intermediates" / "step6_rules_stats.json"
        if candidate.exists():
            source_data_file = candidate

    output_path = _resolve_output(p4.get("output"), output_dir, "part4", "extracted_rules.txt")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    engine = p4.get("engine", "full")
    timeout = p4.get("timeout", 60)
    n_workers = cfg.get("global", {}).get("n_workers", 30)
    batch_size = p4.get("batch_size", 10)
    debug = p4.get("debug", False)

    seed_red_cfg = p4.get("seed_reduction", {})
    dc_red_cfg = p4.get("divide_conquer_reduction", {})

    seed_reduction_enabled = seed_red_cfg.get("enabled", False)
    dc_reduction_enabled = dc_red_cfg.get("enabled", True)

    print(f"\n{'='*60}")
    print(f"Part 4: Reduction")
    print(f"{'='*60}")
    print(f"  Input (rules):  {input_path}")
    print(f"  Source data:    {source_data_file or '(none — will fail if rules need llm_input)'}")
    print(f"  Output:         {output_path}")
    print(f"  engine={engine}, timeout={timeout}, n_workers={n_workers}, batch_size={batch_size}")
    print(f"  seed_reduction={seed_reduction_enabled}, divide_conquer_reduction={dc_reduction_enabled}")

    # Initialize Ray unconditionally
    import ray
    if not ray.is_initialized():
        ray.init(ignore_reinit_error=True)
        print(f"  Ray initialized: {ray.cluster_resources()}")

    from newclid.proof_scout.reduction import (
        RuleReducer,
        DivideConquerReducer,
        load_rules_from_discovery_output,
    )

    # Standard mode: load all rules into memory first
    load_start = time.time()
    if source_data_file and source_data_file.exists():
        rules, failures = load_rules_from_discovery_output(input_path, source_data_file)
    else:
        print(f"  Error: source_data not found. Set part4_reduction.source_data in config to the "
              f"original JSONL or step6_rules_stats.json file.", file=sys.stderr)
        sys.exit(1)

    load_elapsed = time.time() - load_start
    stage_timing["load_rules"] = round(load_elapsed, 2)
    print(f"  Loaded {len(rules)} rules ({len(failures)} failures) in {load_elapsed:.1f}s")

    if failures:
        fail_path = output_path.parent / "load_failures.json"
        with open(fail_path, "w", encoding="utf-8") as f:
            json.dump({
                "total_failures": len(failures),
                "failures": [{"rule_id": r, "rule_text": t, "reason": e} for r, t, e in failures],
            }, f, ensure_ascii=False, indent=2)

    if not rules:
        print("[Part 4] No rules to reduce!")
        # Write empty output
        with open(output_path, "w", encoding="utf-8") as f:
            pass
        total_elapsed = time.time() - start_time
        stats = {
            "input_path": str(input_path),
            "output_path": str(output_path),
            "source_data_path": str(source_data_file) if source_data_file else None,
            "input_count": 0,
            "output_count": 0,
            "elapsed_seconds": round(total_elapsed, 2),
            "stage_timing": stage_timing,
        }
        return output_path, stats

    # Validate seed_reduction precondition
    if seed_reduction_enabled:
        has_seed = any(r.seed is not None for r in rules)
        if not has_seed:
            print(
                "Error: seed_reduction.enabled=true but no rules have a seed field. "
                "Aborting to prevent silent incorrect results.",
                file=sys.stderr,
            )
            sys.exit(1)

    current_rules = list(rules)
    initial_count = len(current_rules)

    # Stats collectors
    seed_red_stats = None
    dc_red_stats = None

    # --- Seed reduction ---
    if seed_reduction_enabled:
        stage_start = time.time()
        print(f"\n[Part 4 / seed_reduction] {len(current_rules)} rules")

        reducer = RuleReducer(
            timeout=timeout,
            n_workers=n_workers,
            batch_size=batch_size,
            debug=debug,
            debug_output_dir=output_path.parent if debug else None,
            solver_type="csolver",
            engine=engine,
            use_ray=True,
        )
        seed_result = reducer.reduce_by_seed(current_rules, use_ray=True)
        seed_input_count = len(current_rules)
        current_rules = seed_result["basis_rules"]
        stage_elapsed = time.time() - stage_start
        stage_timing["seed_reduction"] = round(stage_elapsed, 2)
        print(f"[Part 4 / seed_reduction] {seed_input_count} → {len(current_rules)} rules "
              f"({stage_elapsed:.1f}s)")

        # Collect detailed group stats
        seed_stats_raw = seed_result.get("stats", {})
        group_details = seed_stats_raw.get("group_details", [])
        n_groups = seed_stats_raw.get("n_groups", len(group_details))
        n_no_seed = seed_stats_raw.get("n_no_seed", 0)

        # Compute averages from group_details (field names: seed, input, basis, eliminated, skipped_premises)
        if group_details:
            avg_input = sum(g.get("input", 0) for g in group_details) / len(group_details)
            avg_basis = sum(g.get("basis", 0) for g in group_details) / len(group_details)
            avg_rate = sum(
                (g.get("basis", 0) / g["input"]) if g.get("input", 0) > 0 else 0
                for g in group_details
            ) / len(group_details)
        else:
            avg_input = 0
            avg_basis = 0
            avg_rate = 0

        # Add reduction_rate to each group
        for g in group_details:
            if g.get("input", 0) > 0:
                g["reduction_rate"] = round(g.get("eliminated", 0) / g["input"], 3)
            else:
                g["reduction_rate"] = 0.0

        # Save detailed group stats
        details_path = output_path.parent / "seed_reduction_details.json"
        with open(details_path, "w", encoding="utf-8") as f:
            json.dump({
                "elapsed_seconds": round(stage_elapsed, 2),
                "n_groups": n_groups,
                "n_no_seed": n_no_seed,
                "avg_input_per_seed": round(avg_input, 1),
                "avg_basis_per_seed": round(avg_basis, 1),
                "avg_reduction_rate": round(avg_rate, 3),
                "group_details": group_details,
            }, f, ensure_ascii=False, indent=2)

        # Summary stats (without full group_details)
        seed_red_stats = {
            "enabled": True,
            "n_groups": n_groups,
            "n_no_seed": n_no_seed,
            "input_count": seed_input_count,
            "basis_count": len(current_rules),
            "eliminated_count": seed_input_count - len(current_rules),
            "avg_input_per_seed": round(avg_input, 1),
            "avg_basis_per_seed": round(avg_basis, 1),
            "avg_reduction_rate": round(avg_rate, 3),
            "elapsed_seconds": round(stage_elapsed, 2),
            "details_file": str(details_path.relative_to(output_dir)),
        }

    # --- Divide-and-Conquer reduction ---
    if dc_reduction_enabled:
        stage_start = time.time()
        min_chunk_size = dc_red_cfg.get("min_chunk_size", 50)
        dc_output_dir = output_path.parent / "divide_conquer_reduction"

        print(f"\n[Part 4 / divide_conquer_reduction] {len(current_rules)} rules, "
              f"min_chunk_size={min_chunk_size}, n_workers={n_workers}")
        dc_reducer = DivideConquerReducer(
            timeout=timeout,
            seed=42,
            solver_type="csolver",
            engine=engine,
            min_chunk_size=min_chunk_size,
            n_workers=n_workers,
            batch_size=batch_size,
            verbose=True,
            output_dir=dc_output_dir,
        )
        dc_input_count = len(current_rules)
        dc_result = dc_reducer.reduce(current_rules)
        current_rules = dc_result["basis_rules"]
        dc_stats_raw = dc_result["stats"]
        stage_elapsed = time.time() - stage_start
        stage_timing["divide_conquer_reduction"] = round(stage_elapsed, 2)
        print(f"[Part 4 / divide_conquer_reduction] → {len(current_rules)} rules "
              f"(eliminated {dc_stats_raw.get('eliminated_count', 0)}, "
              f"tests {dc_stats_raw.get('n_subsumption_tests', 0)}, {stage_elapsed:.1f}s)")

        dc_red_stats = {
            "enabled": True,
            "input_count": dc_input_count,
            "basis_count": len(current_rules),
            "eliminated_count": dc_input_count - len(current_rules),
            "reduction_rate": dc_stats_raw.get("reduction_rate", 0.0),
            "n_subsumption_tests": dc_stats_raw.get("n_subsumption_tests", 0),
            "phase1": dc_stats_raw.get("phase1", {}),
            "phase2": dc_stats_raw.get("phase2", {}),
            "elapsed_seconds": round(stage_elapsed, 2),
            "details_dir": str(dc_output_dir.relative_to(output_dir)),
        }

    # Write output
    with open(output_path, "w", encoding="utf-8") as f:
        for rule in current_rules:
            f.write(f"{rule.rule_id}\n{rule.rule_text}\n")

    total_elapsed = time.time() - start_time
    print(f"\n[Part 4] Done — {len(current_rules)} rules → {output_path} ({total_elapsed:.1f}s)")

    # Build final stats dict
    stats = {
        "input_path": str(input_path),
        "output_path": str(output_path),
        "source_data_path": str(source_data_file) if source_data_file else None,
        "input_count": initial_count,
        "output_count": len(current_rules),
        "elapsed_seconds": round(total_elapsed, 2),
        "stage_timing": stage_timing,
        "seed_reduction": seed_red_stats,
        "divide_conquer_reduction": dc_red_stats,
    }
    return output_path, stats


# ============================================================================
# Pipeline orchestrator
# ============================================================================

def run_pipeline(config_path: Path) -> Dict[str, Any]:
    """Load config and run all 4 Parts sequentially."""
    cfg = load_config(config_path)

    global_cfg = cfg.get("global", {})
    output_dir = Path(global_cfg.get("output_dir", "outputs/experiments/pipeline_output"))
    output_dir.mkdir(parents=True, exist_ok=True)

    pipeline_start = time.time()
    summary = PipelineSummary(output_dir)
    print(f"\n{'='*60}")
    print(f"Discovery Pipeline")
    print(f"{'='*60}")
    print(f"  Config:     {config_path}")
    print(f"  Output dir: {output_dir}")

    # Track the last produced output to chain Parts
    last_output: Optional[Path] = None
    source_data_file: Optional[Path] = None  # step6_rules_stats.json from Part 2

    # Part 1
    p1_out, p1_stats = run_part1(cfg, output_dir)
    summary.record_part(
        "part1_filter",
        cfg.get("part1_filter", {}).get("enabled", True),
        p1_stats,
    )
    if p1_out is not None:
        last_output = p1_out
        # Count unique seeds in initial filtered data
        try:
            seed_count = _count_unique_seeds(p1_out)
            summary.set_initial_seed_count(seed_count)
            print(f"[Pipeline] Initial unique seed count: {seed_count}")
        except Exception as e:
            print(f"[Pipeline] Warning: failed to count unique seeds: {e}")

    # Part 2
    p2_out, p2_stats = run_part2(cfg, output_dir, last_output)
    summary.record_part(
        "part2_extract",
        cfg.get("part2_extract", {}).get("enabled", True),
        p2_stats,
    )
    if p2_out is not None:
        last_output = p2_out
        # Try to locate step6_rules_stats.json alongside Part 2 output
        candidate = p2_out.parent / "intermediates" / "step6_rules_stats.json"
        if candidate.exists():
            source_data_file = candidate
        # Or use source_data_file from Part 2 stats if provided
        if p2_stats and p2_stats.get("source_data_file"):
            source_data_file = Path(p2_stats["source_data_file"])

    # Part 3
    p3_out, p3_stats = run_part3(cfg, output_dir, last_output)
    summary.record_part(
        "part3_max_premises",
        cfg.get("part3_max_premises", {}).get("enabled", True),
        p3_stats,
    )
    if p3_out is not None:
        last_output = p3_out

    # Part 4
    p4_out, p4_stats = run_part4(cfg, output_dir, last_output, source_data_file=source_data_file)
    summary.record_part(
        "part4_reduction",
        cfg.get("part4_reduction", {}).get("enabled", True),
        p4_stats,
    )
    if p4_out is not None:
        last_output = p4_out

    total_elapsed = time.time() - pipeline_start

    # Save pipeline summary
    summary.save()

    print(f"\n{'='*60}")
    print(f"Pipeline complete in {total_elapsed:.1f}s")
    print(f"Output: {output_dir}")
    if last_output:
        print(f"Final output: {last_output}")
    print(f"{'='*60}")

    return {
        "output_dir": str(output_dir),
        "total_elapsed_seconds": total_elapsed,
        "part1_output": str(p1_out) if p1_out else None,
        "part2_output": str(p2_out) if p2_out else None,
        "part3_output": str(p3_out) if p3_out else None,
        "part4_output": str(p4_out) if p4_out else None,
    }


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Discovery Pipeline — unified config-based rule extraction and reduction",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with default config
  python scripts/discovery_pipeline.py

  # Run with custom config
  python scripts/discovery_pipeline.py --config my_config.json
        """,
    )
    parser.add_argument(
        "--config", "-c",
        type=Path,
        default=Path(__file__).parent / "discovery_pipeline_config.json",
        help="Path to pipeline config JSON (default: scripts/discovery_pipeline_config.json)",
    )
    args = parser.parse_args()

    if not args.config.exists():
        print(f"Error: config file not found: {args.config}", file=sys.stderr)
        print(f"  Create it at {args.config} using discovery_pipeline_config.json as template.")
        sys.exit(1)

    run_pipeline(args.config)


if __name__ == "__main__":
    main()
