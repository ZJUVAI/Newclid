#!/usr/bin/env python3
"""Backtracking elimination on incremental basis rules."""
import json
import time
from pathlib import Path

from newclid.proof_scout.reduction import load_rules_from_discovery_output, RuleWithSource
from newclid.api import DirectSolver

ERROR_RULES = {'r1837', 'r1858', 'r1806', 'r1834', 'r1780'}
OUTPUT_DIR = Path("outputs/experiments/20260310_02_10k_incremental_reduction")
TIMEOUT = 60
SEED = 42


def main():
    # Load all rules to get source data
    rules, _ = load_rules_from_discovery_output(
        Path("outputs/experiments/20260310_01_10k_normalized_extraction_reduction/discovered_rules.txt"),
        source_data_file=Path("outputs/experiments/20260310_01_10k_normalized_extraction_reduction/intermediates/step1e_rules_stats.json"),
    )
    rule_map = {r.rule_id: r for r in rules}

    # Read basis rules
    basis_ids = []
    with open(OUTPUT_DIR / "basis_rules.txt") as f:
        lines = f.read().strip().split('\n')
        for i in range(0, len(lines), 2):
            basis_ids.append(lines[i].strip())

    # Filter out error rules
    valid_basis = [rule_map[rid] for rid in basis_ids if rid not in ERROR_RULES and rid in rule_map]
    print(f"Total basis: {len(basis_ids)}, error rules: {len(ERROR_RULES)}, valid basis: {len(valid_basis)}")

    # Backtracking elimination
    removable = []
    start = time.time()
    for i, rule in enumerate(valid_basis):
        others = [r.rule_text for j, r in enumerate(valid_basis) if j != i]
        try:
            solver = DirectSolver(
                points=rule.points,
                premises=rule.premises,
                goal=rule.goal,
                seed=SEED,
                custom_rules=others,
            )
            covered = solver.run(timeout=TIMEOUT)
        except Exception as e:
            print(f"  [{i+1}/{len(valid_basis)}] {rule.rule_id} ERROR: {e}")
            covered = False

        elapsed = time.time() - start
        if covered:
            removable.append(rule.rule_id)
            print(f"  [{i+1}/{len(valid_basis)}] {rule.rule_id} REMOVABLE ({elapsed:.1f}s)")
        else:
            print(f"  [{i+1}/{len(valid_basis)}] {rule.rule_id} ESSENTIAL ({elapsed:.1f}s)")

    elapsed = time.time() - start
    final_basis = [r for r in valid_basis if r.rule_id not in set(removable)]

    print(f"\n{'='*60}")
    print(f"Backtracking Elimination Summary")
    print(f"{'='*60}")
    print(f"Input basis:    {len(valid_basis)}")
    print(f"Removable:      {len(removable)} {removable}")
    print(f"Final basis:    {len(final_basis)}")
    print(f"Elapsed:        {elapsed:.1f}s")
    print(f"{'='*60}")

    # Save final basis
    out_file = OUTPUT_DIR / "basis_rules_after_backtrack.txt"
    with open(out_file, 'w') as f:
        for r in final_basis:
            f.write(f"{r.rule_id}\n{r.rule_text}\n")
    print(f"Saved to {out_file}")


if __name__ == "__main__":
    main()
