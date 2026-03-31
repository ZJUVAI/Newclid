#!/usr/bin/env python3
"""Generate simple rule visualization cards from step6_rules_stats.json"""
import json
import sys
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches


def count_premises(rule_text):
    """Count number of premises in a rule."""
    if '=>' not in rule_text:
        return 0
    left = rule_text.split('=>')[0]
    return len([p.strip() for p in left.split(',') if p.strip()])


def render_rule_card(args):
    """Render a simple card showing rule information."""
    rid, entry, output_dir, dpi = args

    try:
        rule_text = entry.get('rule', '')
        rule_original = entry.get('rule_original', '')
        pid = entry.get('pid', '')
        seed = entry.get('seed', '')

        # Count premises and conclusions
        n_premises = count_premises(rule_text)

        # Create figure
        fig, ax = plt.subplots(figsize=(12, 8))
        ax.axis('off')

        # Title
        title_text = f"Rule ID: {rid}"
        if pid:
            title_text += f"  |  Problem ID: {pid}"
        if seed is not None:
            title_text += f"  |  Seed: {seed}"

        ax.text(0.5, 0.95, title_text,
                ha='center', va='top', fontsize=14, fontweight='bold',
                transform=ax.transAxes)

        # Rule statistics box
        stats_text = f"Premises: {n_premises}"
        ax.text(0.5, 0.85, stats_text,
                ha='center', va='top', fontsize=12,
                transform=ax.transAxes,
                bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.5))

        # Normalized rule (wrapped)
        rule_display = rule_text if len(rule_text) <= 200 else rule_text[:200] + '...'
        ax.text(0.05, 0.75, "Normalized Rule:",
                ha='left', va='top', fontsize=11, fontweight='bold',
                transform=ax.transAxes)
        ax.text(0.05, 0.70, rule_display,
                ha='left', va='top', fontsize=9, wrap=True,
                transform=ax.transAxes,
                bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.3))

        # Original rule (if different)
        if rule_original and rule_original != rule_text:
            orig_display = rule_original if len(rule_original) <= 200 else rule_original[:200] + '...'
            ax.text(0.05, 0.45, "Original Rule:",
                    ha='left', va='top', fontsize=11, fontweight='bold',
                    transform=ax.transAxes)
            ax.text(0.05, 0.40, orig_display,
                    ha='left', va='top', fontsize=9, wrap=True,
                    transform=ax.transAxes,
                    bbox=dict(boxstyle='round', facecolor='lightgray', alpha=0.3))

        # Save
        output_path = output_dir / f"{rid}.png"
        fig.savefig(output_path, dpi=dpi, bbox_inches='tight')
        plt.close(fig)

        return rid, 'success', str(output_path)

    except Exception as e:
        return rid, 'failed', str(e)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rules-stats', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=10)
    parser.add_argument('--limit', type=int, default=100)
    parser.add_argument('--dpi', type=int, default=150)
    args = parser.parse_args()

    # Load rules
    print(f"Loading rules from {args.rules_stats}")
    with open(args.rules_stats) as f:
        data = json.load(f)

    entries = data['entries']
    print(f"Found {len(entries)} rules")

    # Limit if requested
    if args.limit > 0:
        entries = entries[:args.limit]
        print(f"Limiting to first {args.limit} rules")

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {args.output_dir}")

    # Prepare tasks
    tasks = [(entry['rid'], entry, args.output_dir, args.dpi) for entry in entries]

    # Render in parallel
    print(f"\nRendering {len(tasks)} rule cards with {args.workers} workers...")
    success_count = 0
    failed_count = 0

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(render_rule_card, task) for task in tasks]

        for i, future in enumerate(as_completed(futures), 1):
            rid, status, msg = future.result()

            if status == 'success':
                success_count += 1
            else:
                failed_count += 1
                print(f"  Failed {rid}: {msg}")

            if i % 50 == 0:
                print(f"  Progress: {i}/{len(tasks)} (success={success_count}, failed={failed_count})")

    print(f"\nCompleted: {success_count} success, {failed_count} failed")
    print(f"Rule cards saved to: {args.output_dir}")


if __name__ == '__main__':
    main()
