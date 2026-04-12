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
    "gpu_first_token_latency_sum_s",
)

COUNT_FIELDS = (
    "prepare_request_submitted_count",
    "prepare_request_completed_count",
    "gpu_request_enqueued_count",
    "gpu_request_dispatched_count",
    "gpu_request_completed_count",
    "gpu_batch_submitted_count",
    "gpu_batch_completed_count",
    "gpu_batch_size_sum",
    "ddar_submitted_count",
    "ddar_completed_count",
    "gpu_prompt_token_count_sum",
    "gpu_generated_token_count_sum",
    "gpu_generated_sequence_count",
    "gpu_raw_candidate_count",
    "gpu_unique_candidate_count",
    "gpu_duplicate_candidate_count",
    "gpu_first_token_latency_count",
    "candidate_parse_failed_count",
    "candidate_parse_success_count",
    "candidate_build_failed_count",
    "candidate_build_success_count",
    "candidate_queued_next_depth_count",
    "next_frontier_proof_built_count",
    "next_frontier_proof_build_failed_count",
)

MAX_FIELDS = (
    "gpu_batch_size_max",
    "gpu_prompt_token_count_max",
    "gpu_generated_token_count_max",
)

DERIVED_FIELDS = (
    "avg_gpu_batch_size",
    "avg_prompt_tokens_per_request",
    "avg_generated_tokens_per_request",
    "avg_generated_tokens_per_sequence",
    "generated_tokens_per_gpu_generate_s",
    "unique_candidates_per_gpu_generate_s",
    "valid_candidates_per_gpu_generate_s",
    "candidate_unique_ratio",
    "candidate_parse_success_rate",
    "candidate_build_success_rate",
    "avg_first_token_latency_s",
)

PROFILE_ROW_FIELDS = WALL_TIME_FIELDS + DETAIL_TIME_FIELDS + COUNT_FIELDS + MAX_FIELDS

CSV_COLUMN_SPECS = (
    ("problem_name", "Problem Name", "text"),
    ("solved", "Solved", "text"),
    ("total_time_s", "Total Time (s)", "float"),
    ("entry_setup_wall_time_s", "Entry Setup Wall Time (s)", "float"),
    ("base_ddar_wall_time_s", "Base DDAR Wall Time (s)", "float"),
    ("request_prepare_wall_time_s", "Request Prepare Wall Time (s)", "float"),
    ("gpu_batch_round_trip_wall_time_s", "GPU Batch Round Trip Wall Time (s)", "float"),
    ("gpu_worker_inference_wall_time_s", "GPU Worker Inference Wall Time (s)", "float"),
    ("gpu_generate_wall_time_s", "GPU Generate Wall Time (s)", "float"),
    ("wait_wall_time_s", "Wait Wall Time (s)", "float"),
    ("ddar_build_work_time_s", "DDAR Build Work Time (s)", "float"),
    ("ddar_engine_work_time_s", "DDAR Engine Work Time (s)", "float"),
    ("scheduler_overhead_wall_time_s", "Scheduler Overhead Wall Time (s)", "float"),
    ("other_wall_time_s", "Other Wall Time (s)", "float"),
    ("gpu_batch_completed_count", "GPU Batch Completed Count", "int"),
    ("avg_gpu_batch_size", "Avg GPU Batch Size", "float"),
    ("ddar_completed_count", "DDAR Completed Count", "int"),
    ("candidate_parse_success_rate", "Candidate Parse Success Rate", "float"),
    ("candidate_build_success_rate", "Candidate Build Success Rate", "float"),
    ("candidate_queued_next_depth_count", "Candidate Queued Next Depth Count", "int"),
)

PROFILED_WALL_COMPONENT_FIELDS = tuple(
    field for field in WALL_TIME_FIELDS if field not in {"total_time_s", "other_wall_time_s"}
)


def create_profiling_payload() -> dict[str, float]:
    return {
        field: 0.0
        for field in PROFILE_ROW_FIELDS + DERIVED_FIELDS
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
    request_completed = float(profiling.get("gpu_request_completed_count", 0.0))
    generated_sequence_count = float(profiling.get("gpu_generated_sequence_count", 0.0))
    generated_token_count_sum = float(profiling.get("gpu_generated_token_count_sum", 0.0))
    unique_candidate_count = float(profiling.get("gpu_unique_candidate_count", 0.0))
    raw_candidate_count = float(profiling.get("gpu_raw_candidate_count", 0.0))
    parse_success_count = float(profiling.get("candidate_parse_success_count", 0.0))
    build_success_count = float(profiling.get("candidate_build_success_count", 0.0))
    gpu_generate_wall_time_s = float(profiling.get("gpu_generate_wall_time_s", 0.0))
    first_token_latency_count = float(profiling.get("gpu_first_token_latency_count", 0.0))
    profiling["avg_prompt_tokens_per_request"] = (
        float(profiling.get("gpu_prompt_token_count_sum", 0.0)) / request_completed
        if request_completed
        else 0.0
    )
    profiling["avg_generated_tokens_per_request"] = (
        generated_token_count_sum / request_completed
        if request_completed
        else 0.0
    )
    profiling["avg_generated_tokens_per_sequence"] = (
        generated_token_count_sum / generated_sequence_count
        if generated_sequence_count
        else 0.0
    )
    profiling["generated_tokens_per_gpu_generate_s"] = (
        generated_token_count_sum / gpu_generate_wall_time_s
        if gpu_generate_wall_time_s
        else 0.0
    )
    profiling["unique_candidates_per_gpu_generate_s"] = (
        unique_candidate_count / gpu_generate_wall_time_s
        if gpu_generate_wall_time_s
        else 0.0
    )
    profiling["valid_candidates_per_gpu_generate_s"] = (
        build_success_count / gpu_generate_wall_time_s
        if gpu_generate_wall_time_s
        else 0.0
    )
    profiling["candidate_unique_ratio"] = (
        unique_candidate_count / raw_candidate_count
        if raw_candidate_count
        else 0.0
    )
    profiling["candidate_parse_success_rate"] = (
        parse_success_count / unique_candidate_count
        if unique_candidate_count
        else 0.0
    )
    profiling["candidate_build_success_rate"] = (
        build_success_count / parse_success_count
        if parse_success_count
        else 0.0
    )
    profiling["avg_first_token_latency_s"] = (
        float(profiling.get("gpu_first_token_latency_sum_s", 0.0)) / first_token_latency_count
        if first_token_latency_count
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
        for field in DETAIL_TIME_FIELDS + COUNT_FIELDS + MAX_FIELDS:
            if field in MAX_FIELDS:
                update_profiling_max(merged, field, payload.get(field))
            else:
                add_profiling_time(merged, field, payload.get(field))
    return merged


def profiling_summary(rows: list[dict[str, Any]]) -> dict[str, float]:
    summary = {
        field: 0.0
        for field in PROFILE_ROW_FIELDS + DERIVED_FIELDS
    }
    for row in rows:
        for field in WALL_TIME_FIELDS + DETAIL_TIME_FIELDS + COUNT_FIELDS + MAX_FIELDS:
            if field in MAX_FIELDS:
                summary[field] = max(summary[field], float(row.get(field, 0.0)))
            else:
                summary[field] += float(row.get(field, 0.0))
    return finalize_profiling(summary, float(summary.get("total_time_s", 0.0)))


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
                    f"GPU Batch Round Trip Wall Time: {summary['gpu_batch_round_trip_wall_time_s']:.2f}s, "
                    f"GPU Worker Inference Wall Time: {summary['gpu_worker_inference_wall_time_s']:.2f}s, "
                    f"GPU Generate Wall Time: {summary['gpu_generate_wall_time_s']:.2f}s, "
                    f"Wait Wall Time: {summary['wait_wall_time_s']:.2f}s, "
                    f"DDAR Build Work Time: {summary['ddar_build_work_time_s']:.2f}s, "
                    f"DDAR Engine Work Time: {summary['ddar_engine_work_time_s']:.2f}s, "
                    f"Scheduler Overhead Wall Time: {summary['scheduler_overhead_wall_time_s']:.2f}s, "
                    f"Other Wall Time: {summary['other_wall_time_s']:.2f}s, "
                    f"GPU Batches Completed: {int(summary['gpu_batch_completed_count'])}, "
                    f"Avg GPU Batch Size: {summary['avg_gpu_batch_size']:.2f}, "
                    f"DDAR Completed: {int(summary['ddar_completed_count'])}, "
                    f"Candidate Parse Success Rate: {summary['candidate_parse_success_rate']:.2f}, "
                    f"Candidate Build Success Rate: {summary['candidate_build_success_rate']:.2f}, "
                    f"Candidate Queued Next Depth: {int(summary['candidate_queued_next_depth_count'])}, "
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
