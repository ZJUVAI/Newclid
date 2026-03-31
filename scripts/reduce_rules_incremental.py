#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Incremental Coverage Reduction - reduce rules by incremental basis building.

Algorithm:
1. Load rules, filter by max_premises
2. Sort by generality (fewer premises first)
3. For each rule, test if the current basis set can solve its source problem
4. If covered → skip; if not → add to basis

This is stronger than pairwise subsumption (R2-R3) because it tests
multi-rule combination coverage.
"""
import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from newclid.proof_scout.reduction import (
    load_rules_from_discovery_output,
    GeneralityScorer,
    RuleWithSource,
)
from newclid.api import DirectSolver


def filter_rules(rules, max_premises=None, verbose=True):
    """Pre-filter rules by premise count."""
    skipped_premises = []

    if max_premises is not None:
        kept = []
        for rule in rules:
            if '=>' in rule.rule_text:
                n_prem = len([c for c in rule.rule_text.split('=>')[0].split(',') if c.strip()])
            else:
                n_prem = 0
            if n_prem <= max_premises:
                kept.append(rule)
            else:
                skipped_premises.append({
                    "rule_id": rule.rule_id,
                    "rule_text": rule.rule_text,
                    "n_premises": n_prem,
                })
        if verbose:
            print(f"  Pre-filter: {len(skipped_premises)} rules skipped (premises > {max_premises})")
            print(f"  Remaining: {len(kept)} rules")
        rules = kept

    return rules, skipped_premises


def incremental_reduce(rules, timeout=60, seed=42, verbose=True):
    """Incremental coverage reduction.

    For each rule (sorted by generality), test if the current basis can
    solve its source problem. If not, add it to the basis.
    """
    scorer = GeneralityScorer()
    for rule in rules:
        rule.generality_score = scorer.score(rule.rule_text)
        rule.parse()

    sorted_rules = sorted(rules, key=lambda r: r.generality_score)

    basis = []
    covered = []
    n_solver_calls = 0

    for i, rule in enumerate(sorted_rules):
        if verbose and (i + 1) % 10 == 0:
            print(f"  Progress: {i+1}/{len(sorted_rules)} rules, basis={len(basis)}, covered={len(covered)}")

        # Write current basis to temp rules
        basis_rules_text = []
        for b in basis:
            basis_rules_text.append(b.rule_text)

        # Test if current basis + DDAR can solve this rule's source problem
        try:
            solver = DirectSolver(
                points=rule.points,
                premises=rule.premises,
                goal=rule.goal,
                seed=seed,
                custom_rules=basis_rules_text if basis_rules_text else None,
            )
            n_solver_calls += 1

            if solver.run(timeout=timeout):
                covered.append({
                    "rule_id": rule.rule_id,
                    "rule_text": rule.rule_text,
                    "covered_by_basis_size": len(basis),
                })
                if verbose:
                    print(f"    Covered: {rule.rule_id} (basis size={len(basis)})")
            else:
                basis.append(rule)
                if verbose:
                    print(f"    Added to basis: {rule.rule_id} (basis size={len(basis)})")
        except Exception as e:
            # Conservative: add to basis on error
            basis.append(rule)
            if verbose:
                print(f"    Error testing {rule.rule_id}: {e}, added to basis")

    return basis, covered, n_solver_calls


def main():
    parser = argparse.ArgumentParser(
        description="Incremental coverage reduction"
    )
    parser.add_argument("--rules", type=Path, required=True,
                        help="Path to rules file (rule_id\\nrule_text\\n...)")
    parser.add_argument("--source-data", type=Path, required=True,
                        help="Path to step6_rules_stats.json")
    parser.add_argument("--output", type=Path, required=True,
                        help="Output directory")
    parser.add_argument("--max-rules", type=int, default=None)
    parser.add_argument("--max-premises", type=int, default=None)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--quiet", action="store_true")

    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    print(f"{'='*60}")
    print(f"Incremental Coverage Reduction")
    print(f"{'='*60}")
    print(f"Rules: {args.rules}")
    print(f"Source data: {args.source_data}")
    print(f"Output: {args.output}")

    # Load rules
    rules, failures = load_rules_from_discovery_output(
        args.rules, args.source_data, max_rules=args.max_rules,
    )
    print(f"Loaded {len(rules)} rules ({len(failures)} failures)")

    # Filter
    rules, skipped_premises = filter_rules(
        rules, max_premises=args.max_premises, verbose=not args.quiet,
    )

    if not rules:
        print("No rules to reduce!")
        return

    # Run incremental reduction
    start = time.time()
    basis, covered, n_solver_calls = incremental_reduce(
        rules, timeout=args.timeout, seed=args.seed, verbose=not args.quiet,
    )
    elapsed = time.time() - start

    # Save basis rules
    with open(args.output / "extracted_rules.txt", 'w') as f:
        for rule in basis:
            f.write(f"{rule.rule_id}\n{rule.rule_text}\n")

    # Save covered rules
    with open(args.output / "covered_rules.json", 'w') as f:
        json.dump(covered, f, indent=2)

    if skipped_premises:
        with open(args.output / "skipped_by_premises.json", 'w') as f:
            json.dump(skipped_premises, f, indent=2)

    # Save stats
    original_count = len(rules) + len(skipped_premises)
    stats = {
        "original_count": original_count,
        "after_filter_count": len(rules),
        "skipped_by_premises_count": len(skipped_premises),
        "basis_count": len(basis),
        "covered_count": len(covered),
        "reduction_rate": len(covered) / len(rules) if rules else 0,
        "n_solver_calls": n_solver_calls,
        "elapsed_seconds": round(elapsed, 1),
        "calls_per_second": round(n_solver_calls / elapsed, 2) if elapsed > 0 else 0,
    }
    with open(args.output / "reduction_stats.json", 'w') as f:
        json.dump(stats, f, indent=2)

    # Summary
    print(f"\n{'='*60}")
    print(f"Incremental Coverage Reduction Summary")
    print(f"{'='*60}")
    print(f"Input rules:          {stats['original_count']}")
    print(f"Skipped (premises):   {stats['skipped_by_premises_count']}")
    print(f"Tested:               {stats['after_filter_count']}")
    print(f"Basis rules:          {stats['basis_count']}")
    print(f"Covered rules:        {stats['covered_count']}")
    print(f"Reduction rate:       {stats['reduction_rate']*100:.1f}%")
    print(f"Solver calls:         {stats['n_solver_calls']}")
    print(f"Elapsed:              {stats['elapsed_seconds']}s")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
