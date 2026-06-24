from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_problem_events(run_dir: Path) -> list[dict[str, Any]]:
    problem_files = sorted((run_dir / "problems").glob("*.jsonl"))
    if not problem_files:
        raise FileNotFoundError(f"No problem event files found under {run_dir / 'problems'}")
    events: list[dict[str, Any]] = []
    for path in problem_files:
        events.extend(load_jsonl(path))
    return events


def summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(event.get("event")) for event in events)
    problems = {
        str(event.get("problem_name"))
        for event in events
        if event.get("event") == "problem_start"
    }
    solved = sum(
        1
        for event in events
        if event.get("event") == "problem_end" and event.get("success") is True
    )
    return {
        "problem_count": len(problems),
        "solved_count": solved,
        "lm_requests": counts["lm_request"],
        "lm_results": counts["lm_result"],
        "candidate_parse": counts["candidate_parse"],
        "candidate_build": counts["candidate_build"],
        "ddar_submit": counts["ddar_submit"],
        "ddar_result": counts["ddar_result"],
        "depth_start": counts["depth_start"],
        "depth_end": counts["depth_end"],
    }


def write_summary_csv(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        writer.writerow(["metric", "value"])
        for key, value in summary.items():
            writer.writerow([key, value])


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize basic evaluation trace events.")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--csv", type=Path, default=None)
    args = parser.parse_args()

    summary = summarize(load_problem_events(args.run_dir))
    for key, value in summary.items():
        print(f"{key}: {value}")
    if args.csv is not None:
        write_summary_csv(args.csv, summary)


if __name__ == "__main__":
    main()
