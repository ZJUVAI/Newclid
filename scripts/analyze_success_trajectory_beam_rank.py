from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_solved_problems(csv_path: Path) -> list[str]:
    solved: list[str] = []
    with open(csv_path, encoding="utf-8") as fp:
        reader = csv.reader(fp)
        next(reader)
        next(reader)
        for row in reader:
            if row[1] == "√":
                solved.append(row[0])
    return solved


def request_path_key(request_id: str | None) -> tuple[int, ...]:
    if not request_id or "_p" not in request_id:
        return ()
    suffix = request_id.split("_p", 1)[1]
    if suffix == "root":
        return ()
    return tuple(int(part) for part in suffix.split("-"))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with open(path, "w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def quantiles(values: list[int]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "p25": None, "median": None, "p75": None, "max": None}
    ordered = sorted(values)
    return {
        "min": float(ordered[0]),
        "p25": float(ordered[(len(ordered) - 1) // 4]),
        "median": float(median(ordered)),
        "p75": float(ordered[((len(ordered) - 1) * 3) // 4]),
        "max": float(ordered[-1]),
    }


def analyze_run(run_dir: Path, beam_size: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    solved_problems = set(load_solved_problems(run_dir.with_suffix(".csv")))
    per_step_rows: list[dict[str, Any]] = []
    base_solved_problems: list[str] = []

    for problem_path in sorted((run_dir / "problems").glob("*.jsonl")):
        events = load_jsonl(problem_path)
        if not events:
            continue
        problem_name = str(events[0]["problem_name"])
        if problem_name not in solved_problems:
            continue

        problem_end = next(
            (
                event
                for event in reversed(events)
                if event.get("event") == "problem_end" and event.get("success")
            ),
            None,
        )
        if problem_end is None:
            continue

        final_node_id = int(problem_end["final_node_id"])
        if final_node_id == 0:
            base_solved_problems.append(problem_name)
            continue

        candidate_events_by_node: dict[int, list[dict[str, Any]]] = {}
        queued_events_by_depth: dict[int, list[dict[str, Any]]] = {}
        ddar_result_by_node: dict[int, dict[str, Any]] = {}

        for event in events:
            node_id = event.get("node_id")
            if node_id is None:
                continue
            node_id = int(node_id)
            if event.get("event") == "candidate_transition":
                candidate_events_by_node.setdefault(node_id, []).append(event)
                if event.get("decision") == "queued_next_depth":
                    depth = int(event["depth"])
                    queued_events_by_depth.setdefault(depth, []).append(event)
            elif event.get("event") == "ddar_result":
                ddar_result_by_node[node_id] = event

        frontier_rank_by_node: dict[int, int] = {}
        for _, queued_events in queued_events_by_depth.items():
            sorted_entries = sorted(
                queued_events,
                key=lambda event: (
                    -float(event["beam_score_after"]),
                    request_path_key(event.get("request_id")),
                    int(event["node_id"]),
                ),
            )
            for rank, event in enumerate(sorted_entries[:beam_size], start=1):
                frontier_rank_by_node[int(event["node_id"])] = rank

        decision_priority = {
            "solved": 4,
            "queued_next_depth": 3,
            "invalid": 2,
            "unsolved": 2,
            "ddar_submitted": 1,
            "parse_failed": 0,
            "build_failed": 0,
        }

        preferred_candidate_by_node: dict[int, dict[str, Any]] = {}
        for node_id, node_events in candidate_events_by_node.items():
            preferred_candidate_by_node[node_id] = max(
                node_events,
                key=lambda event: decision_priority.get(
                    str(event.get("decision")), -1
                ),
            )

        node_meta: dict[int, dict[str, Any]] = dict(preferred_candidate_by_node)
        if final_node_id in ddar_result_by_node:
            node_meta[final_node_id] = ddar_result_by_node[final_node_id]

        path_rows_reversed: list[dict[str, Any]] = []
        node_id = final_node_id
        while node_id != 0:
            meta = node_meta[node_id]
            candidate_event = preferred_candidate_by_node.get(node_id, {})
            parent_node_id = meta.get(
                "parent_node_id", candidate_event.get("parent_node_id")
            )
            step_type = (
                "solved"
                if node_id == final_node_id
                else candidate_event.get("decision", meta.get("status"))
            )
            path_rows_reversed.append(
                {
                    "problem_name": problem_name,
                    "final_node_id": final_node_id,
                    "node_id": node_id,
                    "parent_node_id": parent_node_id,
                    "depth": meta.get("depth", candidate_event.get("depth")),
                    "is_final_step": node_id == final_node_id,
                    "step_type": step_type,
                    "candidate_rank": candidate_event.get("candidate_rank"),
                    "frontier_beam_rank": frontier_rank_by_node.get(node_id),
                    "beam_score_after": candidate_event.get("beam_score_after"),
                    "construction_text": candidate_event.get("construction_text")
                    or meta.get("construction_text"),
                }
            )
            node_id = int(parent_node_id)

        path_rows = list(reversed(path_rows_reversed))
        for step_index, row in enumerate(path_rows, start=1):
            row["step_index"] = step_index
            per_step_rows.append(row)

    searched_problem_names = sorted({row["problem_name"] for row in per_step_rows})
    all_solved_problem_names = searched_problem_names + sorted(base_solved_problems)
    frontier_ranks = [
        int(row["frontier_beam_rank"])
        for row in per_step_rows
        if not row["is_final_step"] and row["frontier_beam_rank"] is not None
    ]
    final_candidate_ranks = [
        int(row["candidate_rank"])
        for row in per_step_rows
        if row["is_final_step"] and row["candidate_rank"] is not None
    ]

    path_length_counter = Counter()
    final_depth_counter = Counter()
    per_problem_rows: dict[str, list[dict[str, Any]]] = {}
    for row in per_step_rows:
        per_problem_rows.setdefault(str(row["problem_name"]), []).append(row)
    for problem_name in searched_problem_names:
        rows = sorted(per_problem_rows[problem_name], key=lambda row: row["step_index"])
        path_length_counter[len(rows)] += 1
        final_depth_counter[int(rows[-1]["depth"])] += 1
    path_length_counter[0] += len(base_solved_problems)
    final_depth_counter[-1] += len(base_solved_problems)

    top_frontier_cases: list[dict[str, Any]] = []
    for problem_name, rows in per_problem_rows.items():
        intermediates = [
            row for row in rows if not row["is_final_step"] and row["frontier_beam_rank"]
        ]
        if not intermediates:
            continue
        worst = max(intermediates, key=lambda row: int(row["frontier_beam_rank"]))
        top_frontier_cases.append(
            {
                "problem_name": problem_name,
                "worst_frontier_beam_rank": int(worst["frontier_beam_rank"]),
                "path_signature": [
                    {
                        "depth": int(row["depth"]),
                        "candidate_rank": (
                            None
                            if row["candidate_rank"] is None
                            else int(row["candidate_rank"])
                        ),
                        "frontier_beam_rank": (
                            None
                            if row["frontier_beam_rank"] is None
                            else int(row["frontier_beam_rank"])
                        ),
                    }
                    for row in sorted(rows, key=lambda row: row["step_index"])
                ],
            }
        )
    top_frontier_cases.sort(
        key=lambda item: (-item["worst_frontier_beam_rank"], item["problem_name"])
    )

    top_final_candidate_cases: list[dict[str, Any]] = []
    for problem_name, rows in per_problem_rows.items():
        final_row = max(rows, key=lambda row: row["step_index"])
        if final_row["candidate_rank"] is None:
            continue
        top_final_candidate_cases.append(
            {
                "problem_name": problem_name,
                "final_candidate_rank": int(final_row["candidate_rank"]),
                "path_signature": [
                    {
                        "depth": int(row["depth"]),
                        "candidate_rank": (
                            None
                            if row["candidate_rank"] is None
                            else int(row["candidate_rank"])
                        ),
                        "frontier_beam_rank": (
                            None
                            if row["frontier_beam_rank"] is None
                            else int(row["frontier_beam_rank"])
                        ),
                    }
                    for row in sorted(rows, key=lambda row: row["step_index"])
                ],
            }
        )
    top_final_candidate_cases.sort(
        key=lambda item: (-item["final_candidate_rank"], item["problem_name"])
    )

    summary = {
        "run_dir": str(run_dir),
        "beam_size": beam_size,
        "solved_problem_count": len(all_solved_problem_names),
        "base_solved_problem_count": len(base_solved_problems),
        "searched_solved_problem_count": len(searched_problem_names),
        "base_solved_problems": sorted(base_solved_problems),
        "total_step_row_count": len(per_step_rows),
        "intermediate_frontier_rank_count": len(frontier_ranks),
        "intermediate_frontier_rank_quantiles": quantiles(frontier_ranks),
        "final_candidate_rank_count": len(final_candidate_ranks),
        "final_candidate_rank_quantiles": quantiles(final_candidate_ranks),
        "success_path_length_distribution": dict(sorted(path_length_counter.items())),
        "success_final_depth_distribution": dict(sorted(final_depth_counter.items())),
        "top_frontier_rank_cases": top_frontier_cases[:10],
        "top_final_candidate_rank_cases": top_final_candidate_cases[:10],
    }
    return per_step_rows, summary


def plot_frontier_rank_distribution(
    step_rows: list[dict[str, Any]], output_path: Path, beam_size: int
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frontier_ranks = [
        int(row["frontier_beam_rank"])
        for row in step_rows
        if not row["is_final_step"] and row["frontier_beam_rank"] is not None
    ]
    if not frontier_ranks:
        raise ValueError("No intermediate frontier beam ranks found to plot.")

    ordered = sorted(frontier_ranks)
    cumulative = [(index + 1) / len(ordered) for index in range(len(ordered))]

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)

    bins = [1, 2, 4, 8, 16, 32, 64, 128, 256, beam_size]
    axes[0].hist(frontier_ranks, bins=bins, color="#3b82f6", edgecolor="white")
    axes[0].set_xscale("log", base=2)
    axes[0].set_xlabel("Frontier Beam Rank")
    axes[0].set_ylabel("Count")
    axes[0].set_title("Histogram of Intermediate Success-Path Beam Ranks")
    axes[0].grid(alpha=0.25, linestyle=":")

    axes[1].plot(ordered, cumulative, color="#ef4444", linewidth=2)
    axes[1].scatter(ordered, cumulative, color="#ef4444", s=10)
    axes[1].set_xscale("log", base=2)
    axes[1].set_xlim(1, beam_size)
    axes[1].set_ylim(0.0, 1.0)
    axes[1].set_xlabel("Frontier Beam Rank")
    axes[1].set_ylabel("Cumulative Fraction")
    axes[1].set_title("ECDF of Intermediate Success-Path Beam Ranks")
    axes[1].grid(alpha=0.25, linestyle=":")

    fig.suptitle(
        "Successful Trajectory Beam-Rank Distribution\n"
        f"Intermediate queued_next_depth steps only, beam_size={beam_size}",
        fontsize=13,
    )
    fig.savefig(output_path, dpi=200)
    plt.close(fig)


def plot_phase_scatter_distribution(
    step_rows: list[dict[str, Any]], output_path: Path, beam_size: int
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        row
        for row in step_rows
        if not row["is_final_step"] and row["frontier_beam_rank"] is not None
    ]
    if not rows:
        raise ValueError("No intermediate frontier beam ranks found to plot.")

    depths = sorted({int(row["depth"]) for row in rows})
    depth_to_points: dict[int, list[int]] = {depth: [] for depth in depths}
    for row in rows:
        depth_to_points[int(row["depth"])].append(int(row["frontier_beam_rank"]))

    fig, ax = plt.subplots(figsize=(9, 5.2), constrained_layout=True)
    palette = ["#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed"]

    xtick_labels: list[str] = []
    for idx, depth in enumerate(depths):
        ranks = sorted(depth_to_points[depth])
        xtick_labels.append(f"depth {depth}\n(n={len(ranks)})")
        x_values = []
        for j, _ in enumerate(ranks):
            offset = ((j % 7) - 3) * 0.035
            x_values.append(depth + offset)
        ax.scatter(
            x_values,
            ranks,
            s=42,
            alpha=0.75,
            color=palette[idx % len(palette)],
            edgecolors="white",
            linewidths=0.5,
        )
        if ranks:
            ax.hlines(
                y=median(ranks),
                xmin=depth - 0.28,
                xmax=depth + 0.28,
                colors=palette[idx % len(palette)],
                linewidth=2.0,
            )

    ax.set_yscale("log", base=2)
    ax.set_ylim(1, beam_size * 1.18)
    ax.set_xticks(depths)
    ax.set_xticklabels(xtick_labels)
    ax.set_xlabel("Search Depth")
    ax.set_ylabel("Frontier Beam Rank")
    ax.set_title("Successful Trajectory Beam Ranks by Search Depth")
    ax.grid(alpha=0.25, linestyle=":", axis="y")
    fig.suptitle(
        "Phase-Wise Dot Distribution of Successful Intermediate States",
        fontsize=13,
    )
    fig.savefig(output_path, dpi=200)
    plt.close(fig)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run_dir", required=True)
    parser.add_argument("--beam_size", type=int, default=512)
    parser.add_argument("--steps_csv", required=True)
    parser.add_argument("--summary_json", required=True)
    parser.add_argument("--plot_png", required=True)
    parser.add_argument("--phase_plot_png", required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_dir = Path(args.run_dir)
    step_rows, summary = analyze_run(run_dir=run_dir, beam_size=args.beam_size)
    write_csv(Path(args.steps_csv), step_rows)
    Path(args.summary_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.summary_json).write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    plot_frontier_rank_distribution(
        step_rows=step_rows,
        output_path=Path(args.plot_png),
        beam_size=args.beam_size,
    )
    plot_phase_scatter_distribution(
        step_rows=step_rows,
        output_path=Path(args.phase_plot_png),
        beam_size=args.beam_size,
    )


if __name__ == "__main__":
    main()
