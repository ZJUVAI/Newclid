from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


LEGACY_TIME_FIELDS = (
    "build_time_s",
    "inference_time_s",
    "ddar_time_s",
    "total_time_s",
    "other_time_s",
)

DETAILED_WALL_TIME_FIELDS = (
    "entry_setup_wall_time_s",
    "base_ddar_wall_time_s",
    "request_build_wall_time_s",
    "gpu_wait_wall_time_s",
    "gpu_result_handle_wall_time_s",
    "ddar_submit_wall_time_s",
    "ddar_wait_wall_time_s",
    "ddar_result_handle_wall_time_s",
    "scheduler_overhead_wall_time_s",
    "total_time_s",
    "other_wall_time_s",
)

DETAILED_WORK_TIME_FIELDS = (
    "gpu_inference_work_time_s",
    "ddar_build_work_time_s",
    "ddar_engine_work_time_s",
)

DETAILED_COUNTER_FIELDS = (
    "num_requests",
    "num_candidates_total",
    "num_candidates_parse_failed",
    "num_candidates_build_failed",
    "num_ddar_submitted",
    "num_ddar_invalid",
)

DETAILED_MAX_FIELDS = (
    "max_running_gpu",
    "max_running_ddar",
    "max_prepared_requests",
    "max_pending_ddar_submit",
)

DETAILED_DEPTH_FIELDS = (
    "depth",
    "frontier_size",
    "requests_built",
    "request_build_wall_time_s",
    "draw_svg_wall_time_s",
    "svg_to_png_wall_time_s",
    "image_postprocess_wall_time_s",
    "dsl_build_wall_time_s",
    "gpu_wait_wall_time_s",
    "gpu_inference_work_time_s",
    "gpu_result_handle_wall_time_s",
    "ddar_submitted",
    "ddar_submit_wall_time_s",
    "ddar_wait_wall_time_s",
    "ddar_build_work_time_s",
    "ddar_engine_work_time_s",
    "ddar_result_handle_wall_time_s",
    "scheduler_overhead_wall_time_s",
    "next_frontier_size",
)


def create_profiling_payload() -> dict[str, float]:
    return {
        "build_time_s": 0.0,
        "inference_time_s": 0.0,
        "ddar_time_s": 0.0,
        "total_time_s": 0.0,
        "other_time_s": 0.0,
    }


def create_detailed_profiling_payload() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "depth_rows": [],
    }
    for field in DETAILED_WALL_TIME_FIELDS:
        payload[field] = 0.0
    for field in DETAILED_WORK_TIME_FIELDS:
        payload[field] = 0.0
    for field in DETAILED_COUNTER_FIELDS:
        payload[field] = 0
    for field in DETAILED_MAX_FIELDS:
        payload[field] = 0
    return payload


def create_depth_profiling_row(*, depth: int, frontier_size: int) -> dict[str, float | int]:
    row: dict[str, float | int] = {
        "depth": depth,
        "frontier_size": frontier_size,
        "requests_built": 0,
        "ddar_submitted": 0,
        "next_frontier_size": 0,
    }
    for field in (
        "request_build_wall_time_s",
        "draw_svg_wall_time_s",
        "svg_to_png_wall_time_s",
        "image_postprocess_wall_time_s",
        "dsl_build_wall_time_s",
        "gpu_wait_wall_time_s",
        "gpu_inference_work_time_s",
        "gpu_result_handle_wall_time_s",
        "ddar_submit_wall_time_s",
        "ddar_wait_wall_time_s",
        "ddar_build_work_time_s",
        "ddar_engine_work_time_s",
        "ddar_result_handle_wall_time_s",
        "scheduler_overhead_wall_time_s",
    ):
        row[field] = 0.0
    return row


def add_profiling_time(profiling: dict[str, Any], field: str, elapsed_s: float | int | None) -> None:
    if elapsed_s is None:
        return
    profiling[field] = profiling.get(field, 0.0) + float(elapsed_s)


def add_profiling_count(profiling: dict[str, Any], field: str, delta: int = 1) -> None:
    profiling[field] = int(profiling.get(field, 0)) + int(delta)


def update_profiling_max(profiling: dict[str, Any], field: str, value: int | float) -> None:
    profiling[field] = max(profiling.get(field, 0), value)


def finalize_profiling(profiling: dict[str, float], total_time_s: float | int) -> dict[str, float]:
    profiling["total_time_s"] = float(total_time_s)
    accounted = (
        profiling.get("build_time_s", 0.0)
        + profiling.get("inference_time_s", 0.0)
        + profiling.get("ddar_time_s", 0.0)
    )
    profiling["other_time_s"] = max(float(total_time_s) - accounted, 0.0)
    return profiling


def finalize_detailed_profiling(profiling: dict[str, Any], total_time_s: float | int) -> dict[str, Any]:
    profiling["total_time_s"] = float(total_time_s)
    accounted = sum(
        float(profiling.get(field, 0.0))
        for field in DETAILED_WALL_TIME_FIELDS
        if field not in {"total_time_s", "other_wall_time_s"}
    )
    profiling["other_wall_time_s"] = max(float(total_time_s) - accounted, 0.0)
    return profiling


def merge_profiling_payloads(*payloads: dict[str, float] | None) -> dict[str, float]:
    merged = create_profiling_payload()
    for payload in payloads:
        if payload is None:
            continue
        for field in ("build_time_s", "inference_time_s", "ddar_time_s"):
            add_profiling_time(merged, field, payload.get(field))
    return merged


def profiling_summary(rows: list[dict[str, Any]], fields: tuple[str, ...] | None = None) -> dict[str, float]:
    summary_fields = fields or LEGACY_TIME_FIELDS
    summary = {
        field: 0.0
        for field in summary_fields
    }
    for row in rows:
        for field in summary_fields:
            summary[field] += float(row.get(field, 0.0))
    return summary


def _is_detailed_row(row: dict[str, Any]) -> bool:
    return "entry_setup_wall_time_s" in row


def _write_legacy_profiling_csv(
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
                    f"Build Time: {summary['build_time_s']:.2f}s, "
                    f"Inference Time: {summary['inference_time_s']:.2f}s, "
                    f"DDAR Time: {summary['ddar_time_s']:.2f}s, "
                    f"Other Time: {summary['other_time_s']:.2f}s"
                )
            ]
        )
        writer.writerow(
            [
                "Problem Name",
                "Solved",
                "Total Time (s)",
                "Build Time (s)",
                "Inference Time (s)",
                "DDAR Time (s)",
                "Other Time (s)",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row["problem_name"],
                    row["solved"],
                    f"{row['total_time_s']:.2f}",
                    f"{row['build_time_s']:.2f}",
                    f"{row['inference_time_s']:.2f}",
                    f"{row['ddar_time_s']:.2f}",
                    f"{row['other_time_s']:.2f}",
                ]
            )


def _write_detailed_wall_profiling_csv(
    csv_path: Path,
    *,
    dataset_name: str,
    solved_count: int,
    total_problems: int,
    total_time_s: float | None,
    rows: list[dict[str, Any]],
) -> None:
    summary = profiling_summary(rows, DETAILED_WALL_TIME_FIELDS)
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
                    f"Request Build Wall Time: {summary['request_build_wall_time_s']:.2f}s, "
                    f"GPU Wait Wall Time: {summary['gpu_wait_wall_time_s']:.2f}s, "
                    f"GPU Result Handle Wall Time: {summary['gpu_result_handle_wall_time_s']:.2f}s, "
                    f"DDAR Submit Wall Time: {summary['ddar_submit_wall_time_s']:.2f}s, "
                    f"DDAR Wait Wall Time: {summary['ddar_wait_wall_time_s']:.2f}s, "
                    f"DDAR Result Handle Wall Time: {summary['ddar_result_handle_wall_time_s']:.2f}s, "
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
                "Request Build Wall Time (s)",
                "GPU Wait Wall Time (s)",
                "GPU Result Handle Wall Time (s)",
                "DDAR Submit Wall Time (s)",
                "DDAR Wait Wall Time (s)",
                "DDAR Result Handle Wall Time (s)",
                "Scheduler Overhead Wall Time (s)",
                "Other Wall Time (s)",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row["problem_name"],
                    row["solved"],
                    f"{row['total_time_s']:.2f}",
                    f"{row['entry_setup_wall_time_s']:.2f}",
                    f"{row['base_ddar_wall_time_s']:.2f}",
                    f"{row['request_build_wall_time_s']:.2f}",
                    f"{row['gpu_wait_wall_time_s']:.2f}",
                    f"{row['gpu_result_handle_wall_time_s']:.2f}",
                    f"{row['ddar_submit_wall_time_s']:.2f}",
                    f"{row['ddar_wait_wall_time_s']:.2f}",
                    f"{row['ddar_result_handle_wall_time_s']:.2f}",
                    f"{row['scheduler_overhead_wall_time_s']:.2f}",
                    f"{row['other_wall_time_s']:.2f}",
                ]
            )


def write_profiling_csv(
    csv_path: Path,
    *,
    dataset_name: str,
    solved_count: int,
    total_problems: int,
    total_time_s: float | None,
    rows: list[dict[str, Any]],
) -> None:
    if rows and _is_detailed_row(rows[0]):
        _write_detailed_wall_profiling_csv(
            csv_path,
            dataset_name=dataset_name,
            solved_count=solved_count,
            total_problems=total_problems,
            total_time_s=total_time_s,
            rows=rows,
        )
        return
    _write_legacy_profiling_csv(
        csv_path,
        dataset_name=dataset_name,
        solved_count=solved_count,
        total_problems=total_problems,
        total_time_s=total_time_s,
        rows=rows,
    )


def write_profiling_work_csv(
    csv_path: Path,
    *,
    dataset_name: str,
    solved_count: int,
    total_problems: int,
    rows: list[dict[str, Any]],
) -> None:
    summary = profiling_summary(rows, DETAILED_WORK_TIME_FIELDS + DETAILED_COUNTER_FIELDS)
    max_summary = {
        field: max((int(row.get(field, 0)) for row in rows), default=0)
        for field in DETAILED_MAX_FIELDS
    }
    with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(
            [
                (
                    f"Dataset: {dataset_name}, Solved: {solved_count}/{total_problems}, "
                    f"GPU Inference Work Time: {summary['gpu_inference_work_time_s']:.2f}s, "
                    f"DDAR Build Work Time: {summary['ddar_build_work_time_s']:.2f}s, "
                    f"DDAR Engine Work Time: {summary['ddar_engine_work_time_s']:.2f}s, "
                    f"Num Requests: {int(summary['num_requests'])}, "
                    f"Num Candidates Total: {int(summary['num_candidates_total'])}, "
                    f"Num DDAR Submitted: {int(summary['num_ddar_submitted'])}, "
                    f"Max Running GPU: {max_summary['max_running_gpu']}, "
                    f"Max Running DDAR: {max_summary['max_running_ddar']}"
                )
            ]
        )
        writer.writerow(
            [
                "Problem Name",
                "Solved",
                "GPU Inference Work Time (s)",
                "DDAR Build Work Time (s)",
                "DDAR Engine Work Time (s)",
                "Num Requests",
                "Num Candidates Total",
                "Num Candidates Parse Failed",
                "Num Candidates Build Failed",
                "Num DDAR Submitted",
                "Num DDAR Invalid",
                "Max Running GPU",
                "Max Running DDAR",
                "Max Prepared Requests",
                "Max Pending DDAR Submit",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row["problem_name"],
                    row["solved"],
                    f"{row['gpu_inference_work_time_s']:.2f}",
                    f"{row['ddar_build_work_time_s']:.2f}",
                    f"{row['ddar_engine_work_time_s']:.2f}",
                    int(row["num_requests"]),
                    int(row["num_candidates_total"]),
                    int(row["num_candidates_parse_failed"]),
                    int(row["num_candidates_build_failed"]),
                    int(row["num_ddar_submitted"]),
                    int(row["num_ddar_invalid"]),
                    int(row["max_running_gpu"]),
                    int(row["max_running_ddar"]),
                    int(row["max_prepared_requests"]),
                    int(row["max_pending_ddar_submit"]),
                ]
            )


def write_profiling_depth_csv(
    csv_path: Path,
    *,
    dataset_name: str,
    rows: list[dict[str, Any]],
) -> None:
    with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([f"Dataset: {dataset_name}, Depth Rows: {len(rows)}"])
        writer.writerow(
            [
                "Problem Name",
                "Depth",
                "Frontier Size",
                "Requests Built",
                "Request Build Wall Time (s)",
                "Draw SVG Wall Time (s)",
                "SVG->PNG Wall Time (s)",
                "Image Postprocess Wall Time (s)",
                "DSL Build Wall Time (s)",
                "GPU Wait Wall Time (s)",
                "GPU Inference Work Time (s)",
                "GPU Result Handle Wall Time (s)",
                "DDAR Submitted",
                "DDAR Submit Wall Time (s)",
                "DDAR Wait Wall Time (s)",
                "DDAR Build Work Time (s)",
                "DDAR Engine Work Time (s)",
                "DDAR Result Handle Wall Time (s)",
                "Scheduler Overhead Wall Time (s)",
                "Next Frontier Size",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row["problem_name"],
                    int(row["depth"]),
                    int(row["frontier_size"]),
                    int(row["requests_built"]),
                    f"{row['request_build_wall_time_s']:.2f}",
                    f"{row['draw_svg_wall_time_s']:.2f}",
                    f"{row['svg_to_png_wall_time_s']:.2f}",
                    f"{row['image_postprocess_wall_time_s']:.2f}",
                    f"{row['dsl_build_wall_time_s']:.2f}",
                    f"{row['gpu_wait_wall_time_s']:.2f}",
                    f"{row['gpu_inference_work_time_s']:.2f}",
                    f"{row['gpu_result_handle_wall_time_s']:.2f}",
                    int(row["ddar_submitted"]),
                    f"{row['ddar_submit_wall_time_s']:.2f}",
                    f"{row['ddar_wait_wall_time_s']:.2f}",
                    f"{row['ddar_build_work_time_s']:.2f}",
                    f"{row['ddar_engine_work_time_s']:.2f}",
                    f"{row['ddar_result_handle_wall_time_s']:.2f}",
                    f"{row['scheduler_overhead_wall_time_s']:.2f}",
                    int(row["next_frontier_size"]),
                ]
            )
