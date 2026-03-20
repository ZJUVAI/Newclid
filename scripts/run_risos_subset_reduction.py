#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run rule reduction on risos subset extracted rules.
"""
import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from newclid.proof_scout.reduction import RuleReducer, load_rules_from_discovery_output  # noqa: E402


INPUT_RULES = PROJECT_ROOT / "outputs/datasets/square_case/risos_on_dia_eqdist_subset_pruned_rules.txt"
INPUT_STATS = PROJECT_ROOT / "outputs/experiments/20260309_01_risos_subset_rule_extraction/intermediates/step1e_rules_stats.json"
OUTPUT_DIR = PROJECT_ROOT / "outputs/experiments/20260309_01_risos_subset_rule_extraction"


def main() -> int:
    print("=" * 60)
    print("Rule Reduction - Risos Subset")
    print("=" * 60)
    print(f"Input rules: {INPUT_RULES}")
    print(f"Output dir: {OUTPUT_DIR}")

    # Load rules
    print("\nLoading rules...")
    rules, failures = load_rules_from_discovery_output(INPUT_RULES, INPUT_STATS)
    print(f"Loaded {len(rules)} rules")
    if failures:
        print(f"Failed to load {len(failures)} rules")
        for rule_id, rule_text, error in failures[:5]:
            print(f"  {rule_id}: {error}")

    # Run reduction
    print("\nRunning reduction...")
    reducer = RuleReducer(
        timeout=60,
        seed=42,
        verbose=True,
        n_workers=1,
        batch_size=10,
        debug=True,
        debug_output_dir=OUTPUT_DIR / "intermediates",
    )

    result = reducer.reduce(rules)

    # Save results
    output_file = OUTPUT_DIR / "reduction_result.json"

    stats = result["stats"]
    with open(output_file, 'w') as f:
        json.dump(stats, f, indent=2)

    # Save basis rules
    basis_file = OUTPUT_DIR / "basis_rules.txt"
    with open(basis_file, 'w') as f:
        for rule in result["basis_rules"]:
            f.write(f"{rule.rule_text}\n")

    # Save eliminated rules
    eliminated_file = OUTPUT_DIR / "eliminated_rules.json"
    with open(eliminated_file, 'w') as f:
        json.dump(result["eliminated_rules"], f, indent=2)

    # Print summary
    print("\n" + "=" * 60)
    print("REDUCTION SUMMARY")
    print("=" * 60)
    print(f"Original rules:       {stats['original_count']}")
    print(f"Basis rules:          {stats['basis_count']}")
    print(f"Eliminated rules:     {stats['eliminated_count']}")
    print(f"Reduction rate:       {stats['reduction_rate']*100:.1f}%")
    print(f"Subsumption tests:    {stats['n_subsumption_tests']}")
    print(f"\nOutput files:")
    print(f"  Stats:      {output_file}")
    print(f"  Basis:      {basis_file}")
    print(f"  Eliminated: {eliminated_file}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
