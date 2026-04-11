from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


WALL_TIME_FIELDS = (
    "entry_setup_wall_time_s",
    "base_ddar_wall_time_s",
    "request_prepare_wall_time_s",
    "prepared_request_ready_wall_time_s",
    "prepared_request_queue_wall_time_s",
    "gpu_request_queue_wall_time_s",
    "gpu_batch_round_trip_wall_time_s",
    "gpu_result_ray_get_wall_time_s",
    "gpu_worker_inference_wall_time_s",
    "gpu_input_build_wall_time_s",
    "gpu_generate_wall_time_s",
    "gpu_decode_wall_time_s",
    "gpu_fallback_wall_time_s",
    "wait_wall_time_s",
    "gpu_result_handle_wall_time_s",
    "ddar_submit_wall_time_s",
    "ddar_result_handle_wall_time_s",
    "next_frontier_finalize_wall_time_s",
    "scheduler_overhead_wall_time_s",
    "total_time_s",
    "other_wall_time_s",
)

DETAIL_TIME_FIELDS = (
    "ddar_build_work_time_s",
    "ddar_engine_work_time_s",
    "ddar_result_ray_get_wall_time_s",
    "ddar_result_next_state_wall_time_s",
    "ddar_result_queue_wall_time_s",
)

COUNT_FIELDS = (
    "prepare_request_submitted_count",
    "prepare_request_completed_count",
    "gpu_request_enqueued_count",
    "gpu_request_dispatched_count",
    "gpu_batch_submitted_count",
    "gpu_batch_completed_count",
    "gpu_batch_size_sum",
    "gpu_batch_size_max",
    "ddar_submitted_count",
    "ddar_completed_count",
    "candidate_parse_failed_count",
    "candidate_build_failed_count",
    "candidate_queued_next_depth_count",
    "next_frontier_proof_built_count",
    "next_frontier_proof_build_failed_count",
)

PROFILE_ROW_FIELDS = WALL_TIME_FIELDS + DETAIL_TIME_FIELDS + COUNT_FIELDS

CSV_COLUMN_SPECS = (
    ("problem_name", "Problem Name", "text"),
    ("solved", "Solved", "text"),
    ("total_time_s", "Total Time (s)", "float"),
    ("entry_setup_wall_time_s", "Entry Setup Wall Time (s)", "float"),
    ("base_ddar_wall_time_s", "Base DDAR Wall Time (s)", "float"),
    ("request_prepare_wall_time_s", "Request Prepare Wall Time (s)", "float"),
    ("prepared_request_ready_wall_time_s", "Prepared Request Ready Wall Time (s)", "float"),
    ("prepared_request_queue_wall_time_s", "Prepared Request Queue Wall Time (s)", "float"),
    ("gpu_request_queue_wall_time_s", "GPU Request Queue Wall Time (s)", "float"),
    ("gpu_batch_round_trip_wall_time_s", "GPU Batch Round Trip Wall Time (s)", "float"),
    ("gpu_result_ray_get_wall_time_s", "GPU Result Ray.get Wall Time (s)", "float"),
    ("gpu_worker_inference_wall_time_s", "GPU Worker Inference Wall Time (s)", "float"),
    ("gpu_input_build_wall_time_s", "GPU Input Build Wall Time (s)", "float"),
    ("gpu_generate_wall_time_s", "GPU Generate Wall Time (s)", "float"),
    ("gpu_decode_wall_time_s", "GPU Decode Wall Time (s)", "float"),
    ("gpu_fallback_wall_time_s", "GPU Fallback Wall Time (s)", "float"),
    ("wait_wall_time_s", "Wait Wall Time (s)", "float"),
    ("gpu_result_handle_wall_time_s", "GPU Result Handle Wall Time (s)", "float"),
    ("ddar_submit_wall_time_s", "DDAR Submit Wall Time (s)", "float"),
    ("ddar_result_handle_wall_time_s", "DDAR Result Handle Wall Time (s)", "float"),
    ("ddar_build_work_time_s", "DDAR Build Work Time (s)", "float"),
    ("ddar_engine_work_time_s", "DDAR Engine Work Time (s)", "float"),
    ("ddar_result_ray_get_wall_time_s", "DDAR Result Ray.get Wall Time (s)", "float"),
    ("ddar_result_next_state_wall_time_s", "DDAR Result Next State Wall Time (s)", "float"),
    ("ddar_result_queue_wall_time_s", "DDAR Result Queue Wall Time (s)", "float"),
    ("next_frontier_finalize_wall_time_s", "Next Frontier Finalize Wall Time (s)", "float"),
    ("scheduler_overhead_wall_time_s", "Scheduler Overhead Wall Time (s)", "float"),
    ("other_wall_time_s", "Other Wall Time (s)", "float"),
    ("prepare_request_submitted_count", "Prepare Request Submitted Count", "int"),
    ("prepare_request_completed_count", "Prepare Request Completed Count", "int"),
    ("gpu_request_enqueued_count", "GPU Request Enqueued Count", "int"),
    ("gpu_request_dispatched_count", "GPU Request Dispatched Count", "int"),
    ("gpu_batch_submitted_count", "GPU Batch Submitted Count", "int"),
    ("gpu_batch_completed_count", "GPU Batch Completed Count", "int"),
    ("gpu_batch_size_sum", "GPU Batch Size Sum", "int"),
    ("gpu_batch_size_max", "GPU Batch Size Max", "int"),
    ("avg_gpu_batch_size", "Avg GPU Batch Size", "float"),
    ("ddar_submitted_count", "DDAR Submitted Count", "int"),
    ("ddar_completed_count", "DDAR Completed Count", "int"),
    ("candidate_parse_failed_count", "Candidate Parse Failed Count", "int"),
    ("candidate_build_failed_count", "Candidate Build Failed Count", "int"),
    ("candidate_queued_next_depth_count", "Candidate Queued Next Depth Count", "int"),
    ("next_frontier_proof_built_count", "Next Frontier Proof Built Count", "int"),
    ("next_frontier_proof_build_failed_count", "Next Frontier Proof Build Failed Count", "int"),
)

PROFILED_WALL_COMPONENT_FIELDS = tuple(
    field for field in WALL_TIME_FIELDS if field not in {"total_time_s", "other_wall_time_s"}
)


def create_profiling_payload() -> dict[str, float]:
    return {
        field: 0.0
        for field in PROFILE_ROW_FIELDS
    }


def create_detailed_profiling_payload() -> dict[str, float]:
    return create_profiling_payload()


def add_profiling_time(profiling: dict[str, Any], field: str, elapsed_s: float | int | None) -> None:
    if elapsed_s is None:
        return
    profiling[field] = profiling.get(field, 0.0) + float(elapsed_s)


def increment_profiling_count(profiling: dict[str, Any], field: str, amount: int | float = 1) -> None:
    profiling[field] = profiling.get(field, 0.0) + amount


def update_profiling_max(profiling: dict[str, Any], field: str, value: float | int | None) -> None:
    if value is None:
        return
    profiling[field] = max(float(profiling.get(field, 0.0)), float(value))


def finalize_profiling(profiling: dict[str, Any], total_time_s: float | int) -> dict[str, Any]:
    profiling["total_time_s"] = float(total_time_s)
    accounted = sum(float(profiling.get(field, 0.0)) for field in PROFILED_WALL_COMPONENT_FIELDS)
    profiling["other_wall_time_s"] = max(float(total_time_s) - accounted, 0.0)
    batch_completed = float(profiling.get("gpu_batch_submitted_count", 0.0))
    profiling["avg_gpu_batch_size"] = (
        float(profiling.get("gpu_batch_size_sum", 0.0)) / batch_completed
        if batch_completed
        else 0.0
    )
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
        for field in DETAIL_TIME_FIELDS + COUNT_FIELDS:
            if field == "gpu_batch_size_max":
                update_profiling_max(merged, field, payload.get(field))
            else:
                add_profiling_time(merged, field, payload.get(field))
    return merged


def profiling_summary(rows: list[dict[str, Any]]) -> dict[str, float]:
    summary = {
        field: 0.0
        for field in PROFILE_ROW_FIELDS
    }
    for row in rows:
        for field in WALL_TIME_FIELDS + DETAIL_TIME_FIELDS + COUNT_FIELDS:
            if field == "gpu_batch_size_max":
                summary[field] = max(summary[field], float(row.get(field, 0.0)))
            else:
                summary[field] += float(row.get(field, 0.0))
    batch_completed = float(summary.get("gpu_batch_submitted_count", 0.0))
    summary["avg_gpu_batch_size"] = (
        float(summary.get("gpu_batch_size_sum", 0.0)) / batch_completed
        if batch_completed
        else 0.0
    )
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
    summary["total_time_s"] = display_total_time_s
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
                    f"Prepared Request Ready Wall Time: {summary['prepared_request_ready_wall_time_s']:.2f}s, "
                    f"Prepared Request Queue Wall Time: {summary['prepared_request_queue_wall_time_s']:.2f}s, "
                    f"GPU Request Queue Wall Time: {summary['gpu_request_queue_wall_time_s']:.2f}s, "
                    f"GPU Batch Round Trip Wall Time: {summary['gpu_batch_round_trip_wall_time_s']:.2f}s, "
                    f"GPU Result Ray.get Wall Time: {summary['gpu_result_ray_get_wall_time_s']:.2f}s, "
                    f"GPU Worker Inference Wall Time: {summary['gpu_worker_inference_wall_time_s']:.2f}s, "
                    f"GPU Input Build Wall Time: {summary['gpu_input_build_wall_time_s']:.2f}s, "
                    f"GPU Generate Wall Time: {summary['gpu_generate_wall_time_s']:.2f}s, "
                    f"GPU Decode Wall Time: {summary['gpu_decode_wall_time_s']:.2f}s, "
                    f"GPU Fallback Wall Time: {summary['gpu_fallback_wall_time_s']:.2f}s, "
                    f"Wait Wall Time: {summary['wait_wall_time_s']:.2f}s, "
                    f"GPU Result Handle Wall Time: {summary['gpu_result_handle_wall_time_s']:.2f}s, "
                    f"DDAR Submit Wall Time: {summary['ddar_submit_wall_time_s']:.2f}s, "
                    f"DDAR Result Handle Wall Time: {summary['ddar_result_handle_wall_time_s']:.2f}s, "
                    f"DDAR Build Work Time: {summary['ddar_build_work_time_s']:.2f}s, "
                    f"DDAR Engine Work Time: {summary['ddar_engine_work_time_s']:.2f}s, "
                    f"DDAR Result Ray.get Wall Time: {summary['ddar_result_ray_get_wall_time_s']:.2f}s, "
                    f"DDAR Result Next State Wall Time: {summary['ddar_result_next_state_wall_time_s']:.2f}s, "
                    f"DDAR Result Queue Wall Time: {summary['ddar_result_queue_wall_time_s']:.2f}s, "
                    f"Next Frontier Finalize Wall Time: {summary['next_frontier_finalize_wall_time_s']:.2f}s, "
                    f"Scheduler Overhead Wall Time: {summary['scheduler_overhead_wall_time_s']:.2f}s, "
                    f"Other Wall Time: {summary['other_wall_time_s']:.2f}s, "
                    f"Avg GPU Batch Size: {summary['avg_gpu_batch_size']:.2f}, "
                    f"Prepare Requests Submitted: {int(summary['prepare_request_submitted_count'])}, "
                    f"Prepare Requests Completed: {int(summary['prepare_request_completed_count'])}, "
                    f"GPU Requests Enqueued: {int(summary['gpu_request_enqueued_count'])}, "
                    f"GPU Requests Dispatched: {int(summary['gpu_request_dispatched_count'])}, "
                    f"GPU Batches Submitted: {int(summary['gpu_batch_submitted_count'])}, "
                    f"GPU Batches Completed: {int(summary['gpu_batch_completed_count'])}, "
                    f"GPU Batch Size Sum: {int(summary['gpu_batch_size_sum'])}, "
                    f"GPU Batch Size Max: {int(summary['gpu_batch_size_max'])}, "
                    f"DDAR Submitted: {int(summary['ddar_submitted_count'])}, "
                    f"DDAR Completed: {int(summary['ddar_completed_count'])}, "
                    f"Candidate Parse Failed: {int(summary['candidate_parse_failed_count'])}, "
                    f"Candidate Build Failed: {int(summary['candidate_build_failed_count'])}, "
                    f"Candidate Queued Next Depth: {int(summary['candidate_queued_next_depth_count'])}, "
                    f"Next Frontier Proof Built: {int(summary['next_frontier_proof_built_count'])}, "
                    f"Next Frontier Proof Build Failed: {int(summary['next_frontier_proof_build_failed_count'])}"
                )
            ]
        )
        writer.writerow([label for _, label, _ in CSV_COLUMN_SPECS])
        for row in rows:
            finalized_row = finalize_profiling(
                {
                    **create_profiling_payload(),
                    **row,
                },
                float(row.get("total_time_s", 0.0)),
            )
            formatted_row: list[str] = []
            for key, _, kind in CSV_COLUMN_SPECS:
                value = finalized_row.get(key, row.get(key, ""))
                if kind == "text":
                    formatted_row.append(str(value))
                elif kind == "int":
                    formatted_row.append(str(int(round(float(value)))))
                else:
                    formatted_row.append(f"{float(value):.2f}")
            writer.writerow(formatted_row)
