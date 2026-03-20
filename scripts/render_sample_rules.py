#!/usr/bin/env python3
"""Render sample rule extraction figures from step6_rules_stats.json"""
import json
import sys
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from newclid.proof_scout.core.single_proof_graph import SingleProofGraph
from newclid.proof_scout.core.graph_pruner import GraphPruner


def render_rule(args):
    """Render a single rule extraction figure."""
    rid, entry, output_dir, dpi = args

    try:
        # Build full graph from llm_input/output
        llm_input = entry['llm_input_renamed']
        llm_output = entry['llm_output_renamed']
        point_coords = entry.get('point_coords', {})

        # Create a record dict for SingleProofGraph
        record = {
            'llm_input_renamed': llm_input,
            'llm_output_renamed': llm_output,
            'point_coords': point_coords,
        }

        # Build full graph
        spg = SingleProofGraph.build_from_result_record(record)
        if not spg:
            return rid, 'failed', 'Failed to build graph'

        # Prune graph
        pruner = GraphPruner()
        pruned_graphs = pruner.prune_proof_graph(spg)
        if not pruned_graphs:
            return rid, 'failed', 'No pruned graphs'

        # Use first pruned graph
        pruned = pruned_graphs[0]

        # Create simple visualization
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))

        # Panel 1: Full graph info
        ax1.text(0.5, 0.5, f"Rule ID: {rid}\n\nFull Graph:\n{len(spg.nodes)} nodes\n{len(spg.edges)} edges",
                ha='center', va='center', fontsize=12)
        ax1.set_title('Full Proof Graph', fontsize=14, fontweight='bold')
        ax1.axis('off')

        # Panel 2: Pruned graph and rule
        rule_text = entry.get('rule', '')
        ax2.text(0.5, 0.7, f"Pruned Graph:\n{len(pruned['nodes'])} nodes\n{len(pruned['edges'])} edges",
                ha='center', va='center', fontsize=12)
        ax2.text(0.5, 0.3, f"Extracted Rule:\n{rule_text[:100]}...",
                ha='center', va='center', fontsize=10, wrap=True)
        ax2.set_title('Pruned Graph & Rule', fontsize=14, fontweight='bold')
        ax2.axis('off')

        plt.tight_layout()

        # Save figure
        output_path = output_dir / f"{rid}.png"
        fig.savefig(output_path, dpi=dpi, bbox_inches='tight')
        plt.close(fig)

        return rid, 'success', str(output_path)

    except Exception as e:
        return rid, 'failed', str(e)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rules-stats', type=Path, required=True,
                       help='Path to step6_rules_stats.json')
    parser.add_argument('--output-dir', type=Path, required=True,
                       help='Output directory for figures')
    parser.add_argument('--workers', type=int, default=10,
                       help='Number of parallel workers')
    parser.add_argument('--limit', type=int, default=100,
                       help='Maximum number of rules to render (0 = all)')
    parser.add_argument('--dpi', type=int, default=250,
                       help='Figure DPI')
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
    tasks = []
    for entry in entries:
        rid = entry['rid']
        tasks.append((rid, entry, args.output_dir, args.dpi))

    # Render in parallel
    print(f"\nRendering {len(tasks)} rules with {args.workers} workers...")
    success_count = 0
    failed_count = 0

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(render_rule, task) for task in tasks]

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
    print(f"Figures saved to: {args.output_dir}")


if __name__ == '__main__':
    main()
