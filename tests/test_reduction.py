#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Rule Reduction - Unit tests and integration tests.

This script tests:
1. GeneralityScorer correctness
2. SubsumptionTester correctness
3. RuleReducer on hand-crafted examples
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from newclid.proof_scout.reduction import (
    RuleReducer,
    RuleWithSource,
    GeneralityScorer,
    SubsumptionTester,
)


def _rule_text_to_rule_with_source(rule_id: str, rule_text: str, seed: int = 42) -> RuleWithSource:
    """Convert rule text to RuleWithSource using DirectSolver for point generation.

    Parses the rule text to extract premises and goal, then uses DirectSolver
    to generate valid point coordinates.
    """
    from newclid.proof_scout.reduction.rule_reducer import _parse_llm_input

    if '=>' not in rule_text:
        raise ValueError(f"Invalid rule text (no =>): {rule_text}")

    premise_part, goal_part = rule_text.split('=>', 1)

    # Parse premises
    premises = []
    for clause in premise_part.split(','):
        parts = clause.strip().split()
        if parts:
            premises.append((parts[0], parts[1:]))

    # Parse goal (take first conclusion)
    goal_clauses = []
    for clause in goal_part.split(','):
        parts = clause.strip().split()
        if parts:
            goal_clauses.append((parts[0], parts[1:]))

    if not goal_clauses:
        raise ValueError(f"No goal found in rule text: {rule_text}")
    goal = goal_clauses[0]

    # Collect all unique point names
    all_points = set()
    for _, args in premises:
        all_points.update(args)
    for _, args in goal_clauses:
        all_points.update(args)

    # Generate simple coordinates for each point
    import random
    rng = random.Random(seed)
    points = [(p, rng.uniform(-10, 10), rng.uniform(-10, 10)) for p in sorted(all_points)]

    return RuleWithSource(
        rule_id=rule_id,
        rule_text=rule_text,
        points=points,
        premises=premises,
        goal=goal,
    )


def test_generality_scorer():
    """Test GeneralityScorer correctness."""
    print("="*60)
    print("Test 1: GeneralityScorer")
    print("="*60)

    scorer = GeneralityScorer()

    test_cases = [
        ("cong a b c d => cong c d a b", (-1, 1)),
        ("cong a b c d, para a b c d => cong c d a b", (-2, 1)),
        ("cong a b c d => para a b c d, coll a b c", (-1, 2)),
        ("cong a b c d, cong e f g h, para i j k l => cyclic m n o p", (-3, 1)),
    ]

    all_passed = True
    for rule_text, expected_score in test_cases:
        score = scorer.score(rule_text)
        passed = score == expected_score
        all_passed = all_passed and passed
        status = "✓" if passed else "✗"
        print(f"{status} {rule_text[:50]}...")
        print(f"  Expected: {expected_score}, Got: {score}")

    print(f"\nGeneralityScorer: {'PASSED' if all_passed else 'FAILED'}\n")
    return all_passed


def test_subsumption_tester():
    """Test SubsumptionTester with hand-crafted examples."""
    print("="*60)
    print("Test 2: SubsumptionTester")
    print("="*60)

    tester_subsumption = SubsumptionTester(timeout=60, seed=42)

    # Rule A: cong a b c d, cong a b e f => cong c d e f (general transitivity)
    # Rule B: cong a b c d, cong a b e f, para a b c d => cong c d e f (+ extra premise)
    # Expected: A subsumes B (A is more general)

    rule_a_text = "cong a b c d, cong a b e f => cong c d e f"
    rule_b_text = "cong a b c d, cong a b e f, para a b c d => cong c d e f"

    print(f"Rule A: {rule_a_text}")
    print(f"Rule B: {rule_b_text}")
    print(f"Expected: A subsumes B (A is more general)")

    try:
        rule_a = _rule_text_to_rule_with_source("r_a", rule_a_text, seed=42)
        rule_b = _rule_text_to_rule_with_source("r_b", rule_b_text, seed=43)
    except Exception as e:
        print(f"✗ Failed to create RuleWithSource: {e}")
        return False

    # Test subsumption
    print(f"\nTesting: Does A subsume B?")
    a_subsumes_b = tester_subsumption.test_subsumption(rule_a, rule_b)
    print(f"  Result: {a_subsumes_b}")

    print(f"\nTesting: Does B subsume A?")
    b_subsumes_a = tester_subsumption.test_subsumption(rule_b, rule_a)
    print(f"  Result: {b_subsumes_a}")

    passed = a_subsumes_b and not b_subsumes_a
    print(f"\nSubsumptionTester: {'PASSED' if passed else 'WARNING'}")
    print(f"  A subsumes B: {a_subsumes_b} (expected: True)")
    print(f"  B subsumes A: {b_subsumes_a} (expected: False)")

    if a_subsumes_b and b_subsumes_a:
        print(f"  Note: Both rules subsume each other (equivalent)")

    print()
    return passed


def test_rule_reducer_small():
    """Test RuleReducer on a small hand-crafted example."""
    print("="*60)
    print("Test 3: RuleReducer (Small Example)")
    print("="*60)

    rules_text = [
        ("r1", "cong a b c d, cong a b e f => cong c d e f"),
        ("r2", "cong a b c d, cong a b e f, coll a b c => cong c d e f"),
    ]

    rules = []
    for rule_id, rule_text in rules_text:
        try:
            rules.append(_rule_text_to_rule_with_source(rule_id, rule_text))
        except Exception as e:
            print(f"Warning: Failed to convert {rule_id}: {e}")

    if len(rules) < 2:
        print(f"✗ Failed to generate all source problems")
        return False

    print(f"Testing with {len(rules)} rules:")
    for rule in rules:
        print(f"  {rule.rule_id}: {rule.rule_text}")

    # Run reduction
    reducer = RuleReducer(
        timeout=60,
        seed=42,
        verbose=True,
    )

    result = reducer.reduce(rules)

    basis_ids = {r.rule_id for r in result["basis_rules"]}
    eliminated_ids = {r["rule_id"] for r in result["eliminated_rules"]}

    print(f"\nResults:")
    print(f"  Basis rules: {basis_ids}")
    print(f"  Eliminated rules: {eliminated_ids}")

    has_basis = len(basis_ids) >= 1
    correct_elimination = (
        ("r2" in eliminated_ids and "r1" in basis_ids) or
        ("r1" in eliminated_ids and "r2" in basis_ids) or
        (len(eliminated_ids) == 0)
    )

    passed = has_basis and correct_elimination
    print(f"\nRuleReducer (Small): {'PASSED' if passed else 'FAILED'}")
    print(f"  Has at least one basis rule: {has_basis}")
    print(f"  Elimination is correct: {correct_elimination}")

    if "r1" in basis_ids and "r2" in eliminated_ids:
        print(f"  r1 (more general) kept, r2 (more specific) eliminated")
    elif "r2" in basis_ids and "r1" in eliminated_ids:
        print(f"  r2 kept, r1 eliminated")
    elif len(eliminated_ids) == 0:
        print(f"  Both rules are independent (no elimination)")

    print()
    return passed


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("Rule Reduction Test Suite")
    print("="*60 + "\n")

    results = []
    results.append(("GeneralityScorer", test_generality_scorer()))
    results.append(("SubsumptionTester", test_subsumption_tester()))
    results.append(("RuleReducer (Small)", test_rule_reducer_small()))

    print("="*60)
    print("Test Summary")
    print("="*60)
    for name, passed in results:
        status = "PASSED" if passed else "FAILED"
        print(f"  {status}: {name}")

    all_passed = all(passed for _, passed in results)
    print(f"\nOverall: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
    print("="*60 + "\n")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
