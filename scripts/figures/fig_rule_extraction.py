#!/usr/bin/env python3
"""
Figure 2: Rule Extraction Illustration

Three panels: (a) Full Proof Graph -> (b) Pruned Graph -> (c) Extracted Rule
Dynamically loads real data from pid:007951 pipeline outputs.

Data sources:
- Full graph: geometry_clauses15_samples10k.jsonl (line 7951)
- Pruned graph + rule: geometry_clauses15_samples10k_pruned.json
"""
import json
import re
import sys
from collections import defaultdict, deque
from pathlib import Path

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from newclid.proof_scout.core.single_proof_graph import SingleProofGraph
from newclid.proof_scout.core.filter_and_prune_engine import _convert_llm_record
from newclid.proof_scout.core.graph_pruner import GraphPruner

# ── Colour scheme ──
BLUE_PRIMARY   = "#2E5C8A"   # premise (no aux)
BLUE_LIGHT     = "#A8C8E8"   # intermediate (no aux)
RED_LIGHT      = "#FFB3B3"   # aux-related (both panels, same color)
ORANGE_PRIMARY = "#E67E22"   # conclusion
GRAY_DARK      = "#4A4A4A"
GRAY_LIGHT     = "#BDC3C7"
FADED          = "#E0E0E0"   # pruned
WHITE          = "#FFFFFF"

plt.rcParams["font.family"] = "DejaVu Sans"
plt.rcParams["font.size"] = 9

# ────────────────────────── Data loading ──────────────────────────


def load_full_graph(problem_id: str, jsonl_path: Path) -> dict:
    """Build full proof graph from JSONL via SingleProofGraph."""
    base, idx = problem_id.split(":")
    idx = int(idx)
    with open(jsonl_path) as fh:
        for i, line in enumerate(fh):
            if i == idx:
                rec = json.loads(line)
                return build_full_graph_from_record(problem_id, rec)
    raise ValueError(f"{problem_id} not found")


def build_full_graph_from_record(problem_id: str, rec: dict) -> dict:
    """Build full proof graph from one raw JSONL record."""
    base, idx = problem_id.split(":")
    idx_int = int(idx)
    conv = _convert_llm_record(rec, base, idx_int)
    spg = SingleProofGraph.build_from_result_record(conv, verbose=False)

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

    return {
        "nodes": nodes,
        "edges": edges,
        "aux_points": set(conv.get("aux_points", [])),
    }


def build_pruned_render_from_record(problem_id: str, rec: dict, rule_text: str | None = None) -> dict:
    """Rebuild the pruned rendered graph for one raw JSONL record."""
    base, idx = problem_id.split(":")
    idx_int = int(idx)
    conv = _convert_llm_record(rec, base, idx_int)
    spg = SingleProofGraph.build_from_result_record(conv, verbose=False)
    pruner = GraphPruner()
    rendered = pruner.prune_proof_graph(spg).get(problem_id)
    if not rendered:
        raise ValueError(f"No pruned graph generated for {problem_id}")
    if isinstance(rendered, list):
        return _select_pruned_render(rendered, rule_text=rule_text)
    return rendered


def load_pruned_data(problem_id: str, path: Path) -> tuple:
    """Return (pruned_rendered, rule_text) from pruned JSON."""
    with open(path) as fh:
        data = json.load(fh)
    for rec in data["results"]:
        if rec["problem_id"] == problem_id:
            return rec["rendered"], rec["proposition_rule"]
    raise ValueError(f"{problem_id} not found in pruned JSON")


def load_default_problem_id(path: Path) -> str:
    """Return the first available problem_id from a pruned JSON file."""
    with open(path) as fh:
        data = json.load(fh)
    for rec in data.get("results", []):
        problem_id = rec.get("problem_id")
        if problem_id:
            return str(problem_id)
    raise ValueError(f"No problem_id found in {path}")


# ────────────────────── Graph transformation ──────────────────────


def _collapse_rules(raw_nodes, raw_edges):
    """Collapse rule nodes: fact→rule→fact becomes fact→fact.

    Returns (fact_nodes, fact_edges) where fact_edges contains
    *all* input→output pairs for every rule.
    """
    type_map = {n["id"]: n["type"] for n in raw_nodes}

    # Collect per-rule inputs / outputs
    rule_in = defaultdict(list)   # rule_id → [fact_id …]
    rule_out = defaultdict(list)  # rule_id → [fact_id …]
    for u, v in raw_edges:
        if type_map.get(u) == "fact" and type_map.get(v) == "rule":
            rule_in[v].append(u)
        elif type_map.get(u) == "rule" and type_map.get(v) == "fact":
            rule_out[u].append(v)

    # Build fact→fact edge set (deduped)
    fact_edges = set()
    for rid, ins in rule_in.items():
        for out in rule_out.get(rid, []):
            for inp in ins:
                fact_edges.add((inp, out))
    # Also keep any direct fact→fact edges
    for u, v in raw_edges:
        if type_map.get(u) == "fact" and type_map.get(v) == "fact":
            fact_edges.add((u, v))

    fact_nodes = [n for n in raw_nodes if n["type"] == "fact"]
    return fact_nodes, list(fact_edges)


def _remove_isolated(fact_nodes, fact_edges):
    """Remove fact nodes with in-degree = out-degree = 0."""
    ids_in_edges = set()
    for u, v in fact_edges:
        ids_in_edges.add(u)
        ids_in_edges.add(v)
    isolated = {n["id"] for n in fact_nodes if n["id"] not in ids_in_edges}
    kept = [n for n in fact_nodes if n["id"] not in isolated]
    return kept, isolated


def _topo_levels(fact_nodes, fact_edges, conclusion_id):
    """Assign hierarchical level via REVERSE BFS from conclusion.

    Depth = distance from conclusion node (conclusion depth=0).
    Uses MAXIMUM depth when a node has multiple paths to conclusion.
    Returns dict {node_id: int_depth}.
    """
    ids = {n["id"] for n in fact_nodes}
    # Build reverse adjacency: v -> [u] (predecessors)
    rev_adj = defaultdict(set)
    for u, v in fact_edges:
        if u in ids and v in ids:
            rev_adj[v].add(u)

    # BFS from conclusion backwards, tracking maximum depth
    depths = {}
    if conclusion_id is None:
        # Fallback: use forward topo if no conclusion
        return {nid: 0 for nid in ids}

    q = deque([conclusion_id])
    depths[conclusion_id] = 0

    # Process all nodes, updating to maximum depth
    while q:
        v = q.popleft()
        for u in rev_adj[v]:
            new_depth = depths[v] + 1
            if u not in depths:
                depths[u] = new_depth
                q.append(u)
            elif new_depth > depths[u]:
                # Update to maximum depth
                depths[u] = new_depth
                q.append(u)  # Re-process to propagate the change

    # Nodes not reachable from conclusion get max depth + 1
    max_d = max(depths.values()) if depths else 0
    for nid in ids:
        if nid not in depths:
            depths[nid] = max_d + 1

    return depths


def _layout(fact_nodes, depths, conclusion_id, fact_edges):
    """Compute (x, y) for every fact node based on reverse depths.

    Depth = distance from conclusion (conclusion depth=0, at bottom).
    Layout: larger depth → higher y (top), smaller depth → lower y (bottom).
    Nodes at same depth are sorted by average x-position of their children.
    """
    max_depth = max(depths.values()) if depths else 0
    y_gap = 2.5
    x_gap = 2.8

    # Group nodes by depth
    groups = defaultdict(list)
    for n in fact_nodes:
        nid = n["id"]
        groups[depths.get(nid, 0)].append(n)

    # Build adjacency: node -> children (nodes at lower depth)
    children = defaultdict(list)
    for u, v in fact_edges:
        if depths.get(u, 0) > depths.get(v, 0):
            children[u].append(v)

    pos = {}

    # Process layers from bottom (depth=0) to top (depth=max)
    for depth in range(max_depth + 1):
        nodes = groups[depth]
        if not nodes:
            continue

        # Sort nodes by average x-position of their children
        def child_x_avg(node):
            nid = node["id"]
            child_ids = children.get(nid, [])
            if not child_ids:
                return 0.0  # Default for nodes without children
            return sum(pos[cid][0] for cid in child_ids if cid in pos) / len(child_ids)

        sorted_nodes = sorted(nodes, key=child_x_avg)

        # Assign x positions
        y = depth * y_gap
        n = len(sorted_nodes)
        x_start = -(n - 1) * x_gap / 2
        for i, node in enumerate(sorted_nodes):
            pos[node["id"]] = (x_start + i * x_gap, y)

    return pos


# ──────────────────────────── Drawing ─────────────────────────────


def _has_aux(full_label, aux_pts):
    if "(" not in full_label:
        return False
    args = full_label.split("(")[1].rstrip(")").split(",")
    return any(a.strip() in aux_pts for a in args)


def _rule_clause_to_full_label(clause: str) -> str | None:
    clause = (clause or "").strip()
    if not clause:
        return None
    parts = clause.split()
    if not parts:
        return None
    pred = parts[0]
    args = parts[1:]
    return f"{pred}({','.join(args)})" if args else pred


def _resolve_conclusion_label(pruned_rendered: dict, rule_text: str | None = None) -> str | None:
    fact_nodes = [n for n in pruned_rendered.get("nodes", []) if n.get("type") == "fact"]
    fact_labels = {str(n.get("label", "")) for n in fact_nodes}

    if rule_text and "=>" in rule_text:
        conclusion_clause = rule_text.split("=>", 1)[1].strip()
        conclusion_label = _rule_clause_to_full_label(conclusion_clause)
        if conclusion_label in fact_labels:
            return conclusion_label

    fact_ids = {n.get("idx") for n in fact_nodes}
    outdeg = {nid: 0 for nid in fact_ids}
    for u, v in pruned_rendered.get("edges", []):
        if u in outdeg:
            outdeg[u] += 1

    sink_labels = [
        str(n.get("label", ""))
        for n in fact_nodes
        if outdeg.get(n.get("idx"), 0) == 0
    ]
    if len(sink_labels) == 1:
        return sink_labels[0]

    pruned_fact_labels = [str(n.get("label", "")) for n in fact_nodes]
    return pruned_fact_labels[-1] if pruned_fact_labels else None


def _select_pruned_render(rendered_list: list[dict], rule_text: str | None = None) -> dict:
    if not rendered_list:
        raise ValueError("rendered_list is empty")
    if len(rendered_list) == 1:
        return rendered_list[0]

    target_label = None
    if rule_text and "=>" in rule_text:
        target_label = _rule_clause_to_full_label(rule_text.split("=>", 1)[1].strip())

    if target_label:
        exact_matches = []
        sink_matches = []
        for rendered in rendered_list:
            fact_labels = {
                str(n.get("label", ""))
                for n in rendered.get("nodes", [])
                if n.get("type") == "fact"
            }
            if target_label in fact_labels:
                exact_matches.append(rendered)
            if _resolve_conclusion_label(rendered, rule_text=None) == target_label:
                sink_matches.append(rendered)

        if len(sink_matches) == 1:
            return sink_matches[0]
        if len(exact_matches) == 1:
            return exact_matches[0]

    return rendered_list[0]


def _node_role(node, conclusion_id, aux_pts, panel, removed, pred_map):
    """Return colour role string."""
    nid = node["id"]
    if nid == conclusion_id:
        return "conclusion"

    has_a = _has_aux(node["full"], aux_pts)

    # In panel-b, if all predecessors are removed → promote to premise
    if panel == "b":
        preds = pred_map.get(nid, set())
        if preds and all(p in removed for p in preds):
            return "premise_aux" if has_a else "premise"

    # Original premise: no predecessors at all
    if nid not in pred_map or not pred_map[nid]:
        return "premise_aux" if has_a else "premise"

    return "intermediate_aux" if has_a else "intermediate"


_STYLES_A = {
    "premise":          (BLUE_PRIMARY, BLUE_PRIMARY, 2.5, 1.0),
    "premise_aux":      (RED_LIGHT,    RED_LIGHT,    2.5, 1.0),
    "conclusion":       (ORANGE_PRIMARY, ORANGE_PRIMARY, 2.5, 1.0),
    "intermediate":     (BLUE_LIGHT,   BLUE_LIGHT,   1.5, 1.0),
    "intermediate_aux": (RED_LIGHT,    RED_LIGHT,    1.5, 1.0),
}
_STYLES_B = _STYLES_A  # Same colors for both panels, no red border


def _draw_graph(ax, pos, fact_nodes, fact_edges, aux_pts,
                removed, conclusion_id, panel, title, *, node_size=825):
    ax.set_title(title, fontsize=13, weight="bold", pad=12)
    ax.axis("off")

    # predecessor map (for role detection)
    pred_map = defaultdict(set)
    for u, v in fact_edges:
        pred_map[v].add(u)

    # ── edges ──
    for u, v in fact_edges:
        if u not in pos or v not in pos:
            continue
        is_rem = panel == "b" and (u in removed or v in removed)
        x1, y1 = pos[u]
        x2, y2 = pos[v]
        d = np.hypot(x2 - x1, y2 - y1)
        if d == 0:
            continue
        ux, uy = (x2 - x1) / d, (y2 - y1) / d
        r = 0.34 if node_size <= 400 else 0.50
        col = GRAY_LIGHT if is_rem else GRAY_DARK
        lw  = 1.0 if is_rem else 1.5
        alp = 0.15 if is_rem else 0.8
        ax.annotate(
            "", xy=(x2 - ux * r, y2 - uy * r),
            xytext=(x1 + ux * r, y1 + uy * r),
            arrowprops=dict(arrowstyle="->", color=col, lw=lw, alpha=alp,
                            shrinkA=0, shrinkB=0),
        )

    # ── nodes ──
    styles = _STYLES_B if panel == "b" else _STYLES_A
    for node in fact_nodes:
        nid = node["id"]
        if nid not in pos:
            continue
        x, y = pos[nid]
        is_rem = nid in removed
        role = _node_role(node, conclusion_id, aux_pts, panel, removed, pred_map)

        if panel == "b" and is_rem:
            fc, ec, lw, alp = FADED, GRAY_LIGHT, 1.0, 0.25
        else:
            fc, ec, lw, alp = styles.get(role, (WHITE, GRAY_DARK, 1.5, 1.0))

        ax.scatter([x], [y], s=node_size, c=[fc], edgecolors=[ec],
                   linewidths=lw, alpha=alp, marker="o", zorder=5)

        txt_alp = 0.2 if (panel == "b" and is_rem) else 1.0
        # Dark text for light backgrounds, white text for dark backgrounds
        font_c = "white" if fc in (BLUE_PRIMARY, ORANGE_PRIMARY) else GRAY_DARK
        ax.text(x, y, node["short"], ha="center", va="center",
                fontsize=7, weight="bold", color=font_c, alpha=txt_alp, zorder=6)

    # ── limits ──
    xs = [pos[n["id"]][0] for n in fact_nodes if n["id"] in pos]
    ys = [pos[n["id"]][1] for n in fact_nodes if n["id"] in pos]
    if xs:
        m = 0.8
        ax.set_xlim(min(xs) - m, max(xs) + m)
        ax.set_ylim(min(ys) - m, max(ys) + m)

    # ── legend (panel b only) ──
    if panel == "b":
        ax.legend(
            handles=[
                mpatches.Patch(fc=BLUE_PRIMARY, ec=BLUE_PRIMARY, label="Premise"),
                mpatches.Patch(fc=RED_LIGHT, ec=RED_LIGHT, label="Aux-related"),
                mpatches.Patch(fc=BLUE_LIGHT, ec=BLUE_LIGHT, label="Intermediate"),
                mpatches.Patch(fc=ORANGE_PRIMARY, ec=ORANGE_PRIMARY, label="Conclusion"),
                mpatches.Patch(fc=FADED, ec=GRAY_LIGHT, label="Pruned"),
            ],
            loc="lower right", fontsize=7, framealpha=0.9, edgecolor=GRAY_DARK,
        )


def _draw_rule(ax, rule_text, *, pid_text: str | None = None):
    ax.set_title("(c) Extracted Rule", fontsize=13, weight="bold", pad=12)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5)
    ax.axis("off")
    if pid_text:
        ax.text(5, 4.55, pid_text, ha="center", va="center", fontsize=9,
                color=GRAY_DARK, family="DejaVu Sans Mono")
    # wrap long rule
    parts = rule_text.split(",")
    mid = len(parts) // 2
    txt = ",".join(parts[:mid]) + ",\n" + ",".join(parts[mid:])
    ax.text(5, 2.5, txt, ha="center", va="center", fontsize=11,
            color=GRAY_DARK,
            bbox=dict(boxstyle="round,pad=0.8", facecolor=WHITE,
                      edgecolor=GRAY_DARK, linewidth=2))


def prepare_figure_data(full_raw: dict, pruned_rendered: dict, rule_text: str | None = None) -> dict:
    """Prepare layout and panel metadata shared by single and batch figures."""
    aux_pts = full_raw["aux_points"]

    fact_nodes, fact_edges = _collapse_rules(full_raw["nodes"], full_raw["edges"])
    fact_nodes, isolated = _remove_isolated(fact_nodes, fact_edges)

    kept_ids = {n["id"] for n in fact_nodes}
    fact_edges = [(u, v) for u, v in fact_edges if u in kept_ids and v in kept_ids]

    conclusion_label = _resolve_conclusion_label(pruned_rendered, rule_text=rule_text)
    conclusion_id = None
    for n in fact_nodes:
        if n["full"] == conclusion_label:
            conclusion_id = n["id"]
            break

    depths = _topo_levels(fact_nodes, fact_edges, conclusion_id)
    pos = _layout(fact_nodes, depths, conclusion_id, fact_edges)

    pruned_labels = {n["label"] for n in pruned_rendered["nodes"]}
    removed = {n["id"] for n in fact_nodes if n["full"] not in pruned_labels}

    return {
        "aux_pts": aux_pts,
        "fact_nodes": fact_nodes,
        "fact_edges": fact_edges,
        "conclusion_id": conclusion_id,
        "removed": removed,
        "pos": pos,
        "isolated": isolated,
        "n_full": len(fact_nodes),
        "n_pruned": sum(1 for n in pruned_rendered["nodes"] if n["type"] == "fact"),
        "max_depth": max(depths.values()) if depths else 0,
    }


def create_three_panel_figure_from_data(
    full_raw: dict,
    pruned_rendered: dict,
    rule_text: str,
    *,
    show_arrows: bool = False,
    figsize: tuple = (16, 7),
    node_size: int = 320,
    pid_text: str | None = None,
    verbose: bool = True,
):
    """Create a three-panel figure from already loaded graph data."""
    prepared = prepare_figure_data(full_raw, pruned_rendered, rule_text=rule_text)

    if verbose:
        print(
            f"Fact nodes: {prepared['n_full']} | Edges: {len(prepared['fact_edges'])} | "
            f"Depths: {prepared['max_depth'] + 1} layers | Removed: {len(prepared['removed'])} | "
            f"Isolated dropped: {len(prepared['isolated'])}"
        )

    if show_arrows:
        fig = plt.figure(figsize=figsize)
        gs = fig.add_gridspec(1, 7, width_ratios=[3, 0.3, 3, 0.3, 2, 0, 0],
                              wspace=0.05)
        ax_a = fig.add_subplot(gs[0])
        ax_arr1 = fig.add_subplot(gs[1])
        ax_b = fig.add_subplot(gs[2])
        ax_arr2 = fig.add_subplot(gs[3])
        ax_c = fig.add_subplot(gs[4])

        for ax_arr in (ax_arr1, ax_arr2):
            ax_arr.set_xlim(0, 1)
            ax_arr.set_ylim(0, 1)
            ax_arr.axis("off")
            ax_arr.add_patch(mpatches.FancyArrowPatch(
                (0.1, 0.5), (0.9, 0.5),
                arrowstyle="->", mutation_scale=30, linewidth=3, color=GRAY_DARK))

        fig.subplots_adjust(left=0.02, right=0.98, top=0.90, bottom=0.05)
    else:
        fig, (ax_a, ax_b, ax_c) = plt.subplots(
            1,
            3,
            figsize=figsize,
            gridspec_kw={"width_ratios": [3, 3, 2]},
        )
        fig.tight_layout()

    _draw_graph(ax_a, prepared["pos"], prepared["fact_nodes"], prepared["fact_edges"],
                prepared["aux_pts"], set(), prepared["conclusion_id"], "a",
                f"(a) Full Proof Graph ({prepared['n_full']} facts)", node_size=node_size)
    _draw_graph(ax_b, prepared["pos"], prepared["fact_nodes"], prepared["fact_edges"],
                prepared["aux_pts"], prepared["removed"], prepared["conclusion_id"], "b",
                f"(b) Pruned Graph ({prepared['n_pruned']} facts)", node_size=node_size)
    _draw_rule(ax_c, rule_text, pid_text=pid_text)
    return fig


# ────────────────────────── Main entry ────────────────────────────


def create_figure(problem_id, jsonl_path, pruned_json_path):
    # 1. Load raw data
    full_raw = load_full_graph(problem_id, jsonl_path)
    pruned_rendered, rule_text = load_pruned_data(problem_id, pruned_json_path)
    return create_three_panel_figure_from_data(
        full_raw,
        pruned_rendered,
        rule_text,
        show_arrows=True,
        figsize=(18, 7),
        verbose=True,
    )


if __name__ == "__main__":
    base = Path("/C20545/home/duzhengtong/GeoDiscovery/outputs/datasets/synthetic_10k_aux_only")
    pruned_json = base / "geometry_clauses15_samples10k_pruned.json"
    pid = load_default_problem_id(pruned_json)
    out = Path("/C20545/home/duzhengtong/GeoDiscovery/outputs/figures/discovery/rule_extractions")
    out.mkdir(parents=True, exist_ok=True)

    fig = create_figure(
        pid,
        base / "geometry_clauses15_samples10k.jsonl",
        pruned_json,
    )
    for fmt in ("pdf", "png"):
        p = out / f"fig2_rule_extraction.{fmt}"
        fig.savefig(p, format=fmt, bbox_inches="tight", dpi=300)
        print(f"Saved: {p}")
    print(f"Using problem_id: {pid}")
    plt.close(fig)
