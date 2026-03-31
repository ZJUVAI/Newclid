#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Debug script to test solver building for a specific problem.

This script tests the solver building process step by step to identify
where the failure occurs.
"""
import sys
import traceback
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from newclid.generation.problem_worker import GeometryProblemWorker
from newclid.formulations.problem import ProblemJGEX
from newclid.api import CSolver


def test_solver_build(fl_statement: str, seed: int = 42, max_attempts: int = 1):
    """Test solver building step by step."""
    print("="*60)
    print("Testing Solver Build")
    print("="*60)
    print(f"Problem: {fl_statement}")
    print(f"Seed: {seed}")
    print(f"Max attempts: {max_attempts}")
    print()

    # Step 1: Parse problem
    print("Step 1: Parsing problem...")
    try:
        problem = ProblemJGEX.from_text(fl_statement)
        print(f"  ✓ Problem parsed successfully")
        print(f"    Name: {problem.name}")
        print(f"    Constructions: {len(problem.constructions)}")
        print(f"    Goals: {len(problem.goals)}")
    except Exception as e:
        print(f"  ✗ Failed to parse problem: {e}")
        traceback.print_exc()
        return False
    print()

    # Step 2: Build solver
    print("Step 2: Building solver...")
    try:
        # Try to build solver manually to see the exception
        from newclid.api import GeometricSolverBuilder
        from newclid.agent.ddarn import DDARN

        solver_builder = GeometricSolverBuilder(seed=998244353)
        solver_builder.with_deductive_agent(DDARN())
        solver_builder.load_problem_from_txt(fl_statement)

        print("  - Solver builder created")
        print("  - Attempting to build solver...")

        solver = solver_builder.build(max_attempts=max_attempts)

        if solver:
            print(f"  ✓ Solver built successfully")
            print(f"    Solver type: {type(solver).__name__}")
        else:
            print(f"  ✗ Solver is None (build failed)")
            return False
    except Exception as e:
        print(f"  ✗ Failed to build solver: {e}")
        print(f"    Exception type: {type(e).__name__}")
        traceback.print_exc()
        return False
    print()

    # Step 3: Create CSolver
    print("Step 3: Creating CSolver...")
    try:
        csolver = CSolver(
            fl_statement,
            seed=seed,
            solver=solver,
            using_log=True,
            using_exp=False
        )
        print(f"  ✓ CSolver created successfully")
    except Exception as e:
        print(f"  ✗ Failed to create CSolver: {e}")
        traceback.print_exc()
        return False
    print()

    # Step 4: Run CSolver (with low max_level for testing)
    print("Step 4: Running CSolver (max_level=10 for testing)...")
    try:
        csolver.run(max_level=10)
        print(f"  ✓ CSolver ran successfully")
        print(f"    Levels explored: {len(csolver.log) if hasattr(csolver, 'log') else 'N/A'}")
    except Exception as e:
        print(f"  ✗ Failed to run CSolver: {e}")
        traceback.print_exc()
        return False
    print()

    print("="*60)
    print("All steps completed successfully!")
    print("="*60)
    return True


if __name__ == "__main__":
    # Test problem from complete_008_7_Book_LLL_L053-1.gex
    fl_statement = "b c d = triangle b c d; e = foot e b c d; a = free a; f = foot f a c d; g = midpoint g b a; h = midpoint h e f ? cong f g g e"

    print("Testing with max_attempts=1 (original setting):")
    success1 = test_solver_build(fl_statement, seed=42, max_attempts=1)
    print()

    print("\nTesting with max_attempts=10:")
    success10 = test_solver_build(fl_statement, seed=42, max_attempts=10)
    print()

    print("\nTesting with max_attempts=100:")
    success100 = test_solver_build(fl_statement, seed=42, max_attempts=100)
    print()

    if success100:
        print("✓ Problem can be solved with max_attempts=100")
    elif success10:
        print("✓ Problem can be solved with max_attempts=10 but not tested with 100")
    else:
        print("✗ Problem still fails even with max_attempts=10")

    sys.exit(0 if success100 else 1)
