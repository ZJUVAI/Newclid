#!/usr/bin/env python3
"""
Render rule extraction visualization samples from new pipeline output.

Generates 3-panel figures (Full Graph + Pruned Graph + Rule Text) for rules
extracted by the discovery pipeline. Reconstructs graphs on-demand from original
JSONL data.

Usage:
    python render_rule_extraction_samples.py \\
        --step3-propositions path/to/step3_propositions.json \\
        --original-jsonl path/to/original_data.jsonl \\
        --output-dir path/to/output \\
        --workers 10 \\
        --limit 100
"""
import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Tuple

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from newclid.proof_scout.core.filter_and_prune_engine import _convert_llm_record
from newclid.proof_scout.core.graph_pruner import GraphPruner
from newclid.proof_scout.core.single_proof_graph import SingleProofGraph

# Import rendering functions from fig_rule_extraction
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "figures"))
from fig_rule_extraction import (
    build_full_graph_from_record,
    create_three_panel_figure_from_data,
    _select_pruned_render,
)


# ============================================================================
# Data Loading
# ============================================================================

def load_rules_from_step3(step3_path: Path) -> List[Tuple[str, List[str], str]]:
    """Load rules from step3_propositions.json.

    Returns:
        List of (pid, aux_points, rule_text) tuples
    """
    with open(step3_path) as f:
        data = json.load(f)

    results = []
    for entry in data.get("success_records", []):
        pid = entry.get("problem_id")
        aux_points = entry.get("aux_points", [])
        rule = entry.get("rule", "")
        if pid and rule:
            results.append((pid, aux_points, rule))

    return results


def load_original_records_by_pid(
    original_jsonl_path: Path, target_pids: set
) -> Dict[str, dict]:
    """Load original JSONL records by pid.

    Args:
        original_jsonl_path: Path to original JSONL file
        target_pids: Set of pids to load

    Returns:
        Dict mapping pid to full record
    """
    records = {}
    with open(original_jsonl_path) as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            pid = rec.get("pid")
            if pid in target_pids:
                records[pid] = rec
                if len(records) == len(target_pids):
                    break  # Found all target pids

    return records


# ============================================================================
# Graph Reconstruction
# ============================================================================

def reconstruct_graphs(pid: str, record: dict) -> Tuple[dict, dict]:
    """Reconstruct full and pruned graphs from original record.

    Args:
        pid: Problem ID
        record: Original JSONL record with llm_input_renamed/llm_output_renamed

    Returns:
        (full_graph, pruned_rendered) tuple
    """
    # Convert record to internal format
    # Use dummy base and index since pid is already in the record
    conv = _convert_llm_record(record, base="p", index=0)

    # Build full graph
    spg = SingleProofGraph.build_from_result_record(conv, verbose=False)

    # Extract full graph structure
    nodes, edges = [], []
    for nid, nd in spg.nodes.items():
        label = nd.get("label", "")
        args = nd.get("args", [])
        full = f"{label}({','.join(args)})" if args else label
        nodes.append({
            "id": nid,
            "type": nd.get("type", "fact"),
            "short": label,
            "full": full,
        })
    for u, v in spg.edges:
        edges.append((u, v))

    full_graph = {
        "nodes": nodes,
        "edges": edges,
        "aux_points": set(conv.get("aux_points", [])),
    }

    # Build pruned graph
    pruner = GraphPruner()
    rendered_result = pruner.prune_proof_graph(spg)
    rendered = rendered_result.get(pid) or rendered_result.get(conv.get("problem_id"))

    if not rendered:
        raise ValueError(f"No pruned graph generated for {pid}")

    # Handle multiple pruned graphs
    if isinstance(rendered, list):
        pruned_rendered = _select_pruned_render(rendered, rule_text=None)
    else:
        pruned_rendered = rendered

    return full_graph, pruned_rendered


# ============================================================================
# Rendering Worker
# ============================================================================

def render_one_rule(
    pid: str,
    record: dict,
    rule_text: str,
    output_dir: Path,
    dpi: int = 250,
) -> Tuple[str, str]:
    """Render one rule extraction figure.

    Args:
        pid: Problem ID
        record: Original JSONL record
        rule_text: Rule text
        output_dir: Output directory
        dpi: Image DPI

    Returns:
        (pid, status) where status is "ok", "failed", or error message
    """
    try:
        # Reconstruct graphs
        full_graph, pruned_rendered = reconstruct_graphs(pid, record)

        # Create figure
        fig = create_three_panel_figure_from_data(
            full_graph,
            pruned_rendered,
            rule_text,
            show_arrows=False,
            figsize=(16, 7),
            node_size=320,
            pid_text=f"Problem ID: {pid}",
            verbose=False,
        )

        # Save figure
        output_path = output_dir / f"{pid}_rule_extraction.png"
        fig.savefig(output_path, format="png", bbox_inches="tight", dpi=dpi)

        # Clean up
        import matplotlib.pyplot as plt
        plt.close(fig)

        return (pid, "ok")

    except Exception as e:
        return (pid, f"failed: {str(e)}")


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Render rule extraction visualization samples"
    )
    parser.add_argument(
        "--step3-propositions",
        type=Path,
        required=True,
        help="Path to step3_propositions.json",
    )
    parser.add_argument(
        "--original-jsonl",
        type=Path,
        required=True,
        help="Path to original JSONL data file",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Output directory for figures",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=10,
        help="Number of parallel workers (default: 10)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of rules to render (default: 100)",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=250,
        help="Image DPI (default: 250)",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=10,
        help="Print progress every N rules (default: 10)",
    )

    args = parser.parse_args()

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Load rules from step3
    print(f"Loading rules from {args.step3_propositions}")
    rules = load_rules_from_step3(args.step3_propositions)
    print(f"Found {len(rules)} rules")

    # Limit number of rules
    if args.limit and args.limit < len(rules):
        rules = rules[:args.limit]
        print(f"Limiting to first {args.limit} rules")

    # Extract pids
    pids = {pid for pid, _, _ in rules}

    # Load original records
    print(f"Loading original records from {args.original_jsonl}")
    records = load_original_records_by_pid(args.original_jsonl, pids)
    print(f"Loaded {len(records)} records")

    # Check for missing records
    missing = pids - set(records.keys())
    if missing:
        print(f"Warning: {len(missing)} pids not found in original JSONL")
        rules = [(pid, aux, rule) for pid, aux, rule in rules if pid not in missing]

    print(f"\nRendering {len(rules)} rules with {args.workers} workers...")
    print(f"Output directory: {args.output_dir}")
    print()

    # Render in parallel
    success_count = 0
    failed_count = 0
    failed_pids = []

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                render_one_rule,
                pid,
                records[pid],
                rule_text,
                args.output_dir,
                args.dpi,
            ): pid
            for pid, _, rule_text in rules
        }

        for idx, future in enumerate(as_completed(futures), start=1):
            pid, status = future.result()

            if status == "ok":
                success_count += 1
            else:
                failed_count += 1
                failed_pids.append((pid, status))

            if args.progress_every and idx % args.progress_every == 0:
                print(
                    f"  Progress: {idx}/{len(rules)} "
                    f"(success={success_count}, failed={failed_count})"
                )

    # Final summary
    print()
    print("=" * 60)
    print(f"Rendering complete!")
    print(f"  Total: {len(rules)}")
    print(f"  Success: {success_count}")
    print(f"  Failed: {failed_count}")
    print(f"  Output: {args.output_dir}")
    print("=" * 60)

    # Print failed pids
    if failed_pids:
        print()
        print("Failed PIDs:")
        for pid, status in failed_pids[:10]:  # Show first 10
            print(f"  {pid}: {status}")
        if len(failed_pids) > 10:
            print(f"  ... and {len(failed_pids) - 10} more")


if __name__ == "__main__":
    main()
