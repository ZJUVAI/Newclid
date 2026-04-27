#!/usr/bin/env python3
"""
Evaluation pipeline for discovered geometric rules using CSolver (C++ DDAR).

Compares CSolver performance with and without extracted rules on benchmark problems.

Usage:
    # 1. Pre-compute CSolver baseline (default rules only)
    python scripts/evaluate_rules_csolver.py baseline \
        --output outputs/eval_baselines_csolver/

    # 2. Evaluate extracted rules against cached baseline
    python scripts/evaluate_rules_csolver.py evaluate \
        --rules outputs/experiments/.../extracted_rules.txt \
        --baseline-cache outputs/eval_baselines_csolver/ \
        --output outputs/experiments/.../eval/
"""

import argparse
import json
import math
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import ray
from ray.exceptions import TaskCancelledError, WorkerCrashedError

os.environ["RAY_memory_monitor_refresh_ms"] = "0"

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from newclid.formulations.rule import Rule

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent

BENCHMARKS: Dict[str, Path] = {
    "hageo_409": PROJECT_ROOT / "benchmarks" / "hageo_409.txt",
    "imo_30": PROJECT_ROOT / "benchmarks" / "imo_ag_30.txt",
    "imo_95": PROJECT_ROOT / "benchmarks" / "imo_95.txt",
    "jgex_231": PROJECT_ROOT / "benchmarks" / "jgex_ag_231.txt",
}

GENERATIVE_RULE_PATTERNS: Set[Tuple[str, str]] = {
    ("cyclic", "eqangle"),
}

# ---------------------------------------------------------------------------
# Problem loading
# ---------------------------------------------------------------------------


def load_problems(
    filepath: Path, skip_ids: Optional[Set[str]] = None
) -> List[Tuple[str, str]]:
    """Load problems from JGEX DSL format (alternating lines: problem_id, problem_text)."""
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

CHECK_INTERVAL = 30.0


def ensure_rule_usage_fields(result: dict) -> dict:
    """Normalize per-problem result shape with rule-usage fields."""
    normalized = dict(result)
    normalized.setdefault('custom_rules_ran', False)
    normalized.setdefault('used_rules', {})
    normalized.setdefault('used_rule_count', 0)
    normalized.setdefault('used_rule_steps', 0)
    normalized.setdefault('rule_usage_analyzed', False)
    normalized.setdefault('rule_usage_error', None)
    return normalized


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
            results.append(ensure_rule_usage_fields(result))
            if result['solved']:
                print(f"  ✓ {result['problem_id']} ({result['time']:.2f}s)")
            else:
                err_tag = f" [{result['error']}]" if result.get('error') else ""
                print(f"  ✗ {result['problem_id']}{err_tag}")

        if not done:
            elapsed = time.time() - batch_start
            if elapsed > timeout:
                for ref in list(remaining):
                    pid = ref_to_pid[ref]
                    print(f"  ⏰ Hard kill: {pid} (elapsed {elapsed:.0f}s > timeout {timeout}s)")
                    ray.cancel(ref, force=True)
                    results.append(ensure_rule_usage_fields({
                        'problem_id': pid, 'solved': False,
                        'time': elapsed, 'error': 'hard_timeout'
                    }))
                remaining = []

    return results


def compute_adaptive_timeout(baseline_results: list[dict]) -> Optional[dict]:
    """Compute adaptive timeout from baseline results."""
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
# Rule format conversion
# ---------------------------------------------------------------------------


def rule_to_pipe_format(rule_id: str, rule_text: str) -> str:
    """Convert JGEX DSL rule to CSolver pipe format.

    Input:  "cong a b c d, perp e f g h => para i j k l"
    Output: "rule_id|cong a b c d,perp e f g h|para i j k l"
    """
    if '=>' not in rule_text:
        return f"{rule_id}||"
    premise_part, conclusion_part = rule_text.split('=>', 1)
    premises = ','.join(p.strip() for p in premise_part.split(','))
    conclusions = ','.join(c.strip() for c in conclusion_part.split(','))
    return f"{rule_id}|{premises}|{conclusions}"


def load_rules_as_pipe(rules_path: Path) -> Tuple[List[str], List[str], int, int]:
    """Load rules from extracted_rules.txt and convert to pipe format.

    Returns: (pipe_rules_list, effective_rule_ids, total_loaded, filtered_count)
    """
    lines = rules_path.read_text(encoding='utf-8').strip().split('\n')
    rules_pipe = []
    effective_rule_ids = []
    filtered = 0
    for i in range(0, len(lines), 2):
        if i + 1 >= len(lines):
            break
        rule_id = lines[i].strip()
        rule_text = lines[i + 1].strip()
        if not rule_id or not rule_text:
            continue

        # Check generative rule patterns
        if '=>' in rule_text:
            premise_part, conclusion_part = rule_text.split('=>', 1)
            premise_preds = set()
            for p in premise_part.split(','):
                tokens = p.strip().split()
                if tokens:
                    premise_preds.add(tokens[0])
            conclusion_preds = set()
            for c in conclusion_part.split(','):
                tokens = c.strip().split()
                if tokens:
                    conclusion_preds.add(tokens[0])
            is_generative = False
            for prem_pat, concl_pat in GENERATIVE_RULE_PATTERNS:
                if prem_pat in premise_preds and concl_pat in conclusion_preds:
                    is_generative = True
                    break
            if is_generative:
                filtered += 1
                print(f"  Filtered generative rule: {rule_id} ({rule_text[:60]}...)")
                continue

        rules_pipe.append(rule_to_pipe_format(rule_id, rule_text))
        effective_rule_ids.append(rule_id)

    return rules_pipe, effective_rule_ids, len(rules_pipe) + filtered, filtered


def summarize_rule_usage(
    results: List[dict],
    effective_rule_ids: List[str],
) -> dict:
    """Aggregate benchmark-level custom rule usage statistics."""
    per_rule_usage: Counter[str] = Counter()
    solved_problems_analyzed = 0
    solved_problems_using_any_custom_rule = 0
    total_rule_applications = 0

    for result in results:
        if not result.get('solved'):
            continue
        if not result.get('custom_rules_ran'):
            continue
        if not result.get('rule_usage_analyzed'):
            continue

        solved_problems_analyzed += 1
        used_rules = result.get('used_rules', {})
        used_rule_steps = int(result.get('used_rule_steps', 0) or 0)
        if used_rules:
            solved_problems_using_any_custom_rule += 1
        total_rule_applications += used_rule_steps
        per_rule_usage.update({rid: int(count) for rid, count in used_rules.items()})

    rules_total_effective = len(effective_rule_ids)
    rules_used = sum(1 for rid in effective_rule_ids if per_rule_usage.get(rid, 0) > 0)
    rules_coverage = (rules_used / rules_total_effective) if rules_total_effective > 0 else 0.0

    order_index = {rid: idx for idx, rid in enumerate(effective_rule_ids)}
    heatmap_rule_order = sorted(
        effective_rule_ids,
        key=lambda rid: (-per_rule_usage.get(rid, 0), order_index[rid]),
    )

    top_rules = [
        {'rule_id': rid, 'count': int(per_rule_usage.get(rid, 0))}
        for rid in heatmap_rule_order[:20]
        if per_rule_usage.get(rid, 0) > 0
    ]
    unused_rules = [rid for rid in effective_rule_ids if per_rule_usage.get(rid, 0) == 0]

    return {
        'rules_total_effective': rules_total_effective,
        'rules_used': rules_used,
        'rules_coverage': round(rules_coverage, 6),
        'solved_problems_analyzed': solved_problems_analyzed,
        'solved_problems_using_any_custom_rule': solved_problems_using_any_custom_rule,
        'total_rule_applications': total_rule_applications,
        'per_rule_usage': {rid: int(per_rule_usage.get(rid, 0)) for rid in effective_rule_ids},
        'top_rules': top_rules,
        'unused_rules': unused_rules,
        'heatmap_rule_order': heatmap_rule_order,
    }


def prepare_rule_usage_heatmap_matrix(rule_usage_summary: dict) -> tuple[np.ndarray, int, int, float]:
    """Build heatmap matrix and metadata from a rule usage summary."""
    rule_order = rule_usage_summary['heatmap_rule_order']
    per_rule_usage = rule_usage_summary['per_rule_usage']
    n_rules = len(rule_order)

    if n_rules == 0:
        return np.full((1, 1), np.nan), 1, 1, 1.0

    cols = math.ceil(math.sqrt(n_rules))
    rows = math.ceil(n_rules / cols)
    values = [float(per_rule_usage.get(rid, 0)) for rid in rule_order]
    matrix = np.full((rows * cols,), np.nan)
    matrix[:n_rules] = values
    matrix = matrix.reshape(rows, cols)

    finite_values = np.array(values, dtype=float)
    vmax = float(finite_values.max()) if finite_values.size > 0 else 0.0
    if vmax <= 0:
        vmax = 1.0
    return matrix, rows, cols, vmax


def render_rule_usage_heatmap(
    ax,
    benchmark_name: str,
    rule_usage_summary: dict,
):
    """Render a rule usage heatmap on an existing matplotlib axis."""
    matrix, rows, cols, vmax = prepare_rule_usage_heatmap_matrix(rule_usage_summary)
    has_effective_rules = rule_usage_summary['rules_total_effective'] > 0

    cmap = mcolors.LinearSegmentedColormap.from_list(
        'white_to_red',
        ['#ffffff', '#fee5d9', '#fcae91', '#fb6a4a', '#de2d26', '#a50f15'],
        N=256,
    )
    cmap.set_bad(color='white')

    image = ax.imshow(matrix, cmap=cmap, vmin=0.0, vmax=vmax)

    if has_effective_rules:
        ax.set_xticks(np.arange(-0.5, cols, 1), minor=True)
        ax.set_yticks(np.arange(-0.5, rows, 1), minor=True)
        ax.grid(which='minor', color='#000000', linestyle='-', linewidth=0.25)
        ax.tick_params(which='minor', bottom=False, left=False)
        title = (
            f"{benchmark_name}\n"
            f"coverage={rule_usage_summary['rules_used']}/{rule_usage_summary['rules_total_effective']}"
            f" ({rule_usage_summary['rules_coverage']:.1%}), "
            f"applications={rule_usage_summary['total_rule_applications']}"
        )
    else:
        title = f"{benchmark_name}\nNo effective custom rules"

    ax.set_title(title)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    return image




def plot_rule_usage_heatmap(
    benchmark_name: str,
    rule_usage_summary: dict,
    output_path: Path,
) -> None:
    """Generate a fixed-size heatmap for one benchmark."""
    fig, ax = plt.subplots(figsize=(10, 10))
    image = render_rule_usage_heatmap(ax, benchmark_name, rule_usage_summary)
    cbar = fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label('Usage count')
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=200, bbox_inches='tight')
    plt.close(fig)


def plot_combined_rule_usage_heatmaps(
    benchmark_summaries: list[tuple[str, dict]],
    output_path: Path,
) -> None:
    """Generate a combined figure with one rule-usage subplot per benchmark."""
    n = len(benchmark_summaries)
    if n == 0:
        return

    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    fig, axes = plt.subplots(rows, cols, figsize=(8 * cols, 8 * rows), constrained_layout=True)
    axes = np.atleast_1d(axes).ravel()

    images = []
    for ax, (benchmark_name, summary) in zip(axes, benchmark_summaries):
        image = render_rule_usage_heatmap(ax, benchmark_name, summary)
        images.append(image)

    for ax in axes[len(benchmark_summaries):]:
        ax.axis('off')

    vmax = max(float(image.norm.vmax) for image in images) if images else 1.0
    shared_norm = plt.Normalize(vmin=0.0, vmax=vmax)
    for image in images:
        image.set_norm(shared_norm)

    cbar = fig.colorbar(images[0], ax=axes[:len(benchmark_summaries)].tolist(), fraction=0.025, pad=0.02)
    cbar.set_label('Usage count')
    fig.suptitle('Rule usage heatmaps by benchmark', fontsize=18)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=200, bbox_inches='tight')
    plt.close(fig)


# ---------------------------------------------------------------------------
# Rule filtering (for Rule objects)
# ---------------------------------------------------------------------------


def is_generative_rule(rule: Rule) -> bool:
    """Check if a rule matches a known inference-explosion pattern."""
    premise_preds = {p[0] for p in rule.premises}
    conclusion_preds = {c[0] for c in rule.conclusions}
    for prem_pat, concl_pat in GENERATIVE_RULE_PATTERNS:
        if prem_pat in premise_preds and concl_pat in conclusion_preds:
            return True
    return False


# ---------------------------------------------------------------------------
# CSolver wrapper
# ---------------------------------------------------------------------------


@ray.remote(max_retries=0)
def solve_single_problem_csolver(
    problem_id: str,
    problem_text: str,
    custom_rules_pipe: Optional[List[str]],
    custom_rule_ids: Optional[List[str]],
    timeout: int,
    seed: int,
    engine: str = "full",
) -> dict:
    """Solve a single problem with CSolver, optionally with custom rules."""
    try:
        from newclid.api import CSolver

        use_log = True
        use_exp = True

        csolver = CSolver(
            problem=problem_text,
            problem_name=problem_id,
            seed=seed,
            using_log=use_log,
            using_exp=use_exp,
            engine=engine,
        )

        start = time.time()
        solved = csolver.run(custom_rules=custom_rules_pipe)
        elapsed = time.time() - start

        used_rules: Dict[str, int] = {}
        used_rule_count = 0
        used_rule_steps = 0
        rule_usage_analyzed = False
        rule_usage_error = None

        if solved and custom_rules_pipe and custom_rule_ids:
            try:
                used_rules = csolver.get_proof_rule_usage(set(custom_rule_ids))
                used_rule_count = len(used_rules)
                used_rule_steps = sum(used_rules.values())
                rule_usage_analyzed = True
            except Exception as e:
                rule_usage_error = str(e)

        return {
            'problem_id': problem_id,
            'solved': solved,
            'time': elapsed,
            'error': None,
            'custom_rules_ran': bool(custom_rules_pipe),
            'used_rules': used_rules,
            'used_rule_count': used_rule_count,
            'used_rule_steps': used_rule_steps,
            'rule_usage_analyzed': rule_usage_analyzed,
            'rule_usage_error': rule_usage_error,
        }
    except Exception as e:
        return {
            'problem_id': problem_id,
            'solved': False,
            'time': 0.0,
            'error': str(e),
            'custom_rules_ran': bool(custom_rules_pipe),
            'used_rules': {},
            'used_rule_count': 0,
            'used_rule_steps': 0,
            'rule_usage_analyzed': False,
            'rule_usage_error': None,
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
    engine: str = "full",
) -> None:
    """Run CSolver with default rules on each benchmark and cache results."""
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_rows = []
    for name in benchmark_names:
        bench_path = BENCHMARKS[name]
        print(f"\n{'='*60}")
        print(f"CSolver Baseline: {name} ({bench_path})")
        print(f"{'='*60}")

        problems = load_problems(bench_path, skip_ids=skip_ids)
        print(f"Loaded {len(problems)} problems")

        ref_to_pid = {}
        refs = []
        for pid, ptext in problems:
            ref = solve_single_problem_csolver.remote(pid, ptext, None, None, timeout, 42, engine)
            refs.append(ref)
            ref_to_pid[ref] = pid

        results = collect_results_with_hard_timeout(refs, ref_to_pid, timeout, label=name)
        solved_count = sum(1 for r in results if r['solved'])

        total = len(problems)
        solve_rate = solved_count / total if total > 0 else 0.0

        timing_stats = compute_adaptive_timeout(results)

        cache = {
            'benchmark': name,
            'solver': f'csolver_{engine}',
            'total': total,
            'solved': solved_count,
            'solve_rate': round(solve_rate, 4),
            'timeout': timeout,
            'timestamp': datetime.now().isoformat(),
            'timing_stats': timing_stats,
            'results': sorted(results, key=lambda r: r['problem_id']),
        }
        cache_path = output_dir / f"{name}_baseline.json"
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)

        print(f"\n{name}: {solved_count}/{total} ({solve_rate:.1%})")
        print(f"Cached to {cache_path}")
        if timing_stats:
            print(f"Timing: max={timing_stats['max_solved_time']:.2f}s, "
                  f"avg={timing_stats['avg_solved_time']:.2f}s, "
                  f"adaptive_timeout={timing_stats['adaptive_timeout']:.2f}s")

        summary_rows.append({
            'benchmark': name, 'total': total, 'solved': solved_count,
            'solve_rate': f"{solve_rate:.1%}",
        })

    print(f"\n{'='*60}")
    print("CSolver Baseline Summary")
    print(f"{'='*60}")
    for row in summary_rows:
        print(f"  {row['benchmark']}: {row['solved']}/{row['total']} ({row['solve_rate']})")


# ---------------------------------------------------------------------------
# Evaluate
# ---------------------------------------------------------------------------


def run_evaluate(
    rules_path: Path,
    baseline_cache_dir: Path,
    output_dir: Path,
    benchmark_names: List[str],
    workers: int,
    timeout: int,
    skip_ids: Optional[Set[str]] = None,
    skip_baseline_solved: bool = False,
    engine: str = "full",
) -> None:
    """Evaluate extracted rules using CSolver against cached baseline."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load rules in pipe format
    rules_pipe, effective_rule_ids, total_loaded, filtered_count = load_rules_as_pipe(rules_path)
    print(f"Loaded {total_loaded} rules, filtered {filtered_count} generative, using {len(rules_pipe)}")

    summary_rows = []
    benchmark_heatmap_summaries: list[tuple[str, dict]] = []
    for name in benchmark_names:
        bench_path = BENCHMARKS[name]
        print(f"\n{'='*60}")
        print(f"CSolver Evaluate: {name}")
        print(f"{'='*60}")

        # Load baseline
        baseline_path = baseline_cache_dir / f"{name}_baseline.json"
        if not baseline_path.exists():
            print(f"  ⚠ No baseline cache for {name}, skipping")
            continue
        with open(baseline_path, encoding='utf-8') as f:
            baseline = json.load(f)

        baseline_results = {r['problem_id']: r for r in baseline['results']}
        baseline_solved = {pid for pid, r in baseline_results.items() if r['solved']}
        print(f"  Baseline: {len(baseline_solved)}/{baseline['total']} solved")

        # Load problems
        problems = load_problems(bench_path, skip_ids=skip_ids)

        # Optionally skip baseline-solved problems
        if skip_baseline_solved:
            problems_to_run = [(pid, pt) for pid, pt in problems if pid not in baseline_solved]
            print(f"  Running {len(problems_to_run)} unsolved problems (skipping {len(baseline_solved)} baseline-solved)")
        else:
            problems_to_run = problems
            print(f"  Running all {len(problems_to_run)} problems")

        # Run with custom rules
        ref_to_pid = {}
        refs = []
        for pid, ptext in problems_to_run:
            ref = solve_single_problem_csolver.remote(
                pid,
                ptext,
                rules_pipe,
                effective_rule_ids,
                timeout,
                42,
                engine,
            )
            refs.append(ref)
            ref_to_pid[ref] = pid

        aug_results_list = collect_results_with_hard_timeout(refs, ref_to_pid, timeout, label=name)

        # Merge with baseline results for skipped problems
        aug_results = {}
        if skip_baseline_solved:
            for pid in baseline_solved:
                if pid in baseline_results:
                    merged_result = baseline_results[pid].copy()
                    merged_result.update({
                        'custom_rules_ran': False,
                        'used_rules': {},
                        'used_rule_count': 0,
                        'used_rule_steps': 0,
                        'rule_usage_analyzed': False,
                        'rule_usage_error': None,
                    })
                    aug_results[pid] = merged_result
        for r in aug_results_list:
            aug_results[r['problem_id']] = r

        aug_solved = {pid for pid, r in aug_results.items() if r['solved']}
        new_solved = aug_solved - baseline_solved
        regressed = baseline_solved - aug_solved

        total = baseline['total']
        print(f"\n  Results: {len(aug_solved)}/{total} ({len(aug_solved)/total:.1%})")
        print(f"  Baseline: {len(baseline_solved)}/{total} ({len(baseline_solved)/total:.1%})")
        print(f"  New solved: {len(new_solved)}")
        if new_solved:
            for pid in sorted(new_solved):
                t = aug_results[pid].get('time', 0)
                print(f"    + {pid} ({t:.2f}s)")
        print(f"  Regressed: {len(regressed)}")
        if regressed:
            for pid in sorted(regressed):
                print(f"    - {pid}")

        benchmark_results = sorted(
            [r for r in aug_results.values()],
            key=lambda r: r['problem_id']
        )
        rule_usage_summary = summarize_rule_usage(benchmark_results, effective_rule_ids)
        heatmap_filename = f"{name}_rule_usage_heatmap.png"
        heatmap_path = output_dir / heatmap_filename
        plot_rule_usage_heatmap(name, rule_usage_summary, heatmap_path)

        # Save evaluation results
        eval_data = {
            'benchmark': name,
            'solver': 'csolver',
            'rules_file': str(rules_path),
            'rules_count': len(rules_pipe),
            'rules_filtered': filtered_count,
            'rule_ids_effective': effective_rule_ids,
            'baseline_solved': len(baseline_solved),
            'augmented_solved': len(aug_solved),
            'total': total,
            'new_solved': sorted(new_solved),
            'regressed': sorted(regressed),
            'net_improvement': len(new_solved) - len(regressed),
            'timestamp': datetime.now().isoformat(),
            'rule_usage_summary': rule_usage_summary,
            'rule_usage_heatmap': str(heatmap_path),
            'results': benchmark_results,
        }
        eval_path = output_dir / f"{name}_eval.json"
        with open(eval_path, 'w', encoding='utf-8') as f:
            json.dump(eval_data, f, ensure_ascii=False, indent=2)

        print(
            f"  Rule usage: analyzed={rule_usage_summary['solved_problems_analyzed']}, "
            f"coverage={rule_usage_summary['rules_used']}/{rule_usage_summary['rules_total_effective']} "
            f"({rule_usage_summary['rules_coverage']:.1%}), "
            f"applications={rule_usage_summary['total_rule_applications']}"
        )
        print(f"  Heatmap: {heatmap_path}")

        benchmark_heatmap_summaries.append((name, rule_usage_summary))

        summary_rows.append({
            'benchmark': name,
            'baseline': f"{len(baseline_solved)}/{total}",
            'augmented': f"{len(aug_solved)}/{total}",
            'new': len(new_solved),
            'regressed': len(regressed),
            'net': len(new_solved) - len(regressed),
            'coverage': rule_usage_summary['rules_coverage'],
        })

    if len(benchmark_heatmap_summaries) > 1:
        combined_heatmap_path = output_dir / "combined_rule_usage_heatmaps.png"
        plot_combined_rule_usage_heatmaps(benchmark_heatmap_summaries, combined_heatmap_path)
        print(f"Combined heatmap: {combined_heatmap_path}")

    # Print summary
    print(f"\n{'='*60}")
    print("CSolver Evaluation Summary")
    print(f"{'='*60}")
    total_new = 0
    total_reg = 0
    for row in summary_rows:
        print(f"  {row['benchmark']}: {row['baseline']} → {row['augmented']} "
              f"(+{row['new']}, -{row['regressed']}, net={row['net']}, "
              f"rule_coverage={row['coverage']:.1%})")
        total_new += row['new']
        total_reg += row['regressed']
    print(f"  Total: +{total_new} new, -{total_reg} regressed, net={total_new - total_reg}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate discovered rules using CSolver (C++ DDAR)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # baseline
    bp = sub.add_parser("baseline", help="Compute CSolver baseline")
    bp.add_argument("--output", type=Path, required=True)
    bp.add_argument("--benchmarks", type=str, default="imo_30,imo_95,hageo_409,jgex_231")
    bp.add_argument("--workers", type=int, default=30)
    bp.add_argument("--timeout", type=int, default=600)
    bp.add_argument("--skip", type=Path, default=None, help="File with problem IDs to skip")
    bp.add_argument("--engine", type=str, default="full", choices=["full", "weak"],
                    help="DDAR engine variant (default: full)")

    # evaluate
    ep = sub.add_parser("evaluate", help="Evaluate rules with CSolver")
    ep.add_argument("--rules", type=Path, required=True)
    ep.add_argument("--baseline-cache", type=Path, required=True)
    ep.add_argument("--output", type=Path, required=True)
    ep.add_argument("--benchmarks", type=str, default="imo_30,imo_95,hageo_409,jgex_231")
    ep.add_argument("--workers", type=int, default=30)
    ep.add_argument("--timeout", type=int, default=600)
    ep.add_argument("--skip", type=Path, default=None, help="File with problem IDs to skip")
    ep.add_argument("--skip-baseline-solved", action="store_true",
                    help="Skip problems already solved by baseline")
    ep.add_argument("--engine", type=str, default="full", choices=["full", "weak"],
                    help="DDAR engine variant (default: full)")

    args = parser.parse_args()

    names = [n.strip() for n in args.benchmarks.split(",")]
    for n in names:
        if n not in BENCHMARKS:
            print(f"Unknown benchmark: {n}")
            print(f"Available: {', '.join(BENCHMARKS.keys())}")
            sys.exit(1)

    skip_ids = None
    if args.skip and args.skip.exists():
        skip_ids = {
            line.strip()
            for line in args.skip.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        }
        print(f"Skip list: {len(skip_ids)} problem IDs loaded from {args.skip}")

    if args.command == "baseline":
        ray.init(num_cpus=args.workers)
        try:
            run_baseline(args.output, names, args.workers, args.timeout, skip_ids=skip_ids, engine=args.engine)
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
                engine=args.engine,
            )
        finally:
            ray.shutdown()


if __name__ == "__main__":
    main()
