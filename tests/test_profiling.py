from __future__ import annotations

import csv

from newclid.profiling import (
    add_profiling_time,
    create_profiling_payload,
    finalize_profiling,
    merge_profiling_payloads,
    write_profiling_csv,
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
