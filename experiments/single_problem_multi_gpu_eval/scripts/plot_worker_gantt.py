from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


GROUP_ORDER = ("Prepare", "GPU", "DDAR")
GROUP_COLORS = {
    "Prepare": "#4c78a8",
    "GPU": "#f58518",
    "DDAR": "#54a24b",
}
DDAR_BUILD_COLOR = "#72b7b2"
DDAR_ENGINE_COLOR = "#54a24b"


class TraceCompatibilityError(RuntimeError):
    pass


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _problem_file_candidates(run_dir: Path) -> list[Path]:
    return sorted((run_dir / "problems").glob("*.jsonl"))


def resolve_problem_file(run_dir: Path, problem_selector: str) -> Path:
    candidates = _problem_file_candidates(run_dir)
    if not candidates:
        raise FileNotFoundError(f"No problem trace files found under {run_dir / 'problems'}")
    if problem_selector.isdigit():
        problem_index = int(problem_selector)
        for path in candidates:
            if path.name.startswith(f"{problem_index:04d}_"):
                return path
    for path in candidates:
        records = load_jsonl(path)
        if records and records[0].get("problem_name") == problem_selector:
            return path
    raise FileNotFoundError(f"Problem '{problem_selector}' not found in {run_dir / 'problems'}")


def _require_fields(event: dict[str, Any], event_name: str, fields: list[str]) -> None:
    missing = [field for field in fields if event.get(field) is None]
    if missing:
        raise TraceCompatibilityError(
            f"Event '{event_name}' is missing worker-level fields {missing}. Re-run profiling with the new trace schema."
        )


def extract_worker_intervals(
    events: list[dict[str, Any]],
    *,
    depths: set[int] | None = None,
    include_base_ddar: bool = False,
) -> tuple[str, list[dict[str, Any]]]:
    if not events:
        raise ValueError("No events found for the selected problem.")
    problem_name = str(events[0].get("problem_name", "<unknown>"))
    intervals: list[dict[str, Any]] = []

    for event in events:
        event_name = event.get("event")
        depth = int(event.get("depth", -1))
        if event_name == "prepare_request_ready":
            if depths is not None and depth not in depths:
                continue
            _require_fields(
                event,
                "prepare_request_ready",
                ["prepare_worker_id", "prepare_started_at_unix_s", "prepare_finished_at_unix_s"],
            )
            intervals.append(
                {
                    "depth": depth,
                    "group": "Prepare",
                    "worker_id": str(event["prepare_worker_id"]),
                    "label": str(event.get("request_id", "<missing>")),
                    "start_unix_s": float(event["prepare_started_at_unix_s"]),
                    "end_unix_s": float(event["prepare_finished_at_unix_s"]),
                }
            )
        elif event_name == "gpu_batch_done":
            if depths is not None and depth not in depths:
                continue
            worker_profile = dict(event.get("worker_batch_profile") or {})
            merged_event = {**event, **worker_profile}
            _require_fields(
                merged_event,
                "gpu_batch_done",
                ["gpu_worker_id", "worker_started_at_unix_s", "worker_finished_at_unix_s"],
            )
            request_ids = ",".join(str(item) for item in event.get("request_ids", []))
            intervals.append(
                {
                    "depth": depth,
                    "group": "GPU",
                    "worker_id": str(merged_event["gpu_worker_id"]),
                    "label": f"{request_ids} (bs={int(event.get('batch_size', 0))})",
                    "start_unix_s": float(merged_event["worker_started_at_unix_s"]),
                    "end_unix_s": float(merged_event["worker_finished_at_unix_s"]),
                }
            )
        elif event_name == "ddar_result":
            if depth < 0 and not include_base_ddar:
                continue
            if depths is not None and depth not in depths:
                continue
            _require_fields(
                event,
                "ddar_result",
                [
                    "ddar_worker_id",
                    "ddar_started_at_unix_s",
                    "ddar_finished_at_unix_s",
                    "ddar_build_started_at_unix_s",
                    "ddar_build_finished_at_unix_s",
                ],
            )
            interval = {
                "depth": depth,
                "group": "DDAR",
                "worker_id": str(event["ddar_worker_id"]),
                "label": str(event.get("attempt_key", "<missing>")),
                "start_unix_s": float(event["ddar_started_at_unix_s"]),
                "end_unix_s": float(event["ddar_finished_at_unix_s"]),
                "build_start_unix_s": float(event["ddar_build_started_at_unix_s"]),
                "build_end_unix_s": float(event["ddar_build_finished_at_unix_s"]),
            }
            if event.get("ddar_engine_started_at_unix_s") is not None and event.get("ddar_engine_finished_at_unix_s") is not None:
                interval["engine_start_unix_s"] = float(event["ddar_engine_started_at_unix_s"])
                interval["engine_end_unix_s"] = float(event["ddar_engine_finished_at_unix_s"])
            intervals.append(interval)

    if not intervals:
        raise ValueError("No worker intervals matched the selected problem/depth filters.")
    return problem_name, intervals


def plot_worker_gantt(
    *,
    problem_name: str,
    intervals: list[dict[str, Any]],
    output_path: Path,
    dpi: int = 160,
) -> None:
    base_start_unix_s = min(float(item["start_unix_s"]) for item in intervals)
    intervals_by_depth: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for interval in intervals:
        intervals_by_depth[int(interval["depth"])].append(interval)

    depth_order = sorted(intervals_by_depth)
    lane_count = sum(
        len({(item["group"], item["worker_id"]) for item in depth_intervals})
        for depth_intervals in intervals_by_depth.values()
    )
    fig, axes = plt.subplots(
        len(depth_order),
        1,
        figsize=(16, max(3.5, 0.45 * lane_count + 1.5 * len(depth_order))),
        squeeze=False,
    )
    axes_list = [axis for row in axes for axis in row]

    for axis, depth in zip(axes_list, depth_order):
        depth_intervals = intervals_by_depth[depth]
        lane_keys: list[tuple[str, str]] = []
        for group in GROUP_ORDER:
            worker_ids = sorted({item["worker_id"] for item in depth_intervals if item["group"] == group})
            lane_keys.extend((group, worker_id) for worker_id in worker_ids)
        lane_y = {lane_key: index for index, lane_key in enumerate(lane_keys)}

        for interval in depth_intervals:
            lane_key = (interval["group"], interval["worker_id"])
            y = lane_y[lane_key]
            start_s = float(interval["start_unix_s"]) - base_start_unix_s
            duration_s = max(float(interval["end_unix_s"]) - float(interval["start_unix_s"]), 0.0)
            axis.barh(
                y,
                duration_s,
                left=start_s,
                height=0.72,
                color=GROUP_COLORS[interval["group"]],
                alpha=0.22 if interval["group"] == "DDAR" else 0.85,
                edgecolor=GROUP_COLORS[interval["group"]],
                linewidth=1.0,
            )
            if interval["group"] == "DDAR":
                build_start = float(interval["build_start_unix_s"]) - base_start_unix_s
                build_duration = max(float(interval["build_end_unix_s"]) - float(interval["build_start_unix_s"]), 0.0)
                axis.barh(y, build_duration, left=build_start, height=0.54, color=DDAR_BUILD_COLOR)
                if "engine_start_unix_s" in interval and "engine_end_unix_s" in interval:
                    engine_start = float(interval["engine_start_unix_s"]) - base_start_unix_s
                    engine_duration = max(
                        float(interval["engine_end_unix_s"]) - float(interval["engine_start_unix_s"]),
                        0.0,
                    )
                    axis.barh(y, engine_duration, left=engine_start, height=0.54, color=DDAR_ENGINE_COLOR)
            if duration_s > 0.03:
                axis.text(
                    start_s + duration_s / 2,
                    y,
                    interval["label"],
                    ha="center",
                    va="center",
                    fontsize=7,
                    clip_on=True,
                )

        axis.set_yticks(list(range(len(lane_keys))))
        axis.set_yticklabels([f"{group} | {worker_id}" for group, worker_id in lane_keys], fontsize=8)
        axis.invert_yaxis()
        axis.grid(axis="x", linestyle="--", linewidth=0.6, alpha=0.5)
        axis.set_title(f"{problem_name} | depth {depth}", fontsize=11)
        axis.set_xlabel("Seconds From First Worker Activity")

        group_boundaries = []
        current = 0
        for group in GROUP_ORDER:
            size = sum(1 for lane_group, _ in lane_keys if lane_group == group)
            if size:
                current += size
                group_boundaries.append(current - 0.5)
        for boundary in group_boundaries[:-1]:
            axis.axhline(boundary, color="#999999", linewidth=0.8, alpha=0.6)

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a worker-level gantt chart for one traced problem.")
    parser.add_argument("--run_dir", required=True, help="Trace run directory containing problems/*.jsonl")
    parser.add_argument("--problem", required=True, help="Exact problem name or zero-based problem index")
    parser.add_argument("--output", required=True, help="Output image path (.png or .svg)")
    parser.add_argument("--depth", action="append", type=int, default=None, help="Depth to render; repeat to select multiple")
    parser.add_argument("--dpi", type=int, default=160, help="Raster DPI for PNG output")
    parser.add_argument("--include_base_ddar", action="store_true", help="Include depth=-1 base DDAR on the chart")
    args = parser.parse_args(argv)

    output_path = Path(args.output)
    if output_path.suffix.lower() not in {".png", ".svg"}:
        raise SystemExit("--output must end with .png or .svg")

    problem_file = resolve_problem_file(Path(args.run_dir), str(args.problem))
    events = load_jsonl(problem_file)
    try:
        problem_name, intervals = extract_worker_intervals(
            events,
            depths=set(args.depth) if args.depth else None,
            include_base_ddar=bool(args.include_base_ddar),
        )
    except TraceCompatibilityError as exc:
        raise SystemExit(str(exc)) from exc
    plot_worker_gantt(
        problem_name=problem_name,
        intervals=intervals,
        output_path=output_path,
        dpi=args.dpi,
    )
    print(f"Wrote worker gantt to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
