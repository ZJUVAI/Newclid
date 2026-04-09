from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


WALL_TIME_FIELDS = (
    "entry_setup_wall_time_s",
    "base_ddar_wall_time_s",
    "request_prepare_wall_time_s",
    "wait_wall_time_s",
    "gpu_result_handle_wall_time_s",
    "ddar_submit_wall_time_s",
    "ddar_result_handle_wall_time_s",
    "scheduler_overhead_wall_time_s",
    "total_time_s",
    "other_wall_time_s",
)

DETAIL_TIME_FIELDS = (
    "ddar_result_ray_get_wall_time_s",
    "ddar_result_next_state_wall_time_s",
    "ddar_result_queue_wall_time_s",
    "ddar_render_work_time_s",
)

PROFILED_WALL_COMPONENT_FIELDS = tuple(
    field for field in WALL_TIME_FIELDS if field not in {"total_time_s", "other_wall_time_s"}
)


def create_profiling_payload() -> dict[str, float]:
    return {
        field: 0.0
        for field in WALL_TIME_FIELDS + DETAIL_TIME_FIELDS
    }


def create_detailed_profiling_payload() -> dict[str, float]:
    return create_profiling_payload()


def add_profiling_time(profiling: dict[str, Any], field: str, elapsed_s: float | int | None) -> None:
    if elapsed_s is None:
        return
    profiling[field] = profiling.get(field, 0.0) + float(elapsed_s)


def finalize_profiling(profiling: dict[str, Any], total_time_s: float | int) -> dict[str, Any]:
    profiling["total_time_s"] = float(total_time_s)
    accounted = sum(float(profiling.get(field, 0.0)) for field in PROFILED_WALL_COMPONENT_FIELDS)
    profiling["other_wall_time_s"] = max(float(total_time_s) - accounted, 0.0)
    return profiling


def finalize_detailed_profiling(profiling: dict[str, Any], total_time_s: float | int) -> dict[str, Any]:
    return finalize_profiling(profiling, total_time_s)


def merge_profiling_payloads(*payloads: dict[str, Any] | None) -> dict[str, float]:
    merged = create_profiling_payload()
    for payload in payloads:
        if payload is None:
            continue
        for field in PROFILED_WALL_COMPONENT_FIELDS:
            add_profiling_time(merged, field, payload.get(field))
    return merged


def profiling_summary(rows: list[dict[str, Any]]) -> dict[str, float]:
    summary = {
        field: 0.0
        for field in WALL_TIME_FIELDS + DETAIL_TIME_FIELDS
    }
    for row in rows:
        for field in WALL_TIME_FIELDS + DETAIL_TIME_FIELDS:
            summary[field] += float(row.get(field, 0.0))
    return summary


def write_profiling_csv(
    csv_path: Path,
    *,
    dataset_name: str,
    solved_count: int,
    total_problems: int,
    total_time_s: float | None,
    rows: list[dict[str, Any]],
) -> None:
    summary = profiling_summary(rows)
    display_total_time_s = summary["total_time_s"] if total_time_s is None else float(total_time_s)
    with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(
            [
                (
                    f"Dataset: {dataset_name}, Solved: {solved_count}/{total_problems}, "
                    f"Total Time: {display_total_time_s:.2f}s, "
                    f"Entry Setup Wall Time: {summary['entry_setup_wall_time_s']:.2f}s, "
                    f"Base DDAR Wall Time: {summary['base_ddar_wall_time_s']:.2f}s, "
                    f"Request Prepare Wall Time: {summary['request_prepare_wall_time_s']:.2f}s, "
                    f"Wait Wall Time: {summary['wait_wall_time_s']:.2f}s, "
                    f"GPU Result Handle Wall Time: {summary['gpu_result_handle_wall_time_s']:.2f}s, "
                    f"DDAR Submit Wall Time: {summary['ddar_submit_wall_time_s']:.2f}s, "
                    f"DDAR Result Handle Wall Time: {summary['ddar_result_handle_wall_time_s']:.2f}s, "
                    f"DDAR Result Ray.get Wall Time: {summary['ddar_result_ray_get_wall_time_s']:.2f}s, "
                    f"DDAR Result Next State Wall Time: {summary['ddar_result_next_state_wall_time_s']:.2f}s, "
                    f"DDAR Result Queue Wall Time: {summary['ddar_result_queue_wall_time_s']:.2f}s, "
                    f"DDAR Render Work Time: {summary['ddar_render_work_time_s']:.2f}s, "
                    f"Scheduler Overhead Wall Time: {summary['scheduler_overhead_wall_time_s']:.2f}s, "
                    f"Other Wall Time: {summary['other_wall_time_s']:.2f}s"
                )
            ]
        )
        writer.writerow(
            [
                "Problem Name",
                "Solved",
                "Total Time (s)",
                "Entry Setup Wall Time (s)",
                "Base DDAR Wall Time (s)",
                "Request Prepare Wall Time (s)",
                "Wait Wall Time (s)",
                "GPU Result Handle Wall Time (s)",
                "DDAR Submit Wall Time (s)",
                "DDAR Result Handle Wall Time (s)",
                "DDAR Result Ray.get Wall Time (s)",
                "DDAR Result Next State Wall Time (s)",
                "DDAR Result Queue Wall Time (s)",
                "DDAR Render Work Time (s)",
                "Scheduler Overhead Wall Time (s)",
                "Other Wall Time (s)",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row["problem_name"],
                    row["solved"],
                    f"{float(row.get('total_time_s', 0.0)):.2f}",
                    f"{float(row.get('entry_setup_wall_time_s', 0.0)):.2f}",
                    f"{float(row.get('base_ddar_wall_time_s', 0.0)):.2f}",
                    f"{float(row.get('request_prepare_wall_time_s', 0.0)):.2f}",
                    f"{float(row.get('wait_wall_time_s', 0.0)):.2f}",
                    f"{float(row.get('gpu_result_handle_wall_time_s', 0.0)):.2f}",
                    f"{float(row.get('ddar_submit_wall_time_s', 0.0)):.2f}",
                    f"{float(row.get('ddar_result_handle_wall_time_s', 0.0)):.2f}",
                    f"{float(row.get('ddar_result_ray_get_wall_time_s', 0.0)):.2f}",
                    f"{float(row.get('ddar_result_next_state_wall_time_s', 0.0)):.2f}",
                    f"{float(row.get('ddar_result_queue_wall_time_s', 0.0)):.2f}",
                    f"{float(row.get('ddar_render_work_time_s', 0.0)):.2f}",
                    f"{float(row.get('scheduler_overhead_wall_time_s', 0.0)):.2f}",
                    f"{float(row.get('other_wall_time_s', 0.0)):.2f}",
                ]
            )
