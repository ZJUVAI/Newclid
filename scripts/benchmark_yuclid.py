#!/usr/bin/env python3
"""
Benchmark script for Yuclid performance analysis.

This script measures Yuclid solving time on geometry problems to compare
with CSolver performance.

Usage:
    conda activate yuclid
    python scripts/benchmark_yuclid.py \
        --problems benchmarks/coords/hageo_409_coords.txt \
        --output outputs/benchmark_yuclid_hageo409.json \
        --timeout 30
"""

import argparse
import json
import time
import sys
import multiprocessing as mp
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Tuple, Optional
import statistics


@dataclass
class ProblemResult:
    """Result of solving a single problem."""
    name: str
    solved: bool
    solve_time: float
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

    avg_time: float
    median_time: float
    max_time: float
    min_time: float
    p90_time: float
    p95_time: float
    p99_time: float

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
    chunks = content.split("Problem Name:")

    for chunk in chunks[1:]:
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
                if ':' in line:
                    name, coords = line.split(':', 1)
                    x, y = coords.split(',')
                    problem['points'].append((name.strip(), float(x), float(y)))
            elif section == 'premises':
                parts = line.split()
                if parts:
                    predicate = parts[0]
                    args = parts[1:]
                    problem['premises'].append((predicate, args))
            elif section == 'goals':
                parts = line.split()
                if parts:
                    predicate = parts[0]
                    args = parts[1:]
                    problem['goals'].append((predicate, args))

        if problem['name']:
            problems.append(problem)

    return problems


def convert_to_yuclid_format(problem: dict) -> str:
    """Convert HAGeo problem dict to yuclid input format."""
    lines = []

    # Points: name:x,y -> point name x y
    for name, x, y in problem['points']:
        lines.append(f"point {name} {x} {y}")

    # Premises: predicate args -> assume predicate args
    for predicate, args in problem['premises']:
        lines.append(f"assume {predicate} {' '.join(args)}")

    # Goals: predicate args -> prove predicate args
    for predicate, args in problem['goals']:
        lines.append(f"prove {predicate} {' '.join(args)}")

    return '\n'.join(lines)


def _run_single_problem_yuclid(prob: dict, timeout: float, result_queue: mp.Queue):
    """Worker function to run a single problem using yuclid binary directly."""
    import subprocess
    import tempfile
    import shutil

    try:
        yuclid_path = shutil.which("yuclid")
        if yuclid_path is None:
            result_queue.put({
                'solved': False,
                'time': 0.0,
                'error': "yuclid binary not found in PATH"
            })
            return

        # Convert problem to yuclid format
        yuclid_input = convert_to_yuclid_format(prob)

        start = time.perf_counter()

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(yuclid_input)
            input_file = f.name

        try:
            result = subprocess.run(
                [
                    yuclid_path,
                    "--mode", "ddar",
                    "--disable-ar-dist",
                    "--disable-ar-squared",
                    "--disable-eqn-statements",
                    "--disable-ar-sin",
                    "--use-json",
                    "--log-level", "warning",
                    "--input-file", input_file
                ],
                capture_output=True,
                text=True,
                timeout=timeout
            )

            elapsed = time.perf_counter() - start

            if result.returncode == 0:
                try:
                    output = json.loads(result.stdout)
                    solved = output.get('status') == 'solved'
                    result_queue.put({
                        'solved': solved,
                        'time': elapsed,
                        'error': None
                    })
                except json.JSONDecodeError as e:
                    result_queue.put({
                        'solved': False,
                        'time': elapsed,
                        'error': f"JSON parse error: {e}"
                    })
            else:
                result_queue.put({
                    'solved': False,
                    'time': elapsed,
                    'error': f"yuclid error: {result.stderr}"
                })
        finally:
            Path(input_file).unlink(missing_ok=True)

    except subprocess.TimeoutExpired:
        result_queue.put({
            'solved': False,
            'time': timeout,
            'error': "TIMEOUT"
        })
    except Exception as e:
        result_queue.put({
            'solved': False,
            'time': 0.0,
            'error': str(e)
        })


def _run_single_problem_newclid(prob: dict, result_queue: mp.Queue):
    """Worker function to run a single problem using newclid API with yuclid backend."""
    try:
        from newclid import GeometricSolverBuilder
        from newclid.problem import ProblemSetup, Point, PredicateConstruction
        from newclid.predicates._index import PredicateType
        from newclid.numerical import Point2D

        start = time.perf_counter()

        # Build problem setup
        points = [
            Point(name=name, num=Point2D(x=x, y=y))
            for name, x, y in prob['points']
        ]

        assumptions = []
        for predicate, args in prob['premises']:
            try:
                pred_type = PredicateType(predicate)
                assumptions.append(
                    PredicateConstruction.from_predicate_type_and_args(pred_type, tuple(args))
                )
            except ValueError:
                pass  # Skip unknown predicates

        goals = []
        for predicate, args in prob['goals']:
            try:
                pred_type = PredicateType(predicate)
                goals.append(
                    PredicateConstruction.from_predicate_type_and_args(pred_type, tuple(args))
                )
            except ValueError:
                pass

        problem_setup = ProblemSetup(
            points=points,
            assumptions=assumptions,
            goals=goals
        )

        builder = GeometricSolverBuilder()
        solver = builder.build(problem_setup)
        solved = solver.run()

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
    timeout: float = 30.0,
    verbose: bool = False,
    limit: int = 0,
    use_newclid_api: bool = False
) -> Tuple[List[ProblemResult], BenchmarkStats]:
    """
    Run benchmark on all problems in a file.

    Args:
        problems_path: Path to benchmark file
        timeout: Timeout per problem in seconds
        verbose: Print progress
        limit: Limit number of problems (0 = no limit)
        use_newclid_api: Use newclid API instead of yuclid binary directly

    Returns:
        Tuple of (list of results, statistics)
    """
    problems = parse_benchmark_file(problems_path)

    if limit > 0:
        problems = problems[:limit]

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
            solve_time=0.0,
            num_points=len(prob['points']),
            num_premises=len(prob['premises'])
        )

        result_queue = mp.Queue()

        if use_newclid_api:
            proc = mp.Process(
                target=_run_single_problem_newclid,
                args=(prob, result_queue)
            )
        else:
            proc = mp.Process(
                target=_run_single_problem_yuclid,
                args=(prob, timeout, result_queue)
            )

        proc.start()
        proc.join(timeout=timeout + 5)  # Extra buffer for subprocess overhead

        if proc.is_alive():
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
                result.error = res['error']

                if verbose:
                    if result.error and result.error != "TIMEOUT":
                        print(f"ERROR: {result.error[:50]}")
                    elif result.error == "TIMEOUT":
                        print(f"TIMEOUT (>{timeout:.0f}s)")
                    else:
                        status = "SOLVED" if result.solved else "FAILED"
                        print(f"{status} ({result.solve_time:.3f}s)")
            except:
                result.error = "NO_RESULT"
                if verbose:
                    print("ERROR: No result from subprocess")

        results.append(result)

    stats = calculate_stats(results)
    return results, stats


def calculate_stats(results: List[ProblemResult]) -> BenchmarkStats:
    """Calculate statistics from benchmark results."""
    successful = [r for r in results if r.error is None]
    solved = [r for r in successful if r.solved]
    failed = [r for r in successful if not r.solved]
    errors = [r for r in results if r.error is not None and r.error != "TIMEOUT"]
    timeouts = [r for r in results if r.error == "TIMEOUT"]

    times = [r.solve_time for r in successful]
    sorted_times = sorted(times) if times else [0.0]

    def percentile(data, p):
        if not data:
            return 0.0
        k = (len(data) - 1) * p / 100
        f = int(k)
        c = f + 1 if f + 1 < len(data) else f
        return data[f] + (k - f) * (data[c] - data[f])

    return BenchmarkStats(
        total_problems=len(results),
        solved_count=len(solved),
        failed_count=len(failed),
        error_count=len(errors),
        timeout_count=len(timeouts),

        avg_time=statistics.mean(times) if times else 0.0,
        median_time=statistics.median(times) if times else 0.0,
        max_time=max(times) if times else 0.0,
        min_time=min(times) if times else 0.0,
        p90_time=percentile(sorted_times, 90),
        p95_time=percentile(sorted_times, 95),
        p99_time=percentile(sorted_times, 99),

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
        'solver': 'yuclid',
        'benchmark_file': str(problems_path),
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'statistics': asdict(stats),
        'results': [asdict(r) for r in results],
        'slowest_problems': [
            {'name': r.name, 'time': r.solve_time, 'solved': r.solved}
            for r in sorted(results, key=lambda x: x.solve_time, reverse=True)[:10]
        ]
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)


def print_summary(stats: BenchmarkStats):
    """Print a summary of benchmark results."""
    print("\n" + "="*60)
    print("YUCLID BENCHMARK SUMMARY")
    print("="*60)
    print(f"Total problems:     {stats.total_problems}")
    print(f"Solved:             {stats.solved_count} ({100*stats.solved_count/stats.total_problems:.1f}%)")
    print(f"Failed:             {stats.failed_count} ({100*stats.failed_count/stats.total_problems:.1f}%)")
    print(f"Timeouts:           {stats.timeout_count}")
    print(f"Errors:             {stats.error_count}")
    print()
    print("Time Statistics (seconds):")
    print(f"  Mean:             {stats.avg_time:.4f}")
    print(f"  Median:           {stats.median_time:.4f}")
    print(f"  Min:              {stats.min_time:.4f}")
    print(f"  Max:              {stats.max_time:.4f}")
    print(f"  P90:              {stats.p90_time:.4f}")
    print(f"  P95:              {stats.p95_time:.4f}")
    print(f"  P99:              {stats.p99_time:.4f}")
    print()
    print("Problem Complexity:")
    print(f"  Average points:   {stats.avg_points:.1f}")
    print(f"  Average premises: {stats.avg_premises:.1f}")
    print("="*60)


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark Yuclid performance on geometry problems"
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
        default=30.0,
        help="Timeout per problem in seconds (default: 30)"
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=0,
        help="Limit number of problems to run (default: 0 = all)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print per-problem output"
    )
    parser.add_argument(
        "--use-newclid-api",
        action="store_true",
        help="Use newclid API instead of yuclid binary directly"
    )

    args = parser.parse_args()

    if not args.problems.exists():
        print(f"Error: Benchmark file not found: {args.problems}")
        sys.exit(1)

    results, stats = run_benchmark(
        args.problems,
        timeout=args.timeout,
        verbose=args.verbose,
        limit=args.limit,
        use_newclid_api=args.use_newclid_api
    )

    print_summary(stats)

    if args.output:
        save_results(results, stats, args.output, args.problems)
        print(f"\nResults saved to: {args.output}")


if __name__ == "__main__":
    main()
