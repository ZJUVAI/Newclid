#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate Synthetic Discovery Data

This script generates synthetic data in the format expected by FilterAndPruneEngine
for testing the discovery pipeline. It uses rules from tmp_rules.txt as templates
to create problems with auxiliary point constructions.

The generated data format:
{
    "problem_id": "unique_id",
    "llm_input_renamed": "<problem>pred1 arg1 arg2 [000] ; pred2 arg3 arg4 [001] ; ? goal_pred args</problem>",
    "llm_output_renamed": "<aux>x1 aux_name construction [NNN] ; </aux><proof>conclusion [NNN] rule_id [premise_ids] ; </proof>",
    "aux_points": ["aux_name"]
}
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def parse_rule_file(path: Path) -> List[Tuple[str, str, str]]:
    """Parse rules from tmp_rules.txt format.

    Format:
        r52 Properties of similar triangles (Direct)
        simtri A B C P Q R => eqangle B A B C Q P Q R, eqratio B A B C Q P Q R

    Returns: List of (rule_id, description, rule_text) tuples
    """
    if not path.exists():
        raise FileNotFoundError(f"Rules file not found: {path}")

    lines = path.read_text(encoding="utf-8").strip().split("\n")
    rules: List[Tuple[str, str, str]] = []

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        # Check if this is a description line (starts with 'r' followed by digits and description)
        match = re.match(r"^(r\d+)\s+(.+)$", line)
        if match:
            rule_id = match.group(1)
            description = match.group(2)
            if i + 1 < len(lines):
                rule_text = lines[i + 1].strip()
                if "=>" in rule_text:
                    rules.append((rule_id, description, rule_text))
                i += 2
            else:
                i += 1
        # Check for numbered lines like "0sub_0"
        elif re.match(r"^\d+sub_\d+$", line):
            rule_id = line
            description = f"Discovered rule {line}"
            if i + 1 < len(lines):
                rule_text = lines[i + 1].strip()
                if "=>" in rule_text:
                    rules.append((rule_id, description, rule_text))
                i += 2
            else:
                i += 1
        else:
            i += 1

    return rules


def split_rule(rule_text: str) -> Tuple[List[Tuple[str, List[str]]], List[Tuple[str, List[str]]]]:
    """Split rule into premises and conclusions.

    Example: "cong a b c d, para e f g h => coll i j k"
    Returns: ([('cong', ['a', 'b', 'c', 'd']), ...], [('coll', ['i', 'j', 'k'])])
    """
    if "=>" not in rule_text:
        return [], []

    left, right = rule_text.split("=>", 1)

    def parse_clauses(text: str) -> List[Tuple[str, List[str]]]:
        clauses = []
        for clause in text.split(","):
            parts = clause.strip().split()
            if parts:
                pred = parts[0].lower()
                args = [a.lower() for a in parts[1:]]
                clauses.append((pred, args))
        return clauses

    premises = parse_clauses(left)
    conclusions = parse_clauses(right)

    return premises, conclusions


def collect_points(clauses: List[Tuple[str, List[str]]]) -> List[str]:
    """Collect all unique point names from clauses."""
    points = []
    for _, args in clauses:
        for arg in args:
            # Skip numeric values like "1/2"
            if re.match(r"^[a-z][a-z0-9_]*$", arg) and arg not in points:
                points.append(arg)
    return points


def generate_synthetic_sample(
    rule_id: str,
    rule_text: str,
    sample_idx: int,
    seed: int,
) -> Optional[Dict[str, Any]]:
    """Generate a synthetic sample from a rule.

    The strategy:
    1. Parse the rule into premises and conclusions
    2. Create a new auxiliary point that is NOT in the original rule
    3. Generate a problem where the premises are given and the conclusion needs to be proven
    4. Create a fake proof trace showing how the conclusion was derived
    """
    random.seed(seed + sample_idx)

    premises, conclusions = split_rule(rule_text)
    if not premises or not conclusions:
        return None

    # Collect all points from the rule
    all_points = collect_points(premises + conclusions)
    if len(all_points) < 3:
        return None

    # Create a NEW auxiliary point that is NOT in the original rule
    # Use a name like 'x', 'y', 'z', 'w' that is unlikely to conflict
    aux_candidates = ['x', 'y', 'z', 'w', 'u', 'v', 'm', 'n']
    aux_point = None
    for candidate in aux_candidates:
        if candidate not in all_points:
            aux_point = candidate
            break

    if aux_point is None:
        # Fallback: use a numbered name
        aux_point = f"aux{sample_idx}"

    # Generate problem_id
    problem_id = f"synth_{rule_id}_{sample_idx:06d}"

    # Build llm_input_renamed (problem statement)
    # Format: <problem>pred1 arg1 arg2 [000] ; pred2 arg3 arg4 [001] ; ? goal_pred args</problem>
    problem_parts = []
    for idx, (pred, args) in enumerate(premises):
        clause = f"{pred} {' '.join(args)} [{idx:03d}]"
        problem_parts.append(clause)

    # Add goal (first conclusion)
    goal_pred, goal_args = conclusions[0]
    goal_str = f"? {goal_pred} {' '.join(goal_args)}"

    llm_input = f"<problem>{' ; '.join(problem_parts)} ; {goal_str}</problem>"

    # Build llm_output_renamed
    # Format: <aux>x1 aux_name construction [NNN] ; </aux><proof>conclusion [NNN] rule_id [premise_ids] ; </proof>

    # Create a simple auxiliary construction using the new aux point
    # The aux point is constructed from existing points
    aux_idx = len(premises)
    base_point1 = all_points[0] if len(all_points) > 0 else 'a'
    base_point2 = all_points[1] if len(all_points) > 1 else 'b'
    aux_construction = f"x1 {aux_point} on_line {base_point1} {base_point2} [{aux_idx:03d}]"

    # Create proof trace
    # Format: conclusion [NNN] rule_code [premise_id1] [premise_id2] ...
    proof_idx = aux_idx + 1
    premise_ids = " ".join([f"[{i:03d}]" for i in range(len(premises))])
    proof_conclusion = f"{goal_pred} {' '.join(goal_args)} [{proof_idx:03d}] {rule_id} {premise_ids}"

    llm_output = f"<aux>{aux_construction} ; </aux><proof>{proof_conclusion} ; </proof>"

    return {
        "problem_id": problem_id,
        "llm_input_renamed": llm_input,
        "llm_output_renamed": llm_output,
        "aux_points": [aux_point],
    }


def generate_samples_from_rules(
    rules: List[Tuple[str, str, str]],
    num_samples: int,
    seed: int,
) -> List[Dict[str, Any]]:
    """Generate synthetic samples from rules.

    Args:
        rules: List of (rule_id, description, rule_text) tuples
        num_samples: Total number of samples to generate
        seed: Random seed

    Returns:
        List of synthetic samples
    """
    random.seed(seed)

    samples = []
    samples_per_rule = max(1, num_samples // len(rules))

    for rule_idx, (rule_id, description, rule_text) in enumerate(rules):
        for sample_idx in range(samples_per_rule):
            sample = generate_synthetic_sample(
                rule_id,
                rule_text,
                rule_idx * samples_per_rule + sample_idx,
                seed,
            )
            if sample:
                samples.append(sample)

            if len(samples) >= num_samples:
                break

        if len(samples) >= num_samples:
            break

    # If we need more samples, cycle through rules again
    while len(samples) < num_samples:
        rule_idx = len(samples) % len(rules)
        rule_id, description, rule_text = rules[rule_idx]
        sample = generate_synthetic_sample(
            rule_id,
            rule_text,
            len(samples),
            seed + len(samples),
        )
        if sample:
            samples.append(sample)

    return samples[:num_samples]


def main():
    parser = argparse.ArgumentParser(
        description="Generate synthetic discovery data for pipeline testing"
    )
    parser.add_argument(
        "--rules", "-r",
        type=str,
        default="datasets/candidate_rules/tmp_rules.txt",
        help="Path to rules file (default: datasets/candidate_rules/tmp_rules.txt)"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        required=True,
        help="Output JSONL file path"
    )
    parser.add_argument(
        "--num_samples", "-n",
        type=int,
        default=1000,
        help="Number of samples to generate (default: 1000)"
    )
    parser.add_argument(
        "--seed", "-s",
        type=int,
        default=42,
        help="Random seed (default: 42)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print verbose output"
    )

    args = parser.parse_args()

    rules_path = Path(args.rules)
    output_path = Path(args.output)

    # Parse rules
    print(f"[generate] Loading rules from {rules_path}")
    rules = parse_rule_file(rules_path)
    print(f"[generate] Loaded {len(rules)} rules")

    if args.verbose:
        for rule_id, desc, rule_text in rules[:5]:
            print(f"  {rule_id}: {desc[:50]}...")

    # Generate samples
    print(f"[generate] Generating {args.num_samples} samples...")
    samples = generate_samples_from_rules(rules, args.num_samples, args.seed)
    print(f"[generate] Generated {len(samples)} samples")

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for sample in samples:
            json.dump(sample, f, ensure_ascii=False)
            f.write("\n")

    print(f"[generate] Wrote {len(samples)} samples to {output_path}")

    # Print sample statistics
    if args.verbose:
        print("\n[generate] Sample statistics:")
        rule_counts: Dict[str, int] = {}
        for sample in samples:
            pid = sample["problem_id"]
            rule_id = pid.split("_")[1]
            rule_counts[rule_id] = rule_counts.get(rule_id, 0) + 1

        print(f"  Unique rules used: {len(rule_counts)}")
        top_rules = sorted(rule_counts.items(), key=lambda x: -x[1])[:5]
        print(f"  Top 5 rules: {top_rules}")


if __name__ == "__main__":
    main()
