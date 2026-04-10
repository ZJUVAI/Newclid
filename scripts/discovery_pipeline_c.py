#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Discovery Pipeline (CSolver) - End-to-end rule extraction and reduction using CSolver.

Identical to discovery_pipeline.py except Stage 2 uses CSolver (C++ DDAR) for
subsumption testing instead of Python DDARN.

Usage:
    python scripts/discovery_pipeline_c.py \
        -i datasets/synthetic_10k.jsonl \
        -o outputs/experiments/YYYYMMDD_experiment \
        --save-intermediates
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from queue import Queue
from typing import Any, Dict, List, Optional

# Reuse Stage 1 from the original pipeline
from discovery_pipeline import run_stage1_extraction


# ============================================================================
# Stage 2: Rule Reduction (CSolver)
# ============================================================================

def run_stage2_reduction_csolver(
    rules_file: Path,
    source_data_file: Path,
    output_dir: Path,
    *,
    timeout: int = 60,
    seed: int = 42,
    max_premises: Optional[int] = None,
    max_rules: Optional[int] = None,
    n_workers: int = 1,
    batch_size: int = 10,
    debug: bool = False,
    no_group_reduction: bool = False,
    engine: str = "full",
) -> Dict[str, Any]:
    """Stage 2: Reduce rules via greedy subsumption using CSolver."""
    from newclid.proof_scout.reduction import RuleReducer, load_rules_from_discovery_output

    start_time = time.time()
    print(f"\n{'='*60}")
    print(f"Stage 2: Rule Reduction (CSolver)")
    print(f"{'='*60}")
    print(f"  Rules: {rules_file}")
    print(f"  Source data: {source_data_file}")
    print(f"  Output: {output_dir}")

    # Load rules
    rules, failures = load_rules_from_discovery_output(
        rules_file, source_data_file, max_rules=max_rules,
    )
    print(f"  Loaded {len(rules)} rules ({len(failures)} failures)")

    if failures:
        failures_path = output_dir / "r0_conversion_failures.json"
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(failures_path, "w", encoding="utf-8") as f:
            json.dump({
                "total_failures": len(failures),
                "failures": [{"rule_id": r, "rule_text": t, "reason": e} for r, t, e in failures],
            }, f, ensure_ascii=False, indent=2)
        print(f"  Failures saved to {failures_path}")

    if not rules:
        print("\n[Stage 2] No rules to reduce!")
        return {"stage": "reduction_csolver", "elapsed_seconds": 0, "stats": {}}

    # Run reduction with CSolver
    reducer = RuleReducer(
        timeout=timeout,
        seed=seed,
        max_premises=max_premises,
        n_workers=n_workers,
        batch_size=batch_size,
        debug=debug,
        debug_output_dir=output_dir if debug else None,
        solver_type="csolver",
        engine=engine,
    )
    has_seed = any(r.seed is not None for r in rules)
    if has_seed and not no_group_reduction:
        print(f"\n[Stage 2] Using seed-based group reduction ({sum(1 for r in rules if r.seed is not None)}/{len(rules)} rules have seed)")
        result = reducer.reduce_by_seed(rules)
    else:
        if not has_seed:
            print("\n[Stage 2] No seed info found, using global reduction only")
        else:
            print("\n[Stage 2] Group reduction disabled, using global reduction only")
        result = reducer.reduce(rules)

    elapsed = time.time() - start_time

    # Save outputs
    output_dir.mkdir(parents=True, exist_ok=True)

    basis_rules = result.get("basis_rules", [])
    mp_suffix = f"_maxprem{max_premises}" if max_premises else ""
    extracted_path = output_dir / f"extracted_rules{mp_suffix}.txt"
    with open(extracted_path, "w", encoding="utf-8") as f:
        for rule in basis_rules:
            f.write(f"{rule.rule_id}\n{rule.rule_text}\n")
    print(f"  Basis rules saved to {extracted_path}")

    eliminated = result.get("eliminated_rules", [])
    if eliminated:
        elim_path = output_dir / f"eliminated_rules{mp_suffix}.json"
        with open(elim_path, "w", encoding="utf-8") as f:
            json.dump(eliminated, f, ensure_ascii=False, indent=2)

    skipped = result.get("skipped_by_premises", [])
    if skipped:
        skip_path = output_dir / f"skipped_by_premises{mp_suffix}.json"
        with open(skip_path, "w", encoding="utf-8") as f:
            json.dump(skipped, f, ensure_ascii=False, indent=2)

    stats = result.get("stats", {})
    stats["elapsed_seconds"] = elapsed
    stats["solver_type"] = "csolver"
    stats_path = output_dir / f"reduction_stats{mp_suffix}.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"\n[Stage 2] Completed in {elapsed:.1f}s")
    print(f"  Basis: {stats.get('basis_count', 0)}")
    print(f"  Eliminated: {stats.get('eliminated_count', 0)}")
    print(f"  Subsumption tests: {stats.get('n_subsumption_tests', 0)}")

    return {
        "stage": "reduction_csolver",
        "elapsed_seconds": elapsed,
        "stats": stats,
        "extracted_rules_path": str(extracted_path),
    }


# ============================================================================
# Chunked Iterative Reduction (CSolver)
# ============================================================================

def run_chunked_iterative_reduction(
    rules_file: Path,
    source_data_file: Path,
    output_dir: Path,
    *,
    timeout: int = 60,
    seed: int = 42,
    max_premises: Optional[int] = None,
    max_rules: Optional[int] = None,
    group_size: int = 500,
    iterations: int = 1,
    chunk_workers: int = 4,
    batch_size: int = 10,
    engine: str = "full",
    filter_only: bool = False,
    resume: bool = True,
    solver_type: str = "csolver",
) -> Dict[str, Any]:
    """Chunked iterative rule reduction using CSolver.

    1. Load rules from discovery output
    2. Optionally filter by max_premises
    3. If filter_only, stop here
    4. Otherwise run ChunkedIterativeReducer.reduce_iterative()
    """
    from newclid.proof_scout.reduction import (
        ChunkedIterativeReducer,
        load_rules_from_discovery_output,
    )

    start_time = time.time()
    print(f"\n{'='*60}")
    print(f"Chunked Iterative Reduction ({solver_type})")
    print(f"{'='*60}")
    print(f"  Rules: {rules_file}")
    print(f"  Source data: {source_data_file}")
    print(f"  Output: {output_dir}")
    print(f"  group_size={group_size}, iterations={iterations}, "
          f"chunk_workers={chunk_workers}")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Load rules
    rules, failures = load_rules_from_discovery_output(
        rules_file, source_data_file, max_rules=max_rules,
    )
    print(f"  Loaded {len(rules)} rules ({len(failures)} failures)")

    if failures:
        failures_path = output_dir / "conversion_failures.json"
        with open(failures_path, "w", encoding="utf-8") as f:
            json.dump({
                "total_failures": len(failures),
                "failures": [{"rule_id": r, "rule_text": t, "reason": e} for r, t, e in failures],
            }, f, ensure_ascii=False, indent=2)

    if not rules:
        print("\nNo rules to process!")
        return {"stage": "chunked_reduction", "elapsed_seconds": 0, "stats": {}}

    # Filter by max_premises
    skipped = []
    if max_premises is not None:
        rules, skipped = ChunkedIterativeReducer.filter_by_premises(rules, max_premises)
        print(f"  Pre-filter: {len(skipped)} rules skipped (premises > {max_premises})")
        print(f"  Remaining: {len(rules)} rules")

        # Save filtered rules
        filtered_path = output_dir / "filtered_rules.txt"
        with open(filtered_path, "w", encoding="utf-8") as f:
            for rule in rules:
                f.write(f"{rule.rule_id}\n{rule.rule_text}\n")

        if skipped:
            skip_path = output_dir / "skipped_by_premises.json"
            with open(skip_path, "w", encoding="utf-8") as f:
                json.dump(skipped, f, ensure_ascii=False, indent=2)

    if filter_only:
        elapsed = time.time() - start_time
        print(f"\n[Filter only] Done in {elapsed:.1f}s — {len(rules)} rules kept")
        return {
            "stage": "chunked_reduction (filter_only)",
            "elapsed_seconds": elapsed,
            "stats": {
                "input_count": len(rules) + len(skipped),
                "filtered_count": len(rules),
                "skipped_count": len(skipped),
            },
        }

    if not rules:
        print("\nNo rules remaining after filter!")
        return {"stage": "chunked_reduction", "elapsed_seconds": 0, "stats": {}}

    # Run chunked iterative reduction
    reducer = ChunkedIterativeReducer(
        timeout=timeout,
        seed=seed,
        batch_size=batch_size,
        solver_type=solver_type,
        engine=engine,
    )

    survivors, overall_stats = reducer.reduce_iterative(
        rules,
        group_size=group_size,
        iterations=iterations,
        chunk_workers=chunk_workers,
        output_dir=output_dir,
        resume=resume,
    )

    elapsed = time.time() - start_time
    overall_stats["elapsed_seconds_total"] = elapsed
    overall_stats["skipped_by_premises_count"] = len(skipped)

    # Save overall stats
    stats_path = output_dir / "chunked_reduction_stats.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(overall_stats, f, ensure_ascii=False, indent=2)

    print(f"\n[Chunked Reduction] Completed in {elapsed:.1f}s")
    print(f"  Final basis: {len(survivors)} rules")

    return {
        "stage": "chunked_reduction",
        "elapsed_seconds": elapsed,
        "stats": overall_stats,
    }


# ============================================================================
# Pipeline Orchestrator
# ============================================================================

def run_pipeline(
    *,
    input_path: Optional[Path] = None,
    output_dir: Path,
    max_workers: int = 30,
    save_intermediates: bool = False,
    skip_extraction: bool = False,
    skip_reduction: bool = False,
    skip_predicates: Optional[List[str]] = None,
    rule_skip_predicates: Optional[List[str]] = None,
    render_images: bool = False,
    # Streaming params (passed through to Stage 1)
    streaming: bool = False,
    chunk_size: int = 10000,
    inflight_limit: int = 300,
    overlap_reduction: bool = False,
    # Reduction params
    rules_file: Optional[Path] = None,
    source_data_file: Optional[Path] = None,
    timeout: int = 60,
    seed: int = 42,
    max_premises: Optional[int] = None,
    max_rules: Optional[int] = None,
    batch_size: int = 10,
    debug: bool = False,
    no_group_reduction: bool = False,
    engine: str = "full",
) -> Dict[str, Any]:
    """Run the CSolver discovery pipeline."""
    pipeline_start = time.time()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results: Dict[str, Any] = {
        "output_dir": str(output_dir),
        "solver_type": "csolver",
        "stages": [],
    }

    # Setup incremental reducer for overlap mode (CSolver backend)
    seed_reducer_queue: Optional[Queue] = None
    incremental_reducer = None

    if streaming and overlap_reduction and not skip_extraction and not skip_reduction:
        from newclid.proof_scout.reduction import RuleReducer, IncrementalReducer

        seed_reducer_queue = Queue()
        reducer = RuleReducer(
            timeout=timeout,
            seed=seed,
            max_premises=max_premises,
            n_workers=1,
            batch_size=batch_size,
            debug=debug,
            debug_output_dir=output_dir if debug else None,
            solver_type="csolver",
            engine=engine,
        )
        incremental_reducer = IncrementalReducer(reducer, seed_reducer_queue)
        incremental_reducer.start()
        print("[pipeline] Incremental Stage 2 reducer (CSolver) started in background")

    # Stage 1: Extraction (same as Python pipeline)
    if not skip_extraction:
        if input_path is None:
            print("Error: --input is required when not using --skip-extraction")
            sys.exit(1)

        stage1 = run_stage1_extraction(
            input_path, output_dir,
            max_workers=max_workers,
            save_intermediates=save_intermediates,
            skip_predicates=skip_predicates,
            rule_skip_predicates=rule_skip_predicates,
            render_images=render_images,
            streaming=streaming,
            chunk_size=chunk_size,
            inflight_limit=inflight_limit,
            seed_reducer_queue=seed_reducer_queue,
        )
        results["stages"].append(stage1)

        if rules_file is None and stage1.get("rules_file"):
            rules_file = Path(stage1["rules_file"])
        if source_data_file is None and stage1.get("source_data_file"):
            source_data_file = Path(stage1["source_data_file"])

    # Stage 2: Reduction (CSolver)
    if not skip_reduction:
        if incremental_reducer is not None:
            # Overlap mode: wait for incremental reducer to finish
            print("\n[pipeline] Waiting for incremental Stage 2 reducer (CSolver) to finish...")
            reduction_result = incremental_reducer.join(timeout=None)

            if reduction_result:
                elapsed_reduction = time.time() - pipeline_start
                basis_rules = reduction_result.get("basis_rules", [])
                mp_suffix = f"_maxprem{max_premises}" if max_premises else ""
                extracted_path = output_dir / f"extracted_rules{mp_suffix}.txt"
                with open(extracted_path, "w", encoding="utf-8") as f:
                    for rule in basis_rules:
                        f.write(f"{rule.rule_id}\n{rule.rule_text}\n")

                stats = reduction_result.get("stats", {})
                stats["elapsed_seconds"] = elapsed_reduction
                stats["solver_type"] = "csolver"
                stats_path = output_dir / f"reduction_stats{mp_suffix}.json"
                with open(stats_path, "w", encoding="utf-8") as f:
                    json.dump(stats, f, ensure_ascii=False, indent=2)

                print(f"  Basis: {stats.get('basis_count', 0)}")
                print(f"  Total eliminated: {stats.get('total_eliminated', 0)}")

                results["stages"].append({
                    "stage": "reduction_csolver (incremental)",
                    "elapsed_seconds": elapsed_reduction,
                    "stats": stats,
                    "extracted_rules_path": str(extracted_path),
                })
            else:
                print("[pipeline] Incremental reducer returned no result")
        else:
            if rules_file is None or source_data_file is None:
                print("Error: --rules and --source-data are required for reduction")
                print("  (either run extraction first, or provide them explicitly)")
                sys.exit(1)

            if not Path(rules_file).exists():
                print(f"Error: Rules file not found: {rules_file}")
                sys.exit(1)
            if not Path(source_data_file).exists():
                print(f"Error: Source data file not found: {source_data_file}")
                sys.exit(1)

            stage2 = run_stage2_reduction_csolver(
                Path(rules_file), Path(source_data_file), output_dir,
                timeout=timeout,
                seed=seed,
                max_premises=max_premises,
                max_rules=max_rules,
                n_workers=max_workers,
                batch_size=batch_size,
                debug=debug,
                no_group_reduction=no_group_reduction,
                engine=engine,
            )
            results["stages"].append(stage2)

    total_elapsed = time.time() - pipeline_start
    results["total_elapsed_seconds"] = total_elapsed

    print(f"\n{'='*60}")
    print(f"Pipeline (CSolver) complete in {total_elapsed:.1f}s")
    print(f"Output: {output_dir}")
    print(f"{'='*60}")

    return results


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Discovery Pipeline (CSolver) — rule extraction and reduction using C++ DDAR",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    stage1 = parser.add_argument_group("Stage 1: Extraction")
    stage1.add_argument("-i", "--input", type=Path, default=None, help="Input JSONL file")
    stage1.add_argument("-o", "--output", type=Path, required=True, help="Output directory")
    stage1.add_argument("--max-workers", type=int, default=30, help="Parallel workers (default: 30)")
    stage1.add_argument("--save-intermediates", action="store_true", help="Save intermediate results")
    stage1.add_argument("--skip-predicates", type=str, default=None,
                        help="Comma-separated predicates to filter from input")
    stage1.add_argument("--rule-skip-predicates", type=str, default=None,
                        help="Comma-separated predicates to filter from rules")
    stage1.add_argument("--render-images", action="store_true", help="Render comparison images")

    streaming_grp = parser.add_argument_group("Streaming mode (for large datasets)")
    streaming_grp.add_argument("--streaming", action="store_true",
                               help="Use streaming mode (chunk-based + Ray) for large datasets")
    streaming_grp.add_argument("--chunk-size", type=int, default=10000,
                               help="Records per chunk in streaming mode (default: 10000)")
    streaming_grp.add_argument("--inflight-limit", type=int, default=300,
                               help="Max in-flight Ray tasks in streaming mode (default: 300)")
    streaming_grp.add_argument("--overlap-reduction", action="store_true",
                               help="Overlap Stage 1 + Stage 2 via incremental group reduction (streaming only)")

    stage2 = parser.add_argument_group("Stage 2: Reduction (CSolver)")
    stage2.add_argument("--timeout", type=int, default=60, help="Subsumption test timeout (default: 60)")
    stage2.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    stage2.add_argument("--max-premises", type=int, default=None, help="Max premises for reduction pre-filter")
    stage2.add_argument("--max-rules", type=int, default=None, help="Max rules to load (for testing)")
    stage2.add_argument("--batch-size", type=int, default=10, help="Reduction batch size (default: 10)")
    stage2.add_argument("--debug", action="store_true", help="Enable debug output for reduction")
    stage2.add_argument("--no-group-reduction", action="store_true",
                        help="Disable seed-based group reduction")
    stage2.add_argument("--engine", type=str, default="full", choices=["full", "weak"],
                        help="DDAR engine variant for subsumption testing (default: full)")

    skip = parser.add_argument_group("Skip flags")
    skip.add_argument("--skip-extraction", action="store_true", help="Skip Stage 1")
    skip.add_argument("--skip-reduction", action="store_true", help="Skip Stage 2")

    standalone = parser.add_argument_group("Standalone reduction (with --skip-extraction)")
    standalone.add_argument("--rules", type=Path, default=None, help="Path to rules file")
    standalone.add_argument("--source-data", type=Path, default=None, help="Path to step6_rules_stats.json")

    chunked = parser.add_argument_group("Chunked Iterative Reduction")
    chunked.add_argument("--chunked", action="store_true",
                         help="Enable chunked iterative reduction mode")
    chunked.add_argument("--group-size", type=int, default=500,
                         help="Rules per chunk (default: 500, requires --chunked)")
    chunked.add_argument("--iterations", type=int, default=1,
                         help="Number of iterative rounds (default: 1, requires --chunked)")
    chunked.add_argument("--chunk-workers", type=int, default=4,
                         help="Parallel workers for chunk reduction (default: 4)")
    chunked.add_argument("--no-resume", action="store_true",
                         help="Disable checkpoint resume (default: resume enabled)")
    chunked.add_argument("--filter-only", action="store_true",
                         help="Only do max_premises filtering, no reduction")

    args = parser.parse_args()

    if not args.skip_extraction and args.input is None:
        parser.error("--input is required unless --skip-extraction is set")
    if args.skip_extraction and (args.rules is None or args.source_data is None):
        parser.error("--rules and --source-data are required with --skip-extraction")
    if args.overlap_reduction and not args.streaming:
        parser.error("--overlap-reduction requires --streaming")
    if args.filter_only and not args.chunked:
        # filter_only can work standalone with --skip-extraction
        if not args.skip_extraction:
            parser.error("--filter-only requires --chunked or --skip-extraction with --rules/--source-data")

    skip_preds = [p.strip() for p in args.skip_predicates.split(",")] if args.skip_predicates else None
    rule_skip_preds = [p.strip() for p in args.rule_skip_predicates.split(",")] if args.rule_skip_predicates else None

    # Chunked iterative reduction mode
    if args.chunked or args.filter_only:
        if args.rules is None or args.source_data is None:
            parser.error("--rules and --source-data are required with --chunked/--filter-only")
        run_chunked_iterative_reduction(
            rules_file=args.rules,
            source_data_file=args.source_data,
            output_dir=args.output,
            timeout=args.timeout,
            seed=args.seed,
            max_premises=args.max_premises,
            max_rules=args.max_rules,
            group_size=args.group_size,
            iterations=args.iterations,
            chunk_workers=args.chunk_workers,
            batch_size=args.batch_size,
            engine=args.engine,
            filter_only=args.filter_only,
            resume=not args.no_resume,
            solver_type="csolver",
        )
        return

    run_pipeline(
        input_path=args.input,
        output_dir=args.output,
        max_workers=args.max_workers,
        save_intermediates=args.save_intermediates,
        skip_extraction=args.skip_extraction,
        skip_reduction=args.skip_reduction,
        skip_predicates=skip_preds,
        rule_skip_predicates=rule_skip_preds,
        render_images=args.render_images,
        streaming=args.streaming,
        chunk_size=args.chunk_size,
        inflight_limit=args.inflight_limit,
        overlap_reduction=args.overlap_reduction,
        rules_file=args.rules,
        source_data_file=args.source_data,
        timeout=args.timeout,
        seed=args.seed,
        max_premises=args.max_premises,
        max_rules=args.max_rules,
        batch_size=args.batch_size,
        debug=args.debug,
        no_group_reduction=args.no_group_reduction,
        engine=args.engine,
    )


if __name__ == "__main__":
    main()
