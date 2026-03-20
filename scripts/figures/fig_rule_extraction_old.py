#!/usr/bin/env python3
"""
Figure 2: Rule Extraction Illustration
Three panels: (a) Full Proof Graph -> (b) Pruned Graph -> (c) Extracted Rule
Uses real data from pid:007951 (24 nodes full -> 15 nodes pruned)
Rule: coll a b c, coll a b d, cong a c b c, cong a d b d, perp c e c f => perp e d f d
"""
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from pathlib import Path

# Color scheme
BLUE_PRIMARY = "#2E5C8A"      # premise (no aux)
BLUE_LIGHT   = "#A8C8E8"      # intermediate fact (no aux)
RED_LIGHT    = "#FFB3B3"      # aux-related facts (light red)
ORANGE_PRIMARY = "#E67E22"    # conclusion
GRAY_DARK = "#4A4A4A"         # edges, text
GRAY_MED = "#95A5A6"
GRAY_LIGHT = "#BDC3C7"
FADED = "#E0E0E0"             # pruned nodes
RED_CROSS = "#E74C3C"         # aux border in panel b
WHITE = "#FFFFFF"

plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['font.size'] = 9

# ── Real data from pid:007951 (removed unused nodes and rules) ──
# Only fact nodes, no rule nodes
# Aux point: k
# Premises (layer 1): 0,1,2,3,4,5
# Derived facts: 6,7,8,9,10,11,12,13
# Conclusion: 13 perp(g,j,i,j)

FULL_NODES = [
    # idx, type, short_label, layer, has_aux
    (0,  'fact', 'midp',      1, False),  # midp(f,a,b) - PREMISE
    (1,  'fact', 'midp',      1, False),  # midp(j,a,b) - PREMISE
    (2,  'fact', 'cong',      1, True),   # cong(a,f,a,k) - PREMISE, has aux k
    (3,  'fact', 'ncoll',     1, True),   # ncoll(a,f,k) - PREMISE, has aux k
    (4,  'fact', 'perp',      1, False),  # perp(c,e,f,g) - PREMISE
    (5,  'fact', 'para',      1, False),  # para(c,e,f,i) - PREMISE
    (6,  'fact', 'coll',      2, False),  # coll(a,b,f)
    (7,  'fact', 'coll',      2, False),  # coll(a,b,j)
    (8,  'fact', 'cong',      3, True),   # cong(a,k,a,j) - has aux k
    (9,  'fact', 'constline', 4, True),   # constline(k,f,j) - has aux k
    (10, 'fact', 'eqpoint',   5, False),  # eqpoint(f,j)
    (11, 'fact', 'perp',      2, False),  # perp(f,g,f,i)
    (12, 'fact', 'perp',      6, False),  # perp(g,j,i,j) - intermediate
    (13, 'fact', 'perp',      7, False),  # perp(g,j,i,j) - CONCLUSION
]

# Fact-to-fact edges (skipping rule nodes)
FULL_EDGES = [
    # midp(f) -> coll(f)
    (0, 6),
    # midp(j) -> coll(j)
    (1, 7),
    # coll(f), coll(j), cong(aux) -> cong(aux intermediate)
    (6, 8), (7, 8), (2, 8),
    # coll(f), coll(j), cong(aux), cong(aux intermediate) -> constline(aux)
    (6, 9), (7, 9), (2, 9), (8, 9),
    # coll(f), coll(j), constline(aux), ncoll(aux) -> eqpoint
    (6, 10), (7, 10), (9, 10), (3, 10),
    # perp, para -> perp(intermediate)
    (4, 11), (5, 11),
    # eqpoint, perp(intermediate) -> perp(intermediate 2)
    (10, 12), (11, 12),
    # perp(intermediate 2) -> perp(conclusion)
    (12, 13),
]

# Pruned graph keeps: indices in pruned data
# Removed: 0(midp), 1(midp), 8(cong-aux)
# The pruned graph has 11 nodes
PRUNED_INDICES = {2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13}
REMOVED_INDICES = set(range(14)) - PRUNED_INDICES


def _layout_full():
    """Manual hierarchical layout for 14-node fact-only graph.
    Separated layout to avoid overlap between midp(j) branch and aux cong.
    """
    return {
        # Layer 1: premises (y=6.0)
        0:  (-4.0, 6.0),   # midp(f,a,b)
        1:  (-1.5, 6.0),   # midp(j,a,b) - moved left to separate from aux
        2:  (1.5, 6.0),    # cong(a,f,a,k) - aux
        3:  (3.5, 6.0),    # ncoll(a,f,k) - aux
        4:  (5.5, 6.0),    # perp(c,e,f,g)
        5:  (7.0, 6.0),    # para(c,e,f,i)

        # Layer 2: coll facts (y=4.0)
        6:  (-4.0, 4.0),   # coll(a,b,f) - directly below midp(f)
        7:  (-1.5, 4.0),   # coll(a,b,j) - directly below midp(j)
        11: (6.25, 4.0),   # perp(f,g,f,i) - from perp/para

        # Layer 3: cong(aux intermediate) (y=2.5)
        8:  (0.0, 2.5),    # cong(a,k,a,j) - centered between coll branches and aux

        # Layer 4: constline(aux) (y=1.0)
        9:  (0.5, 1.0),    # constline(k,f,j)

        # Layer 5: eqpoint (y=-0.5)
        10: (1.5, -0.5),   # eqpoint(f,j)

        # Layer 6: perp(intermediate) (y=-2.0)
        12: (3.0, -2.0),   # perp(g,j,i,j) - intermediate

        # Layer 7: perp(conclusion) (y=-3.5)
        13: (3.0, -3.5),   # perp(g,j,i,j) - CONCLUSION
    }


def _get_node_role(idx, panel='a'):
    """Determine node role for coloring.
    In panel b, nodes that become premises (predecessors removed) are colored as premises.
    """
    ntype = FULL_NODES[idx][1]
    layer = FULL_NODES[idx][3]
    has_aux = FULL_NODES[idx][4]

    # Conclusion is always conclusion
    if idx == 13:
        return 'conclusion'

    # Original premises (layer 1)
    if ntype == 'fact' and layer == 1:
        if has_aux:
            return 'premise_aux'
        return 'premise'

    # In panel b, check if this node becomes a premise (all predecessors removed)
    if panel == 'b':
        # Find predecessors
        predecessors = [u for u, v in FULL_EDGES if v == idx]
        # If all predecessors are removed, this becomes a premise
        if predecessors and all(pred in REMOVED_INDICES for pred in predecessors):
            if has_aux:
                return 'premise_aux'
            return 'premise'

    # Otherwise, intermediate
    if has_aux:
        return 'intermediate_aux'
    return 'intermediate'


def _has_aux_edge(u, v):
    """Check if edge involves any aux node."""
    return FULL_NODES[u][4] or FULL_NODES[v][4]


def _role_style(role, is_removed=False, panel='a'):
    """Return (facecolor, edgecolor, linewidth, alpha) based on role."""
    if panel == 'b' and is_removed:
        return FADED, GRAY_LIGHT, 1.0, 0.25

    if panel == 'a':
        styles = {
            'premise':          (BLUE_PRIMARY, BLUE_PRIMARY, 2.5, 1.0),
            'premise_aux':      (RED_LIGHT, RED_LIGHT, 2.5, 1.0),
            'conclusion':       (ORANGE_PRIMARY, ORANGE_PRIMARY, 2.5, 1.0),
            'intermediate':     (BLUE_LIGHT, BLUE_LIGHT, 1.5, 1.0),
            'intermediate_aux': (RED_LIGHT, RED_LIGHT, 1.5, 1.0),
        }
    else:  # panel == 'b' - kept nodes restore to full color
        styles = {
            'premise':          (BLUE_PRIMARY, BLUE_PRIMARY, 2.5, 1.0),
            'premise_aux':      (RED_LIGHT, RED_CROSS, 2.5, 1.0),
            'conclusion':       (ORANGE_PRIMARY, ORANGE_PRIMARY, 2.5, 1.0),
            'intermediate':     (BLUE_LIGHT, BLUE_LIGHT, 1.5, 1.0),
            'intermediate_aux': (RED_LIGHT, RED_CROSS, 1.5, 1.0),
        }
    return styles.get(role, (WHITE, GRAY_DARK, 1.5, 1.0))


def _draw_graph(ax, pos, panel='a', title=''):
    ax.set_title(title, fontsize=13, weight='bold', pad=12)
    ax.axis('off')

    # Draw edges first (behind nodes) - uniform color, no distinction for aux
    for u, v in FULL_EDGES:
        is_removed = (panel == 'b') and (u in REMOVED_INDICES or v in REMOVED_INDICES)

        x1, y1 = pos[u]
        x2, y2 = pos[v]
        dx, dy = x2 - x1, y2 - y1
        dist = np.hypot(dx, dy)
        if dist == 0:
            continue
        ux, uy = dx / dist, dy / dist
        r = 0.22  # all nodes are facts now
        x1a, y1a = x1 + ux * r, y1 + uy * r
        x2a, y2a = x2 - ux * r, y2 - uy * r

        if is_removed:
            style, color, width, alpha = 'solid', GRAY_LIGHT, 1.0, 0.15
        else:
            style, color, width, alpha = 'solid', GRAY_DARK, 1.5, 0.8

        ax.annotate('', xy=(x2a, y2a), xytext=(x1a, y1a),
                    arrowprops=dict(arrowstyle='->', color=color,
                                    lw=width, linestyle=style, alpha=alpha,
                                    shrinkA=0, shrinkB=0))

    # Draw nodes
    for idx, ntype, label, layer, has_aux in FULL_NODES:
        x, y = pos[idx]
        role = _get_node_role(idx, panel)
        is_removed = idx in REMOVED_INDICES
        fc, ec, lw, alpha = _role_style(role, is_removed, panel)

        size = 450  # all nodes are facts

        ax.scatter([x], [y], s=size, c=[fc], edgecolors=[ec],
                   linewidths=lw, alpha=alpha, marker='o', zorder=5)

        # Label
        txt = label
        if panel == 'b' and is_removed:
            txt_alpha = 0.2
        else:
            txt_alpha = 1.0

        # Determine text color based on background
        if fc in [BLUE_PRIMARY, ORANGE_PRIMARY, RED_LIGHT] and alpha > 0.8:
            if fc == RED_LIGHT:
                font_color = GRAY_DARK
            else:
                font_color = 'white'
        elif fc == BLUE_LIGHT:
            font_color = GRAY_DARK
        else:
            font_color = GRAY_DARK

        ax.text(x, y, txt, ha='center', va='center', fontsize=7,
                weight='bold', color=font_color, alpha=txt_alpha, zorder=6)

    # Auto-fit limits
    xs = [pos[i][0] for i in range(14)]
    ys = [pos[i][1] for i in range(14)]
    margin = 0.8
    ax.set_xlim(min(xs) - margin, max(xs) + margin)
    ax.set_ylim(min(ys) - margin, max(ys) + margin)

    # Legend only on panel b
    if panel == 'b':
        legend_elements = [
            mpatches.Patch(facecolor=BLUE_PRIMARY, edgecolor=BLUE_PRIMARY, label='Premise'),
            mpatches.Patch(facecolor=RED_LIGHT, edgecolor=RED_LIGHT, label='Aux-related'),
            mpatches.Patch(facecolor=BLUE_LIGHT, edgecolor=BLUE_LIGHT, label='Intermediate'),
            mpatches.Patch(facecolor=ORANGE_PRIMARY, edgecolor=ORANGE_PRIMARY, label='Conclusion'),
            mpatches.Patch(facecolor=FADED, edgecolor=GRAY_LIGHT, label='Pruned'),
        ]
        ax.legend(handles=legend_elements, loc='lower right', fontsize=7,
                  framealpha=0.9, edgecolor=GRAY_DARK)


def draw_panel_c(ax):
    """Panel (c): Only the extracted rule text in box, centered."""
    ax.set_title("(c) Extracted Rule", fontsize=13, weight='bold', pad=12)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5)
    ax.axis('off')

    # Rule text in box, centered
    rule_text = "coll a b c, coll a b d, cong a c b c,\ncong a d b d, perp c e c f => perp e d f d"
    ax.text(5, 2.5, rule_text, ha='center', va='center',
            fontsize=11, color=GRAY_DARK,
            bbox=dict(boxstyle='round,pad=0.8', facecolor=WHITE,
                      edgecolor=GRAY_DARK, linewidth=2))


def create_figure():
    fig = plt.figure(figsize=(18, 7))

    gs = fig.add_gridspec(1, 7, width_ratios=[3, 0.3, 3, 0.3, 2, 0, 0], wspace=0.05)
    ax_a = fig.add_subplot(gs[0])
    ax_arrow1 = fig.add_subplot(gs[1])
    ax_b = fig.add_subplot(gs[2])
    ax_arrow2 = fig.add_subplot(gs[3])
    ax_c = fig.add_subplot(gs[4])

    pos = _layout_full()

    _draw_graph(ax_a, pos, panel='a', title='(a) Full Proof Graph (14 nodes)')
    _draw_graph(ax_b, pos, panel='b', title='(b) Pruned Graph (11 nodes)')
    draw_panel_c(ax_c)

    # Transition arrows
    for ax_arr in [ax_arrow1, ax_arrow2]:
        ax_arr.set_xlim(0, 1)
        ax_arr.set_ylim(0, 1)
        ax_arr.axis('off')
        arrow = mpatches.FancyArrowPatch(
            (0.1, 0.5), (0.9, 0.5),
            arrowstyle='->', mutation_scale=30,
            linewidth=3, color=GRAY_DARK
        )
        ax_arr.add_patch(arrow)

    fig.subplots_adjust(left=0.02, right=0.98, top=0.90, bottom=0.05)
    return fig


if __name__ == "__main__":
    output_dir = Path("/C20545/home/duzhengtong/GeoDiscovery/outputs/experiments/20260307_discovery_10k_aux_only/figures")
    output_dir.mkdir(parents=True, exist_ok=True)

    fig = create_figure()

    pdf_path = output_dir / "fig2_rule_extraction.pdf"
    png_path = output_dir / "fig2_rule_extraction.png"

    fig.savefig(pdf_path, format='pdf', bbox_inches='tight', dpi=300)
    fig.savefig(png_path, format='png', bbox_inches='tight', dpi=300)

    print(f"Saved: {pdf_path}")
    print(f"Saved: {png_path}")
    plt.close(fig)
