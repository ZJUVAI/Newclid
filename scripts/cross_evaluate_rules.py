#!/usr/bin/env python3
"""
Cross Rule-Set Comparison Pipeline.

Evaluates capability differences between two rule sets by cross-solving:
  - Direction 1: rules_A solves problems derived from data_B
  - Direction 2: rules_B solves problems derived from data_A

Usage:
    python scripts/cross_evaluate_rules.py \
        --rules-a outputs/.../rA/extracted_rules.txt \
        --data-a  outputs/.../dA/geometry_clauses15_samples.jsonl \
        --rules-b outputs/.../rB/extracted_rules.txt \
        --data-b  outputs/.../dB/geometry_clauses15_samples.jsonl \
        --output  outputs/experiments/YYYYMMDD_XX_cross_eval/ \
        --engine  full \
        --timeout 600 \
        --workers 30
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

import os

os.environ["RAY_memory_monitor_refresh_ms"] = "0"

import ray

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.evaluate_rules_csolver import (
    collect_results_with_hard_timeout,
    load_rules_as_pipe,
    solve_single_problem_csolver,
)
from newclid.proof_scout.reduction.rule_reducer import (
    _parse_rule_map,
    _scan_jsonl_for_rules,
)


# ---------------------------------------------------------------------------
# Problem extraction from JSONL
# ---------------------------------------------------------------------------


def extract_problems_from_jsonl(
    rules_path: Path, data_path: Path
) -> List[Tuple[str, str]]:
    """Extract unique problems from JSONL using rule_id -> seed dedup.

    Returns list of (problem_id, fl_problem_text) tuples, deduplicated by seed.
    """
    rule_map = _parse_rule_map(str(rules_path))
    entry_map = _scan_jsonl_for_rules(str(data_path), rule_map)

    seen_seeds = set()
    problems = []
    skipped_no_fl = 0

    for rule_id, entry in entry_map.items():
        fl_problem = entry.get("fl_problem", "")
        if not fl_problem:
            skipped_no_fl += 1
            continue

        seed = entry.get("seed")
        if seed is not None and seed in seen_seeds:
            continue
        if seed is not None:
            seen_seeds.add(seed)

        pid = f"seed_{seed}" if seed is not None else f"rule_{rule_id}"
        problems.append((pid, fl_problem))

    print(f"  Rules in file: {len(rule_map)}")
    print(f"  Matched JSONL entries: {len(entry_map)}")
    print(f"  Unique problems (by seed): {len(problems)}")
    if skipped_no_fl:
        print(f"  Skipped (no fl_problem): {skipped_no_fl}")

    return problems


# ---------------------------------------------------------------------------
# Cross-solve one direction
# ---------------------------------------------------------------------------


def cross_solve(
    rules_pipe: List[str],
    rule_ids: List[str],
    problems: List[Tuple[str, str]],
    timeout: int,
    seed: int,
    engine: str,
    label: str,
) -> dict:
    """Solve a set of problems using given rules via Ray-parallel CSolver.

    Returns dict with solved/failed lists and stats.
    """
    if not problems:
        return {"total": 0, "solved": 0, "solve_rate": 0.0,
                "solved_list": [], "failed_list": []}

    print(f"\n{'='*60}")
    print(f"Cross-solve: {label}")
    print(f"  Rules: {len(rule_ids)}, Problems: {len(problems)}")
    print(f"  Engine: {engine}, Timeout: {timeout}s")
    print(f"{'='*60}")

    refs = []
    ref_to_pid = {}
    for pid, problem_text in problems:
        ref = solve_single_problem_csolver.remote(
            problem_id=pid,
            problem_text=problem_text,
            custom_rules_pipe=rules_pipe,
            custom_rule_ids=rule_ids,
            timeout=timeout,
            seed=seed,
            engine=engine,
        )
        refs.append(ref)
        ref_to_pid[ref] = pid

    hard_timeout = timeout * len(problems) + 300
    results = collect_results_with_hard_timeout(
        refs, ref_to_pid, hard_timeout, label=label
    )

    solved_list = [r["problem_id"] for r in results if r.get("solved")]
    failed_list = [r["problem_id"] for r in results if not r.get("solved")]

    solve_rate = len(solved_list) / len(problems) if problems else 0.0
    print(f"\n  Result: {len(solved_list)}/{len(problems)} solved ({solve_rate:.1%})")

    return {
        "total": len(problems),
        "solved": len(solved_list),
        "solve_rate": round(solve_rate, 6),
        "solved_list": solved_list,
        "failed_list": failed_list,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Cross Rule-Set Comparison Pipeline")
    parser.add_argument("--rules-a", required=True, type=Path, help="Rule set A (extracted_rules.txt)")
    parser.add_argument("--data-a", required=True, type=Path, help="JSONL data for rule set A")
    parser.add_argument("--rules-b", required=True, type=Path, help="Rule set B (extracted_rules.txt)")
    parser.add_argument("--data-b", required=True, type=Path, help="JSONL data for rule set B")
    parser.add_argument("--output", required=True, type=Path, help="Output directory")
    parser.add_argument("--engine", default="full", choices=["full", "weak"], help="DDAR engine variant")
    parser.add_argument("--timeout", type=int, default=600, help="Per-problem timeout (seconds)")
    parser.add_argument("--workers", type=int, default=30, help="Number of Ray workers")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)

    # Step 1: Load rule sets
    print("=" * 60)
    print("Step 1: Loading rule sets")
    print("=" * 60)

    print("\nRule set A:")
    pipes_a, ids_a, total_a, filtered_a = load_rules_as_pipe(args.rules_a)
    print(f"  Total: {total_a}, Effective: {len(ids_a)}, Filtered: {filtered_a}")

    print("\nRule set B:")
    pipes_b, ids_b, total_b, filtered_b = load_rules_as_pipe(args.rules_b)
    print(f"  Total: {total_b}, Effective: {len(ids_b)}, Filtered: {filtered_b}")

    # Step 2: Extract problems from JSONL
    print("\n" + "=" * 60)
    print("Step 2: Extracting problems from JSONL")
    print("=" * 60)

    print("\nProblems from data A:")
    problems_a = extract_problems_from_jsonl(args.rules_a, args.data_a)

    print("\nProblems from data B:")
    problems_b = extract_problems_from_jsonl(args.rules_b, args.data_b)

    if not problems_a and not problems_b:
        print("\nERROR: No problems extracted from either dataset. Aborting.")
        sys.exit(1)

    # Step 3: Cross-solve with Ray
    print("\n" + "=" * 60)
    print("Step 3: Cross-solving")
    print("=" * 60)

    ray.init(num_cpus=args.workers, ignore_reinit_error=True)

    result_ra_on_pb = cross_solve(
        rules_pipe=pipes_a, rule_ids=ids_a, problems=problems_b,
        timeout=args.timeout, seed=args.seed, engine=args.engine,
        label="rA_on_pB (rules A solving problems B)",
    )

    result_rb_on_pa = cross_solve(
        rules_pipe=pipes_b, rule_ids=ids_b, problems=problems_a,
        timeout=args.timeout, seed=args.seed, engine=args.engine,
        label="rB_on_pA (rules B solving problems A)",
    )

    ray.shutdown()

    # Step 4: Build and save report
    report = {
        "config": {
            "rules_a": str(args.rules_a),
            "data_a": str(args.data_a),
            "rules_b": str(args.rules_b),
            "data_b": str(args.data_b),
            "engine": args.engine,
            "timeout": args.timeout,
            "workers": args.workers,
            "seed": args.seed,
        },
        "rule_sets": {
            "A": {"total_rules": total_a, "effective_rules": len(ids_a)},
            "B": {"total_rules": total_b, "effective_rules": len(ids_b)},
        },
        "problems": {
            "pA": {"total": len(problems_a), "unique_seeds": len(problems_a)},
            "pB": {"total": len(problems_b), "unique_seeds": len(problems_b)},
        },
        "cross_solve": {
            "rA_on_pB": result_ra_on_pb,
            "rB_on_pA": result_rb_on_pa,
        },
        "timestamp": datetime.now().isoformat(),
    }

    report_path = args.output / "cross_eval_results.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nReport saved to {report_path}")

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"  rA on pB: {result_ra_on_pb['solved']}/{result_ra_on_pb['total']} ({result_ra_on_pb['solve_rate']:.1%})")
    print(f"  rB on pA: {result_rb_on_pa['solved']}/{result_rb_on_pa['total']} ({result_rb_on_pa['solve_rate']:.1%})")


if __name__ == "__main__":
    main()

