from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import to_rgb
from matplotlib.lines import Line2D

from analyze_success_trajectory_beam_rank import analyze_run


DEFAULT_SFT44_RUN_DIR = Path(
    "results/pre_grpo_vlm_sft44_checkpoint20084_qwen3_vl_text_multiaux/"
    "eval_single_problem_multi_gpu_qwen3_vl_text_imo_95_vlm_sft44_checkpoint-20084_"
    "sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260522T073225Z"
)
DEFAULT_V19_RUN_DIR = Path(
    "results/v19_lr5e6_checkpoint500_qwen3_vl_text_multiaux/"
    "eval_single_problem_multi_gpu_qwen3_vl_text_imo_95_v0-20260508-105855_"
    "checkpoint-500_sv1_auxfull_d32_b512_s4_gbs2_gbt100_seed123_20260521T133115Z"
)
DEFAULT_SINGLE_OUTPUT = Path(
    "docs/_static/imo95_sft44_success_trajectory_phase_scatter.png"
)
DEFAULT_COMPARE_OUTPUT = Path(
    "docs/_static/imo95_v19_vs_sft44_success_trajectory_phase_scatter.png"
)
DEFAULT_MANIFEST_OUTPUT = Path(
    "docs/_static/imo95_v19_vs_sft44_success_trajectory_phase_scatter_manifest.json"
)

BEAM_SIZE = 512
DEPTH_COLORS = ["#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed"]
SFT44_COLOR = "#0f766e"
V19_COLOR = "#d97706"
GRID_COLOR = "#d1d5db"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sft44_run_dir", default=str(DEFAULT_SFT44_RUN_DIR))
    parser.add_argument("--v19_run_dir", default=str(DEFAULT_V19_RUN_DIR))
    parser.add_argument("--single_output_path", default=str(DEFAULT_SINGLE_OUTPUT))
    parser.add_argument("--compare_output_path", default=str(DEFAULT_COMPARE_OUTPUT))
    parser.add_argument("--manifest_output_path", default=str(DEFAULT_MANIFEST_OUTPUT))
    parser.add_argument("--beam_size", type=int, default=BEAM_SIZE)
    return parser.parse_args()


def load_intermediate_rows(
    run_dir: Path, beam_size: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    step_rows, summary = analyze_run(run_dir=run_dir, beam_size=beam_size)
    intermediate_rows = [
        row
        for row in step_rows
        if not row["is_final_step"] and row["frontier_beam_rank"] is not None
    ]
    return intermediate_rows, summary


def make_point_key(row: dict[str, Any]) -> tuple[str, int]:
    return str(row["problem_name"]), int(row["depth"])


def depth_counts(rows: list[dict[str, Any]]) -> dict[int, int]:
    return dict(sorted(Counter(int(row["depth"]) for row in rows).items()))


def compute_x_positions(
    rows: list[dict[str, Any]],
    *,
    depth_offset: float,
    max_spread: float = 0.065,
) -> dict[tuple[str, int], float]:
    by_depth: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        by_depth.setdefault(int(row["depth"]), []).append(row)

    positions: dict[tuple[str, int], float] = {}
    for depth, depth_rows in by_depth.items():
        ordered_rows = sorted(
            depth_rows,
            key=lambda row: (
                int(row["frontier_beam_rank"]),
                str(row["problem_name"]),
            ),
        )
        count = len(ordered_rows)
        if count == 1:
            jitters = [0.0]
        else:
            step = (2.0 * max_spread) / (count - 1)
            jitters = [(-max_spread + (index * step)) for index in range(count)]
        for row, jitter in zip(ordered_rows, jitters, strict=True):
            positions[make_point_key(row)] = depth + depth_offset + jitter
    return positions


def plot_single_run_phase_scatter(
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
    output_path: Path,
    beam_size: int,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    depths = sorted({int(row["depth"]) for row in rows})
    depth_to_points: dict[int, list[int]] = {depth: [] for depth in depths}
    for row in rows:
        depth_to_points[int(row["depth"])].append(int(row["frontier_beam_rank"]))

    fig, ax = plt.subplots(figsize=(12, 6.8), constrained_layout=True)
    xtick_labels: list[str] = []
    for idx, depth in enumerate(depths):
        ranks = sorted(depth_to_points[depth])
        xtick_labels.append(f"depth {depth}\n(n={len(ranks)})")
        x_values = [depth + (((j % 7) - 3) * 0.035) for j in range(len(ranks))]
        color = DEPTH_COLORS[idx % len(DEPTH_COLORS)]
        ax.scatter(
            x_values,
            ranks,
            s=68,
            alpha=0.78,
            color=color,
            edgecolors="white",
            linewidths=0.65,
        )
        if ranks:
            ax.hlines(
                y=median(ranks),
                xmin=depth - 0.28,
                xmax=depth + 0.28,
                colors=color,
                linewidth=2.4,
            )

    ax.set_yscale("log", base=2)
    ax.set_ylim(1, beam_size * 1.18)
    ax.set_xticks(depths)
    ax.set_xticklabels(xtick_labels)
    ax.set_xlabel("Search Depth", fontsize=14)
    ax.set_ylabel("Frontier Beam Rank", fontsize=16)
    ax.tick_params(axis="both", labelsize=12)
    ax.grid(alpha=0.55, linestyle=":", axis="y", color=GRID_COLOR)
    ax.set_title("Successful Trajectory Beam Ranks by Search Depth", fontsize=19, pad=14)
    fig.suptitle(
        "Phase-Wise Dot Distribution of Successful Intermediate States\n"
        f"sft44 solved {summary['solved_problem_count']}/95, intermediate points={len(rows)}",
        fontsize=24,
    )
    fig.savefig(output_path, dpi=220)
    plt.close(fig)


def _interpolate_rgb(
    start_rgb: tuple[float, float, float],
    end_rgb: tuple[float, float, float],
    ratio: float,
) -> tuple[float, float, float]:
    return tuple(
        start_rgb[channel] + ((end_rgb[channel] - start_rgb[channel]) * ratio)
        for channel in range(3)
    )


def add_gradient_line(
    ax,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    *,
    start_color: str,
    end_color: str,
    linewidth: float = 1.8,
    alpha: float = 0.85,
    segment_count: int = 24,
) -> None:
    if x0 == x1 and y0 == y1:
        return
    xs = [x0 + ((x1 - x0) * index / segment_count) for index in range(segment_count + 1)]
    ys = [y0 + ((y1 - y0) * index / segment_count) for index in range(segment_count + 1)]
    segments = [
        [(xs[index], ys[index]), (xs[index + 1], ys[index + 1])]
        for index in range(segment_count)
    ]
    start_rgb = to_rgb(start_color)
    end_rgb = to_rgb(end_color)
    colors = [
        _interpolate_rgb(start_rgb, end_rgb, index / max(segment_count - 1, 1))
        for index in range(segment_count)
    ]
    collection = LineCollection(
        segments,
        colors=colors,
        linewidths=linewidth,
        alpha=alpha,
        zorder=2,
    )
    ax.add_collection(collection)


def plot_compare_phase_scatter(
    sft44_rows: list[dict[str, Any]],
    v19_rows: list[dict[str, Any]],
    sft44_summary: dict[str, Any],
    v19_summary: dict[str, Any],
    output_path: Path,
    beam_size: int,
) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    sft44_positions = compute_x_positions(sft44_rows, depth_offset=-0.14)
    v19_positions = compute_x_positions(v19_rows, depth_offset=0.14)

    sft44_by_key = {make_point_key(row): row for row in sft44_rows}
    v19_by_key = {make_point_key(row): row for row in v19_rows}
    common_keys = sorted(set(sft44_by_key) & set(v19_by_key))
    sft44_only_keys = sorted(set(sft44_by_key) - set(v19_by_key))
    v19_only_keys = sorted(set(v19_by_key) - set(sft44_by_key))

    matched_rank_deltas: list[dict[str, Any]] = []
    for problem_name, depth in common_keys:
        sft44_rank = int(sft44_by_key[(problem_name, depth)]["frontier_beam_rank"])
        v19_rank = int(v19_by_key[(problem_name, depth)]["frontier_beam_rank"])
        matched_rank_deltas.append(
            {
                "problem_name": problem_name,
                "depth": depth,
                "sft44_rank": sft44_rank,
                "v19_rank": v19_rank,
                "delta": v19_rank - sft44_rank,
            }
        )

    max_depth = 0
    for row in sft44_rows + v19_rows:
        max_depth = max(max_depth, int(row["depth"]))
    x_ticks = list(range(max_depth + 1))

    fig, ax = plt.subplots(figsize=(13.5, 7.6), constrained_layout=True)

    for depth in x_ticks:
        sft44_depth_rows = sorted(
            [row for row in sft44_rows if int(row["depth"]) == depth],
            key=lambda row: (
                int(row["frontier_beam_rank"]),
                str(row["problem_name"]),
            ),
        )
        v19_depth_rows = sorted(
            [row for row in v19_rows if int(row["depth"]) == depth],
            key=lambda row: (
                int(row["frontier_beam_rank"]),
                str(row["problem_name"]),
            ),
        )
        if sft44_depth_rows:
            ranks = [int(row["frontier_beam_rank"]) for row in sft44_depth_rows]
            ax.hlines(
                y=median(ranks),
                xmin=depth - 0.28,
                xmax=depth - 0.02,
                colors=SFT44_COLOR,
                linewidth=2.2,
                zorder=2.5,
            )
        if v19_depth_rows:
            ranks = [int(row["frontier_beam_rank"]) for row in v19_depth_rows]
            ax.hlines(
                y=median(ranks),
                xmin=depth + 0.02,
                xmax=depth + 0.28,
                colors=V19_COLOR,
                linewidth=2.2,
                zorder=2.5,
            )

    for problem_name, depth in common_keys:
        sft44_row = sft44_by_key[(problem_name, depth)]
        v19_row = v19_by_key[(problem_name, depth)]
        add_gradient_line(
            ax,
            sft44_positions[(problem_name, depth)],
            float(sft44_row["frontier_beam_rank"]),
            v19_positions[(problem_name, depth)],
            float(v19_row["frontier_beam_rank"]),
            start_color=SFT44_COLOR,
            end_color=V19_COLOR,
        )

    ax.scatter(
        [sft44_positions[make_point_key(row)] for row in sft44_rows],
        [int(row["frontier_beam_rank"]) for row in sft44_rows],
        s=64,
        alpha=0.9,
        color=SFT44_COLOR,
        edgecolors="white",
        linewidths=0.65,
        zorder=3,
        label=f"sft44 points ({len(sft44_rows)})",
    )
    ax.scatter(
        [v19_positions[make_point_key(row)] for row in v19_rows],
        [int(row["frontier_beam_rank"]) for row in v19_rows],
        s=64,
        alpha=0.9,
        color=V19_COLOR,
        edgecolors="white",
        linewidths=0.65,
        zorder=3,
        label=f"v19 points ({len(v19_rows)})",
    )

    ax.set_xticks(x_ticks)
    ax.set_xticklabels([f"depth {depth}" for depth in x_ticks])
    ax.set_xlim(-0.5, max_depth + 0.5)
    ax.set_yscale("log", base=2)
    ax.set_ylim(1, beam_size * 1.18)
    ax.set_xlabel("Search Depth", fontsize=14)
    ax.set_ylabel("Frontier Beam Rank", fontsize=16)
    ax.tick_params(axis="both", labelsize=12)
    ax.grid(alpha=0.55, linestyle=":", axis="y", color=GRID_COLOR)
    ax.set_title(
        "Successful Trajectory Beam-Rank Comparison by Search Depth",
        fontsize=19,
        pad=14,
    )

    legend_handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="None",
            markersize=8,
            markerfacecolor=SFT44_COLOR,
            markeredgecolor="white",
            label=f"sft44 ({sft44_summary['solved_problem_count']}/95 solved)",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="None",
            markersize=8,
            markerfacecolor=V19_COLOR,
            markeredgecolor="white",
            label=f"v19 ({v19_summary['solved_problem_count']}/95 solved)",
        ),
        Line2D(
            [0, 1],
            [0, 0],
            color="#8b5cf6",
            linewidth=2.0,
            label="gradient line: sft44 -> v19",
        ),
    ]
    ax.legend(handles=legend_handles, loc="upper left", frameon=False, fontsize=11)

    fig.suptitle(
        "IMO95 Successful Trajectory Phase Scatter: sft44 vs v19\n"
        f"Paired by (problem, depth): matched={len(common_keys)}, "
        f"sft44-only={len(sft44_only_keys)}, v19-only={len(v19_only_keys)}",
        fontsize=23,
    )
    fig.savefig(output_path, dpi=220)
    plt.close(fig)

    delta_counts = Counter()
    for item in matched_rank_deltas:
        if item["delta"] < 0:
            delta_counts["v19_better"] += 1
        elif item["delta"] > 0:
            delta_counts["v19_worse"] += 1
        else:
            delta_counts["unchanged"] += 1

    return {
        "matched_pair_count": len(common_keys),
        "sft44_only_pair_count": len(sft44_only_keys),
        "v19_only_pair_count": len(v19_only_keys),
        "common_problem_count": len({problem_name for problem_name, _ in common_keys}),
        "delta_counts": dict(delta_counts),
        "depth_counts": {
            "common": dict(sorted(Counter(depth for _, depth in common_keys).items())),
            "sft44_only": dict(sorted(Counter(depth for _, depth in sft44_only_keys).items())),
            "v19_only": dict(sorted(Counter(depth for _, depth in v19_only_keys).items())),
        },
        "sample_sft44_only": [
            {"problem_name": problem_name, "depth": depth}
            for problem_name, depth in sft44_only_keys[:12]
        ],
        "sample_v19_only": [
            {"problem_name": problem_name, "depth": depth}
            for problem_name, depth in v19_only_keys[:12]
        ],
        "rank_deltas": matched_rank_deltas,
    }


def main() -> None:
    args = parse_args()
    beam_size = int(args.beam_size)
    sft44_run_dir = Path(args.sft44_run_dir)
    v19_run_dir = Path(args.v19_run_dir)

    sft44_rows, sft44_summary = load_intermediate_rows(sft44_run_dir, beam_size)
    v19_rows, v19_summary = load_intermediate_rows(v19_run_dir, beam_size)

    plot_single_run_phase_scatter(
        rows=sft44_rows,
        summary=sft44_summary,
        output_path=Path(args.single_output_path),
        beam_size=beam_size,
    )
    compare_manifest = plot_compare_phase_scatter(
        sft44_rows=sft44_rows,
        v19_rows=v19_rows,
        sft44_summary=sft44_summary,
        v19_summary=v19_summary,
        output_path=Path(args.compare_output_path),
        beam_size=beam_size,
    )

    manifest = {
        "beam_size": beam_size,
        "single_plot": {
            "run_dir": str(sft44_run_dir),
            "output_path": str(Path(args.single_output_path)),
            "solved_problem_count": sft44_summary["solved_problem_count"],
            "intermediate_point_count": len(sft44_rows),
            "depth_counts": depth_counts(sft44_rows),
        },
        "compare_plot": {
            "sft44_run_dir": str(sft44_run_dir),
            "v19_run_dir": str(v19_run_dir),
            "output_path": str(Path(args.compare_output_path)),
            "sft44": {
                "solved_problem_count": sft44_summary["solved_problem_count"],
                "intermediate_point_count": len(sft44_rows),
                "depth_counts": depth_counts(sft44_rows),
            },
            "v19": {
                "solved_problem_count": v19_summary["solved_problem_count"],
                "intermediate_point_count": len(v19_rows),
                "depth_counts": depth_counts(v19_rows),
            },
            "pairing": compare_manifest,
        },
    }

    manifest_output_path = Path(args.manifest_output_path)
    manifest_output_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_output_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
