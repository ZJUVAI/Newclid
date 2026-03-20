#!/usr/bin/env python3
"""
Figure 1: Discovery Pipeline Flow Diagram
Horizontal flow aligned with the current two-stage discovery pipeline.
"""
from pathlib import Path

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

# Color scheme
BLUE_PRIMARY = "#2E5C8A"
BLUE_LIGHT = "#5B9BD5"
GRAY_DARK = "#4A4A4A"
ORANGE_PRIMARY = "#E67E22"
ORANGE_LIGHT = "#FBE5D6"
GREEN_ACCENT = "#27AE60"

plt.rcParams["font.family"] = "DejaVu Sans"
plt.rcParams["font.size"] = 10

# Stage 1: FilterAndPruneEngine (step-level funnel data from 10k experiment)
STAGE1_DATA = [
    ("Step 1\nInput Filter", 10050, 4650, 0.4627),
    ("Step 2\nGraph Prune", 4650, 4120, 0.8860),
    ("Step 3\nProposition\nExtraction", 4120, 3281, 0.7964),
    ("Step 4\nNormalization", 3281, 3281, 1.0000),
    ("Step 5\nDedup", 3281, 1186, 0.3615),
    ("Step 6\nRule Output", 1186, 1082, 0.9123),
]

# Stage 2: RuleReducer (phase structure only; do not show unstable funnel counts)
STAGE2_PHASES = [
    ("Phase 1\nGroup Reduction", "by seed"),
    ("Phase 2\nGlobal Reduction", "basis rules"),
]


def _draw_box(ax, x, y, width, height, label, center_text, color):
    box = mpatches.FancyBboxPatch(
        (x - width / 2, y),
        width,
        height,
        boxstyle="round,pad=0.1",
        facecolor=color,
        edgecolor=GRAY_DARK,
        linewidth=2,
    )
    ax.add_patch(box)
    ax.text(
        x,
        y + height - 0.28,
        label,
        ha="center",
        va="top",
        fontsize=8.5,
        weight="bold",
        color="white",
    )
    ax.text(
        x,
        y + height * 0.34,
        center_text,
        ha="center",
        va="center",
        fontsize=13,
        weight="bold",
        color="white",
    )


def _draw_arrow(ax, start_x, end_x, y, *, label=None):
    arrow = mpatches.FancyArrowPatch(
        (start_x, y),
        (end_x, y),
        arrowstyle="->",
        mutation_scale=22,
        linewidth=2.5,
        color=GRAY_DARK,
    )
    ax.add_patch(arrow)
    if label:
        ax.text(
            (start_x + end_x) / 2,
            y + 0.3,
            label,
            ha="center",
            va="bottom",
            fontsize=8,
            weight="bold",
            color=GREEN_ACCENT,
            bbox=dict(
                boxstyle="round,pad=0.25",
                facecolor="white",
                edgecolor=GREEN_ACCENT,
                linewidth=1.2,
            ),
        )


def draw_pipeline():
    fig, ax = plt.subplots(figsize=(20, 4.8))
    ax.set_xlim(0, 20)
    ax.set_ylim(0, 5.2)
    ax.axis("off")

    box_width = 1.15
    box_height = 2.35
    box_y = 1.0
    step_positions = [1.7, 3.5, 5.3, 7.1, 8.9, 10.7, 14.0, 16.6]
    pad = 0.4

    stage_configs = [
        (
            "Stage 1: FilterAndPruneEngine",
            step_positions[0] - box_width / 2 - pad,
            step_positions[5] + box_width / 2 + pad,
            BLUE_LIGHT,
            0.15,
        ),
        (
            "Stage 2: RuleReducer",
            step_positions[6] - box_width / 2 - pad,
            step_positions[7] + box_width / 2 + pad,
            ORANGE_LIGHT,
            0.20,
        ),
    ]

    for title, x_left, x_right, bg_color, alpha in stage_configs:
        bg = mpatches.FancyBboxPatch(
            (x_left, box_y - 0.32),
            x_right - x_left,
            box_height + 0.88,
            boxstyle="round,pad=0.25",
            facecolor=bg_color,
            edgecolor=GRAY_DARK,
            linewidth=1.5,
            alpha=alpha,
        )
        ax.add_patch(bg)
        ax.text(
            (x_left + x_right) / 2,
            box_y + box_height + 0.72,
            title,
            ha="center",
            va="center",
            fontsize=12,
            weight="bold",
            color=GRAY_DARK,
        )

    for i, (label, _input_count, output_count, retention) in enumerate(STAGE1_DATA):
        x = step_positions[i]
        count_text = f"{output_count:,}" if output_count >= 100 else str(output_count)
        _draw_box(ax, x, box_y, box_width, box_height, label, count_text, BLUE_PRIMARY)

        if i < len(STAGE1_DATA) - 1:
            next_x = step_positions[i + 1]
            _draw_arrow(
                ax,
                x + box_width / 2 + 0.1,
                next_x - box_width / 2 - 0.1,
                box_y + box_height / 2,
                label=f"{retention * 100:.1f}%",
            )

    for i, (label, center_text) in enumerate(STAGE2_PHASES, start=6):
        x = step_positions[i]
        _draw_box(ax, x, box_y, box_width, box_height, label, center_text, ORANGE_PRIMARY)

    _draw_arrow(
        ax,
        step_positions[5] + box_width / 2 + 0.1,
        step_positions[6] - box_width / 2 - 0.1,
        box_y + box_height / 2,
    )
    _draw_arrow(
        ax,
        step_positions[6] + box_width / 2 + 0.1,
        step_positions[7] - box_width / 2 - 0.1,
        box_y + box_height / 2,
    )

    ax.text(
        step_positions[0] - box_width / 2 - 0.65,
        box_y + box_height / 2,
        "10,050",
        ha="right",
        va="center",
        fontsize=15,
        weight="bold",
        color=BLUE_PRIMARY,
        bbox=dict(
            boxstyle="round,pad=0.4",
            facecolor="white",
            edgecolor=BLUE_PRIMARY,
            linewidth=2,
        ),
    )

    ax.text(
        (step_positions[5] + step_positions[6]) / 2,
        box_y + box_height / 2 + 0.55,
        "1,082 extracted rules",
        ha="center",
        va="bottom",
        fontsize=9,
        weight="bold",
        color=GRAY_DARK,
        bbox=dict(
            boxstyle="round,pad=0.25",
            facecolor="white",
            edgecolor=GRAY_DARK,
            linewidth=1.2,
        ),
    )

    ax.text(
        step_positions[-1] + box_width / 2 + 0.65,
        box_y + box_height / 2,
        "11",
        ha="left",
        va="center",
        fontsize=15,
        weight="bold",
        color=ORANGE_PRIMARY,
        bbox=dict(
            boxstyle="round,pad=0.4",
            facecolor="white",
            edgecolor=ORANGE_PRIMARY,
            linewidth=2,
        ),
    )

    ax.text(
        10,
        0.28,
        "Overall: 10,050 samples  ->  1,082 extracted rules  ->  11 basis rules",
        ha="center",
        va="center",
        fontsize=11,
        weight="bold",
        color=GRAY_DARK,
        bbox=dict(
            boxstyle="round,pad=0.5",
            facecolor="white",
            edgecolor=GRAY_DARK,
            linewidth=1.5,
        ),
    )

    plt.tight_layout()
    return fig


if __name__ == "__main__":
    output_dir = Path("/C20545/home/duzhengtong/GeoDiscovery/outputs/figures/discovery/pipeline_diagrams")
    output_dir.mkdir(parents=True, exist_ok=True)

    fig = draw_pipeline()

    pdf_path = output_dir / "fig1_pipeline_flow.pdf"
    png_path = output_dir / "fig1_pipeline_flow.png"

    fig.savefig(pdf_path, format="pdf", bbox_inches="tight", dpi=300)
    fig.savefig(png_path, format="png", bbox_inches="tight", dpi=300)

    print(f"Saved: {pdf_path}")
    print(f"Saved: {png_path}")
    plt.close(fig)
