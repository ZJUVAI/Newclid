#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Performance Benchmark - Test rule reduction at different scales.

This script tests the performance of rule reduction at different scales:
- 10, 20, 50, 100, 200, 500, 1000 rules

For each scale:
- Measure total time
- Measure time per rule
- Measure time per subsumption test
"""
import argparse
import json
import time
from pathlib import Path
from datetime import datetime

from newclid.proof_scout.reduction import RuleReducer, load_rules_from_discovery_output


def benchmark_at_scale(rules_file: Path, n_rules: int, output_dir: Path, seed: int = 42):
    """Benchmark rule reduction at a specific scale."""
    print(f"\n{'='*60}")
    print(f"Benchmarking with {n_rules} rules")
    print(f"{'='*60}")

    # Load rules
    print(f"Loading {n_rules} rules...")
    rules = load_rules_from_discovery_output(rules_file, max_rules=n_rules, seed=seed)

    if len(rules) < n_rules:
        print(f"Warning: Only {len(rules)} rules available (requested {n_rules})")
        if len(rules) == 0:
            print(f"Skipping this scale")
            return None

    # Run reduction
    print(f"Running reduction...")
    reducer = RuleReducer(
        timeout=60,
        seed=seed,
        verbose=False,
    )

    start_time = time.time()
    result = reducer.reduce(rules)
    end_time = time.time()
    elapsed = end_time - start_time

    # Compute metrics
    stats = result["stats"]
    stats["elapsed_seconds"] = elapsed
    stats["rules_per_second"] = len(rules) / elapsed if elapsed > 0 else 0
    stats["tests_per_second"] = stats["n_subsumption_tests"] / elapsed if elapsed > 0 else 0
    stats["seconds_per_rule"] = elapsed / len(rules) if len(rules) > 0 else 0
    stats["seconds_per_test"] = elapsed / stats["n_subsumption_tests"] if stats["n_subsumption_tests"] > 0 else 0

    # Print summary
    print(f"\nResults:")
    print(f"  Original rules:       {stats['original_count']}")
    print(f"  Basis rules:          {stats['basis_count']}")
    print(f"  Eliminated rules:     {stats['eliminated_count']}")
    print(f"  Reduction rate:       {stats['reduction_rate']*100:.1f}%")
    print(f"  Subsumption tests:    {stats['n_subsumption_tests']}")
    print(f"  Elapsed time:         {elapsed:.1f}s")
    print(f"  Rules/second:         {stats['rules_per_second']:.2f}")
    print(f"  Tests/second:         {stats['tests_per_second']:.2f}")
    print(f"  Seconds/rule:         {stats['seconds_per_rule']:.2f}")
    print(f"  Seconds/test:         {stats['seconds_per_test']:.2f}")

    # Save results
    output_file = output_dir / f"benchmark_{n_rules}_rules.json"
    with open(output_file, 'w') as f:
        json.dump(stats, f, indent=2)
    print(f"  Saved to: {output_file}")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark rule reduction at different scales"
    )
    parser.add_argument(
        "--rules",
        type=Path,
        required=True,
        help="Path to discovered_rules.txt",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output directory for benchmark results",
    )
    parser.add_argument(
        "--scales",
        type=int,
        nargs="+",
        default=[10, 20, 50, 100, 200, 500, 1000],
        help="Scales to test (default: 10 20 50 100 200 500 1000)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed (default: 42)",
    )

    args = parser.parse_args()

    # Create output directory
    args.output.mkdir(parents=True, exist_ok=True)

    print(f"Rule Reduction Performance Benchmark")
    print(f"Rules file: {args.rules}")
    print(f"Output dir: {args.output}")
    print(f"Scales: {args.scales}")

    # Run benchmarks
    all_stats = []
    for n_rules in args.scales:
        stats = benchmark_at_scale(args.rules, n_rules, args.output, args.seed)
        if stats:
            all_stats.append(stats)

    # Save summary
    summary_file = args.output / "benchmark_summary.json"
    with open(summary_file, 'w') as f:
        json.dump(all_stats, f, indent=2)
    print(f"\n{'='*60}")
    print(f"Benchmark complete! Summary saved to {summary_file}")
    print(f"{'='*60}")

    # Analyze results to determine retriever threshold
    print(f"\nAnalyzing results to determine retriever threshold...")
    print(f"\n{'Scale':<10} {'Time(s)':<10} {'Tests':<10} {'Tests/s':<10}")
    print(f"{'-'*40}")
    for stats in all_stats:
        print(f"{stats['original_count']:<10} {stats['elapsed_seconds']:<10.1f} "
              f"{stats['n_subsumption_tests']:<10} {stats['tests_per_second']:<10.2f}")

    # Find threshold where time exceeds 2 hours (7200s)
    threshold = None
    for stats in all_stats:
        if stats['elapsed_seconds'] > 7200:
            threshold = stats['original_count']
            break

    if threshold:
        print(f"\n✓ Recommended retriever threshold: {threshold} rules")
        print(f"  (Time exceeded 2 hours at this scale)")
    else:
        print(f"\n✓ No threshold needed (all scales completed within 2 hours)")
        if all_stats:
            max_scale = max(s['original_count'] for s in all_stats)
            print(f"  Tested up to {max_scale} rules")


if __name__ == "__main__":
    main()
