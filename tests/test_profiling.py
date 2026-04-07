from __future__ import annotations

import csv

from newclid.profiling import (
    add_profiling_count,
    add_profiling_time,
    create_depth_profiling_row,
    create_detailed_profiling_payload,
    create_profiling_payload,
    finalize_detailed_profiling,
    finalize_profiling,
    merge_profiling_payloads,
    write_profiling_csv,
    write_profiling_depth_csv,
    write_profiling_work_csv,
)


def test_finalize_profiling_computes_other_time() -> None:
    profiling = create_profiling_payload()
    add_profiling_time(profiling, "build_time_s", 1.25)
    add_profiling_time(profiling, "inference_time_s", 2.5)
    add_profiling_time(profiling, "ddar_time_s", 0.75)

    finalized = finalize_profiling(profiling, 5.0)

    assert finalized["total_time_s"] == 5.0
    assert finalized["build_time_s"] == 1.25
    assert finalized["inference_time_s"] == 2.5
    assert finalized["ddar_time_s"] == 0.75
    assert finalized["other_time_s"] == 0.5


def test_finalize_profiling_clamps_negative_other_time() -> None:
    profiling = create_profiling_payload()
    add_profiling_time(profiling, "build_time_s", 2.0)
    add_profiling_time(profiling, "inference_time_s", 2.0)
    add_profiling_time(profiling, "ddar_time_s", 2.0)

    finalized = finalize_profiling(profiling, 5.0)

    assert finalized["other_time_s"] == 0.0


def test_write_profiling_csv_outputs_summary_and_rows(tmp_path) -> None:
    csv_path = tmp_path / "eval_demo_profiling.csv"
    rows = [
        {
            "problem_name": "p1",
            "solved": "√",
            "total_time_s": 4.0,
            "build_time_s": 1.0,
            "inference_time_s": 2.0,
            "ddar_time_s": 0.5,
            "other_time_s": 0.5,
        },
        {
            "problem_name": "p2",
            "solved": "x",
            "total_time_s": 2.0,
            "build_time_s": 0.5,
            "inference_time_s": 0.5,
            "ddar_time_s": 0.5,
            "other_time_s": 0.5,
        },
    ]

    write_profiling_csv(
        csv_path,
        dataset_name="demo",
        solved_count=1,
        total_problems=2,
        total_time_s=6.0,
        rows=rows,
    )

    with open(csv_path, newline="", encoding="utf-8") as f:
        written_rows = list(csv.reader(f))

    assert "Dataset: demo, Solved: 1/2" in written_rows[0][0]
    assert "Total Time: 6.00s" in written_rows[0][0]
    assert "Build Time: 1.50s" in written_rows[0][0]
    assert written_rows[1] == [
        "Problem Name",
        "Solved",
        "Total Time (s)",
        "Build Time (s)",
        "Inference Time (s)",
        "DDAR Time (s)",
        "Other Time (s)",
    ]
    assert written_rows[2] == ["p1", "√", "4.00", "1.00", "2.00", "0.50", "0.50"]
    assert written_rows[3] == ["p2", "x", "2.00", "0.50", "0.50", "0.50", "0.50"]


def test_merge_profiling_payloads_only_accumulates_profiled_stages() -> None:
    merged = merge_profiling_payloads(
        {"build_time_s": 1.0},
        {"inference_time_s": 2.0, "ddar_time_s": 3.0, "other_time_s": 99.0},
    )

    assert merged["build_time_s"] == 1.0
    assert merged["inference_time_s"] == 2.0
    assert merged["ddar_time_s"] == 3.0
    assert merged["total_time_s"] == 0.0
    assert merged["other_time_s"] == 0.0


def test_finalize_detailed_profiling_computes_other_wall_time() -> None:
    profiling = create_detailed_profiling_payload()
    add_profiling_time(profiling, "entry_setup_wall_time_s", 0.2)
    add_profiling_time(profiling, "base_ddar_wall_time_s", 0.3)
    add_profiling_time(profiling, "request_build_wall_time_s", 0.4)
    add_profiling_time(profiling, "gpu_wait_wall_time_s", 0.5)
    add_profiling_time(profiling, "gpu_result_handle_wall_time_s", 0.6)
    add_profiling_time(profiling, "ddar_submit_wall_time_s", 0.1)
    add_profiling_time(profiling, "ddar_wait_wall_time_s", 0.7)
    add_profiling_time(profiling, "ddar_result_handle_wall_time_s", 0.2)
    add_profiling_time(profiling, "scheduler_overhead_wall_time_s", 0.4)

    finalized = finalize_detailed_profiling(profiling, 4.0)

    assert finalized["total_time_s"] == 4.0
    assert abs(finalized["other_wall_time_s"] - 0.6) < 1e-9


def test_write_profiling_csv_outputs_detailed_wall_rows(tmp_path) -> None:
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
        }
    ]

    write_profiling_csv(
        csv_path,
        dataset_name="demo",
        solved_count=1,
        total_problems=1,
        total_time_s=5.0,
        rows=rows,
    )

    with open(csv_path, newline="", encoding="utf-8") as f:
        written_rows = list(csv.reader(f))

    assert "Entry Setup Wall Time: 0.50s" in written_rows[0][0]
    assert "DDAR Submit Wall Time: 0.10s" in written_rows[0][0]
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


def test_write_profiling_work_and_depth_csv(tmp_path) -> None:
    work_csv_path = tmp_path / "eval_demo_profiling_work.csv"
    depth_csv_path = tmp_path / "eval_demo_profiling_depth.csv"
    depth_row = create_depth_profiling_row(depth=1, frontier_size=3)
    add_profiling_time(depth_row, "request_build_wall_time_s", 1.5)
    add_profiling_time(depth_row, "draw_svg_wall_time_s", 0.8)
    add_profiling_time(depth_row, "ddar_submit_wall_time_s", 0.1)
    add_profiling_time(depth_row, "scheduler_overhead_wall_time_s", 0.2)
    add_profiling_count(depth_row, "requests_built", 2)
    add_profiling_count(depth_row, "ddar_submitted", 4)
    depth_row["next_frontier_size"] = 2

    rows = [
        {
            "problem_name": "p1",
            "solved": "x",
            "gpu_inference_work_time_s": 1.1,
            "ddar_build_work_time_s": 2.2,
            "ddar_engine_work_time_s": 3.3,
            "num_requests": 4,
            "num_candidates_total": 9,
            "num_candidates_parse_failed": 2,
            "num_candidates_build_failed": 1,
            "num_ddar_submitted": 6,
            "num_ddar_invalid": 1,
            "max_running_gpu": 2,
            "max_running_ddar": 5,
            "max_prepared_requests": 3,
            "max_pending_ddar_submit": 4,
            "depth_rows": [depth_row],
        }
    ]

    write_profiling_work_csv(
        work_csv_path,
        dataset_name="demo",
        solved_count=0,
        total_problems=1,
        rows=rows,
    )
    write_profiling_depth_csv(
        depth_csv_path,
        dataset_name="demo",
        rows=[{"problem_name": "p1", **depth_row}],
    )

    with open(work_csv_path, newline="", encoding="utf-8") as f:
        work_rows = list(csv.reader(f))
    with open(depth_csv_path, newline="", encoding="utf-8") as f:
        depth_rows = list(csv.reader(f))

    assert "GPU Inference Work Time: 1.10s" in work_rows[0][0]
    assert work_rows[2] == [
        "p1",
        "x",
        "1.10",
        "2.20",
        "3.30",
        "4",
        "9",
        "2",
        "1",
        "6",
        "1",
        "2",
        "5",
        "3",
        "4",
    ]
    assert depth_rows[1] == [
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
    assert depth_rows[2] == [
        "p1",
        "1",
        "3",
        "2",
        "1.50",
        "0.80",
        "0.00",
        "0.00",
        "0.00",
        "0.00",
        "0.00",
        "0.00",
        "4",
        "0.10",
        "0.00",
        "0.00",
        "0.00",
        "0.00",
        "0.20",
        "2",
    ]
