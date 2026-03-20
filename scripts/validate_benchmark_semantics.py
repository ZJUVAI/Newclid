#!/usr/bin/env python3
"""
Validate JGEX benchmark semantics using DDAR engine.

This script tests whether JGEX-formatted problems can be successfully parsed
and solved by the DDAR engine, validating semantic correctness beyond syntax.

Usage:
    # Test MO-TG-225 benchmark
    python scripts/validate_benchmark_semantics.py \
        --benchmark datasets/mo_tg_225/mo_tg_225_draft.txt \
        --output outputs/mo_tg_225_validation.json \
        --timeout 30

    # Test IMO-AG-30 benchmark
    python scripts/validate_benchmark_semantics.py \
        --benchmark benchmarks/core/imo_ag_30.txt \
        --output outputs/imo_ag_30_validation.json \
        --timeout 30

    # Test multiple benchmarks
    python scripts/validate_benchmark_semantics.py \
        --benchmark datasets/mo_tg_225/mo_tg_225_draft.txt \
        --benchmark benchmarks/core/imo_ag_30.txt \
        --output outputs/combined_validation.json
"""

import argparse
import json
import time
import sys
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
import statistics

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from newclid.api import GeometricSolverBuilder
from newclid.numerical.geometries import PointNum


@dataclass
class ValidationResult:
    """Result of validating a single problem."""
    name: str
    benchmark: str
    status: str  # 'solved', 'failed', 'timeout', 'parse_error', 'runtime_error'
    solve_time: float
    error_message: Optional[str] = None
    num_points: int = 0
    num_premises: int = 0
    num_goals: int = 0


@dataclass
class ValidationStats:
    """Statistics for a validation run."""
    benchmark: str
    total_problems: int
    solved_count: int
    failed_count: int
    timeout_count: int
    parse_error_count: int
    runtime_error_count: int

    # Time statistics (only for completed runs)
    avg_time: float
    median_time: float
    max_time: float
    min_time: float

    # Problem complexity
    avg_points: float
    avg_premises: float
    avg_goals: float


def parse_jgex_file(filepath: Path) -> List[Dict[str, str]]:
    """
    Parse a JGEX benchmark file.

    Format (two lines per problem):
        problem_name
        <construction> ? <goals>

    Returns:
        List of dicts with keys: name, jgex_text
    """
    problems = []

    with open(filepath, 'r') as f:
        lines = [line.strip() for line in f if line.strip()]

    # Parse two lines at a time
    for i in range(0, len(lines), 2):
        if i + 1 >= len(lines):
            break

        name = lines[i]
        jgex_text = lines[i + 1]

        problems.append({
            'name': name,
            'jgex_text': jgex_text
        })

    return problems


def validate_problem(problem: Dict[str, str], timeout: int) -> ValidationResult:
    """
    Validate a single problem using GeometricSolver.

    Args:
        problem: Dict with 'name' and 'jgex_text'
        timeout: Timeout in seconds

    Returns:
        ValidationResult with status and timing
    """
    name = problem['name']
    jgex_text = problem['jgex_text']

    start_time = time.time()

    try:
        # Build solver using GeometricSolverBuilder
        solver = (
            GeometricSolverBuilder(seed=123)
            .load_problem_from_txt(jgex_text)
            .build()
        )

        # Extract problem info
        num_points = len([n for n, node in solver.proof.symbols_graph.name2node.items()
                         if isinstance(node.num, PointNum)])
        num_premises = len(solver.proof.dep_graph.hyper_graph)
        num_goals = len(solver.goals)

        # Run solver with timeout
        solved = solver.run(timeout=timeout)

        elapsed = time.time() - start_time

        # Check if we exceeded timeout
        if elapsed >= timeout:
            status = 'timeout'
        elif solved:
            status = 'solved'
        else:
            status = 'failed'

        return ValidationResult(
            name=name,
            benchmark='',  # Will be set by caller
            status=status,
            solve_time=elapsed,
            num_points=num_points,
            num_premises=num_premises,
            num_goals=num_goals
        )

    except SyntaxError as e:
        elapsed = time.time() - start_time
        return ValidationResult(
            name=name,
            benchmark='',
            status='parse_error',
            solve_time=elapsed,
            error_message=str(e)
        )

    except Exception as e:
        elapsed = time.time() - start_time
        return ValidationResult(
            name=name,
            benchmark='',
            status='runtime_error',
            solve_time=elapsed,
            error_message=str(e)
        )


def compute_stats(results: List[ValidationResult], benchmark_name: str) -> ValidationStats:
    """Compute statistics from validation results."""
    total = len(results)
    solved = sum(1 for r in results if r.status == 'solved')
    failed = sum(1 for r in results if r.status == 'failed')
    timeout = sum(1 for r in results if r.status == 'timeout')
    parse_error = sum(1 for r in results if r.status == 'parse_error')
    runtime_error = sum(1 for r in results if r.status == 'runtime_error')

    # Time stats (only for completed runs, excluding errors)
    completed = [r for r in results if r.status in ['solved', 'failed', 'timeout']]
    times = [r.solve_time for r in completed] if completed else [0.0]

    # Complexity stats (only for successfully parsed problems)
    parsed = [r for r in results if r.status not in ['parse_error']]
    points = [r.num_points for r in parsed] if parsed else [0]
    premises = [r.num_premises for r in parsed] if parsed else [0]
    goals = [r.num_goals for r in parsed] if parsed else [0]

    return ValidationStats(
        benchmark=benchmark_name,
        total_problems=total,
        solved_count=solved,
        failed_count=failed,
        timeout_count=timeout,
        parse_error_count=parse_error,
        runtime_error_count=runtime_error,
        avg_time=statistics.mean(times),
        median_time=statistics.median(times),
        max_time=max(times),
        min_time=min(times),
        avg_points=statistics.mean(points),
        avg_premises=statistics.mean(premises),
        avg_goals=statistics.mean(goals)
    )


def print_stats(stats: ValidationStats):
    """Print validation statistics in a readable format."""
    print(f"\n{'='*80}")
    print(f"Validation Results: {stats.benchmark}")
    print(f"{'='*80}")
    print(f"\nTotal Problems: {stats.total_problems}")
    print(f"  Solved:        {stats.solved_count:4d} ({stats.solved_count/stats.total_problems*100:5.1f}%)")
    print(f"  Failed:        {stats.failed_count:4d} ({stats.failed_count/stats.total_problems*100:5.1f}%)")
    print(f"  Timeout:       {stats.timeout_count:4d} ({stats.timeout_count/stats.total_problems*100:5.1f}%)")
    print(f"  Parse Error:   {stats.parse_error_count:4d} ({stats.parse_error_count/stats.total_problems*100:5.1f}%)")
    print(f"  Runtime Error: {stats.runtime_error_count:4d} ({stats.runtime_error_count/stats.total_problems*100:5.1f}%)")

    print(f"\nTime Statistics:")
    print(f"  Mean:   {stats.avg_time:.3f}s")
    print(f"  Median: {stats.median_time:.3f}s")
    print(f"  Min:    {stats.min_time:.3f}s")
    print(f"  Max:    {stats.max_time:.3f}s")

    print(f"\nProblem Complexity:")
    print(f"  Avg Points:   {stats.avg_points:.1f}")
    print(f"  Avg Premises: {stats.avg_premises:.1f}")
    print(f"  Avg Goals:    {stats.avg_goals:.1f}")


def main():
    parser = argparse.ArgumentParser(
        description='Validate JGEX benchmark semantics using DDAR engine',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        '--benchmark',
        type=Path,
        action='append',
        required=True,
        help='Path to JGEX benchmark file (can specify multiple times)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        required=True,
        help='Output JSON file for validation results'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=30,
        help='Timeout per problem in seconds (default: 30)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Print progress for each problem'
    )

    args = parser.parse_args()

    # Validate input files
    for benchmark_path in args.benchmark:
        if not benchmark_path.exists():
            print(f"Error: Benchmark file not found: {benchmark_path}")
            sys.exit(1)

    # Create output directory
    args.output.parent.mkdir(parents=True, exist_ok=True)

    # Process each benchmark
    all_results = []
    all_stats = []

    for benchmark_path in args.benchmark:
        benchmark_name = benchmark_path.stem
        print(f"\n{'='*80}")
        print(f"Processing: {benchmark_path}")
        print(f"{'='*80}")

        # Parse problems
        problems = parse_jgex_file(benchmark_path)
        print(f"Found {len(problems)} problems")

        # Validate each problem
        results = []
        for i, problem in enumerate(problems, 1):
            if args.verbose:
                print(f"[{i}/{len(problems)}] Testing {problem['name']}...", end=' ', flush=True)

            result = validate_problem(problem, args.timeout)
            result.benchmark = benchmark_name
            results.append(result)

            if args.verbose:
                print(f"{result.status} ({result.solve_time:.3f}s)")

        # Compute and print stats
        stats = compute_stats(results, benchmark_name)
        print_stats(stats)

        all_results.extend(results)
        all_stats.append(stats)

    # Save results
    output_data = {
        'benchmarks': [asdict(s) for s in all_stats],
        'results': [asdict(r) for r in all_results],
        'config': {
            'timeout': args.timeout,
            'benchmark_files': [str(p) for p in args.benchmark]
        }
    }

    with open(args.output, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"\n{'='*80}")
    print(f"Results saved to: {args.output}")
    print(f"{'='*80}")

    # Print summary if multiple benchmarks
    if len(all_stats) > 1:
        print(f"\nSummary Across All Benchmarks:")
        total_problems = sum(s.total_problems for s in all_stats)
        total_solved = sum(s.solved_count for s in all_stats)
        total_failed = sum(s.failed_count for s in all_stats)
        total_timeout = sum(s.timeout_count for s in all_stats)
        total_parse_error = sum(s.parse_error_count for s in all_stats)
        total_runtime_error = sum(s.runtime_error_count for s in all_stats)

        print(f"  Total Problems: {total_problems}")
        print(f"  Solved:         {total_solved} ({total_solved/total_problems*100:.1f}%)")
        print(f"  Failed:         {total_failed} ({total_failed/total_problems*100:.1f}%)")
        print(f"  Timeout:        {total_timeout} ({total_timeout/total_problems*100:.1f}%)")
        print(f"  Parse Error:    {total_parse_error} ({total_parse_error/total_problems*100:.1f}%)")
        print(f"  Runtime Error:  {total_runtime_error} ({total_runtime_error/total_problems*100:.1f}%)")


if __name__ == '__main__':
    main()
