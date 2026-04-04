#!/usr/bin/env python3
"""
Split multi-fact Tong Geometry cases into separate JGEX problems.

For cases that have multiple Fact() lines, this script generates one JGEX
problem per fact, reusing the same construction but with different goals.
"""

import re
import sys
from pathlib import Path
from typing import List, Tuple


def parse_tong_case(case_file: Path) -> Tuple[str, List[str]]:
    """
    Parse a Tong case file and extract all Fact lines.

    Returns:
        (case_name, list_of_fact_lines)
    """
    content = case_file.read_text()
    lines = content.strip().split('\n')

    # Extract case name from first comment or filename
    case_name = case_file.stem

    # Find all Fact lines
    facts = []
    for line in lines:
        line = line.strip()
        if line.startswith('Fact('):
            facts.append(line)

    return case_name, facts


def parse_jgex_problem(jgex_line: str) -> Tuple[str, str, str]:
    """
    Parse a JGEX problem line into (name, construction, goal).

    Example input:
        case24_nine_point_circle
        c b a = triangle c b a; ... ? cong v d v e

    Returns:
        (name, construction_part, goal_part)
    """
    parts = jgex_line.split('?')
    if len(parts) != 2:
        raise ValueError(f"Invalid JGEX format: {jgex_line}")

    construction = parts[0].strip()
    goal = parts[1].strip()

    return construction, goal


def convert_fact_to_jgex_goal(fact_line: str) -> str:
    """
    Convert a Tong Fact() line to JGEX goal format.

    Examples:
        Fact("perp", [Angle(*"DGH")]) → perp d g g h
        Fact("cong", [Segment(*"VD"), Segment(*"VE")]) → cong v d v e
        Fact("eqcircle", [Circle(None, [*"LMN"]), Circle(None, [*"LMN"])]) → (complex, needs analysis)
    """
    # Extract predicate type
    pred_match = re.search(r'Fact\("(\w+)"', fact_line)
    if not pred_match:
        return None

    predicate = pred_match.group(1)

    # Extract point sequences
    # Pattern: *"ABC" extracts ABC
    point_seqs = re.findall(r'\*"([A-Za-z]+)"', fact_line)

    if not point_seqs:
        return None

    # Convert to lowercase and join
    jgex_points = ' '.join(' '.join(seq.lower()) for seq in point_seqs)

    return f"{predicate} {jgex_points}"


def main():
    # Paths
    tong_cases_dir = Path("datasets/mo_tg_225/tong_geometry_cases")
    v1_jgex_file = Path("datasets/mo_tg_225/mo_tg_225_draft.txt")
    output_file = Path("datasets/mo_tg_225/mo_tg_225_multi_fact.txt")
    report_file = Path("datasets/mo_tg_225/multi_fact_split_report.md")

    # Multi-fact cases (from earlier analysis)
    multi_fact_cases = [
        24, 29, 40, 51, 56, 61, 64, 67, 68, 77, 78, 91, 98, 99,
        102, 120, 142, 150, 163, 167
    ]

    # Load v1 JGEX (name → jgex_line mapping)
    v1_jgex = {}
    if v1_jgex_file.exists():
        lines = v1_jgex_file.read_text().strip().split('\n')
        for i in range(0, len(lines), 2):
            if i + 1 < len(lines):
                name = lines[i].strip()
                jgex = lines[i + 1].strip()
                v1_jgex[name] = jgex

    print(f"Loaded {len(v1_jgex)} existing JGEX problems from v1")

    # Process multi-fact cases
    new_problems = []
    stats = {
        'processed': 0,
        'facts_extracted': 0,
        'new_problems': 0,
        'failed': []
    }

    for case_num in multi_fact_cases:
        case_file = tong_cases_dir / f"case{case_num}.txt"
        if not case_file.exists():
            stats['failed'].append((case_num, "File not found"))
            continue

        # Parse Tong case
        case_name, facts = parse_tong_case(case_file)
        stats['processed'] += 1
        stats['facts_extracted'] += len(facts)

        if len(facts) <= 1:
            print(f"Warning: case{case_num} has {len(facts)} facts, expected >1")
            continue

        # Find corresponding v1 JGEX
        v1_key = None
        for key in v1_jgex:
            if key.startswith(f"case{case_num}"):
                v1_key = key
                break

        if not v1_key:
            stats['failed'].append((case_num, "No v1 JGEX found"))
            print(f"Warning: No v1 JGEX found for case{case_num}")
            continue

        v1_jgex_line = v1_jgex[v1_key]

        try:
            construction, v1_goal = parse_jgex_problem(v1_jgex_line)
        except ValueError as e:
            stats['failed'].append((case_num, str(e)))
            print(f"Error parsing v1 JGEX for case{case_num}: {e}")
            continue

        # Generate one JGEX problem per fact
        for fact_idx, fact_line in enumerate(facts, start=1):
            jgex_goal = convert_fact_to_jgex_goal(fact_line)

            if not jgex_goal:
                print(f"Warning: Could not convert fact {fact_idx} in case{case_num}: {fact_line}")
                continue

            # Generate problem name
            if fact_idx == 1:
                problem_name = f"case{case_num}_fact1"
            else:
                problem_name = f"case{case_num}_fact{fact_idx}"

            # Generate JGEX line
            jgex_line = f"{construction} ? {jgex_goal}"

            new_problems.append((problem_name, jgex_line))
            stats['new_problems'] += 1

            print(f"Generated: {problem_name} ({len(jgex_goal.split())} tokens)")

    # Write output
    with output_file.open('w') as f:
        for name, jgex in new_problems:
            f.write(f"{name}\n{jgex}\n")

    # Write report
    with report_file.open('w') as f:
        f.write("# Multi-Fact Split Report\n\n")
        f.write(f"**Date**: {Path(__file__).stat().st_mtime}\n\n")
        f.write("## Summary\n\n")
        f.write(f"- Cases processed: {stats['processed']}\n")
        f.write(f"- Total facts extracted: {stats['facts_extracted']}\n")
        f.write(f"- New JGEX problems generated: {stats['new_problems']}\n")
        f.write(f"- Failed: {len(stats['failed'])}\n\n")

        if stats['failed']:
            f.write("## Failed Cases\n\n")
            for case_num, reason in stats['failed']:
                f.write(f"- case{case_num}: {reason}\n")

    print(f"\nConversion complete!")
    print(f"  Processed: {stats['processed']} cases")
    print(f"  Generated: {stats['new_problems']} new JGEX problems")
    print(f"  Output: {output_file}")
    print(f"  Report: {report_file}")


if __name__ == '__main__':
    main()
