#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test CSolver on synthetic geometry problems with renamed format.

This script tests CSolver (C++ DDAR) on problems from the synthetic data
generation pipeline. CSolver can handle problems without explicit coordinates
by using the JGEX construction internally.
"""
import sys
import json
import time
from pathlib import Path
from typing import List, Dict, Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def load_synthetic_problems(
    jsonl_file: Path,
    max_problems: int = 100,
) -> List[Dict[str, Any]]:
    """Load synthetic problems from JSONL file.

    Args:
        jsonl_file: Path to JSONL file with synthetic problems
        max_problems: Maximum number of problems to load

    Returns:
        List of problem dictionaries
    """
    problems = []
    with open(jsonl_file) as f:
        for i, line in enumerate(f):
            if i >= max_problems:
                break
            problems.append(json.loads(line))
    return problems


def test_csolver_on_synthetic(
    jsonl_file: Path,
    max_problems: int = 100,
    timeout: int = 30,
) -> Dict[str, Any]:
    """Test CSolver on synthetic problems.

    Args:
        jsonl_file: Path to JSONL file with synthetic problems
        max_problems: Maximum number of problems to test
        timeout: Timeout per problem in seconds

    Returns:
        Dictionary with test results
    """
    from newclid.api import CSolver

    print(f"\nTesting CSolver on {jsonl_file.name}...")
    print(f"  Max problems: {max_problems}")
    print(f"  Timeout: {timeout}s\n")

    problems = load_synthetic_problems(jsonl_file, max_problems)
    print(f"Loaded {len(problems)} problems\n")

    results = {
        "total": len(problems),
        "solved": 0,
        "failed": 0,
        "error": 0,
        "solve_times": [],
        "failed_problems": [],
        "error_problems": [],
    }

    for i, problem in enumerate(problems):
        problem_id = problem.get("problem_id", f"problem_{i}")
        problem_txt = problem["llm_input_renamed"]

        try:
            # Create CSolver
            t0 = time.time()
            solver = CSolver(
                problem=problem_txt,
                problem_name=problem_id,
                seed=42,
                using_log=True,
                using_exp=False,  # Match generation settings
            )

            # Run solver
            solved = solver.run(max_level=500)
            runtime = time.time() - t0

            if solved:
                results["solved"] += 1
                results["solve_times"].append(runtime)
                status = f"✓ SOLVED ({runtime:.3f}s)"
            else:
                results["failed"] += 1
                results["failed_problems"].append({
                    "problem_id": problem_id,
                    "runtime": runtime,
                })
                status = f"✗ FAILED ({runtime:.3f}s)"

            print(f"  [{i+1}/{len(problems)}] {problem_id}: {status}")

        except Exception as e:
            results["error"] += 1
            results["error_problems"].append({
                "problem_id": problem_id,
                "error": str(e),
            })
            print(f"  [{i+1}/{len(problems)}] {problem_id}: ✗ ERROR - {e}")

    return results


def print_summary(results: Dict[str, Any]):
    """Print test summary."""
    print("\n" + "="*60)
    print("CSolver Test Summary")
    print("="*60)
    print(f"Total problems:    {results['total']}")
    print(f"Solved:            {results['solved']} ({results['solved']/results['total']*100:.1f}%)")
    print(f"Failed:            {results['failed']} ({results['failed']/results['total']*100:.1f}%)")
    print(f"Errors:            {results['error']} ({results['error']/results['total']*100:.1f}%)")

    if results["solve_times"]:
        import statistics
        print(f"\nSolve times:")
        print(f"  Mean:   {statistics.mean(results['solve_times']):.3f}s")
        print(f"  Median: {statistics.median(results['solve_times']):.3f}s")
        print(f"  Min:    {min(results['solve_times']):.3f}s")
        print(f"  Max:    {max(results['solve_times']):.3f}s")

    if results["failed_problems"]:
        print(f"\nFailed problems (first 10):")
        for p in results["failed_problems"][:10]:
            print(f"  - {p['problem_id']} ({p['runtime']:.3f}s)")

    if results["error_problems"]:
        print(f"\nError problems (first 10):")
        for p in results["error_problems"][:10]:
            print(f"  - {p['problem_id']}: {p['error']}")

    print("="*60)


def main():
    """Run CSolver tests on synthetic data."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Test CSolver on synthetic geometry problems"
    )
    parser.add_argument(
        "--data",
        type=Path,
        required=True,
        help="Path to JSONL file with synthetic problems",
    )
    parser.add_argument(
        "--max-problems",
        type=int,
        default=100,
        help="Maximum number of problems to test (default: 100)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout per problem in seconds (default: 30)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional: Save results to JSON file",
    )

    args = parser.parse_args()

    # Run tests
    results = test_csolver_on_synthetic(
        args.data,
        max_problems=args.max_problems,
        timeout=args.timeout,
    )

    # Print summary
    print_summary(results)

    # Save results if requested
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
