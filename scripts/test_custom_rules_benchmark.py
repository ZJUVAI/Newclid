#!/usr/bin/env python3
"""
Benchmark test for CSolver with custom rules on HAGeo problems.
"""

import sys
import json
import time
sys.path.insert(0, '/root/GenesisGeo/src')

from newclid.DDAR.build import DDAR


def load_problems(filepath: str, limit: int = 10):
    """Load problems from benchmark file."""
    problems = []
    with open(filepath, 'r') as f:
        content = f.read()

    blocks = content.strip().split('\n\n')
    for block in blocks[:limit]:
        lines = block.strip().split('\n')
        if len(lines) < 4:
            continue

        name = None
        points = []
        premises = []
        goals = []

        section = None
        for line in lines:
            line = line.strip()
            if line == 'Problem Name:':
                section = 'name'
            elif line == 'Points:':
                section = 'points'
            elif line == 'Premises:':
                section = 'premises'
            elif line == 'Goal:' or line == 'Goals:':
                section = 'goals'
            elif section == 'name' and line:
                name = line
            elif section == 'points' and ':' in line:
                parts = line.split(':')
                pt_name = parts[0].strip()
                coords = parts[1].strip().split(',')
                points.append((pt_name, float(coords[0]), float(coords[1])))
            elif section == 'premises' and line:
                parts = line.split()
                premises.append((parts[0], parts[1:]))
            elif section == 'goals' and line:
                parts = line.split()
                goals.append((parts[0], parts[1:]))

        if name and points and premises and goals:
            problems.append({
                'name': name,
                'points': points,
                'premises': premises,
                'goals': goals
            })

    return problems


def test_with_custom_rules():
    """Test CSolver with and without custom rules."""
    benchmark_file = '/root/GenesisGeo/benchmarks/coords/hageo_409_coords.txt'

    print("Loading problems...")
    problems = load_problems(benchmark_file, limit=5)
    print(f"Loaded {len(problems)} problems")

    # Custom rules to test
    custom_rules = [
        "cong a b c d => cong c d a b",  # congruence symmetry
        "para a b c d => para c d a b",  # parallel symmetry
    ]

    results_without = []
    results_with = []

    for prob in problems:
        print(f"\nTesting: {prob['name']}")

        # Without custom rules
        t0 = time.time()
        try:
            solved1, _ = DDAR.run_ddar(
                prob['name'],
                prob['points'],
                prob['premises'],
                prob['goals'],
                500, True, True
            )
            time1 = time.time() - t0
            results_without.append({'name': prob['name'], 'solved': solved1, 'time': time1})
            print(f"  Without custom rules: solved={solved1}, time={time1:.3f}s")
        except Exception as e:
            print(f"  Without custom rules: ERROR - {e}")
            results_without.append({'name': prob['name'], 'solved': False, 'time': 0, 'error': str(e)})

        # With custom rules
        t0 = time.time()
        try:
            solved2, _ = DDAR.run_ddar_with_rules(
                prob['name'],
                prob['points'],
                prob['premises'],
                prob['goals'],
                custom_rules,
                500, True, True
            )
            time2 = time.time() - t0
            results_with.append({'name': prob['name'], 'solved': solved2, 'time': time2})
            print(f"  With custom rules: solved={solved2}, time={time2:.3f}s")
        except Exception as e:
            print(f"  With custom rules: ERROR - {e}")
            results_with.append({'name': prob['name'], 'solved': False, 'time': 0, 'error': str(e)})

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    solved_without = sum(1 for r in results_without if r.get('solved', False))
    solved_with = sum(1 for r in results_with if r.get('solved', False))

    print(f"Without custom rules: {solved_without}/{len(problems)} solved")
    print(f"With custom rules: {solved_with}/{len(problems)} solved")

    return solved_without == solved_with  # Should be the same for these simple rules


if __name__ == "__main__":
    success = test_with_custom_rules()
    print(f"\nTest {'PASSED' if success else 'FAILED'}")
    sys.exit(0 if success else 1)
