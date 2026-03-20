#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Debug script: test r0012 subsumption against all basis rules' source problems.

r0012: perp a b a c, perp b d c d, cong a d b c, ncoll a b d => para a b c d
"""
import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from newclid.proof_scout.reduction import load_rules_from_discovery_output  # noqa: E402
from newclid.proof_scout.reduction.subsumption_tester import SubsumptionTester  # noqa: E402
from newclid.proof_scout.reduction.rule_reducer import RuleWithSource  # noqa: E402

INPUT_RULES = PROJECT_ROOT / "outputs/datasets/square_case/risos_on_dia_eqdist_subset_pruned_rules.txt"
INPUT_STATS = PROJECT_ROOT / "outputs/experiments/20260309_01_risos_subset_rule_extraction/intermediates/step1e_rules_stats.json"
BASIS_FILE = PROJECT_ROOT / "outputs/experiments/20260309_01_risos_subset_rule_extraction/basis_rules.txt"

R0012_TEXT = "perp a b a c, perp b d c d, cong a d b c, ncoll a b d => para a b c d"


def main() -> int:
    # Load all rules (to get source problem data)
    print("Loading all rules...")
    all_rules, failures = load_rules_from_discovery_output(INPUT_RULES, INPUT_STATS)
    rule_by_id = {r.rule_id: r for r in all_rules}
    print(f"Loaded {len(all_rules)} rules")

    # Read basis rule IDs
    basis_texts = set()
    with open(BASIS_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                basis_texts.add(line)
    print(f"Basis rules: {len(basis_texts)}")

    # Find basis rules with source data
    basis_rules = [r for r in all_rules if r.rule_text in basis_texts]
    print(f"Basis rules with source data: {len(basis_rules)}")

    # Get r0012 source data
    r0012 = rule_by_id.get("r0012")
    if not r0012:
        print("ERROR: r0012 not found in loaded rules")
        return 1

    print(f"\nTest rule: {r0012.rule_id} => {r0012.rule_text}")
    print(f"Testing against {len(basis_rules)} basis rules...\n")

    tester = SubsumptionTester(timeout=60, seed=42)

    solved = []
    unsolved = []

    for i, basis_rule in enumerate(basis_rules):
        print(f"[{i+1}/{len(basis_rules)}] Testing {basis_rule.rule_id}: {basis_rule.rule_text[:80]}...")
        result = tester.test_subsumption(r0012, basis_rule, debug=True)
        if result:
            solved.append(basis_rule)
            print(f"  => SOLVED (r0012 subsumes {basis_rule.rule_id})")
        else:
            unsolved.append(basis_rule)
            print(f"  => NOT SOLVED")

    # Summary
    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"Test rule: r0012 => {R0012_TEXT}")
    print(f"Total basis rules tested: {len(basis_rules)}")
    print(f"Solved (subsumed):        {len(solved)}")
    print(f"Not solved:               {len(unsolved)}")

    if solved:
        print(f"\nSubsumed basis rules:")
        for r in solved:
            print(f"  {r.rule_id}: {r.rule_text}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
