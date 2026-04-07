from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def create_profiling_payload() -> dict[str, float]:
    return {
        "build_time_s": 0.0,
        "inference_time_s": 0.0,
        "ddar_time_s": 0.0,
        "total_time_s": 0.0,
        "other_time_s": 0.0,
    }


def add_profiling_time(profiling: dict[str, float], field: str, elapsed_s: float | int | None) -> None:
    if elapsed_s is None:
        return
    profiling[field] = profiling.get(field, 0.0) + float(elapsed_s)


def finalize_profiling(profiling: dict[str, float], total_time_s: float | int) -> dict[str, float]:
    profiling["total_time_s"] = float(total_time_s)
    accounted = (
        profiling.get("build_time_s", 0.0)
        + profiling.get("inference_time_s", 0.0)
        + profiling.get("ddar_time_s", 0.0)
    )
    profiling["other_time_s"] = max(float(total_time_s) - accounted, 0.0)
    return profiling


def merge_profiling_payloads(*payloads: dict[str, float] | None) -> dict[str, float]:
    merged = create_profiling_payload()
    for payload in payloads:
        if payload is None:
            continue
        for field in ("build_time_s", "inference_time_s", "ddar_time_s"):
            add_profiling_time(merged, field, payload.get(field))
    return merged


def profiling_summary(rows: list[dict[str, Any]]) -> dict[str, float]:
    summary = {
        "total_time_s": 0.0,
        "build_time_s": 0.0,
        "inference_time_s": 0.0,
        "ddar_time_s": 0.0,
        "other_time_s": 0.0,
    }
    for row in rows:
        summary["total_time_s"] += float(row.get("total_time_s", 0.0))
        summary["build_time_s"] += float(row.get("build_time_s", 0.0))
        summary["inference_time_s"] += float(row.get("inference_time_s", 0.0))
        summary["ddar_time_s"] += float(row.get("ddar_time_s", 0.0))
        summary["other_time_s"] += float(row.get("other_time_s", 0.0))
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
