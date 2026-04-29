#!/usr/bin/env python3
"""Compare imo_95 results between two versions."""
import csv
import sys
from pathlib import Path

def load_results(csv_path):
    """Load results from CSV file."""
    results = {}
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            problem = row['Problem Name']
            solved = row['Solved']
            time = row['Time (s)']
            results[problem] = {'solved': solved, 'time': time}
    return results

def compare_results(v16_csv, v17_csv):
    """Compare results between v16 and v17."""
    v16 = load_results(v16_csv)
    v17 = load_results(v17_csv)

    # Find differences
    v17_new_solved = []
    v16_regression = []

    for problem in v16:
        if problem not in v17:
            continue
        v16_solved = v16[problem]['solved'] == '√'
        v17_solved = v17[problem]['solved'] == '√'

        if v17_solved and not v16_solved:
            v17_new_solved.append(problem)
        elif v16_solved and not v17_solved:
            v16_regression.append(problem)

    return v17_new_solved, v16_regression

if __name__ == '__main__':
    v16_csv = sys.argv[1]
    v17_csv = sys.argv[2]

    new_solved, regressions = compare_results(v16_csv, v17_csv)

    print(f"v17 新增解题 (+{len(new_solved)}):")
    for p in new_solved:
        print(f"  - {p}")

    print(f"\nv17 回退题 (-{len(regressions)}):")
    for p in regressions:
        print(f"  - {p}")

    print(f"\n净提升: {len(new_solved) - len(regressions)} 题")
