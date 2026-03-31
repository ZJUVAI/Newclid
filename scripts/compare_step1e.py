#!/usr/bin/env python3
"""
Step 1e 规则规范化 + 去重 对比脚本

将 Step 1e 前后数据对应起来，生成联合报告。
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple


def load_normalized_rules(path: Path) -> Dict[str, dict]:
    """Load normalized rules JSON and build pid -> rule mapping."""
    with open(path, 'r', encoding='utf-8') as f:
        rules = json.load(f)
    return {rule['pid']: rule for rule in rules}


def load_stats(path: Path) -> Tuple[List[dict], List[dict], List[dict]]:
    """Load stats JSON and extract entries, dedup_groups, skipped_entries."""
    with open(path, 'r', encoding='utf-8') as f:
        stats = json.load(f)

    # Extract entries (kept rules with rid)
    entries = []
    if 'entries' in stats:
        entries = stats['entries']

    # Extract dedup groups
    dedup_groups = stats.get('dedup_groups', [])

    # Extract skipped entries
    skipped_entries = stats.get('skipped_entries', [])

    return entries, dedup_groups, skipped_entries


def build_pid_to_rid_map(entries: List[dict]) -> Dict[str, str]:
    """Build mapping from pid to rid."""
    return {entry['pid']: entry['rid'] for entry in entries}


def generate_report(
    normalized_rules: Dict[str, dict],
    entries: List[dict],
    dedup_groups: List[dict],
    skipped_entries: List[dict],
    stats: dict,
    output_path: Path
) -> None:
    """Generate human-readable comparison report."""
    with open(output_path, 'w', encoding='utf-8') as f:
        # Header
        f.write("=== Step 1e 规则规范化 + 去重 对比报告 ===\n")
        f.write(f"输入: {stats.get('input_rules_raw', 0)} 条原始规则\n")
        f.write(f"输出: {stats.get('output_rules_deduped', 0)} 条去重后规则\n")
        f.write(f"跳过: {stats.get('skipped_rules', 0)} 条 (missing_points)\n")

        # Calculate dedup count
        total_deduped = sum(g['count'] - 1 for g in dedup_groups if g['count'] > 1)
        num_dedup_groups = sum(1 for g in dedup_groups if g['count'] > 1)
        f.write(f"去重: {total_deduped} 条 ({num_dedup_groups} 个去重组)\n\n")

        # Part 1: Kept rules
        f.write("─" * 40 + "\n")
        f.write("保留的规则 (按 rid 排序):\n")
        f.write("─" * 40 + "\n\n")

        for entry in sorted(entries, key=lambda x: x['rid']):
            rid = entry['rid']
            pid = entry['pid']
            rule_info = normalized_rules.get(pid, {})

            f.write(f"[保留] {rid} (pid={pid})\n")
            f.write(f"  原始规则: {rule_info.get('original', 'N/A')}\n")
            f.write(f"  规范化后: {rule_info.get('normalized', 'N/A')}\n")
            f.write(f"  签名: {rule_info.get('signature', 'N/A')}\n")
            f.write("\n" + "─" * 40 + "\n\n")

        # Part 2: Dedup groups
        if num_dedup_groups > 0:
            f.write("=" * 40 + "\n")
            f.write("去重组详情:\n")
            f.write("=" * 40 + "\n\n")

            group_idx = 1
            for group in dedup_groups:
                if group['count'] <= 1:
                    continue

                f.write(f"去重组 #{group_idx} (hash={group['hash']}, 共 {group['count']} 条规则)\n")
                f.write(f"  规范化形式: {group['normalized']}\n\n")

                # First rule is kept
                first_rule = group['rules'][0]
                f.write(f"  [保留] pid={first_rule['pid']}\n")
                f.write(f"    原始: {first_rule['original']}\n\n")

                # Rest are removed
                for rule in group['rules'][1:]:
                    f.write(f"  [去掉] pid={rule['pid']}\n")
                    f.write(f"    原始: {rule['original']}\n")
                    f.write(f"    原因: 规范化后与 pid={first_rule['pid']} 的规则相同 (SHA256 哈希一致)\n\n")

                f.write("=" * 40 + "\n\n")
                group_idx += 1

        # Part 3: Skipped rules
        f.write("=" * 40 + "\n")
        f.write("跳过的规则 (missing_points):\n")
        f.write("=" * 40 + "\n\n")

        if skipped_entries:
            for entry in skipped_entries:
                f.write(f"  pid={entry.get('pid', 'N/A')}\n")
                f.write(f"    原因: {entry.get('reason', 'N/A')}\n")
                f.write(f"    规则: {entry.get('rule', 'N/A')}\n\n")
        else:
            f.write("  (无)\n\n")


def main():
    parser = argparse.ArgumentParser(
        description="Compare Step 1e input/output data and generate report"
    )
    parser.add_argument(
        '--experiment',
        type=str,
        default='outputs/experiments/20260308_step1e_enhanced_symmetry',
        help='Experiment directory path'
    )
    args = parser.parse_args()

    exp_dir = Path(args.experiment)
    intermediates_dir = exp_dir / 'intermediates'

    # Load data
    print("Loading normalized rules...")
    normalized_rules = load_normalized_rules(
        intermediates_dir / 'step1e_normalized_rules.json'
    )

    print("Loading stats...")
    with open(intermediates_dir / 'step1e_rules_stats.json', 'r', encoding='utf-8') as f:
        stats = json.load(f)

    entries, dedup_groups, skipped_entries = load_stats(
        intermediates_dir / 'step1e_rules_stats.json'
    )

    # Generate report
    output_path = exp_dir / 'step1e_comparison.txt'
    print(f"Generating report to {output_path}...")
    generate_report(
        normalized_rules,
        entries,
        dedup_groups,
        skipped_entries,
        stats,
        output_path
    )

    print(f"Report generated: {output_path}")
    print(f"  Input rules: {stats.get('input_rules_raw', 0)}")
    print(f"  Output rules: {stats.get('output_rules_deduped', 0)}")
    print(f"  Skipped: {stats.get('skipped_rules', 0)}")
    print(f"  Dedup groups: {sum(1 for g in dedup_groups if g['count'] > 1)}")


if __name__ == '__main__':
    main()

