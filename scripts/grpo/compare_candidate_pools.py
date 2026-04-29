#!/usr/bin/env python3
"""
Compare two candidate pools to diagnose quality differences.

Usage:
    python compare_candidate_pools.py \
        --old datasets/v10_auxfix/.../candidate_pool.jsonl \
        --new datasets/maxaux5/candidate_pool.jsonl
"""

import json
import argparse
from collections import Counter
import numpy as np


def load_pool(path, limit=None):
    """Load candidate pool from jsonl."""
    samples = []
    with open(path) as f:
        for i, line in enumerate(f):
            if limit and i >= limit:
                break
            samples.append(json.loads(line))
    return samples


def analyze_pool(samples, name):
    """Analyze candidate pool statistics."""
    print(f"\n{'='*60}")
    print(f"{name} 候选池分析")
    print(f"{'='*60}")

    print(f"\n总样本数: {len(samples):,}")

    # 辅助点结构
    if 'aux_points_total' in samples[0]:
        aux_counts = [s['aux_points_total'] for s in samples]
        print(f"\n辅助点数量分布:")
        aux_dist = Counter(aux_counts)
        for k in sorted(aux_dist.keys()):
            cnt = aux_dist[k]
            pct = cnt / len(samples) * 100
            print(f"  {k} 个辅助点: {cnt:6,} ({pct:5.1f}%)")
        print(f"  平均: {np.mean(aux_counts):.2f}")
        print(f"  中位数: {np.median(aux_counts):.0f}")

    # 前提数量
    if 'n_premises' in samples[0]:
        n_premises = [s['n_premises'] for s in samples]
        print(f"\n前提数量分布:")
        print(f"  平均: {np.mean(n_premises):.2f}")
        print(f"  中位数: {np.median(n_premises):.0f}")
        print(f"  最小: {min(n_premises)}")
        print(f"  最大: {max(n_premises)}")

        # 分桶统计
        bins = [0, 2, 5, 10, 15, 20, 100]
        print(f"\n前提数量分桶:")
        for i in range(len(bins)-1):
            cnt = sum(1 for n in n_premises if bins[i] <= n < bins[i+1])
            pct = cnt / len(samples) * 100
            print(f"  [{bins[i]:2d}, {bins[i+1]:2d}): {cnt:6,} ({pct:5.1f}%)")

    # 谓词类型
    if 'goal_predicate' in samples[0]:
        goal_preds = [s['goal_predicate'] for s in samples]
        print(f"\n目标谓词分布 (top 10):")
        pred_dist = Counter(goal_preds)
        for pred, cnt in pred_dist.most_common(10):
            pct = cnt / len(samples) * 100
            print(f"  {pred:12s}: {cnt:6,} ({pct:5.1f}%)")

    # 谓词家族
    if 'predicate_family_tags' in samples[0]:
        all_families = []
        for s in samples:
            all_families.extend(s['predicate_family_tags'])
        print(f"\n谓词家族分布:")
        fam_dist = Counter(all_families)
        for fam, cnt in fam_dist.most_common():
            pct = cnt / len(samples) * 100
            print(f"  {fam:24s}: {cnt:6,} ({pct:5.1f}%)")


def compare_pools(old_samples, new_samples):
    """Compare two candidate pools."""
    print(f"\n{'='*60}")
    print("候选池对比")
    print(f"{'='*60}")

    print(f"\n样本数量:")
    print(f"  旧版本: {len(old_samples):,}")
    print(f"  新版本: {len(new_samples):,}")
    print(f"  变化:   {len(new_samples) - len(old_samples):+,} ({(len(new_samples)/len(old_samples)-1)*100:+.1f}%)")

    # 辅助点数量对比
    if 'aux_points_total' in old_samples[0] and 'aux_points_total' in new_samples[0]:
        old_aux = [s['aux_points_total'] for s in old_samples]
        new_aux = [s['aux_points_total'] for s in new_samples]

        print(f"\n辅助点数量:")
        print(f"  旧版本平均: {np.mean(old_aux):.2f}")
        print(f"  新版本平均: {np.mean(new_aux):.2f}")
        print(f"  变化:       {np.mean(new_aux) - np.mean(old_aux):+.2f}")

    # 前提数量对比
    if 'n_premises' in old_samples[0] and 'n_premises' in new_samples[0]:
        old_prem = [s['n_premises'] for s in old_samples]
        new_prem = [s['n_premises'] for s in new_samples]

        print(f"\n前提数量:")
        print(f"  旧版本平均: {np.mean(old_prem):.2f}")
        print(f"  新版本平均: {np.mean(new_prem):.2f}")
        print(f"  变化:       {np.mean(new_prem) - np.mean(old_prem):+.2f}")

    # 谓词分布对比
    if 'goal_predicate' in old_samples[0] and 'goal_predicate' in new_samples[0]:
        old_preds = Counter([s['goal_predicate'] for s in old_samples])
        new_preds = Counter([s['goal_predicate'] for s in new_samples])

        print(f"\n目标谓词分布变化 (top 10):")
        all_preds = set(old_preds.keys()) | set(new_preds.keys())
        pred_changes = []
        for pred in all_preds:
            old_cnt = old_preds.get(pred, 0)
            new_cnt = new_preds.get(pred, 0)
            old_pct = old_cnt / len(old_samples) * 100
            new_pct = new_cnt / len(new_samples) * 100
            delta = new_pct - old_pct
            pred_changes.append((pred, old_pct, new_pct, delta))

        pred_changes.sort(key=lambda x: abs(x[3]), reverse=True)
        for pred, old_pct, new_pct, delta in pred_changes[:10]:
            print(f"  {pred:12s}: {old_pct:5.1f}% → {new_pct:5.1f}% ({delta:+5.1f}%)")


def main():
    parser = argparse.ArgumentParser(description='Compare candidate pools')
    parser.add_argument('--old', required=True, help='Old candidate pool path')
    parser.add_argument('--new', required=True, help='New candidate pool path')
    parser.add_argument('--limit', type=int, help='Limit samples for quick analysis')
    args = parser.parse_args()

    print("加载候选池...")
    old_samples = load_pool(args.old, args.limit)
    new_samples = load_pool(args.new, args.limit)

    analyze_pool(old_samples, "旧版本")
    analyze_pool(new_samples, "新版本")
    compare_pools(old_samples, new_samples)


if __name__ == '__main__':
    main()
