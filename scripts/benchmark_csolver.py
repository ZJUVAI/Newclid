#!/usr/bin/env python3
"""
Benchmark script for CSolver performance analysis.

This script measures CSolver solving time on geometry problems to identify
performance bottlenecks and provide baseline metrics for optimization.

Usage:
    python scripts/benchmark_csolver.py \
        --problems benchmarks/coords/hageo_409_coords.txt \
        --output outputs/benchmark_hageo409.json \
        --timeout 60
"""

import argparse
import json
import time
import sys
import signal
import multiprocessing as mp
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Tuple, Optional
import statistics

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@dataclass
class ProblemResult:
    """Result of solving a single problem."""
    name: str
    solved: bool
    build_time: float  # Time to build CSolver (parse + setup)
    solve_time: float  # Time for DDAR.run_ddar()
    total_time: float  # build_time + solve_time
    error: Optional[str] = None
    num_points: int = 0
    num_premises: int = 0


@dataclass
class BenchmarkStats:
    """Statistics for a benchmark run."""
    total_problems: int
    solved_count: int
    failed_count: int
    error_count: int
    timeout_count: int

    # Time statistics (only for successful runs)
    avg_build_time: float
    avg_solve_time: float
    avg_total_time: float
    median_total_time: float
    max_total_time: float
    min_total_time: float

    # Problem complexity stats
    avg_points: float
    avg_premises: float


def parse_benchmark_file(filepath: Path) -> List[dict]:
    """
    Parse a benchmark file with coordinates format.

    Format:
        Problem Name:
        <name>
        Points:
        <point>:<x>,<y>
        ...
        Premises:
        <predicate> <arg1> <arg2> ...
        ...
        Goal:
        <predicate> <arg1> <arg2> ...

        [next problem...]

    Returns:
        List of dicts with keys: name, points, premises, goals
    """
    with open(filepath, 'r') as f:
        content = f.read()

    problems = []

    # Split by "Problem Name:" to get individual problems
    chunks = content.split("Problem Name:")

    for chunk in chunks[1:]:  # Skip first empty chunk
        lines = [line.strip() for line in chunk.strip().split('\n') if line.strip()]
        if not lines:
            continue

        problem = {
            'name': '',
            'points': [],
            'premises': [],
            'goals': []
        }

        section = 'name'

        for line in lines:
            if line == "Points:":
                section = 'points'
                continue
            elif line == "Premises:":
                section = 'premises'
                continue
            elif line == "Goal:":
                section = 'goals'
                continue

            if section == 'name':
                problem['name'] = line
            elif section == 'points':
                # Format: name:x,y
                if ':' in line:
                    name, coords = line.split(':', 1)
                    x, y = coords.split(',')
                    problem['points'].append((name.strip(), float(x), float(y)))
            elif section == 'premises':
                # Format: predicate arg1 arg2 ...
                parts = line.split()
                if parts:
                    predicate = parts[0]
                    args = parts[1:]
                    problem['premises'].append((predicate, args))
            elif section == 'goals':
                # Format: predicate arg1 arg2 ...
                parts = line.split()
                if parts:
                    predicate = parts[0]
                    args = parts[1:]
                    problem['goals'].append((predicate, args))

        if problem['name']:
            problems.append(problem)

    return problems


def _run_single_problem(prob: dict, max_level: int, result_queue: mp.Queue):
    """Worker function to run a single problem in a subprocess."""
    try:
        from newclid.DDAR.build import DDAR

        start = time.perf_counter()
        solved, dep_graph = DDAR.run_ddar(
            prob['name'],
            prob['points'],
            prob['premises'],
            prob['goals'],
            max_level,
            True,  # log_enabled
            True   # exp_enabled
        )
        elapsed = time.perf_counter() - start

        result_queue.put({
            'solved': solved,
            'time': elapsed,
            'error': None
        })
    except Exception as e:
        result_queue.put({
            'solved': False,
            'time': 0.0,
            'error': str(e)
        })


def run_benchmark(
    problems_path: Path,
    timeout: float = 60.0,
    max_level: int = 500,
    verbose: bool = False,
    use_subprocess: bool = True
) -> Tuple[List[ProblemResult], BenchmarkStats]:
    """
    Run benchmark on all problems in a file.

    Args:
        problems_path: Path to benchmark file
        timeout: Timeout per problem in seconds
        max_level: Maximum DDAR inference level
        verbose: Print progress
        use_subprocess: Run each problem in subprocess for isolation

    Returns:
        Tuple of (list of results, statistics)
    """
    problems = parse_benchmark_file(problems_path)
    results: List[ProblemResult] = []

    if verbose:
        print(f"Loaded {len(problems)} problems from {problems_path}")

    for i, prob in enumerate(problems):
        name = prob['name']

        if verbose:
            print(f"[{i+1}/{len(problems)}] {name}...", end=" ", flush=True)

        result = ProblemResult(
            name=name,
            solved=False,
            build_time=0.0,
            solve_time=0.0,
            total_time=0.0,
            num_points=len(prob['points']),
            num_premises=len(prob['premises'])
        )

        if use_subprocess:
            # Run in subprocess for memory isolation
            result_queue = mp.Queue()
            proc = mp.Process(
                target=_run_single_problem,
                args=(prob, max_level, result_queue)
            )
            proc.start()
            proc.join(timeout=timeout)

            if proc.is_alive():
                # Timeout - kill the process
                proc.terminate()
                proc.join(timeout=1)
                if proc.is_alive():
                    proc.kill()
                    proc.join()
                result.error = "TIMEOUT"
                if verbose:
                    print(f"TIMEOUT (>{timeout:.0f}s)")
            else:
                try:
                    res = result_queue.get_nowait()
                    result.solved = res['solved']
                    result.solve_time = res['time']
                    result.total_time = res['time']
                    result.error = res['error']

                    if verbose:
                        if result.error:
                            print(f"ERROR: {result.error}")
                        else:
                            status = "SOLVED" if result.solved else "FAILED"
                            print(f"{status} ({result.total_time:.3f}s)")
                except:
                    result.error = "NO_RESULT"
                    if verbose:
                        print("ERROR: No result from subprocess")
        else:
            # Run directly (faster but no isolation)
            try:
                from newclid.DDAR.build import DDAR

                total_start = time.perf_counter()
                solve_start = time.perf_counter()

                solved, dep_graph = DDAR.run_ddar(
                    name,
                    prob['points'],
                    prob['premises'],
                    prob['goals'],
                    max_level,
                    True,  # log_enabled
                    True   # exp_enabled
                )

                solve_end = time.perf_counter()
                total_end = time.perf_counter()

                result.solved = solved
                result.build_time = solve_start - total_start
                result.solve_time = solve_end - solve_start
                result.total_time = total_end - total_start

                if verbose:
                    status = "SOLVED" if solved else "FAILED"
                    print(f"{status} ({result.total_time:.3f}s)")

            except Exception as e:
                result.error = str(e)
                if verbose:
                    print(f"ERROR: {e}")

        results.append(result)

    # Calculate statistics
    stats = calculate_stats(results)

    return results, stats


def calculate_stats(results: List[ProblemResult]) -> BenchmarkStats:
    """Calculate statistics from benchmark results."""
    successful = [r for r in results if r.error is None]
    solved = [r for r in successful if r.solved]
    failed = [r for r in successful if not r.solved]
    errors = [r for r in results if r.error is not None and r.error != "TIMEOUT"]
    timeouts = [r for r in results if r.error == "TIMEOUT"]

    # Time stats (only from successful runs)
    build_times = [r.build_time for r in successful]
    solve_times = [r.solve_time for r in successful]
    total_times = [r.total_time for r in successful]

    return BenchmarkStats(
        total_problems=len(results),
        solved_count=len(solved),
        failed_count=len(failed),
        error_count=len(errors),
        timeout_count=len(timeouts),

        avg_build_time=statistics.mean(build_times) if build_times else 0.0,
        avg_solve_time=statistics.mean(solve_times) if solve_times else 0.0,
        avg_total_time=statistics.mean(total_times) if total_times else 0.0,
        median_total_time=statistics.median(total_times) if total_times else 0.0,
        max_total_time=max(total_times) if total_times else 0.0,
        min_total_time=min(total_times) if total_times else 0.0,

        avg_points=statistics.mean([r.num_points for r in results]) if results else 0.0,
        avg_premises=statistics.mean([r.num_premises for r in results]) if results else 0.0
    )


def save_results(
    results: List[ProblemResult],
    stats: BenchmarkStats,
    output_path: Path,
    problems_path: Path
):
    """Save benchmark results to JSON file."""
    output = {
        'benchmark_file': str(problems_path),
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'statistics': asdict(stats),
        'results': [asdict(r) for r in results],
        # Top 10 slowest problems
        'slowest_problems': [
            {'name': r.name, 'time': r.total_time, 'solved': r.solved}
            for r in sorted(results, key=lambda x: x.total_time, reverse=True)[:10]
        ]
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)


def print_summary(stats: BenchmarkStats):
    """Print a summary of benchmark results."""
    print("\n" + "="*60)
    print("BENCHMARK SUMMARY")
    print("="*60)
    print(f"Total problems:     {stats.total_problems}")
    print(f"Solved:             {stats.solved_count} ({100*stats.solved_count/stats.total_problems:.1f}%)")
    print(f"Failed:             {stats.failed_count} ({100*stats.failed_count/stats.total_problems:.1f}%)")
    print(f"Timeouts:           {stats.timeout_count}")
    print(f"Errors:             {stats.error_count}")
    print()
    print("Time Statistics (seconds):")
    print(f"  Average total:    {stats.avg_total_time:.4f}")
    print(f"  Median total:     {stats.median_total_time:.4f}")
    print(f"  Min total:        {stats.min_total_time:.4f}")
    print(f"  Max total:        {stats.max_total_time:.4f}")
    print(f"  Average solve:    {stats.avg_solve_time:.4f}")
    print()
    print("Problem Complexity:")
    print(f"  Average points:   {stats.avg_points:.1f}")
    print(f"  Average premises: {stats.avg_premises:.1f}")
    print("="*60)


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark CSolver performance on geometry problems"
    )
    parser.add_argument(
        "--problems", "-p",
        type=Path,
        required=True,
        help="Path to benchmark file with coordinates"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Output JSON file for results"
    )
    parser.add_argument(
        "--timeout", "-t",
        type=float,
        default=60.0,
        help="Timeout per problem in seconds (default: 60)"
    )
    parser.add_argument(
        "--max-level", "-l",
        type=int,
        default=500,
        help="Maximum DDAR inference level (default: 500)"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress per-problem output"
    )
    parser.add_argument(
        "--no-subprocess",
        action="store_true",
        help="Run directly without subprocess isolation (faster but may crash on memory issues)"
    )

    args = parser.parse_args()

    if not args.problems.exists():
        print(f"Error: Benchmark file not found: {args.problems}")
        sys.exit(1)

    results, stats = run_benchmark(
        args.problems,
        timeout=args.timeout,
        max_level=args.max_level,
        verbose=not args.quiet,
        use_subprocess=not args.no_subprocess
    )

    print_summary(stats)

    if args.output:
        save_results(results, stats, args.output, args.problems)
        print(f"\nResults saved to: {args.output}")


if __name__ == "__main__":
    main()
