from __future__ import annotations

import json
from pathlib import Path

from experiments.single_problem_multi_gpu_eval.scripts.analyze_eval_trace import analyze_run_dir


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False))
            fp.write("\n")


def test_analyze_run_dir_summarizes_occupancy_and_latency(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_jsonl(
        run_dir / "problems" / "0000_demo.jsonl",
        [
            {"event": "scheduler_state", "elapsed_s": 0.0, "depth": 0, "running_prepare": 1, "prepared_requests": 0, "pending_gpu_requests": 0, "active_gpu_batches": 0, "idle_gpu_workers": 4, "pending_ddar_submit": 0, "running_ddar": 0, "frontier_exhausted": False},
            {"event": "prepare_request_submitted", "elapsed_s": 0.0, "depth": 0, "request_id": "r0"},
            {"event": "scheduler_state", "elapsed_s": 1.0, "depth": 0, "running_prepare": 0, "prepared_requests": 1, "pending_gpu_requests": 0, "active_gpu_batches": 1, "idle_gpu_workers": 3, "pending_ddar_submit": 0, "running_ddar": 0, "frontier_exhausted": False},
            {"event": "prepare_request_ready", "elapsed_s": 1.0, "depth": 0, "request_id": "r0"},
            {"event": "gpu_batch_submitted", "elapsed_s": 1.0, "depth": 0, "request_ids": ["r0"]},
            {"event": "scheduler_state", "elapsed_s": 3.0, "depth": 0, "running_prepare": 0, "prepared_requests": 0, "pending_gpu_requests": 0, "active_gpu_batches": 0, "idle_gpu_workers": 4, "pending_ddar_submit": 0, "running_ddar": 1, "frontier_exhausted": True},
            {"event": "gpu_batch_done", "elapsed_s": 3.0, "depth": 0, "request_ids": ["r0"]},
            {"event": "ddar_submit", "elapsed_s": 3.0, "depth": 0, "attempt_key": "a0"},
            {"event": "scheduler_state", "elapsed_s": 5.0, "depth": 0, "running_prepare": 0, "prepared_requests": 0, "pending_gpu_requests": 0, "active_gpu_batches": 0, "idle_gpu_workers": 4, "pending_ddar_submit": 0, "running_ddar": 0, "frontier_exhausted": True},
            {"event": "ddar_result", "elapsed_s": 5.0, "depth": 0, "attempt_key": "a0"},
            {"event": "depth_start", "elapsed_s": 0.0, "depth": 0},
            {"event": "depth_end", "elapsed_s": 5.0, "depth": 0},
        ],
    )
    _write_jsonl(
        run_dir / "attempts" / "0000_demo.jsonl",
        [
            {"attempt_type": "candidate", "attempt_key": "a0", "ddar_build_work_time_s": 0.2, "ddar_engine_work_time_s": 0.8},
        ],
    )

    analysis = analyze_run_dir(run_dir)
    summary = analysis["summary"]

    assert round(summary["avg_prepare_inflight"], 2) == 0.2
    assert round(summary["avg_gpu_batches_inflight"], 2) == 0.4
    assert round(summary["avg_ddar_inflight"], 2) == 0.4
    assert summary["latency"]["prepare_submit_to_ready"]["mean_s"] == 1.0
    assert summary["latency"]["gpu_submit_to_done"]["mean_s"] == 2.0
    assert summary["latency"]["ddar_submit_to_result"]["mean_s"] == 2.0
    assert summary["ddar_work"]["build"]["mean_s"] == 0.2
    assert summary["ddar_work"]["engine"]["mean_s"] == 0.8
    assert analysis["depth_rows"][0]["ddar_submit"] == 1
    assert "model_response" not in analysis["depth_rows"][0]


def test_analyze_run_dir_dedupes_duplicate_attempt_records(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_jsonl(
        run_dir / "problems" / "0000_demo.jsonl",
        [
            {"event": "gpu_batch_done", "elapsed_s": 1.0, "worker_batch_profile": {"generate_time_s": 2.0}},
        ],
    )
    _write_jsonl(
        run_dir / "attempts" / "0000_demo.jsonl",
        [
            {
                "attempt_type": "candidate",
                "attempt_key": "a0",
                "request_id": "r0",
                "decision": "invalid",
                "prompt_token_count": 10,
                "generated_token_count_sum": 6,
                "generated_sequence_count": 2,
                "raw_candidate_count": 2,
                "unique_candidate_count": 1,
                "duplicate_candidate_count": 1,
                "first_token_latency_s": 0.5,
                "ddar_build_work_time_s": 0.2,
                "ddar_engine_work_time_s": 0.8,
            },
            {
                "attempt_type": "candidate",
                "attempt_key": "a0",
                "request_id": "r0",
                "decision": "invalid",
                "prompt_token_count": 10,
                "generated_token_count_sum": 6,
                "generated_sequence_count": 2,
                "raw_candidate_count": 2,
                "unique_candidate_count": 1,
                "duplicate_candidate_count": 1,
                "first_token_latency_s": 0.5,
                "ddar_build_work_time_s": 0.2,
                "ddar_engine_work_time_s": 0.8,
            },
        ],
    )

    analysis = analyze_run_dir(run_dir)
    metrics = analysis["summary"]["candidate_metrics"]

    assert metrics["request_count"] == 1
    assert metrics["build_success_count"] == 1
    assert metrics["generated_token_count_sum"] == 6
    assert metrics["valid_candidates_per_gpu_generate_s"] == 0.5
    assert analysis["summary"]["ddar_work"]["build"]["count"] == 1
