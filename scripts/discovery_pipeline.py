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
    Part 4: Reduction         — seed / chunk / global subsumption-based rule reduction

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
# Part 1: Input filter
# ============================================================================

def run_part1(cfg: Dict[str, Any], output_dir: Path) -> Optional[Path]:
    """Run Part 1 (input filter). Returns path to filtered.jsonl, or None if disabled."""
    p1 = cfg.get("part1_filter", {})
    if not p1.get("enabled", True):
        print("[Part 1] Disabled, skipping.")
        return None

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
    stats = engine.run_part1_filter(input_path, output_path)

    print(f"[Part 1] Done — {stats['kept']}/{stats['total']} records kept → {output_path}")
    return output_path


# ============================================================================
# Part 2: Graph prune + rule extraction
# ============================================================================

def run_part2(
    cfg: Dict[str, Any],
    output_dir: Path,
    prev_output: Optional[Path],
) -> Optional[Path]:
    """Run Part 2 (extract rules). Returns path to rules.txt, or None if disabled."""
    p2 = cfg.get("part2_extract", {})
    if not p2.get("enabled", True):
        print("[Part 2] Disabled, skipping.")
        return None

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

    max_workers = p2.get("max_workers", 30)
    rule_skip_predicates = p2.get("rule_skip_predicates") or []
    save_intermediates = cfg.get("global", {}).get("save_intermediates", False)

    streaming_cfg = p2.get("streaming", {})
    use_streaming = streaming_cfg.get("enabled", False)

    print(f"\n{'='*60}")
    print(f"Part 2: Rule Extraction {'(STREAMING)' if use_streaming else ''}")
    print(f"{'='*60}")
    print(f"  Input:  {input_path}")
    print(f"  Output: {part2_dir}")

    from newclid.proof_scout.core.filter_and_prune_engine import FilterAndPruneEngine

    engine = FilterAndPruneEngine(
        max_workers=max_workers,
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

    if rules_file and rules_file.exists():
        print(f"[Part 2] Done — {result.get('rules', 0)} rules → {rules_file}")
    else:
        print("[Part 2] Warning: no rules_file produced")

    return rules_file


# ============================================================================
# Part 3: max_premises filter
# ============================================================================

def run_part3(
    cfg: Dict[str, Any],
    output_dir: Path,
    prev_output: Optional[Path],
) -> Optional[Path]:
    """Run Part 3 (max_premises filter). Returns filtered_rules.txt path, or None."""
    p3 = cfg.get("part3_max_premises", {})

    # If max_premises is null, skip this Part entirely
    max_premises = p3.get("max_premises")
    if not p3.get("enabled", True) or max_premises is None:
        reason = "disabled" if not p3.get("enabled", True) else "max_premises is null"
        print(f"[Part 3] Skipped ({reason}).")
        return None

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
    print(f"[Part 3] {n_kept} kept, {skipped} skipped (premises > {max_premises})")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(kept_lines))
        if kept_lines:
            f.write("\n")

    print(f"[Part 3] Done → {output_path}")
    return output_path


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
) -> Optional[Path]:
    """Run Part 4 (reduction). Returns extracted_rules.txt path, or None."""
    p4 = cfg.get("part4_reduction", {})
    if not p4.get("enabled", True):
        print("[Part 4] Disabled, skipping.")
        return None

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
    n_workers = p4.get("n_workers", 4)
    batch_size = p4.get("batch_size", 10)
    debug = p4.get("debug", False)

    seed_red_cfg = p4.get("seed_reduction", {})
    chunk_red_cfg = p4.get("chunk_reduction", {})
    global_red_cfg = p4.get("global_reduction", {})

    seed_reduction_enabled = seed_red_cfg.get("enabled", False)
    chunk_reduction_enabled = chunk_red_cfg.get("enabled", False)
    global_reduction_enabled = global_red_cfg.get("enabled", True)
    use_ray = p4.get("use_ray", False)

    print(f"\n{'='*60}")
    print(f"Part 4: Reduction")
    print(f"{'='*60}")
    print(f"  Input (rules):  {input_path}")
    print(f"  Source data:    {source_data_file or '(none — will fail if rules need llm_input)'}")
    print(f"  Output:         {output_path}")
    print(f"  engine={engine}, timeout={timeout}, n_workers={n_workers}, batch_size={batch_size}")
    print(f"  use_ray={use_ray}")
    print(f"  seed_reduction={seed_reduction_enabled}, chunk_reduction={chunk_reduction_enabled}, "
          f"global_reduction={global_reduction_enabled}")

    from newclid.proof_scout.reduction import (
        RuleReducer,
        ChunkedIterativeReducer,
        load_rules_from_discovery_output,
    )

    # Streaming chunk reduction: skip full load, go directly to stream path
    streaming_load = chunk_reduction_enabled and chunk_red_cfg.get("streaming_load", False)
    if streaming_load:
        if source_data_file is None or not source_data_file.exists():
            print("Error: chunk_reduction.streaming_load=true requires source_data in config",
                  file=sys.stderr)
            sys.exit(1)
        if seed_reduction_enabled:
            print("Error: seed_reduction cannot be combined with streaming_load", file=sys.stderr)
            sys.exit(1)
        # Run streaming chunk reduction (includes optional global reduction inside)
        group_size = chunk_red_cfg.get("group_size", 500)
        chunk_dir = output_path.parent / "chunk_reduction"
        chunk_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n[Part 4 / chunk_reduction (streaming)] group_size={group_size}, "
              f"n_workers={n_workers}, global_reduction={global_reduction_enabled}")
        from newclid.proof_scout.reduction import stream_chunked_reduce_from_files
        reducer_cfg_dict = {
            "timeout": timeout,
            "n_workers": n_workers,
            "batch_size": batch_size,
            "solver_type": "csolver",
            "engine": engine,
            "debug": debug,
            "debug_output_dir": output_path.parent if debug else None,
            "global_reduction": global_reduction_enabled,
        }
        final_rules, stream_stats = stream_chunked_reduce_from_files(
            rules_file=input_path,
            source_data_file=source_data_file,
            group_size=group_size,
            reducer_cfg=reducer_cfg_dict,
            output_dir=chunk_dir,
        )
        print(f"[Part 4 / streaming] → {len(final_rules)} rules")
        with open(output_path, "w", encoding="utf-8") as f:
            for rule in final_rules:
                f.write(f"{rule.rule_id}\n{rule.rule_text}\n")
        print(f"\n[Part 4] Done — {len(final_rules)} rules → {output_path}")
        return output_path

    # Standard mode: load all rules into memory first
    if source_data_file and source_data_file.exists():
        rules, failures = load_rules_from_discovery_output(input_path, source_data_file)
    else:
        print(f"  Error: source_data not found. Set part4_reduction.source_data in config to the "
              f"original JSONL or step6_rules_stats.json file.", file=sys.stderr)
        sys.exit(1)

    print(f"  Loaded {len(rules)} rules ({len(failures)} failures)")

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
        return output_path

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

    # --- Seed reduction ---
    if seed_reduction_enabled:
        print(f"\n[Part 4 / seed_reduction] {len(current_rules)} rules")

        if use_ray:
            # Ray mode: init Ray if not already running, then parallel seed groups
            import ray
            if not ray.is_initialized():
                ray.init(ignore_reinit_error=True)
                print(f"  Ray initialized: {ray.cluster_resources()}")

        reducer = RuleReducer(
            timeout=timeout,
            n_workers=n_workers,
            batch_size=batch_size,
            debug=debug,
            debug_output_dir=output_path.parent if debug else None,
            solver_type="csolver",
            engine=engine,
        )
        result = reducer.reduce_by_seed(current_rules, use_ray=use_ray)
        current_rules = result["basis_rules"]
        print(f"[Part 4 / seed_reduction] {len(rules)} → {len(current_rules)} rules")

    # --- Chunk reduction ---
    if chunk_reduction_enabled:
        group_size = chunk_red_cfg.get("group_size", 500)
        iterations = chunk_red_cfg.get("iterations", 1)
        streaming_load = chunk_red_cfg.get("streaming_load", False)

        chunk_dir = output_path.parent / "chunk_reduction"
        chunk_dir.mkdir(parents=True, exist_ok=True)

        if streaming_load:
            # Streaming mode: scan JSONL once, reduce chunk-by-chunk without loading all rules
            if source_data_file is None or not source_data_file.exists():
                print("Error: chunk_reduction.streaming_load=true requires source_data_file",
                      file=sys.stderr)
                sys.exit(1)
            print(f"\n[Part 4 / chunk_reduction (streaming)] group_size={group_size}, "
                  f"n_workers={n_workers}")
            from newclid.proof_scout.reduction import stream_chunked_reduce_from_files
            reducer_cfg = {
                "timeout": timeout,
                "n_workers": n_workers,
                "batch_size": batch_size,
                "solver_type": "csolver",
                "engine": engine,
                "debug": debug,
                "debug_output_dir": output_path.parent if debug else None,
                "global_reduction": global_reduction_enabled,
            }
            current_rules, stream_stats = stream_chunked_reduce_from_files(
                rules_file=input_path,
                source_data_file=source_data_file,
                group_size=group_size,
                reducer_cfg=reducer_cfg,
                output_dir=chunk_dir,
            )
            print(f"[Part 4 / chunk_reduction (streaming)] → {len(current_rules)} rules")
            # Global reduction already done inside streaming if enabled; skip below
            global_reduction_enabled = False
        else:
            # Standard mode: rules already loaded into current_rules
            print(f"\n[Part 4 / chunk_reduction] {len(current_rules)} rules, "
                  f"group_size={group_size}, iterations={iterations}, n_workers={n_workers}")
            cir = ChunkedIterativeReducer(
                timeout=timeout,
                batch_size=batch_size,
                solver_type="csolver",
                engine=engine,
            )
            current_rules, chunk_stats = cir.reduce_iterative(
                current_rules,
                group_size=group_size,
                iterations=iterations,
                n_workers=n_workers,
                output_dir=chunk_dir,
                resume=False,
            )
            print(f"[Part 4 / chunk_reduction] → {len(current_rules)} rules")

    # --- Global reduction ---
    if global_reduction_enabled:
        print(f"\n[Part 4 / global_reduction] {len(current_rules)} rules")
        reducer = RuleReducer(
            timeout=timeout,
            n_workers=n_workers,
            batch_size=batch_size,
            debug=debug,
            debug_output_dir=output_path.parent if debug else None,
            solver_type="csolver",
            engine=engine,
        )
        result = reducer.reduce(current_rules)
        current_rules = result["basis_rules"]
        stats = result["stats"]
        print(f"[Part 4 / global_reduction] → {len(current_rules)} rules "
              f"(eliminated {stats.get('eliminated_count', 0)}, "
              f"tests {stats.get('n_subsumption_tests', 0)})")

    # Write output
    with open(output_path, "w", encoding="utf-8") as f:
        for rule in current_rules:
            f.write(f"{rule.rule_id}\n{rule.rule_text}\n")

    print(f"\n[Part 4] Done — {len(current_rules)} rules → {output_path}")
    return output_path


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
    print(f"\n{'='*60}")
    print(f"Discovery Pipeline")
    print(f"{'='*60}")
    print(f"  Config:     {config_path}")
    print(f"  Output dir: {output_dir}")

    # Track the last produced output to chain Parts
    last_output: Optional[Path] = None
    source_data_file: Optional[Path] = None  # step6_rules_stats.json from Part 2

    # Part 1
    p1_out = run_part1(cfg, output_dir)
    if p1_out is not None:
        last_output = p1_out

    # Part 2
    p2_out = run_part2(cfg, output_dir, last_output)
    if p2_out is not None:
        last_output = p2_out
        # Try to locate step6_rules_stats.json alongside Part 2 output
        candidate = p2_out.parent / "intermediates" / "step6_rules_stats.json"
        if candidate.exists():
            source_data_file = candidate

    # Part 3
    p3_out = run_part3(cfg, output_dir, last_output)
    if p3_out is not None:
        last_output = p3_out

    # Part 4
    p4_out = run_part4(cfg, output_dir, last_output, source_data_file=source_data_file)
    if p4_out is not None:
        last_output = p4_out

    total_elapsed = time.time() - pipeline_start

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
