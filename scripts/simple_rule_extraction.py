#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple Rule Extraction - Extract rules directly from proof steps without complex graph analysis.

This is a simplified version that bypasses the missing proof_scout.core module.
"""

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple
import argparse


def parse_proof_step(step: str) -> Tuple[str, List[str], List[str]]:
    """
    Parse a single proof step to extract conclusion and premises.

    Format: predicate args [id] rule_name [premise_ids]
    Example: cyclic a b h i [006] r04 [005] [004]

    Returns:
        (conclusion, premises, rule_name)
    """
    # Match pattern: predicate args [id] rule_name [premise_ids...]
    match = re.match(r'([a-z]+)\s+([\w\s]+?)\s+\[(\d+)\]\s+([A-Z]+|r\d+)\s+((?:\[\d+\]\s*)+)', step.strip())

    if not match:
        return None, [], None

    predicate = match.group(1)
    args = match.group(2).strip().split()
    conclusion_id = match.group(3)
    rule_name = match.group(4)
    premise_ids_str = match.group(5)

    # Extract premise IDs
    premise_ids = re.findall(r'\[(\d+)\]', premise_ids_str)

    conclusion = f"{predicate} {' '.join(args)}"

    return conclusion, premise_ids, rule_name


def extract_rules_from_jsonl(input_file: Path, max_samples: int = None) -> Dict:
    """
    Extract rules from JSONL file containing proof data.

    Returns:
        Dict with extracted rules and statistics
    """
    rules = defaultdict(int)  # rule_pattern -> count
    rule_examples = defaultdict(list)  # rule_pattern -> examples
    total_problems = 0
    total_steps = 0
    skipped = 0

    with open(input_file, 'r') as f:
        for idx, line in enumerate(f):
            if max_samples and idx >= max_samples:
                break

            try:
                data = json.loads(line)
                total_problems += 1

                # Parse llm_input_renamed to get premises
                llm_input = data.get('llm_input_renamed', '')
                llm_output = data.get('llm_output_renamed', '')

                if not llm_output:
                    continue

                # Extract proof steps
                proof_match = re.search(r'<proof>(.*?)</proof>', llm_output, re.DOTALL)
                if not proof_match:
                    continue

                proof_text = proof_match.group(1)
                steps = [s.strip() for s in proof_text.split(';') if s.strip()]

                # Build statement map from input
                statements = {}  # id -> statement
                input_match = re.findall(r'([a-z]+\s+[\w\s]+?)\s+\[(\d+)\]', llm_input)
                for stmt, stmt_id in input_match:
                    statements[stmt_id] = stmt.strip()

                # Process each proof step
                for step in steps:
                    total_steps += 1
                    conclusion, premise_ids, rule_name = parse_proof_step(step)

                    if not conclusion or not premise_ids:
                        skipped += 1
                        continue

                    # Get premise statements
                    premises = []
                    for pid in premise_ids:
                        if pid in statements:
                            premises.append(statements[pid])

                    if not premises:
                        skipped += 1
                        continue

                    # Create rule pattern
                    rule_pattern = f"{', '.join(premises)} => {conclusion}"
                    rules[rule_pattern] += 1

                    # Store example (keep first 3)
                    if len(rule_examples[rule_pattern]) < 3:
                        rule_examples[rule_pattern].append({
                            'problem_id': idx,
                            'step': step,
                            'rule_name': rule_name
                        })

                    # Add conclusion to statements for next steps
                    # Extract conclusion ID
                    concl_match = re.search(r'\[(\d+)\]', step)
                    if concl_match:
                        statements[concl_match.group(1)] = conclusion

            except Exception as e:
                print(f"Error processing line {idx}: {e}")
                continue

    return {
        'rules': dict(rules),
        'rule_examples': dict(rule_examples),
        'total_problems': total_problems,
        'total_steps': total_steps,
        'skipped_steps': skipped,
        'unique_rules': len(rules)
    }


def save_rules(rules: Dict[str, int], output_file: Path, min_count: int = 2):
    """Save extracted rules to file, filtering by minimum count."""
    sorted_rules = sorted(rules.items(), key=lambda x: x[1], reverse=True)

    with open(output_file, 'w') as f:
        for rule, count in sorted_rules:
            if count >= min_count:
                f.write(f"{rule}\n")

    print(f"Saved {len([r for r, c in sorted_rules if c >= min_count])} rules to {output_file}")
    print(f"  (filtered from {len(rules)} total rules with min_count={min_count})")


def main():
    parser = argparse.ArgumentParser(description='Simple rule extraction from proof data')
    parser.add_argument('--input', '-i', required=True, help='Input JSONL file')
    parser.add_argument('--output', '-o', required=True, help='Output directory')
    parser.add_argument('--max_samples', type=int, help='Maximum samples to process')
    parser.add_argument('--min_count', type=int, default=2, help='Minimum rule count to keep')

    args = parser.parse_args()

    input_file = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Extracting rules from {input_file}")
    print(f"Output directory: {output_dir}")

    # Extract rules
    result = extract_rules_from_jsonl(input_file, args.max_samples)

    # Print statistics
    print(f"\n{'='*60}")
    print("Extraction Statistics")
    print(f"{'='*60}")
    print(f"Total problems: {result['total_problems']}")
    print(f"Total proof steps: {result['total_steps']}")
    print(f"Skipped steps: {result['skipped_steps']}")
    print(f"Unique rules extracted: {result['unique_rules']}")

    # Save rules
    rules_file = output_dir / "extracted_rules.txt"
    save_rules(result['rules'], rules_file, args.min_count)

    # Save statistics
    stats_file = output_dir / "extraction_stats.json"
    with open(stats_file, 'w') as f:
        json.dump({
            'total_problems': result['total_problems'],
            'total_steps': result['total_steps'],
            'skipped_steps': result['skipped_steps'],
            'unique_rules': result['unique_rules'],
            'top_10_rules': sorted(result['rules'].items(), key=lambda x: x[1], reverse=True)[:10]
        }, f, indent=2)

    print(f"\nStatistics saved to {stats_file}")
    print(f"\nTop 10 most frequent rules:")
    for rule, count in sorted(result['rules'].items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  [{count:4d}] {rule[:80]}...")


if __name__ == '__main__':
    main()
