#!/usr/bin/env python3
"""
Extract problems containing specific construction patterns from dataset.
"""
import json
import argparse
from pathlib import Path


def extract_problems_with_construction(
    input_jsonl: Path,
    output_jsonl: Path,
    construction_pattern: str
):
    """
    Extract problems containing the specified construction pattern.

    Args:
        input_jsonl: Path to input JSONL file
        output_jsonl: Path to output JSONL file
        construction_pattern: Construction pattern to search for (e.g., "risos a b c")
    """
    matched_problems = []
    total_count = 0

    with open(input_jsonl, 'r') as f:
        for line in f:
            total_count += 1
            problem = json.loads(line.strip())
            fl_problem = problem.get('fl_problem', '')

            # Check if construction pattern exists in fl_problem
            if construction_pattern in fl_problem:
                matched_problems.append(problem)

    # Write matched problems to output file
    with open(output_jsonl, 'w') as f:
        for problem in matched_problems:
            f.write(json.dumps(problem) + '\n')

    print(f"Total problems scanned: {total_count}")
    print(f"Matched problems: {len(matched_problems)}")
    print(f"Match rate: {len(matched_problems)/total_count*100:.2f}%")
    print(f"Output written to: {output_jsonl}")

    return len(matched_problems)


def main():
    parser = argparse.ArgumentParser(
        description='Extract problems with specific construction patterns'
    )
    parser.add_argument(
        '--input',
        type=str,
        required=True,
        help='Input JSONL file path'
    )
    parser.add_argument(
        '--output',
        type=str,
        required=True,
        help='Output JSONL file path'
    )
    parser.add_argument(
        '--pattern',
        type=str,
        required=True,
        help='Construction pattern to search for'
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        return

    # Create output directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    extract_problems_with_construction(
        input_path,
        output_path,
        args.pattern
    )


if __name__ == '__main__':
    main()
