#!/usr/bin/env python3
"""
Step 2 谓词验证 对比脚本

将 Step 2 前后数据对应起来，生成联合报告。
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict


def parse_rule_file(path: Path) -> Dict[str, str]:
    """Parse rule file with alternating ID and rule text lines."""
    rules = {}
    with open(path, 'r', encoding='utf-8') as f:
        lines = [line.rstrip('\n') for line in f]

    # Parse alternating lines: ID, rule, ID, rule, ...
    for i in range(0, len(lines), 2):
        if i + 1 < len(lines):
            rule_id = lines[i].strip()
            rule_text = lines[i + 1].strip()
            rules[rule_id] = rule_text

    return rules


def parse_skipped_file(path: Path) -> Dict[str, Tuple[str, List[str]]]:
    """Parse skipped rules file with ID+reason and rule text lines."""
    skipped = {}
    with open(path, 'r', encoding='utf-8') as f:
        lines = [line.rstrip('\n') for line in f]

    # Parse alternating lines: ID + reason, rule, ID + reason, rule, ...
    for i in range(0, len(lines), 2):
        if i + 1 < len(lines):
            # Parse "r0000 invalid_predicates=['aconst', 'aconst']"
            id_line = lines[i].strip()
            rule_text = lines[i + 1].strip()

            # Extract rule ID and invalid predicates
            parts = id_line.split(' ', 1)
            rule_id = parts[0]

            invalid_preds = []
            if len(parts) > 1 and 'invalid_predicates=' in parts[1]:
                # Extract list from string representation
                pred_str = parts[1].split('=', 1)[1]
                # Simple parsing: extract items between quotes
                import re
                invalid_preds = re.findall(r"'([^']+)'", pred_str)

            skipped[rule_id] = (rule_text, invalid_preds)

    return skipped


def generate_report(
    input_rules: Dict[str, str],
    output_rules: Dict[str, str],
    skipped_rules: Dict[str, Tuple[str, List[str]]],
    output_path: Path
) -> None:
    """Generate human-readable comparison report."""
    with open(output_path, 'w', encoding='utf-8') as f:
        # Header
        f.write("=== Step 2 谓词验证 对比报告 ===\n")
        f.write(f"输入: {len(input_rules)} 条规则 (来自 Step 1e)\n")
        f.write(f"输出: {len(output_rules)} 条通过验证\n")
        f.write(f"跳过: {len(skipped_rules)} 条 (含不支持谓词)\n\n")

        # Part 1: Passed rules
        f.write("─" * 40 + "\n")
        f.write("通过验证的规则 (按 rid 排序):\n")
        f.write("─" * 40 + "\n\n")

        for rid in sorted(output_rules.keys()):
            input_text = input_rules.get(rid, 'N/A')
            output_text = output_rules[rid]

            f.write(f"[通过] {rid}\n")
            f.write(f"  输入规则: {input_text}\n")
            f.write(f"  输出规则: {output_text}\n")

            # Check if rule changed
            if input_text != output_text and input_text != 'N/A':
                f.write("  变化: 规则文本已修改 (可能是点名重命名)\n")
            else:
                f.write("  (规则文本未变化)\n")

            f.write("\n" + "─" * 40 + "\n\n")

        # Part 2: Skipped rules
        f.write("=" * 40 + "\n")
        f.write("跳过的规则 (按 rid 排序):\n")
        f.write("=" * 40 + "\n\n")

        for rid in sorted(skipped_rules.keys()):
            rule_text, invalid_preds = skipped_rules[rid]
            input_text = input_rules.get(rid, 'N/A')

            f.write(f"[跳过] {rid}\n")
            f.write(f"  输入规则: {input_text}\n")
            f.write(f"  跳过原因: 含不支持谓词 {invalid_preds}\n")
            f.write("\n" + "=" * 40 + "\n\n")

        # Part 3: Skip reason statistics
        f.write("=" * 40 + "\n")
        f.write("跳过原因统计:\n")
        f.write("=" * 40 + "\n\n")

        # Count by predicate type
        pred_counts = defaultdict(int)
        for _, (_, invalid_preds) in skipped_rules.items():
            for pred in invalid_preds:
                pred_counts[pred] += 1

        if pred_counts:
            for pred, count in sorted(pred_counts.items(), key=lambda x: -x[1]):
                f.write(f"  {pred}: {count} 条\n")
        else:
            f.write("  (无)\n")

        f.write("\n")


def main():
    parser = argparse.ArgumentParser(
        description="Compare Step 2 input/output data and generate report"
    )
    parser.add_argument(
        '--experiment',
        type=str,
        default='outputs/experiments/20260308_step1e_enhanced_symmetry',
        help='Experiment directory path'
    )
    args = parser.parse_args()

    exp_dir = Path(args.experiment)

    # Load Step 1e output (input to Step 2)
    print("Loading Step 1e output (Step 2 input)...")
    input_path = exp_dir / 'intermediates' / 'step1e_rules_deduped.txt'
    input_rules = parse_rule_file(input_path)

    # Load Step 2 output
    print("Loading Step 2 output...")
    output_path = exp_dir / 'discovered_rules.txt'
    output_rules = parse_rule_file(output_path)

    # Load Step 2 skipped
    print("Loading Step 2 skipped rules...")
    skipped_path = exp_dir / 'discovered_rules_skipped.txt'
    skipped_rules = parse_skipped_file(skipped_path)

    # Generate report
    report_path = exp_dir / 'step2_comparison.txt'
    print(f"Generating report to {report_path}...")
    generate_report(input_rules, output_rules, skipped_rules, report_path)

    print(f"Report generated: {report_path}")
    print(f"  Input rules: {len(input_rules)}")
    print(f"  Output rules: {len(output_rules)}")
    print(f"  Skipped: {len(skipped_rules)}")


if __name__ == '__main__':
    main()

