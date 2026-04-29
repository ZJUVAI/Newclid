#!/usr/bin/env python3
"""Analyze proposal distribution from evaluation traces."""
import json
import sys
from pathlib import Path
from collections import Counter
import math

def extract_constructions(trace_dir):
    """Extract construction types from all problem traces (candidate_transition events)."""
    all_constructions = []
    per_problem = {}

    trace_dir = Path(trace_dir)
    for problem_file in sorted(trace_dir.glob('*.jsonl')):
        problem_name = problem_file.stem
        constructions = []

        with open(problem_file) as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if entry.get('event') == 'candidate_transition' and 'construction_text' in entry:
                        constructions.append(entry['construction_text'])
                except:
                    continue

        if constructions:
            per_problem[problem_name] = constructions
            all_constructions.extend(constructions)

    return all_constructions, per_problem

def classify_construction(text):
    """Classify construction by family."""
    t = text.lower()
    if 'on_circum' in t:
        return 'on_circum'
    elif 'on_circle' in t:
        return 'on_circle'
    elif 'on_tline' in t:
        return 'on_tline'
    elif 'on_bline' in t:
        return 'on_bline'
    elif 'on_line' in t:
        return 'on_line'
    elif 'eqdistance' in t:
        return 'eqdistance'
    elif 'midp' in t:
        return 'midp'
    elif 'foot' in t:
        return 'foot'
    elif 'reflect' in t:
        return 'reflect'
    elif 'angle_bisector' in t:
        return 'angle_bisector'
    elif 'inter' in t:
        return 'intersect'
    else:
        return 'other'

def diversity_metrics(constructions):
    """Compute unique_ratio, top1_share, effective_ratio (Shannon entropy based)."""
    if not constructions:
        return None
    counter = Counter(constructions)
    n = len(constructions)
    unique_ratio = len(counter) / n
    top1_share = counter.most_common(1)[0][1] / n
    # Shannon entropy -> effective count -> ratio
    entropy = -sum((c/n) * math.log(c/n) for c in counter.values())
    effective_ratio = math.exp(entropy) / n
    return unique_ratio, top1_share, effective_ratio

def analyze(trace_dir, label):
    all_constructions, per_problem = extract_constructions(trace_dir)

    if not all_constructions:
        print(f"{label}: no constructions found")
        return {}

    # Per-problem diversity
    unique_ratios, top1_shares, eff_ratios = [], [], []
    for constructions in per_problem.values():
        m = diversity_metrics(constructions)
        if m:
            unique_ratios.append(m[0])
            top1_shares.append(m[1])
            eff_ratios.append(m[2])

    mean_unique = sum(unique_ratios) / len(unique_ratios)
    mean_top1 = sum(top1_shares) / len(top1_shares)
    mean_eff = sum(eff_ratios) / len(eff_ratios)

    # Family distribution
    families = [classify_construction(c) for c in all_constructions]
    counter = Counter(families)
    total = len(families)

    print(f"\n=== {label} ===")
    print(f"Total constructions: {total}  Problems: {len(per_problem)}")
    print(f"mean_unique_ratio:   {mean_unique:.4f}")
    print(f"mean_top1_share:     {mean_top1:.4f}")
    print(f"mean_effective_ratio:{mean_eff:.4f}")
    print("Family distribution:")
    for family, count in counter.most_common():
        print(f"  {family:15s}: {count:6d}  ({count/total*100:5.2f}%)")

    return {
        'total': total,
        'mean_unique_ratio': mean_unique,
        'mean_top1_share': mean_top1,
        'mean_effective_ratio': mean_eff,
        'family_pct': {f: count/total*100 for f, count in counter.items()},
    }

if __name__ == '__main__':
    BASE = Path('/C20545/home/wangzi/GenesisGeo-grpo/results')

    sft_dir  = BASE / 'devimo_grpo_compare/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_vlm_sft44_checkpoint-20084_d32_b512_s4_gbs2_gbt100_seed123_20260417T052620Z/problems'
    grpo505_dir = BASE / 'devimo_grpo_compare/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v1-20260417-084328_checkpoint-505_sv1_d32_b512_s4_gbs2_gbt100_seed123_20260418T035755Z/problems'
    v16_dir  = BASE / 'v16_lr5e6_checkpoint500/eval_single_problem_multi_gpu_vlm_dev_imo_v0-20260422-154539_checkpoint-500_sv1_d32_b512_s4_gbs2_gbt100_seed123_20260422T134636Z/problems'
    v17_dir  = BASE / 'v17_lr5e6_checkpoint500/eval_single_problem_multi_gpu_vlm_dev_imo_v0-20260423-165556_checkpoint-500_sv1_d32_b512_s4_gbs2_gbt100_seed123_20260423T112909Z/problems'

    results = {}
    for label, d in [('SFT baseline', sft_dir), ('GRPO505 sv1', grpo505_dir), ('v16 ckpt-500', v16_dir), ('v17 ckpt-500', v17_dir)]:
        if Path(d).exists():
            results[label] = analyze(str(d), label)
        else:
            print(f"\n{label}: directory not found: {d}")

    # Summary comparison table
    print("\n\n=== COMPARISON TABLE ===")
    print(f"{'Metric':<22}", end='')
    for label in results:
        print(f"  {label:<16}", end='')
    print()
    for metric in ['mean_unique_ratio', 'mean_top1_share', 'mean_effective_ratio']:
        print(f"{metric:<22}", end='')
        for r in results.values():
            print(f"  {r.get(metric, 0):<16.4f}", end='')
        print()

    print(f"\n{'Family':<22}", end='')
    for label in results:
        print(f"  {label:<16}", end='')
    print()
    all_families = sorted(set(f for r in results.values() for f in r.get('family_pct', {})))
    for family in all_families:
        print(f"{family:<22}", end='')
        for r in results.values():
            pct = r.get('family_pct', {}).get(family, 0)
            print(f"  {pct:<16.2f}", end='')
        print()
