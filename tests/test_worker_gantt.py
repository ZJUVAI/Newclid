from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.single_problem_multi_gpu_eval.scripts.plot_worker_gantt import (
    TraceCompatibilityError,
    extract_worker_intervals,
    main,
    resolve_problem_file,
)


def _write_problem_trace(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False))
            handle.write("\n")


def _sample_worker_trace(problem_name: str = "demo_problem") -> list[dict]:
    return [
        {
            "event": "prepare_request_ready",
            "problem_name": problem_name,
            "depth": 0,
            "request_id": "d0_proot",
            "prepare_worker_id": "prepare_0",
            "prepare_started_at_unix_s": 100.0,
            "prepare_finished_at_unix_s": 100.4,
        },
        {
            "event": "prepare_request_ready",
            "problem_name": problem_name,
            "depth": 1,
            "request_id": "d1_p0",
            "prepare_worker_id": "prepare_1",
            "prepare_started_at_unix_s": 101.0,
            "prepare_finished_at_unix_s": 101.3,
        },
        {
            "event": "gpu_batch_done",
            "problem_name": problem_name,
            "depth": 0,
            "request_ids": ["d0_proot"],
            "batch_size": 1,
            "worker_batch_profile": {
                "gpu_worker_id": "gpu:0",
                "worker_started_at_unix_s": 100.5,
                "worker_finished_at_unix_s": 101.2,
            },
        },
        {
            "event": "gpu_batch_done",
            "problem_name": problem_name,
            "depth": 1,
            "request_ids": ["d1_p0", "d1_p1"],
            "batch_size": 2,
            "worker_batch_profile": {
                "gpu_worker_id": "gpu:1",
                "worker_started_at_unix_s": 101.4,
                "worker_finished_at_unix_s": 102.0,
            },
        },
        {
            "event": "ddar_result",
            "problem_name": problem_name,
            "depth": 0,
            "attempt_key": "d0_proot:0",
            "ddar_worker_id": "127.0.0.1:5001",
            "ddar_started_at_unix_s": 101.3,
            "ddar_finished_at_unix_s": 101.8,
            "ddar_build_started_at_unix_s": 101.3,
            "ddar_build_finished_at_unix_s": 101.45,
            "ddar_engine_started_at_unix_s": 101.45,
            "ddar_engine_finished_at_unix_s": 101.75,
        },
        {
            "event": "ddar_result",
            "problem_name": problem_name,
            "depth": 1,
            "attempt_key": "d1_p0:0",
            "ddar_worker_id": "127.0.0.1:5002",
            "ddar_started_at_unix_s": 102.1,
            "ddar_finished_at_unix_s": 102.7,
            "ddar_build_started_at_unix_s": 102.1,
            "ddar_build_finished_at_unix_s": 102.3,
            "ddar_engine_started_at_unix_s": 102.3,
            "ddar_engine_finished_at_unix_s": 102.6,
        },
    ]


def test_extract_worker_intervals_groups_real_workers() -> None:
    problem_name, intervals = extract_worker_intervals(_sample_worker_trace())

    assert problem_name == "demo_problem"
    assert {(item["group"], item["worker_id"]) for item in intervals} == {
        ("Prepare", "prepare_0"),
        ("Prepare", "prepare_1"),
        ("GPU", "gpu:0"),
        ("GPU", "gpu:1"),
        ("DDAR", "127.0.0.1:5001"),
        ("DDAR", "127.0.0.1:5002"),
    }


def test_extract_worker_intervals_rejects_old_trace_schema() -> None:
    with pytest.raises(TraceCompatibilityError):
        extract_worker_intervals(
            [
                {
                    "event": "gpu_batch_done",
                    "problem_name": "old_problem",
                    "depth": 0,
                    "request_ids": ["d0_proot"],
                    "batch_size": 1,
                    "worker_batch_profile": {},
                }
            ]
        )


def test_plot_worker_gantt_script_writes_png_and_svg(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    problem_path = run_dir / "problems" / "0000_demo_problem.jsonl"
    _write_problem_trace(problem_path, _sample_worker_trace())

    resolved = resolve_problem_file(run_dir, "demo_problem")
    assert resolved == problem_path

    png_path = tmp_path / "demo.png"
    svg_path = tmp_path / "demo.svg"
    assert main(["--run_dir", str(run_dir), "--problem", "demo_problem", "--output", str(png_path)]) == 0
    assert main(["--run_dir", str(run_dir), "--problem", "0", "--output", str(svg_path), "--depth", "1"]) == 0
    assert png_path.exists() and png_path.stat().st_size > 0
    assert svg_path.exists() and svg_path.stat().st_size > 0
