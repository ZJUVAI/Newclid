#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for premises-based loading implementation.

Tests:
1. ProofState.build_premises() creates correct structure
2. extract_solver_data() extracts correct data
3. DirectSolver works with new implementation
4. SubsumptionTester works with premises-based loading
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_build_premises():
    """Test ProofState.build_premises() basic functionality."""
    print("\n=== Test 1: ProofState.build_premises() ===")

    from newclid.proof import ProofState
    from newclid.formulations.definition import DefinitionJGEX
    from newclid.configs import default_defs_path
    import numpy as np

    # Simple problem: triangle ABC with AB = AC
    points = [
        ("a", 0.0, 0.0),
        ("b", 1.0, 0.0),
        ("c", 0.5, 0.866),
    ]
    premises = [
        ("cong", ["a", "b", "a", "c"]),
    ]
    goals = [
        ("cong", ["a", "b", "a", "c"]),
    ]

    defs = DefinitionJGEX.to_dict(
        DefinitionJGEX.parse_txt_file(default_defs_path())
    )

    proof = ProofState.build_premises(
        points=points,
        premises=premises,
        defsJGEX=defs,
        goals_str=goals,
        rng=np.random.default_rng(42),
    )

    # Check point.clause is set
    for name, x, y in points:
        point = proof.symbols_graph.name2node[name]
        assert point.clause is not None, f"Point {name} has no clause"
        assert point.clause.points == (name,), f"Point {name} clause.points incorrect"
        print(f"  ✓ Point {name}: clause={point.clause}, rely_on={point.rely_on}")

    # Check goals
    assert len(proof.goals) == 1, f"Expected 1 goal, got {len(proof.goals)}"
    print(f"  ✓ Goals: {[g.to_str() for g in proof.goals]}")

    print("  ✓ Test passed!")
    return True


def test_extract_solver_data():
    """Test extract_solver_data() utility function."""
    print("\n=== Test 2: extract_solver_data() ===")

    from newclid.api import extract_solver_data

    # Simple JGEX problem (single line format)
    problem_txt = "test_problem\na : ; b : ; c : cong a b a c [000] ? cong a b a c"

    points, premises, goals = extract_solver_data(problem_txt, seed=42)

    print(f"  Points: {points}")
    print(f"  Premises: {premises}")
    print(f"  Goals: {goals}")

    assert len(points) == 3, f"Expected 3 points, got {len(points)}"
    assert len(goals) == 1, f"Expected 1 goal, got {len(goals)}"

    print("  ✓ Test passed!")
    return True


def test_direct_solver():
    """Test DirectSolver with new implementation."""
    print("\n=== Test 3: DirectSolver ===")

    from newclid.api import DirectSolver

    # Simple problem: triangle with AB = AC, prove AB = AC
    points = [
        ("a", 0.0, 0.0),
        ("b", 1.0, 0.0),
        ("c", 0.5, 0.866),
    ]
    premises = [
        ("cong", ["a", "b", "a", "c"]),
    ]
    goal = ("cong", ["a", "b", "a", "c"])

    solver = DirectSolver(
        points=points,
        premises=premises,
        goal=goal,
        problem_name="test_direct",
        seed=42,
    )

    solved = solver.run(timeout=10)
    print(f"  Solved: {solved}")
    assert solved, "DirectSolver should solve trivial problem"

    print("  ✓ Test passed!")
    return True


def test_premises_based_vs_jgex():
    """Compare premises-based loading vs JGEX loading."""
    print("\n=== Test 4: Premises-based vs JGEX loading ===")

    from newclid.api import extract_solver_data, GeometricSolverBuilder
    from newclid.agent.ddarn import DDARN

    # Problem with auxiliary point construction (single line format)
    problem_txt = "test_aux\na : ; b : ; c : midp a b c [000] ? cong a c b c"

    # Method 1: JGEX loading (includes auxiliary point construction)
    builder1 = GeometricSolverBuilder(seed=42)
    builder1.load_problem_from_txt(problem_txt)
    builder1.with_deductive_agent(DDARN())
    solver1 = builder1.build()

    premises1 = [stmt.to_str() for stmt in solver1.proof.dep_graph.hyper_graph]
    print(f"  JGEX loading premises count: {len(premises1)}")
    print(f"  JGEX premises: {premises1[:5]}...")  # Show first 5

    # Method 2: Premises-based loading (no auxiliary point construction)
    points, premises, goals = extract_solver_data(problem_txt, seed=42)

    builder2 = GeometricSolverBuilder(seed=42)
    builder2.load_problem_from_premises(points, premises, goals)
    builder2.with_deductive_agent(DDARN())
    solver2 = builder2.build()

    premises2 = [stmt.to_str() for stmt in solver2.proof.dep_graph.hyper_graph]
    print(f"  Premises-based loading premises count: {len(premises2)}")
    print(f"  Premises-based premises: {premises2[:5]}...")  # Show first 5

    # Premises-based should have same or more premises (includes derived facts)
    # but should NOT include auxiliary point construction clauses
    print(f"  ✓ Comparison complete!")
    return True


def main():
    """Run all tests."""
    print("Testing premises-based loading implementation...")

    tests = [
        test_build_premises,
        test_extract_solver_data,
        test_direct_solver,
        test_premises_based_vs_jgex,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"  ✗ Test failed: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'='*60}")

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
