#!/usr/bin/env python3
"""
Batch Rule Extraction Visualization (New Pipeline)

Generates three-panel figures for extracted rules:
  (a) Full Proof Graph -> (b) Pruned Graph -> (c) Extracted Rule

Reads from step6_rules_stats.json (new pipeline format).
Supports parallel rendering with ProcessPoolExecutor.

Usage:
    python scripts/figures/fig_rule_extraction_batch.py \
        --rules-stats outputs/experiments/.../intermediates/step6_rules_stats.json \
        --output-dir outputs/experiments/.../rule_extraction_figures \
        --workers 10 --limit 100 --dpi 250
"""
import argparse
import json
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))


def _setup_paths():
    """Ensure PROJECT_ROOT and src are on sys.path (needed in worker processes)."""
    root = str(PROJECT_ROOT)
    src = str(PROJECT_ROOT / "src")
    if root not in sys.path:
        sys.path.insert(0, root)
    if src not in sys.path:
        sys.path.insert(0, src)


def _select_pruned_render(rendered_list, rule_text=None):
    """Select the best pruned render from a list, matching rule_text if possible."""
    if not rendered_list:
        raise ValueError("rendered_list is empty")
    if len(rendered_list) == 1:
        return rendered_list[0]

    target_label = None
    if rule_text and "=>" in rule_text:
        conclusion_clause = rule_text.split("=>", 1)[1].strip()
        parts = conclusion_clause.split()
        if parts:
            pred = parts[0]
            args = parts[1:]
            target_label = f"{pred}({','.join(args)})" if args else pred

    if target_label:
        for rendered in rendered_list:
            fact_labels = {
                str(n.get("label", ""))
                for n in rendered.get("nodes", [])
                if n.get("type") == "fact"
            }
            if target_label in fact_labels:
                return rendered

    return rendered_list[0]


def _build_graphs_from_entry(entry: dict) -> tuple:
    """Build full and pruned graph data from a step6 entry.

    Returns (full_raw, pruned_rendered, rule_text).
    Raises on failure.
    """
    from newclid.proof_scout.core.single_proof_graph import SingleProofGraph
    from newclid.proof_scout.core.filter_and_prune_engine import _convert_llm_record
    from newclid.proof_scout.core.graph_pruner import GraphPruner

    pid = entry["pid"]
    rule_text = entry["rule"]

    # Convert to internal format
    conv = _convert_llm_record(entry, pid, 0)
    spg = SingleProofGraph.build_from_result_record(conv, verbose=False)

    # Build full graph
    nodes, edges = [], []
    for nid, nd in spg.nodes.items():
        label = nd.get("label", "")
        args = nd.get("args", [])
        full = f"{label}({','.join(args)})" if args else label
        nodes.append({"id": nid, "type": nd.get("type", "fact"), "short": label, "full": full})
    for u, v in spg.edges:
        edges.append((u, v))
    full_raw = {"nodes": nodes, "edges": edges, "aux_points": set(conv.get("aux_points", []))}

    # Build pruned graph
    pruner = GraphPruner()
    rendered_map = pruner.prune_proof_graph(spg)
    rendered_list = rendered_map.get(pid, [])
    if not rendered_list:
        raise ValueError(f"No pruned graph for {pid}")

    # Select best pruned render matching the rule
    pruned_rendered = _select_pruned_render(rendered_list, rule_text=rule_text) if len(rendered_list) > 1 else rendered_list[0]

    return full_raw, pruned_rendered, rule_text


def _count_premises(rule_text: str) -> int:
    """Count number of premises in a rule text (everything before '=>')."""
    if "=>" not in rule_text:
        return 0
    premises_part = rule_text.split("=>")[0].strip()
    if not premises_part:
        return 0
    return len([p.strip() for p in premises_part.split(",") if p.strip()])


def _worker_render(entry: dict, output_path: str, dpi: int) -> tuple:
    """Worker function: build graphs and render one figure.

    Returns (rid, "ok") on success, (rid, error_msg) on failure.
    """
    import matplotlib
    matplotlib.use("Agg")

    rid = entry.get("rid", "unknown")
    try:
        full_raw, pruned_rendered, rule_text = _build_graphs_from_entry(entry)

        # Import the figure creation function from the existing module
        _setup_paths()
        from scripts.figures.fig_rule_extraction import create_three_panel_figure_from_data
        fig = create_three_panel_figure_from_data(
            full_raw, pruned_rendered, rule_text,
            show_arrows=False, figsize=(16, 7),
            pid_text=f"{entry['pid']} / {rid}", verbose=False,
        )
        fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
        import matplotlib.pyplot as plt
        plt.close(fig)
        return (rid, "ok")
    except Exception as e:
        return (rid, f"{type(e).__name__}: {e}")


def main():
    parser = argparse.ArgumentParser(description="Batch rule extraction visualization")
    parser.add_argument("--rules-stats", required=True, help="Path to step6_rules_stats.json")
    parser.add_argument("--output-dir", required=True, help="Output directory for figures")
    parser.add_argument("--workers", type=int, default=4, help="Number of parallel workers")
    parser.add_argument("--limit", type=int, default=100, help="Max number of figures to render")
    parser.add_argument("--offset", type=int, default=0, help="Skip first N entries")
    parser.add_argument("--dpi", type=int, default=200, help="Figure DPI")
    parser.add_argument("--progress-every", type=int, default=10, help="Print progress every N")
    args = parser.parse_args()

    # Load data
    print(f"Loading rules from {args.rules_stats}")
    with open(args.rules_stats) as f:
        data = json.load(f)
    entries = data.get("entries", [])
    print(f"Found {len(entries)} rules")

    # Apply offset and limit
    entries = entries[args.offset:]
    if args.limit:
        entries = entries[:args.limit]
    print(f"Rendering {len(entries)} rules (offset={args.offset}, limit={args.limit})")

    # Prepare output directory
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output: {out_dir}\n")

    # Render in parallel
    ok_count, fail_count = 0, 0
    failures = []

    if args.workers > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futs = {}
            for entry in entries:
                rid = entry.get("rid", "unknown")
                n_prem = _count_premises(entry.get("rule", ""))
                out_path = str(out_dir / f"{rid}_prem{n_prem}.png")
                fut = ex.submit(_worker_render, entry, out_path, args.dpi)
                futs[fut] = rid

            for i, fut in enumerate(as_completed(futs), 1):
                rid, status = fut.result()
                if status == "ok":
                    ok_count += 1
                else:
                    fail_count += 1
                    failures.append({"rid": rid, "error": status})
                    if fail_count <= 20:
                        print(f"  Failed {rid}: {status}")
                if i % args.progress_every == 0:
                    print(f"  [{i}/{len(entries)}] ok={ok_count} fail={fail_count}")
    else:
        for i, entry in enumerate(entries, 1):
            rid = entry.get("rid", "unknown")
            n_prem = _count_premises(entry.get("rule", ""))
            out_path = str(out_dir / f"{rid}_prem{n_prem}.png")
            rid, status = _worker_render(entry, out_path, args.dpi)
            if status == "ok":
                ok_count += 1
            else:
                fail_count += 1
                failures.append({"rid": rid, "error": status})
                if fail_count <= 20:
                    print(f"  Failed {rid}: {status}")
            if i % args.progress_every == 0:
                print(f"  [{i}/{len(entries)}] ok={ok_count} fail={fail_count}")

    print(f"\nDone: {ok_count} ok, {fail_count} failed out of {len(entries)}")

    # Save failure log
    if failures:
        fail_path = out_dir / "render_failures.json"
        with open(fail_path, "w") as f:
            json.dump(failures, f, indent=2)
        print(f"Failures saved to {fail_path}")


if __name__ == "__main__":
    main()
