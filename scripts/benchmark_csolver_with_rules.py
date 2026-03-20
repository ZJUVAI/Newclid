#!/usr/bin/env python3
"""
Benchmark script for CSolver with custom rules support.

This script extends benchmark_csolver.py to support custom geometric rules,
enabling evaluation of discovered rules on benchmark problems.

Usage:
    # Baseline (no rules)
    python scripts/benchmark_csolver_with_rules.py \
        --problems benchmarks/coords/hageo_409_coords.txt \
        --output outputs/benchmark_baseline.json \
        --timeout 30

    # With custom rules
    python scripts/benchmark_csolver_with_rules.py \
        --problems benchmarks/coords/hageo_409_coords.txt \
        --rules outputs/discovery_direct_test/valid_rules.txt \
        --output outputs/benchmark_with_rules.json \
        --timeout 30

    # Compare results
    python scripts/benchmark_csolver_with_rules.py \
        --compare outputs/benchmark_baseline.json outputs/benchmark_with_rules.json
"""

import argparse
import json
import re
import time
import sys
import multiprocessing as mp
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Tuple, Optional, Set
import statistics

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# Patterns of (premise_predicate, conclusion_predicate) that cause inference explosion
# These rules create feedback loops with built-in DDAR rules
GENERATIVE_RULE_PATTERNS: Set[Tuple[str, str]] = {
    ('cyclic', 'eqangle'),  # r03: cyclic => eqangle creates feedback with r04: eqangle => cyclic
}


def parse_rule_predicates(rule_text: str) -> Tuple[Set[str], Set[str]]:
    """Parse a rule and extract premise and conclusion predicates.

    Args:
        rule_text: Rule in format "premise1, premise2 => conclusion1, conclusion2"

    Returns:
        Tuple of (premise_predicates, conclusion_predicates)
    """
    if '=>' not in rule_text:
        return set(), set()

    premise_part, conclusion_part = rule_text.split('=>', 1)

    # Extract predicates (first word of each condition)
    premise_preds = set()
    for condition in premise_part.split(','):
        parts = re.findall(r'\w+', condition)
        if parts:
            premise_preds.add(parts[0])

    conclusion_preds = set()
    for condition in conclusion_part.split(','):
        parts = re.findall(r'\w+', condition)
        if parts:
            conclusion_preds.add(parts[0])

    return premise_preds, conclusion_preds


def is_generative_rule(rule_text: str) -> bool:
    """Check if a rule causes inference explosion.

    A rule is considered generative if it matches any pattern in GENERATIVE_RULE_PATTERNS,
    where the premise contains the first predicate and conclusion contains the second.

    Args:
        rule_text: Rule in format "premise1, premise2 => conclusion"

    Returns:
        True if the rule is generative (should be filtered out)
    """
    premise_preds, conclusion_preds = parse_rule_predicates(rule_text)

    for premise_pred, conclusion_pred in GENERATIVE_RULE_PATTERNS:
        if premise_pred in premise_preds and conclusion_pred in conclusion_preds:
            return True

    return False


def filter_generative_rules(rules: List[str], verbose: bool = False) -> Tuple[List[str], List[str]]:
    """Filter out rules that cause inference explosion.

    Args:
        rules: List of rule strings
        verbose: Print information about filtered rules

    Returns:
        Tuple of (safe_rules, blocked_rules)
    """
    safe_rules = []
    blocked_rules = []

    for rule in rules:
        if is_generative_rule(rule):
            blocked_rules.append(rule)
            if verbose:
                print(f"  Filtered (generative): {rule[:60]}...")
        else:
            safe_rules.append(rule)

    return safe_rules, blocked_rules


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

    # Custom rules info
    num_rules: int = 0


def parse_rules_file(filepath: Path) -> List[str]:
    """
    Parse rules file and return list of rule strings.

    Format (every 2 lines):
        r11
        eqratio a b a c d b d c, coll a b c, ncoll d b c => eqangle d b d a d a d c
        r60
        eqratio a b a c d e d f, eqratio c b c a f e f d, sameclock b a c e d f => simtri b a c e d f
        ...

    Returns:
        List of rule strings (premise1, premise2 => conclusion1, conclusion2)
    """
    lines = filepath.read_text().strip().split('\n')
    rules = []

    for i in range(0, len(lines), 2):
        if i + 1 < len(lines):
            rule_text = lines[i + 1].strip()
            if '=>' in rule_text:
                rules.append(rule_text)

    return rules


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


def _run_single_problem(prob: dict, max_level: int, custom_rules: List[str], result_queue: mp.Queue):
    """Worker function to run a single problem in a subprocess."""
    try:
        from newclid.DDAR.build import DDAR

        start = time.perf_counter()

        if custom_rules:
            solved, dep_graph = DDAR.run_ddar_with_rules(
                prob['name'],
                prob['points'],
                prob['premises'],
                prob['goals'],
                custom_rules,
                max_level,
                True,  # log_enabled
                True   # exp_enabled
            )
        else:
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
    custom_rules: Optional[List[str]] = None,
    timeout: float = 60.0,
    max_level: int = 500,
    verbose: bool = False,
    use_subprocess: bool = True
) -> Tuple[List[ProblemResult], BenchmarkStats]:
    """
    Run benchmark on all problems in a file.

    Args:
        problems_path: Path to benchmark file
        custom_rules: Optional list of custom rule strings
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
        if custom_rules:
            print(f"Using {len(custom_rules)} custom rules")

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
                args=(prob, max_level, custom_rules or [], result_queue)
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

                if custom_rules:
                    solved, dep_graph = DDAR.run_ddar_with_rules(
                        name,
                        prob['points'],
                        prob['premises'],
                        prob['goals'],
                        custom_rules,
                        max_level,
                        True,  # log_enabled
                        True   # exp_enabled
                    )
                else:
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
    stats = calculate_stats(results, num_rules=len(custom_rules) if custom_rules else 0)

    return results, stats


def calculate_stats(results: List[ProblemResult], num_rules: int = 0) -> BenchmarkStats:
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
        avg_premises=statistics.mean([r.num_premises for r in results]) if results else 0.0,

        num_rules=num_rules
    )


def save_results(
    results: List[ProblemResult],
    stats: BenchmarkStats,
    output_path: Path,
    problems_path: Path,
    rules_path: Optional[Path] = None
):
    """Save benchmark results to JSON file."""
    output = {
        'benchmark_file': str(problems_path),
        'rules_file': str(rules_path) if rules_path else None,
        'num_rules': stats.num_rules,
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
    if stats.num_rules > 0:
        print(f"Custom rules:       {stats.num_rules}")
        print()
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


def compare_results(baseline_path: Path, experiment_path: Path):
    """Compare baseline and experiment results."""
    with open(baseline_path) as f:
        baseline = json.load(f)
    with open(experiment_path) as f:
        experiment = json.load(f)

    baseline_stats = baseline['statistics']
    experiment_stats = experiment['statistics']

    baseline_results = {r['name']: r for r in baseline['results']}
    experiment_results = {r['name']: r for r in experiment['results']}

    # Find differences
    newly_solved = []
    no_longer_solved = []

    for name in baseline_results:
        b_solved = baseline_results[name]['solved']
        e_solved = experiment_results[name]['solved']

        if not b_solved and e_solved:
            newly_solved.append(name)
        elif b_solved and not e_solved:
            no_longer_solved.append(name)

    print("\n" + "="*60)
    print("COMPARISON REPORT")
    print("="*60)
    print(f"Baseline:  {baseline_path.name}")
    print(f"           {baseline_stats['solved_count']}/{baseline_stats['total_problems']} solved ({100*baseline_stats['solved_count']/baseline_stats['total_problems']:.1f}%)")
    print(f"           Avg time: {baseline_stats['avg_total_time']:.4f}s")
    print()
    print(f"Experiment: {experiment_path.name}")
    print(f"           {experiment_stats['num_rules']} custom rules")
    print(f"           {experiment_stats['solved_count']}/{experiment_stats['total_problems']} solved ({100*experiment_stats['solved_count']/experiment_stats['total_problems']:.1f}%)")
    print(f"           Avg time: {experiment_stats['avg_total_time']:.4f}s")
    print()
    print("="*60)
    print("CHANGES")
    print("="*60)

    delta_solved = experiment_stats['solved_count'] - baseline_stats['solved_count']
    delta_time = experiment_stats['avg_total_time'] - baseline_stats['avg_total_time']

    print(f"Solved count:  {delta_solved:+d} ({experiment_stats['solved_count']} vs {baseline_stats['solved_count']})")
    print(f"Avg time:      {delta_time:+.4f}s ({experiment_stats['avg_total_time']:.4f}s vs {baseline_stats['avg_total_time']:.4f}s)")
    print()

    if newly_solved:
        print(f"Newly solved ({len(newly_solved)}):")
        for name in newly_solved[:10]:  # Show first 10
            print(f"  + {name}")
        if len(newly_solved) > 10:
            print(f"  ... and {len(newly_solved) - 10} more")
        print()

    if no_longer_solved:
        print(f"No longer solved ({len(no_longer_solved)}):")
        for name in no_longer_solved[:10]:  # Show first 10
            print(f"  - {name}")
        if len(no_longer_solved) > 10:
            print(f"  ... and {len(no_longer_solved) - 10} more")
        print()

    # Analysis
    print("="*60)
    print("ANALYSIS")
    print("="*60)

    if delta_solved > 0:
        print(f"✓ Rules are EFFECTIVE: +{delta_solved} problems solved")
    elif delta_solved == 0:
        print("○ Rules are NEUTRAL: no change in solved count")
    else:
        print(f"✗ Rules cause BLOCKING: {delta_solved} fewer problems solved")
        print("  This suggests the rules introduce invalid inference paths")

    if delta_time > 0.1:
        print(f"⚠ Rules add overhead: +{delta_time:.4f}s average time")
    elif delta_time < -0.1:
        print(f"✓ Rules improve speed: {delta_time:.4f}s average time")
    else:
        print("○ Rules have minimal time impact")

    print("="*60)


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark CSolver with custom rules support"
    )
    parser.add_argument(
        "--problems", "-p",
        type=Path,
        help="Path to benchmark file with coordinates"
    )
    parser.add_argument(
        "--rules", "-r",
        type=Path,
        help="Path to custom rules file"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
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
        help="Run directly without subprocess isolation"
    )
    parser.add_argument(
        "--compare", "-c",
        nargs=2,
        metavar=("BASELINE", "EXPERIMENT"),
        help="Compare two result files"
    )
    parser.add_argument(
        "--no-filter",
        action="store_true",
        help="Disable automatic filtering of generative rules"
    )

    args = parser.parse_args()

    # Compare mode
    if args.compare:
        baseline_path = Path(args.compare[0])
        experiment_path = Path(args.compare[1])

        if not baseline_path.exists():
            print(f"Error: Baseline file not found: {baseline_path}")
            sys.exit(1)
        if not experiment_path.exists():
            print(f"Error: Experiment file not found: {experiment_path}")
            sys.exit(1)

        compare_results(baseline_path, experiment_path)
        return

    # Benchmark mode
    if not args.problems:
        print("Error: --problems is required for benchmark mode")
        sys.exit(1)

    if not args.problems.exists():
        print(f"Error: Benchmark file not found: {args.problems}")
        sys.exit(1)

    # Load custom rules if provided
    custom_rules = None
    if args.rules:
        if not args.rules.exists():
            print(f"Error: Rules file not found: {args.rules}")
            sys.exit(1)
        custom_rules = parse_rules_file(args.rules)
        print(f"Loaded {len(custom_rules)} custom rules from {args.rules}")

        # Filter generative rules unless --no-filter is specified
        if not args.no_filter:
            safe_rules, blocked_rules = filter_generative_rules(custom_rules, verbose=not args.quiet)
            if blocked_rules:
                print(f"Filtered {len(blocked_rules)} generative rules (use --no-filter to disable):")
                for rule in blocked_rules:
                    print(f"  - {rule[:70]}{'...' if len(rule) > 70 else ''}")
            custom_rules = safe_rules
            print(f"Using {len(custom_rules)} rules after filtering")

    results, stats = run_benchmark(
        args.problems,
        custom_rules=custom_rules,
        timeout=args.timeout,
        max_level=args.max_level,
        verbose=not args.quiet,
        use_subprocess=not args.no_subprocess
    )

    print_summary(stats)

    if args.output:
        save_results(results, stats, args.output, args.problems, args.rules)
        print(f"\nResults saved to: {args.output}")


if __name__ == "__main__":
    main()
