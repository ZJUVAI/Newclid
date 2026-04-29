#!/usr/bin/env python3
"""
Quick sample GRPO training set based on structure features (no VLM labeling needed).

Usage:
    python scripts/grpo/quick_sample_by_structure.py \
        --input datasets/grpo_geometry100k_vlm_label_20260421_maxaux5/candidate_pool.jsonl \
        --output datasets/grpo_geometry100k_structure_sample_2k \
        --target_size 2000 \
        --seed 42

Strategy:
    - Stratified sampling by aux_points_total (30%/40%/30% for 1/2/3+ points)
    - Filter easy tail (aux_points=1 and n_premises<5)
    - Require aux_segment_count>=1
    - Goal predicate balance (max 18% per predicate)
    - Premise coverage (n_premises 2-25)
"""

import json
import random
import argparse
from pathlib import Path
from collections import Counter, defaultdict
from typing import List, Dict, Any
import sys


def load_candidate_pool(path: str) -> List[Dict[str, Any]]:
    """Load candidate pool from JSONL."""
    samples = []
    with open(path) as f:
        for line in f:
            samples.append(json.loads(line))
    return samples


def filter_samples(samples: List[Dict[str, Any]], config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Apply filtering constraints."""
    filtered = []

    for sample in samples:
        # Require aux_segment_count >= 1
        if sample.get('aux_segment_count', 0) < 1:
            continue

        # Filter easy tail: aux_points=1 and n_premises<5
        if config.get('filter_easy_tail', True):
            if sample.get('aux_points_total', 0) == 1 and sample.get('n_premises', 0) < 5:
                continue

        # Premise coverage: 2-25
        n_premises = sample.get('n_premises', 0)
        if n_premises < 2 or n_premises > 25:
            continue

        filtered.append(sample)

    return filtered


def stratified_sample(
    samples: List[Dict[str, Any]],
    target_size: int,
    strata_config: Dict[int, float],
    goal_cap: float = 0.18,
    seed: int = 42
) -> List[Dict[str, Any]]:
    """
    Stratified sampling by aux_points_total with goal predicate balance.

    Args:
        samples: Candidate pool
        target_size: Total samples to select
        strata_config: {aux_points: ratio}, e.g., {1: 0.3, 2: 0.4, 3: 0.3}
        goal_cap: Max ratio per goal_predicate
        seed: Random seed
    """
    random.seed(seed)

    # Group by aux_points_total
    strata = defaultdict(list)
    for sample in samples:
        aux_points = sample.get('aux_points_total', 0)
        # Map 3+ to 3
        if aux_points >= 3:
            aux_points = 3
        strata[aux_points].append(sample)

    # Calculate target per stratum
    selected = []
    for aux_points, ratio in sorted(strata_config.items()):
        target_count = int(target_size * ratio)
        pool = strata.get(aux_points, [])

        if len(pool) < target_count:
            print(f"Warning: aux_points={aux_points} has only {len(pool)} samples, need {target_count}")
            selected.extend(pool)
        else:
            # Sample with goal predicate balance
            sampled = sample_with_goal_balance(pool, target_count, goal_cap, seed + aux_points)
            selected.extend(sampled)

    return selected


def sample_with_goal_balance(
    pool: List[Dict[str, Any]],
    target_count: int,
    goal_cap: float,
    seed: int
) -> List[Dict[str, Any]]:
    """Sample from pool while maintaining goal predicate balance."""
    random.seed(seed)
    random.shuffle(pool)

    selected = []
    goal_counts = Counter()
    max_per_goal = int(target_count * goal_cap)

    for sample in pool:
        if len(selected) >= target_count:
            break

        goal = sample.get('goal_predicate', 'unknown')
        if goal_counts[goal] < max_per_goal:
            selected.append(sample)
            goal_counts[goal] += 1

    # If we didn't reach target (due to goal_cap), relax constraint
    if len(selected) < target_count:
        remaining = [s for s in pool if s not in selected]
        needed = target_count - len(selected)
        selected.extend(remaining[:needed])

    return selected


def generate_report(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate structure distribution report."""
    report = {
        'total_samples': len(samples),
        'aux_points_distribution': Counter(s.get('aux_points_total', 0) for s in samples),
        'aux_segment_distribution': Counter(s.get('aux_segment_count', 0) for s in samples),
        'goal_predicate_distribution': Counter(s.get('goal_predicate', 'unknown') for s in samples),
        'n_premises_stats': {
            'min': min(s.get('n_premises', 0) for s in samples),
            'max': max(s.get('n_premises', 0) for s in samples),
            'mean': sum(s.get('n_premises', 0) for s in samples) / len(samples),
        },
    }

    # Predicate family coverage
    family_counter = Counter()
    for sample in samples:
        for family in sample.get('predicate_family_tags', []):
            family_counter[family] += 1
    report['predicate_family_coverage'] = dict(family_counter)

    return report


def main():
    parser = argparse.ArgumentParser(description='Quick sample by structure features')
    parser.add_argument('--input', required=True, help='Input candidate pool JSONL')
    parser.add_argument('--output', required=True, help='Output directory')
    parser.add_argument('--target_size', type=int, default=2000, help='Target sample size')
    parser.add_argument('--seed', type=int, default=42, help='Random seed')
    parser.add_argument('--no_filter_easy_tail', action='store_true', help='Disable easy tail filter')
    parser.add_argument('--goal_cap', type=float, default=0.18, help='Max ratio per goal predicate')

    args = parser.parse_args()

    # Load candidate pool
    print(f"Loading candidate pool from {args.input}...")
    samples = load_candidate_pool(args.input)
    print(f"Loaded {len(samples)} samples")

    # Filter samples
    print("\nApplying filters...")
    config = {'filter_easy_tail': not args.no_filter_easy_tail}
    filtered = filter_samples(samples, config)
    print(f"After filtering: {len(filtered)} samples")

    # Stratified sampling (conservative config: 30%/40%/30%)
    print("\nStratified sampling...")
    strata_config = {1: 0.30, 2: 0.40, 3: 0.30}  # 3 means 3+
    selected = stratified_sample(
        filtered,
        args.target_size,
        strata_config,
        goal_cap=args.goal_cap,
        seed=args.seed
    )
    print(f"Selected {len(selected)} samples")

    # Generate report
    print("\nGenerating report...")
    report = generate_report(selected)

    # Create output directory
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write output
    output_jsonl = output_dir / 'grpo_train_structure_based.jsonl'
    with open(output_jsonl, 'w') as f:
        for sample in selected:
            f.write(json.dumps(sample, ensure_ascii=False) + '\n')
    print(f"Wrote {len(selected)} samples to {output_jsonl}")

    # Write report
    report_json = output_dir / 'structure_distribution_report.json'
    with open(report_json, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"Wrote report to {report_json}")

    # Write sampling log
    log_txt = output_dir / 'sampling_log.txt'
    with open(log_txt, 'w') as f:
        f.write(f"Input: {args.input}\n")
        f.write(f"Total candidates: {len(samples)}\n")
        f.write(f"After filtering: {len(filtered)}\n")
        f.write(f"Selected: {len(selected)}\n")
        f.write(f"Target size: {args.target_size}\n")
        f.write(f"Seed: {args.seed}\n")
        f.write(f"Filter easy tail: {not args.no_filter_easy_tail}\n")
        f.write(f"Goal cap: {args.goal_cap}\n")
        f.write(f"\nStrata config: {strata_config}\n")
        f.write(f"\nAux points distribution:\n")
        for k, v in sorted(report['aux_points_distribution'].items()):
            f.write(f"  {k}: {v} ({v/len(selected)*100:.1f}%)\n")
        f.write(f"\nGoal predicate distribution (top 10):\n")
        for goal, count in Counter(report['goal_predicate_distribution']).most_common(10):
            f.write(f"  {goal}: {count} ({count/len(selected)*100:.1f}%)\n")
    print(f"Wrote log to {log_txt}")

    # Print summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Total selected: {len(selected)}")
    print(f"\nAux points distribution:")
    for k, v in sorted(report['aux_points_distribution'].items()):
        print(f"  {k} points: {v:4d} ({v/len(selected)*100:5.1f}%)")
    print(f"\nPremise stats:")
    print(f"  Min: {report['n_premises_stats']['min']}")
    print(f"  Max: {report['n_premises_stats']['max']}")
    print(f"  Mean: {report['n_premises_stats']['mean']:.2f}")
    print(f"\nGoal predicate balance (top 5):")
    for goal, count in Counter(report['goal_predicate_distribution']).most_common(5):
        print(f"  {goal}: {count:4d} ({count/len(selected)*100:5.1f}%)")


if __name__ == '__main__':
    main()
