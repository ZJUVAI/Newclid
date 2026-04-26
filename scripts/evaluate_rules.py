#!/usr/bin/env python3
"""
Evaluation pipeline for discovered geometric rules.

Compares solver performance with and without extracted rules on benchmark problems.
Uses JGEX DSL format benchmarks and GeometricSolverBuilder API.

Usage:
    # 1. Pre-compute baseline (default rules only)
    python scripts/evaluate_rules.py baseline \
        --output outputs/eval_baselines/

    # 2. Evaluate extracted rules against cached baseline
    python scripts/evaluate_rules.py evaluate \
        --rules outputs/experiments/.../basis_rules.txt \
        --baseline-cache outputs/eval_baselines/ \
        --output outputs/experiments/.../eval/

    # 3. Optional flags
        --benchmarks hageo_409,imo_95,jgex_ag_231
        --workers 50
        --timeout 3600
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import os

import ray
from ray.exceptions import TaskCancelledError, WorkerCrashedError

# Disable Ray's OOM killer to prevent infinite OOM retries
os.environ["RAY_memory_monitor_refresh_ms"] = "0"

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from newclid import GeometricSolverBuilder
from newclid.formulations.rule import Rule

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent

BENCHMARKS: Dict[str, Path] = {
    "hageo_409": PROJECT_ROOT / "benchmarks" / "hageo_409.txt",
    "imo_95": PROJECT_ROOT / "benchmarks" / "imo_95.txt",
    "jgex_ag_231": PROJECT_ROOT / "benchmarks" / "jgex_ag_231.txt",
}

# Patterns of (premise_pred, conclusion_pred) that cause inference explosion
GENERATIVE_RULE_PATTERNS: Set[Tuple[str, str]] = {
    ("cyclic", "eqangle"),
}

# ---------------------------------------------------------------------------
# Problem loading (JGEX DSL format)
# ---------------------------------------------------------------------------


def load_problems(
    filepath: Path, skip_ids: Optional[Set[str]] = None
) -> List[Tuple[str, str]]:
    """Load problems from JGEX DSL format (alternating lines: problem_id, problem_text).

    If *skip_ids* is provided, problems whose id is in the set are silently skipped.
    """
    lines = filepath.read_text(encoding='utf-8').strip().split('\n')
    problems = []
    skipped = 0
    for i in range(0, len(lines), 2):
        if i + 1 < len(lines):
            problem_id = lines[i].strip()
            problem_text = lines[i + 1].strip()
            if problem_id and problem_text:
                if skip_ids and problem_id in skip_ids:
                    skipped += 1
                    continue
                problems.append((problem_id, problem_text))
    if skipped:
        print(f"Skipped {skipped} problems from skip list")
    return problems


# ---------------------------------------------------------------------------
# Result collection with hard timeout
# ---------------------------------------------------------------------------

CHECK_INTERVAL = 30.0  # seconds between timeout checks


def collect_results_with_hard_timeout(
    refs: list,
    ref_to_pid: dict,
    timeout: int,
    label: str = "",
) -> list[dict]:
    """Collect Ray task results with hard kill for timed-out tasks."""
    results = []
    remaining = list(refs)
    batch_start = time.time()

    while remaining:
        done, remaining = ray.wait(remaining, num_returns=1, timeout=CHECK_INTERVAL)

        # Process completed tasks
        for ref in done:
            pid = ref_to_pid[ref]
            try:
                result = ray.get(ref)
            except (TaskCancelledError, WorkerCrashedError) as e:
                result = {'problem_id': pid, 'solved': False, 'time': 0.0,
                          'error': f'worker killed: {e}'}
            except Exception as e:
                result = {'problem_id': pid, 'solved': False, 'time': 0.0,
                          'error': f'worker crashed: {e}'}
            results.append(result)
            if result['solved']:
                print(f"  ✓ {result['problem_id']} ({result['time']:.2f}s)")
            else:
                err_tag = f" [{result['error']}]" if result.get('error') else ""
                print(f"  ✗ {result['problem_id']}{err_tag}")

        # Check for timed-out tasks and hard kill
        if not done:
            elapsed = time.time() - batch_start
            if elapsed > timeout:
                for ref in list(remaining):
                    pid = ref_to_pid[ref]
                    print(f"  ⏰ Hard kill: {pid} (elapsed {elapsed:.0f}s > timeout {timeout}s)")
                    ray.cancel(ref, force=True)
                    results.append({
                        'problem_id': pid, 'solved': False,
                        'time': elapsed, 'error': 'hard_timeout'
                    })
                remaining = []

    return results


def compute_adaptive_timeout(baseline_results: list[dict]) -> Optional[dict]:
    """Compute adaptive timeout from baseline results.

    Returns {max_solved_time, avg_solved_time, adaptive_timeout, solved_count} or None.
    """
    solved_times = [r['time'] for r in baseline_results if r.get('solved')]
    if not solved_times:
        return None
    max_t = max(solved_times)
    avg_t = sum(solved_times) / len(solved_times)
    return {
        'max_solved_time': round(max_t, 2),
        'avg_solved_time': round(avg_t, 2),
        'adaptive_timeout': round(max_t * 3, 2),
        'solved_count': len(solved_times),
    }


# ---------------------------------------------------------------------------
# Rule filtering
# ---------------------------------------------------------------------------


def is_generative_rule(rule: Rule) -> bool:
    """Check if a rule matches a known inference-explosion pattern."""
    premise_preds = {p[0] for p in rule.premises}
    conclusion_preds = {c[0] for c in rule.conclusions}
    for prem_pat, concl_pat in GENERATIVE_RULE_PATTERNS:
        if prem_pat in premise_preds and concl_pat in conclusion_preds:
            return True
    return False


def filter_generative_rules(
    rules: List[Rule], verbose: bool = False
) -> Tuple[List[Rule], List[Rule]]:
    """Separate rules into safe and blocked (generative) lists."""
    safe, blocked = [], []
    for r in rules:
        if is_generative_rule(r):
            blocked.append(r)
        else:
            safe.append(r)
    if verbose and blocked:
        print(f"Filtered {len(blocked)} generative rules:")
        for r in blocked:
            rule_str = str(r)
            print(f"  - {rule_str[:80]}{'...' if len(rule_str) > 80 else ''}")
    return safe, blocked


def rule_to_dsl(rule: Rule) -> str:
    """Serialize a Rule back to JGEX DSL text: 'pred a b c, pred2 d e => pred3 f g'."""
    def clause(c: tuple) -> str:
        return " ".join(c)
    lhs = ", ".join(clause(p) for p in rule.premises)
    rhs = ", ".join(clause(c) for c in rule.conclusions)
    return f"{lhs} => {rhs}"


def rules_to_text(rules: List[Rule]) -> str:
    """Convert list of Rule objects to JGEX DSL text for append_rules_from_txt."""
    lines = []
    for i, rule in enumerate(rules):
        lines.append(f"extracted_{i:04d}")
        lines.append(rule_to_dsl(rule))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Solver wrapper
# ---------------------------------------------------------------------------


@ray.remote(max_retries=0)
def solve_single_problem(
    problem_id: str,
    problem_text: str,
    rules_text: Optional[str],
    timeout: int,
    seed: int
) -> dict:
    """Solve a single problem with optional custom rules."""
    try:
        builder = GeometricSolverBuilder(seed=seed)
        builder.load_problem_from_txt(problem_text)

        if rules_text:
            builder.append_rules_from_txt(rules_text)

        solver = builder.build(max_attempts=100)

        start = time.time()
        solved = solver.run(timeout=timeout)
        elapsed = time.time() - start

        return {
            'problem_id': problem_id,
            'solved': solved,
            'time': elapsed,
            'error': None
        }
    except Exception as e:
        return {
            'problem_id': problem_id,
            'solved': False,
            'time': 0.0,
            'error': str(e)
        }


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------


def run_baseline(
    output_dir: Path,
    benchmark_names: List[str],
    workers: int,
    timeout: int,
    skip_ids: Optional[Set[str]] = None,
) -> None:
    """Run solver with default rules on each benchmark and cache results."""
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_rows = []
    for name in benchmark_names:
        bench_path = BENCHMARKS[name]
        print(f"\n{'='*60}")
        print(f"Baseline: {name} ({bench_path})")
        print(f"{'='*60}")

        problems = load_problems(bench_path, skip_ids=skip_ids)
        print(f"Loaded {len(problems)} problems")

        ref_to_pid = {}
        refs = []
        for pid, ptext in problems:
            ref = solve_single_problem.remote(pid, ptext, None, timeout, 42)
            refs.append(ref)
            ref_to_pid[ref] = pid

        results = collect_results_with_hard_timeout(refs, ref_to_pid, timeout, label=name)
        solved_count = sum(1 for r in results if r['solved'])

        total = len(problems)
        solve_rate = solved_count / total if total > 0 else 0.0

        # Compute adaptive timeout
        timing_stats = compute_adaptive_timeout(results)
        if timing_stats:
            print(f"Timing stats: avg={timing_stats['avg_solved_time']:.2f}s, "
                  f"max={timing_stats['max_solved_time']:.2f}s, "
                  f"adaptive_timeout={timing_stats['adaptive_timeout']:.2f}s")

        # Save results
        output_data = {
            'total': total,
            'solved': solved_count,
            'solve_rate': solve_rate,
            'timing_stats': timing_stats,
            'results': results
        }

        out_path = output_dir / f"{name}_baseline.json"
        with open(out_path, "w") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"Saved: {out_path}")

        summary_rows.append((name, total, solved_count, solve_rate))

    # Print summary table
    print(f"\n{'='*50}")
    print("Baseline Summary")
    print(f"{'='*50}")
    print(f"{'Benchmark':<20} {'Solved':>12} {'Rate':>8}")
    print("-" * 42)
    total_all, solved_all = 0, 0
    for name, total, solved, rate in summary_rows:
        print(f"{name:<20} {solved:>4}/{total:<4}     {rate:>6.1%}")
        total_all += total
        solved_all += solved
    print("-" * 42)
    rate_all = solved_all / total_all if total_all > 0 else 0.0
    print(f"{'Total':<20} {solved_all:>4}/{total_all:<4}     {rate_all:>6.1%}")


# ---------------------------------------------------------------------------
# Evaluate
# ---------------------------------------------------------------------------


def load_baseline(cache_dir: Path, benchmark_name: str) -> Optional[dict]:
    """Load cached baseline JSON for a benchmark."""
    path = cache_dir / f"{benchmark_name}_baseline.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def build_solved_set(result: dict) -> set:
    """Extract set of solved problem_ids from a batch result dict."""
    return {
        r["problem_id"]
        for r in result.get("results", [])
        if r.get("solved")
    }


def run_evaluate(
    rules_path: Path,
    baseline_cache_dir: Optional[Path],
    output_dir: Path,
    benchmark_names: List[str],
    workers: int,
    timeout: int,
    skip_ids: Optional[Set[str]] = None,
    skip_baseline_solved: bool = True,
) -> None:
    """Evaluate extracted rules against baseline on each benchmark."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Parse and filter extracted rules
    print(f"Loading rules from {rules_path}")
    rules = Rule.parse_txt_file(rules_path)
    print(f"Loaded {len(rules)} rules")

    safe_rules, blocked_rules = filter_generative_rules(rules, verbose=True)
    if blocked_rules:
        print(f"Using {len(safe_rules)} rules after filtering")
    rules_count = len(safe_rules)

    # Convert to text format
    rules_text = rules_to_text(safe_rules)

    report: Dict = {
        "timestamp": datetime.now().isoformat(),
        "rules_file": str(rules_path),
        "rules_count": rules_count,
        "filtered_rules_count": len(blocked_rules),
        "benchmarks": {},
        "summary": {},
    }

    table_rows = []

    for name in benchmark_names:
        bench_path = BENCHMARKS[name]

        # --- Baseline ---
        baseline_result = None
        if baseline_cache_dir:
            baseline_result = load_baseline(baseline_cache_dir, name)
            if baseline_result:
                print(f"\nLoaded cached baseline for {name}")

        if baseline_result is None:
            print(f"\n{'='*60}")
            print(f"Running baseline for {name} (no cache found)")
            print(f"{'='*60}")

            problems = load_problems(bench_path, skip_ids=skip_ids)

            ref_to_pid = {}
            refs = []
            for pid, ptext in problems:
                ref = solve_single_problem.remote(pid, ptext, None, timeout, 42)
                refs.append(ref)
                ref_to_pid[ref] = pid

            results = collect_results_with_hard_timeout(refs, ref_to_pid, timeout, label=name)
            solved_count = sum(1 for r in results if r['solved'])

            baseline_result = {
                'total': len(problems),
                'solved': solved_count,
                'solve_rate': solved_count / len(problems) if problems else 0.0,
                'results': results
            }

        # --- Augmented ---
        print(f"\n{'='*60}")
        print(f"Augmented: {name} ({bench_path})")
        print(f"{'='*60}")

        # Determine which problems to run
        all_problems = load_problems(bench_path, skip_ids=skip_ids)
        baseline_solved_ids = set()
        if skip_baseline_solved and baseline_result:
            baseline_solved_ids = build_solved_set(baseline_result)
            problems_to_run = [(pid, pt) for pid, pt in all_problems if pid not in baseline_solved_ids]
            skipped_from_baseline = len(all_problems) - len(problems_to_run)
            print(f"Loaded {len(all_problems)} problems, skipping {skipped_from_baseline} baseline-solved")
        else:
            problems_to_run = all_problems
            skipped_from_baseline = 0
            print(f"Loaded {len(all_problems)} problems")

        # Run augmented solver on remaining problems
        ref_to_pid = {}
        refs = []
        for pid, ptext in problems_to_run:
            ref = solve_single_problem.remote(pid, ptext, rules_text, timeout, 42)
            refs.append(ref)
            ref_to_pid[ref] = pid

        results = collect_results_with_hard_timeout(refs, ref_to_pid, timeout, label=name)

        # Merge skipped problems from baseline cache
        if skipped_from_baseline > 0:
            baseline_results_by_id = {r['problem_id']: r for r in baseline_result['results']}
            for pid in baseline_solved_ids:
                if pid in baseline_results_by_id:
                    merged = dict(baseline_results_by_id[pid])
                    merged['source'] = 'baseline_cache'
                    results.append(merged)

        solved_count = sum(1 for r in results if r['solved'])
        hard_timeout_count = sum(1 for r in results if r.get('error') == 'hard_timeout')

        augmented_result = {
            'total': len(all_problems),
            'solved': solved_count,
            'solve_rate': solved_count / len(all_problems) if all_problems else 0.0,
            'results': results
        }

        # Save augmented result
        aug_path = output_dir / f"{name}_with_rules.json"
        with open(aug_path, "w") as f:
            json.dump(augmented_result, f, indent=2, ensure_ascii=False)

        # Compare
        b_total = baseline_result["total"]
        b_solved = baseline_result["solved"]
        a_total = augmented_result["total"]
        a_solved = augmented_result["solved"]
        b_rate = b_solved / b_total if b_total > 0 else 0.0
        a_rate = a_solved / a_total if a_total > 0 else 0.0

        baseline_solved_set = build_solved_set(baseline_result)
        augmented_solved_set = build_solved_set(augmented_result)
        new_solved = sorted(augmented_solved_set - baseline_solved_set)
        regressed = sorted(baseline_solved_set - augmented_solved_set)

        report["benchmarks"][name] = {
            "baseline": {"total": b_total, "solved": b_solved, "rate": round(b_rate, 4)},
            "augmented": {"total": a_total, "solved": a_solved, "rate": round(a_rate, 4)},
            "delta": {
                "solved": a_solved - b_solved,
                "rate_diff": round(a_rate - b_rate, 4),
            },
            "new_solved": new_solved,
            "regressed": regressed,
            "skipped_baseline_solved": skipped_from_baseline,
            "timeout_used": timeout,
            "hard_timeouts": hard_timeout_count,
        }

        table_rows.append((name, b_total, b_solved, a_solved))

    # Summary
    total_b_solved = sum(r["baseline"]["solved"] for r in report["benchmarks"].values())
    total_a_solved = sum(r["augmented"]["solved"] for r in report["benchmarks"].values())
    total_problems = sum(r["baseline"]["total"] for r in report["benchmarks"].values())
    total_new = sum(len(r["new_solved"]) for r in report["benchmarks"].values())
    total_regressed = sum(len(r["regressed"]) for r in report["benchmarks"].values())

    report["summary"] = {
        "total_baseline_solved": total_b_solved,
        "total_augmented_solved": total_a_solved,
        "total_problems": total_problems,
        "total_delta": total_a_solved - total_b_solved,
        "total_new_solved": total_new,
        "total_regressed": total_regressed,
        "net_improvement": total_a_solved > total_b_solved,
    }

    # Save report
    report_path = output_dir / "evaluation_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nReport saved: {report_path}")

    # Print comparison table
    print(f"\n{'='*55}")
    print("Evaluation Report")
    print(f"{'='*55}")
    print(f"Rules: {rules_count} extracted rules from {rules_path}")
    if blocked_rules:
        print(f"       ({len(blocked_rules)} generative rules filtered)")
    print()
    print(f"{'Benchmark':<20} {'Baseline':>10} {'Augmented':>10} {'Delta':>12}")
    print("-" * 55)
    total_b, total_a, total_t = 0, 0, 0
    for name, t, b, a in table_rows:
        delta = a - b
        rate_diff = (a - b) / t * 100 if t > 0 else 0.0
        sign = "+" if delta >= 0 else ""
        print(f"{name:<20} {b:>4}/{t:<4}   {a:>4}/{t:<4}   {sign}{delta:<3} ({sign}{rate_diff:.1f}%)")
        total_b += b
        total_a += a
        total_t += t
    print("-" * 55)
    total_delta = total_a - total_b
    total_rate_diff = (total_a - total_b) / total_t * 100 if total_t > 0 else 0.0
    sign = "+" if total_delta >= 0 else ""
    print(f"{'Total':<20} {total_b:>4}/{total_t:<4}   {total_a:>4}/{total_t:<4}   {sign}{total_delta:<3} ({sign}{total_rate_diff:.1f}%)")
    print()
    print(f"New solved: {total_new} problems")
    print(f"Regressed:  {total_regressed} problems (net: {sign}{total_delta})")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate discovered geometric rules on benchmarks"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- baseline ---
    p_base = subparsers.add_parser("baseline", help="Pre-compute baseline results")
    p_base.add_argument("--output", type=Path, required=True, help="Output directory for baseline JSONs")
    p_base.add_argument("--benchmarks", type=str, default=None, help="Comma-separated benchmark names (default: all)")
    p_base.add_argument("--workers", type=int, default=30, help="Parallel workers (default: 30)")
    p_base.add_argument("--timeout", type=int, default=3600, help="Per-problem timeout in seconds (default: 3600)")
    p_base.add_argument("--skip", type=Path, default=None, help="File with problem IDs to skip (one per line)")

    # --- evaluate ---
    p_eval = subparsers.add_parser("evaluate", help="Evaluate extracted rules against baseline")
    p_eval.add_argument("--rules", type=Path, required=True, help="Extracted rules file")
    p_eval.add_argument("--baseline-cache", type=Path, default=None, help="Directory with cached baseline JSONs")
    p_eval.add_argument("--output", type=Path, required=True, help="Output directory for evaluation results")
    p_eval.add_argument("--benchmarks", type=str, default=None, help="Comma-separated benchmark names (default: all)")
    p_eval.add_argument("--workers", type=int, default=30, help="Parallel workers (default: 30)")
    p_eval.add_argument("--timeout", type=int, default=600, help="Per-problem timeout in seconds (default: 600)")
    p_eval.add_argument("--skip", type=Path, default=None, help="File with problem IDs to skip (one per line)")
    p_eval.add_argument(
        "--skip-baseline-solved",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip problems already solved by baseline (default: True)"
    )

    args = parser.parse_args()

    # Resolve benchmark list
    if args.benchmarks:
        names = [n.strip() for n in args.benchmarks.split(",")]
        for n in names:
            if n not in BENCHMARKS:
                print(f"Error: unknown benchmark '{n}'. Available: {', '.join(BENCHMARKS)}")
                sys.exit(1)
    else:
        names = list(BENCHMARKS.keys())

    # Load skip list
    skip_ids: Optional[Set[str]] = None
    if args.skip:
        if not args.skip.exists():
            print(f"Error: skip file not found: {args.skip}")
            sys.exit(1)
        skip_ids = {
            line.strip()
            for line in args.skip.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        }
        print(f"Skip list: {len(skip_ids)} problem IDs loaded from {args.skip}")

    if args.command == "baseline":
        ray.init(num_cpus=args.workers)
        try:
            run_baseline(args.output, names, args.workers, args.timeout, skip_ids=skip_ids)
        finally:
            ray.shutdown()

    elif args.command == "evaluate":
        if not args.rules.exists():
            print(f"Error: rules file not found: {args.rules}")
            sys.exit(1)
        ray.init(num_cpus=args.workers)
        try:
            run_evaluate(
                args.rules,
                args.baseline_cache,
                args.output,
                names,
                args.workers,
                args.timeout,
                skip_ids=skip_ids,
                skip_baseline_solved=args.skip_baseline_solved,
            )
        finally:
            ray.shutdown()


if __name__ == "__main__":
    main()
