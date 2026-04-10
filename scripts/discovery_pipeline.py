#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Discovery Pipeline - End-to-end rule extraction and reduction.

Stage 1: FilterAndPruneEngine — filter, prune, extract, normalize, dedup, dump rules
Stage 2: RuleReducer — greedy subsumption-based rule reduction

Modes:
  - Default: in-memory pipeline (original run())
  - Streaming: chunk-based pipeline (run_streaming()) for large datasets (10M+)

Usage:
    # Full pipeline (extraction + reduction)
    python scripts/discovery_pipeline.py \
        -i datasets/synthetic_10k.jsonl \
        -o outputs/experiments/YYYYMMDD_experiment \
        --save-intermediates

    # Streaming mode (for large datasets)
    python scripts/discovery_pipeline.py \
        -i datasets/synthetic_10M.jsonl \
        -o outputs/experiments/YYYYMMDD_experiment \
        --streaming --chunk-size 10000 --inflight-limit 300 \
        --save-intermediates

    # Extraction only
    python scripts/discovery_pipeline.py \
        -i datasets/synthetic_10k.jsonl \
        -o outputs/experiments/YYYYMMDD_experiment \
        --skip-reduction --save-intermediates

    # Reduction only (from existing extraction output)
    python scripts/discovery_pipeline.py \
        -o outputs/experiments/YYYYMMDD_experiment \
        --skip-extraction \
        --rules <rules.txt> --source-data <step6_rules_stats.json>
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from queue import Queue
from typing import Any, Dict, List, Optional


# ============================================================================
# Stage 1: Rule Extraction
# ============================================================================

def run_stage1_extraction(
    input_path: Path,
    output_dir: Path,
    *,
    max_workers: int = 30,
    save_intermediates: bool = False,
    skip_predicates: Optional[List[str]] = None,
    rule_skip_predicates: Optional[List[str]] = None,
    render_images: bool = False,
    streaming: bool = False,
    chunk_size: int = 10000,
    inflight_limit: int = 300,
    seed_reducer_queue: Optional[Queue] = None,
) -> Dict[str, Any]:
    """Stage 1: Extract rules using FilterAndPruneEngine.

    Steps 1-6: Input Filter → Graph Prune → Proposition Extract →
               Normalization → Deduplication → Rule Dump

    Args:
        streaming: Use streaming mode for large datasets.
        chunk_size: Records per chunk in streaming mode.
        inflight_limit: Max in-flight Ray tasks in streaming mode.
        seed_reducer_queue: Queue for incremental Stage 2 reduction (streaming only).

    Returns:
        Dict with extraction results and paths to output files.
    """
    from newclid.proof_scout.core.filter_and_prune_engine import FilterAndPruneEngine

    start_time = time.time()
    print(f"\n{'='*60}")
    print(f"Stage 1: Rule Extraction {'(STREAMING)' if streaming else ''}")
    print(f"{'='*60}")
    print(f"  Input: {input_path}")
    print(f"  Output: {output_dir}")

    engine_kwargs = dict(
        max_workers=max_workers,
        render_by_rule=render_images,
        keep_pid_images=False,
    )
    if skip_predicates is not None:
        engine_kwargs["skip_predicates"] = skip_predicates
    if rule_skip_predicates is not None:
        engine_kwargs["rule_skip_predicates"] = rule_skip_predicates

    engine = FilterAndPruneEngine(**engine_kwargs)

    if streaming:
        result = engine.run_streaming(
            input_path, output_dir,
            chunk_size=chunk_size,
            inflight_limit=inflight_limit,
            save_intermediates=save_intermediates,
            seed_reducer_queue=seed_reducer_queue,
        )
        elapsed = time.time() - start_time
        print(f"\n[Stage 1] Completed in {elapsed:.1f}s (streaming)")
        print(f"  Rules extracted: {result.get('rules', 0)}")

        rules_file = result.get("json", "")
        source_data_file = result.get("source_data_file")
        return {
            "stage": "extraction",
            "elapsed_seconds": elapsed,
            "stats": result,
            "rules_file": rules_file,
            "source_data_file": source_data_file,
        }
    else:
        result = engine.run(input_path, output_dir, save_intermediates=save_intermediates)
        elapsed = time.time() - start_time
        print(f"\n[Stage 1] Completed in {elapsed:.1f}s")
        print(f"  Rules extracted: {result.get('rules', 0)}")
        print(f"  JSON: {result.get('json', '')}")

        return {
            "stage": "extraction",
            "elapsed_seconds": elapsed,
            "stats": result,
            "rules_file": result.get("json", "").replace(".json", "_rules.txt") if result.get("json") else None,
            "source_data_file": str(Path(output_dir) / "intermediates" / "step6_rules_stats.json") if save_intermediates else None,
        }


# ============================================================================
# Stage 2: Rule Reduction
# ============================================================================

def run_stage2_reduction(
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
) -> Dict[str, Any]:
    """Stage 2: Reduce rules via greedy subsumption.

    Returns:
        Dict with reduction results and paths to output files.
    """
    from newclid.proof_scout.reduction import RuleReducer, load_rules_from_discovery_output

    start_time = time.time()
    print(f"\n{'='*60}")
    print(f"Stage 2: Rule Reduction")
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
        return {"stage": "reduction", "elapsed_seconds": 0, "stats": {}}

    # Run reduction
    reducer = RuleReducer(
        timeout=timeout,
        seed=seed,
        max_premises=max_premises,
        n_workers=n_workers,
        batch_size=batch_size,
        debug=debug,
        debug_output_dir=output_dir if debug else None,
    )
    # Run reduction — use seed-based group reduction if seed info is available
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

    # Save extracted_rules.txt (basis rules)
    basis_rules = result.get("basis_rules", [])
    mp_suffix = f"_maxprem{max_premises}" if max_premises else ""
    extracted_path = output_dir / f"extracted_rules{mp_suffix}.txt"
    with open(extracted_path, "w", encoding="utf-8") as f:
        for rule in basis_rules:
            f.write(f"{rule.rule_id}\n{rule.rule_text}\n")
    print(f"  Basis rules saved to {extracted_path}")

    # Save eliminated rules
    eliminated = result.get("eliminated_rules", [])
    if eliminated:
        elim_path = output_dir / f"eliminated_rules{mp_suffix}.json"
        with open(elim_path, "w", encoding="utf-8") as f:
            json.dump(eliminated, f, ensure_ascii=False, indent=2)

    # Save skipped by premises
    skipped = result.get("skipped_by_premises", [])
    if skipped:
        skip_path = output_dir / f"skipped_by_premises{mp_suffix}.json"
        with open(skip_path, "w", encoding="utf-8") as f:
            json.dump(skipped, f, ensure_ascii=False, indent=2)

    # Save stats
    stats = result.get("stats", {})
    stats["elapsed_seconds"] = elapsed
    stats_path = output_dir / f"reduction_stats{mp_suffix}.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"\n[Stage 2] Completed in {elapsed:.1f}s")
    print(f"  Basis: {stats.get('basis_count', 0)}")
    print(f"  Eliminated: {stats.get('eliminated_count', 0)}")
    print(f"  Subsumption tests: {stats.get('n_subsumption_tests', 0)}")

    return {
        "stage": "reduction",
        "elapsed_seconds": elapsed,
        "stats": stats,
        "extracted_rules_path": str(extracted_path),
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
    # Streaming params
    streaming: bool = False,
    chunk_size: int = 10000,
    inflight_limit: int = 300,
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
    overlap_reduction: bool = False,
) -> Dict[str, Any]:
    """Run the discovery pipeline.

    Args:
        input_path: Input JSONL file (required unless skip_extraction)
        output_dir: Output directory
        max_workers: Parallel workers for both Stage 1 and Stage 2
        save_intermediates: Save intermediate results for each step
        skip_extraction: Skip Stage 1 (use existing rules_file/source_data_file)
        skip_reduction: Skip Stage 2
        skip_predicates: Predicates to filter from input records (default: eqpoint, constline)
        rule_skip_predicates: Predicates to filter from final rules (default: aconst, rconst)
        render_images: Render comparison images
        streaming: Use streaming mode for large datasets
        chunk_size: Records per chunk in streaming mode
        inflight_limit: Max in-flight Ray tasks in streaming mode
        rules_file: Path to rules file (for skip_extraction mode)
        source_data_file: Path to source data file (for skip_extraction mode)
        timeout: Subsumption test timeout
        seed: Random seed
        max_premises: Max premises for reduction pre-filter
        max_rules: Max rules to load for reduction
        batch_size: Batch size for reduction
        debug: Enable debug output for reduction
        overlap_reduction: Overlap Stage 1 + Stage 2 via incremental group reduction
    """
    pipeline_start = time.time()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results: Dict[str, Any] = {
        "output_dir": str(output_dir),
        "stages": [],
    }

    # Setup incremental reducer for overlap mode
    seed_reducer_queue: Optional[Queue] = None
    incremental_reducer = None

    if streaming and overlap_reduction and not skip_extraction and not skip_reduction:
        from newclid.proof_scout.reduction import RuleReducer, IncrementalReducer

        seed_reducer_queue = Queue()
        reducer = RuleReducer(
            timeout=timeout,
            seed=seed,
            max_premises=max_premises,
            n_workers=1,  # sequential within reducer, Ray handles parallelism
            batch_size=batch_size,
            debug=debug,
            debug_output_dir=output_dir if debug else None,
        )
        incremental_reducer = IncrementalReducer(reducer, seed_reducer_queue)
        incremental_reducer.start()
        print("[pipeline] Incremental Stage 2 reducer started in background")

    # Stage 1: Extraction
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

        # Auto-detect rules file and source data for Stage 2
        if rules_file is None and stage1.get("rules_file"):
            rules_file = Path(stage1["rules_file"])
        if source_data_file is None and stage1.get("source_data_file"):
            source_data_file = Path(stage1["source_data_file"])

    # Stage 2: Reduction
    if not skip_reduction:
        if incremental_reducer is not None:
            # Overlap mode: wait for incremental reducer to finish
            print("\n[pipeline] Waiting for incremental Stage 2 reducer to finish...")
            reduction_result = incremental_reducer.join(timeout=None)

            if reduction_result:
                elapsed_reduction = time.time() - pipeline_start

                # Save outputs
                basis_rules = reduction_result.get("basis_rules", [])
                mp_suffix = f"_maxprem{max_premises}" if max_premises else ""
                extracted_path = output_dir / f"extracted_rules{mp_suffix}.txt"
                with open(extracted_path, "w", encoding="utf-8") as f:
                    for rule in basis_rules:
                        f.write(f"{rule.rule_id}\n{rule.rule_text}\n")

                stats = reduction_result.get("stats", {})
                stats["elapsed_seconds"] = elapsed_reduction
                stats_path = output_dir / f"reduction_stats{mp_suffix}.json"
                with open(stats_path, "w", encoding="utf-8") as f:
                    json.dump(stats, f, ensure_ascii=False, indent=2)

                print(f"  Basis: {stats.get('basis_count', 0)}")
                print(f"  Total eliminated: {stats.get('total_eliminated', 0)}")

                results["stages"].append({
                    "stage": "reduction (incremental)",
                    "elapsed_seconds": elapsed_reduction,
                    "stats": stats,
                    "extracted_rules_path": str(extracted_path),
                })
            else:
                print("[pipeline] Incremental reducer returned no result")
        else:
            # Standard (non-overlap) reduction
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

            stage2 = run_stage2_reduction(
                Path(rules_file), Path(source_data_file), output_dir,
                timeout=timeout,
                seed=seed,
                max_premises=max_premises,
                max_rules=max_rules,
                n_workers=max_workers,
                batch_size=batch_size,
                debug=debug,
                no_group_reduction=no_group_reduction,
            )
            results["stages"].append(stage2)

    total_elapsed = time.time() - pipeline_start
    results["total_elapsed_seconds"] = total_elapsed

    print(f"\n{'='*60}")
    print(f"Pipeline complete in {total_elapsed:.1f}s")
    print(f"Output: {output_dir}")
    print(f"{'='*60}")

    return results


# ============================================================================
# Chunked Iterative Reduction (Python solver)
# ============================================================================

def _run_chunked_iterative_reduction(
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
    filter_only: bool = False,
    resume: bool = True,
    solver_type: str = "python",
) -> Dict[str, Any]:
    """Chunked iterative rule reduction (Python solver version).

    Identical logic to discovery_pipeline_c.run_chunked_iterative_reduction
    but defaults to solver_type="python".
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

    output_dir = Path(output_dir)
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

    reducer = ChunkedIterativeReducer(
        timeout=timeout,
        seed=seed,
        batch_size=batch_size,
        solver_type=solver_type,
        engine="full",
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
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Discovery Pipeline — rule extraction and reduction",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Stage 1 args
    stage1 = parser.add_argument_group("Stage 1: Extraction")
    stage1.add_argument("-i", "--input", type=Path, default=None, help="Input JSONL file")
    stage1.add_argument("-o", "--output", type=Path, required=True, help="Output directory")
    stage1.add_argument("--max-workers", type=int, default=30, help="Parallel workers (default: 30)")
    stage1.add_argument("--save-intermediates", action="store_true", help="Save intermediate results")
    stage1.add_argument("--skip-predicates", type=str, default=None,
                        help="Comma-separated predicates to filter from input (default: eqpoint,constline)")
    stage1.add_argument("--rule-skip-predicates", type=str, default=None,
                        help="Comma-separated predicates to filter from rules (default: aconst,rconst)")
    stage1.add_argument("--render-images", action="store_true", help="Render comparison images")

    # Streaming args
    streaming_grp = parser.add_argument_group("Streaming mode (for large datasets)")
    streaming_grp.add_argument("--streaming", action="store_true",
                               help="Use streaming mode (chunk-based + Ray) for large datasets")
    streaming_grp.add_argument("--chunk-size", type=int, default=10000,
                               help="Records per chunk in streaming mode (default: 10000)")
    streaming_grp.add_argument("--inflight-limit", type=int, default=300,
                               help="Max in-flight Ray tasks in streaming mode (default: 300)")
    streaming_grp.add_argument("--overlap-reduction", action="store_true",
                               help="Overlap Stage 1 + Stage 2 via incremental group reduction (streaming only)")

    # Stage 2 args
    stage2 = parser.add_argument_group("Stage 2: Reduction")
    stage2.add_argument("--timeout", type=int, default=60, help="Subsumption test timeout (default: 60)")
    stage2.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    stage2.add_argument("--max-premises", type=int, default=None, help="Max premises for reduction pre-filter")
    stage2.add_argument("--max-rules", type=int, default=None, help="Max rules to load (for testing)")
    stage2.add_argument("--batch-size", type=int, default=10, help="Reduction batch size (default: 10)")
    stage2.add_argument("--debug", action="store_true", help="Enable debug output for reduction")
    stage2.add_argument("--no-group-reduction", action="store_true",
                        help="Disable seed-based group reduction (use global reduction only)")

    # Skip flags
    skip = parser.add_argument_group("Skip flags")
    skip.add_argument("--skip-extraction", action="store_true", help="Skip Stage 1 (use --rules/--source-data)")
    skip.add_argument("--skip-reduction", action="store_true", help="Skip Stage 2")

    # Standalone reduction inputs
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

    # Validate
    if not args.skip_extraction and args.input is None:
        parser.error("--input is required unless --skip-extraction is set")
    if args.skip_extraction and (args.rules is None or args.source_data is None):
        parser.error("--rules and --source-data are required with --skip-extraction")
    if args.overlap_reduction and not args.streaming:
        parser.error("--overlap-reduction requires --streaming")
    if args.filter_only and not args.chunked:
        if not args.skip_extraction:
            parser.error("--filter-only requires --chunked or --skip-extraction with --rules/--source-data")

    # Parse predicate lists
    skip_preds = [p.strip() for p in args.skip_predicates.split(",")] if args.skip_predicates else None
    rule_skip_preds = [p.strip() for p in args.rule_skip_predicates.split(",")] if args.rule_skip_predicates else None

    # Chunked iterative reduction mode
    if args.chunked or args.filter_only:
        if args.rules is None or args.source_data is None:
            parser.error("--rules and --source-data are required with --chunked/--filter-only")
        _run_chunked_iterative_reduction(
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
            filter_only=args.filter_only,
            resume=not args.no_resume,
            solver_type="python",
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
        rules_file=args.rules,
        source_data_file=args.source_data,
        timeout=args.timeout,
        seed=args.seed,
        max_premises=args.max_premises,
        max_rules=args.max_rules,
        batch_size=args.batch_size,
        debug=args.debug,
        no_group_reduction=args.no_group_reduction,
        overlap_reduction=args.overlap_reduction,
    )


if __name__ == "__main__":
    main()
