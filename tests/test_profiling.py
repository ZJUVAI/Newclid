from __future__ import annotations

import csv

from newclid.profiling import (
    add_profiling_time,
    create_detailed_profiling_payload,
    create_profiling_payload,
    finalize_detailed_profiling,
    finalize_profiling,
    merge_profiling_payloads,
    write_profiling_csv,
)


def test_finalize_profiling_computes_other_wall_time() -> None:
    profiling = create_profiling_payload()
    add_profiling_time(profiling, "entry_setup_wall_time_s", 0.2)
    add_profiling_time(profiling, "base_ddar_wall_time_s", 0.3)
    add_profiling_time(profiling, "request_build_wall_time_s", 0.4)
    add_profiling_time(profiling, "gpu_wait_wall_time_s", 0.5)
    add_profiling_time(profiling, "gpu_result_handle_wall_time_s", 0.6)
    add_profiling_time(profiling, "ddar_submit_wall_time_s", 0.1)
    add_profiling_time(profiling, "ddar_wait_wall_time_s", 0.7)
    add_profiling_time(profiling, "ddar_result_handle_wall_time_s", 0.2)
    add_profiling_time(profiling, "scheduler_overhead_wall_time_s", 0.4)

    finalized = finalize_profiling(profiling, 4.0)

    assert finalized["total_time_s"] == 4.0
    assert abs(finalized["other_wall_time_s"] - 0.6) < 1e-9


def test_finalize_profiling_clamps_negative_other_wall_time() -> None:
    profiling = create_profiling_payload()
    add_profiling_time(profiling, "entry_setup_wall_time_s", 2.0)
    add_profiling_time(profiling, "base_ddar_wall_time_s", 2.0)
    add_profiling_time(profiling, "request_build_wall_time_s", 2.0)

    finalized = finalize_profiling(profiling, 5.0)

    assert finalized["other_wall_time_s"] == 0.0


def test_merge_profiling_payloads_accumulates_wall_stages_only() -> None:
    merged = merge_profiling_payloads(
        {"entry_setup_wall_time_s": 1.0},
        {"gpu_wait_wall_time_s": 2.0, "ddar_wait_wall_time_s": 3.0, "other_wall_time_s": 99.0},
    )

    assert merged["entry_setup_wall_time_s"] == 1.0
    assert merged["gpu_wait_wall_time_s"] == 2.0
    assert merged["ddar_wait_wall_time_s"] == 3.0
    assert merged["total_time_s"] == 0.0
    assert merged["other_wall_time_s"] == 0.0


def test_detailed_helpers_alias_wall_only_payload() -> None:
    profiling = create_detailed_profiling_payload()
    add_profiling_time(profiling, "gpu_wait_wall_time_s", 1.5)

    finalized = finalize_detailed_profiling(profiling, 2.0)

    assert finalized["gpu_wait_wall_time_s"] == 1.5
    assert finalized["other_wall_time_s"] == 0.5


def test_write_profiling_csv_outputs_wall_summary_and_rows(tmp_path) -> None:
    csv_path = tmp_path / "eval_demo_profiling.csv"
    rows = [
        {
            "problem_name": "p1",
            "solved": "√",
            "total_time_s": 5.0,
            "entry_setup_wall_time_s": 0.5,
            "base_ddar_wall_time_s": 0.4,
            "request_build_wall_time_s": 1.2,
            "gpu_wait_wall_time_s": 0.9,
            "gpu_result_handle_wall_time_s": 0.3,
            "ddar_submit_wall_time_s": 0.1,
            "ddar_wait_wall_time_s": 0.7,
            "ddar_result_handle_wall_time_s": 0.4,
            "scheduler_overhead_wall_time_s": 0.2,
            "other_wall_time_s": 0.3,
        },
        {
            "problem_name": "p2",
            "solved": "x",
            "total_time_s": 2.0,
            "entry_setup_wall_time_s": 0.2,
            "base_ddar_wall_time_s": 0.1,
            "request_build_wall_time_s": 0.3,
            "gpu_wait_wall_time_s": 0.4,
            "gpu_result_handle_wall_time_s": 0.2,
            "ddar_submit_wall_time_s": 0.0,
            "ddar_wait_wall_time_s": 0.3,
            "ddar_result_handle_wall_time_s": 0.1,
            "scheduler_overhead_wall_time_s": 0.1,
            "other_wall_time_s": 0.3,
        },
    ]

    write_profiling_csv(
        csv_path,
        dataset_name="demo",
        solved_count=1,
        total_problems=2,
        total_time_s=7.0,
        rows=rows,
    )

    with open(csv_path, newline="", encoding="utf-8") as f:
        written_rows = list(csv.reader(f))

    assert "Dataset: demo, Solved: 1/2" in written_rows[0][0]
    assert "Total Time: 7.00s" in written_rows[0][0]
    assert "Request Build Wall Time: 1.50s" in written_rows[0][0]
    assert written_rows[1] == [
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
    assert written_rows[2] == [
        "p1",
        "√",
        "5.00",
        "0.50",
        "0.40",
        "1.20",
        "0.90",
        "0.30",
        "0.10",
        "0.70",
        "0.40",
        "0.20",
        "0.30",
    ]
