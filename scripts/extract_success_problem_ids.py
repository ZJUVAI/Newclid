#!/usr/bin/env python3
"""Extract problem_id with success==true from JSON result files.

Default behavior:
- Scan: datasets/c10s50k/*.json
- Output: datasets/c10s50k_success_problem_ids.txt
- One problem_id per line (sorted, de-duplicated)

This script is intentionally tolerant to slight schema differences:
- Top-level dict with a "results" list (common)
- Top-level list of result dicts
- JSONL fallback if a .json file is newline-delimited

Additional feature:
- Compare extracted problem IDs with a benchmark file (e.g., hageo_224.txt)
- Output a checklist with ✅ (solved) or ❌ (unsolved) markers
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Iterator

SHOW_PROBLEM_ID=True

def _is_truthy_success(value: Any) -> bool:
    if value is True:
        return True
    if value is False or value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() == "true"
    if isinstance(value, (int, float)):
        return value == 1
    return False


def _iter_record_dicts(obj: Any) -> Iterator[dict[str, Any]]:
    if isinstance(obj, dict):
        results = obj.get("results")
        if isinstance(results, list):
            for item in results:
                if isinstance(item, dict):
                    yield item
            return
        # Fallback: try dict values
        for value in obj.values():
            if isinstance(value, dict):
                yield value
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        yield item
        return

    if isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict):
                yield item


def _load_json_or_jsonl(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        records: list[Any] = []
        with path.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                s = line.strip()
                if not s:
                    continue
                try:
                    records.append(json.loads(s))
                except json.JSONDecodeError as e:
                    raise json.JSONDecodeError(
                        f"JSON decode error in {path} at line {line_no}: {e.msg}",
                        e.doc,
                        e.pos,
                    )
        return records


def extract_success_problem_ids(input_dir: Path) -> list[str]:
    problem_ids: set[str] = set()

    json_files = sorted(input_dir.glob("*.json"))
    if not json_files:
        raise FileNotFoundError(f"No .json files found under: {input_dir}")

    for json_path in json_files:
        try:
            obj = _load_json_or_jsonl(json_path)
        except Exception as e:
            print(f"[WARN] Skip unreadable JSON: {json_path} ({e})", file=sys.stderr)
            continue

        for rec in _iter_record_dicts(obj):
            if not _is_truthy_success(rec.get("success")):
                continue

            problem_id = rec.get("problem_id")
            if not isinstance(problem_id, str) or not problem_id.strip():
                # Optional fallback
                problem = rec.get("problem")
                if isinstance(problem, dict):
                    pid2 = problem.get("problem_id")
                    if isinstance(pid2, str):
                        problem_id = pid2

            if isinstance(problem_id, str) and problem_id.strip():
                problem_ids.add(problem_id.strip())

    return sorted(problem_ids)


def load_benchmark_problems(benchmark_path: Path) -> list[str]:
    """Load problem names from a benchmark file (e.g., hageo_224.txt).
    
    The benchmark file format is:
    - Odd lines: problem name/path (e.g., examples/HAGeo-IMO/2000USATSTp2.gex)
    - Even lines: problem definition
    
    Returns a list of problem names in order.
    """
    problems: list[str] = []
    with benchmark_path.open("r", encoding="utf-8") as f:
        lines = f.readlines()
    
    for i, line in enumerate(lines):
        # Odd lines (0-indexed: 0, 2, 4, ...) are problem names
        if i % 2 == 0:
            name = line.strip()
            if name:
                problems.append(name)
    
    return problems


def generate_checklist(
    benchmark_problems: list[str],
    success_problem_ids: set[str],
) -> list[str]:
    """Generate a checklist comparing benchmark problems with solved ones.
    
    Returns a list of strings, each line formatted as:
    ✅ problem_name (if solved)
    ❌ problem_name (if not solved)
    """
    checklist: list[str] = []
    for problem in benchmark_problems:
        if SHOW_PROBLEM_ID:
            if problem in success_problem_ids:
                checklist.append(f"✅ {problem}")
            else:
                checklist.append(f"❌ {problem}")
        else:
            if problem in success_problem_ids:
                checklist.append(f"✅")
            else:
                checklist.append(f"❌")
    return checklist


def main(argv: Iterable[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    # default_input_dir = repo_root / "datasets" / "solve_results" / "c10s50k"
    default_input_dir = repo_root / "datasets" / "solve_results" / "tmp"
    # default_output_path = repo_root / "datasets" / "solve_results" / "c10s50k_success_problem_ids.txt"
    default_output_path = repo_root / "datasets" / "solve_results" / "tmp.txt"
    # default_benchmark_path = repo_root / "benchmarks" / "hageo_224.txt"
    default_benchmark_path = repo_root / "benchmarks" / "jgex_ag_231.txt"
    # default_checklist_path = repo_root / "datasets" / "solve_results" / "c10s50k_checklist.txt"
    default_checklist_path = repo_root / "datasets" / "solve_results" / "tmp.txt"

    parser = argparse.ArgumentParser(
        description="Collect problem_id entries with success and compare with benchmark",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=default_input_dir,
        help=f"Input directory containing result JSON files (default: {default_input_dir})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=default_output_path,
        help=f"Output txt path for success problem IDs (default: {default_output_path})",
    )
    parser.add_argument(
        "--benchmark",
        type=Path,
        default=default_benchmark_path,
        help=f"Benchmark file path (default: {default_benchmark_path})",
    )
    parser.add_argument(
        "--checklist",
        type=Path,
        default=default_checklist_path,
        help=f"Output checklist txt path (default: {default_checklist_path})",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    input_dir: Path = args.input_dir
    output_path: Path = args.output
    benchmark_path: Path = args.benchmark
    checklist_path: Path = args.checklist

    # Extract success problem IDs
    problem_ids = extract_success_problem_ids(input_dir)
    success_set = set(problem_ids)

    # Write success problem IDs
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for pid in problem_ids:
            f.write(pid)
            f.write("\n")

    print(f"Wrote {len(problem_ids)} problem_id(s) -> {output_path}")

    # Load benchmark and generate checklist
    if benchmark_path.exists():
        benchmark_problems = load_benchmark_problems(benchmark_path)
        checklist = generate_checklist(benchmark_problems, success_set)
        
        # Count statistics
        solved_count = sum(1 for line in checklist if line.startswith("✅"))
        total_count = len(benchmark_problems)
        
        # Write checklist
        checklist_path.parent.mkdir(parents=True, exist_ok=True)
        with checklist_path.open("w", encoding="utf-8") as f:
            # Write header with statistics
            f.write(f"# Solve Results: {solved_count}/{total_count} ({solved_count/total_count*100:.2f}%)\n")
            f.write(f"# Benchmark: {benchmark_path.name}\n")
            f.write(f"# Source: {input_dir.name}\n")
            f.write("#\n")
            for line in checklist:
                f.write(line)
                f.write("\n")
        
        print(f"Wrote checklist ({solved_count}/{total_count} solved) -> {checklist_path}")
    else:
        print(f"[WARN] Benchmark file not found: {benchmark_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
