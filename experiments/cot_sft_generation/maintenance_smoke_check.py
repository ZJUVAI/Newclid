#!/usr/bin/env python3
"""
Run the minimal maintenance checks for the CoT SFT generation pipeline.
"""

from __future__ import annotations

import argparse
import json
import py_compile
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
TESTS_DIR = REPO_ROOT / "tests"
CORE_FILES = [
    SCRIPT_DIR / "generate_cot_sft.py",
    SCRIPT_DIR / "geometry_text.py",
    SCRIPT_DIR / "writer_contracts.py",
    SCRIPT_DIR / "run_artifacts.py",
    SCRIPT_DIR / "semantic_review.py",
]
BENCHMARK_MANIFEST = SCRIPT_DIR / "benchmarks" / "fixed_v104sample_manifest.json"
BENCHMARK_INPUT = SCRIPT_DIR / "benchmarks" / "fixed_v104sample_input.jsonl"


def count_nonempty_jsonl_lines(path: Path) -> int:
    with open(path, "r", encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def validate_benchmark_manifest(manifest_path: Path, input_jsonl_path: Path) -> dict:
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    records = manifest.get("records")
    subsets = manifest.get("subsets")
    if not isinstance(records, list):
        raise ValueError("benchmark manifest field 'records' must be a list")
    if not isinstance(subsets, dict):
        raise ValueError("benchmark manifest field 'subsets' must be an object")

    line_count = count_nonempty_jsonl_lines(input_jsonl_path)
    if len(records) != line_count:
        raise ValueError(
            f"benchmark manifest record count mismatch: manifest has {len(records)}, input has {line_count}"
        )

    valid_indices = set(range(line_count))
    for idx, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"benchmark manifest record {idx} must be an object")
        if record.get("sample_order") != idx:
            raise ValueError(
                f"benchmark manifest record {idx} has sample_order={record.get('sample_order')} instead of {idx}"
            )

    for subset_name, subset in subsets.items():
        if not isinstance(subset, list):
            raise ValueError(f"benchmark subset '{subset_name}' must be a list")
        for item in subset:
            if not isinstance(item, int):
                raise ValueError(f"benchmark subset '{subset_name}' contains non-integer item: {item!r}")
            if item not in valid_indices:
                raise ValueError(f"benchmark subset '{subset_name}' contains out-of-range index: {item}")

    return {
        "records": line_count,
        "subsets": len(subsets),
    }


def run_subprocess(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )


def run_check(label: str, fn) -> None:
    print(f"[check] {label}")
    fn()
    print(f"[pass]  {label}")


def check_py_compile() -> None:
    for path in CORE_FILES:
        py_compile.compile(str(path), doraise=True)


def check_semantic_review_help() -> None:
    result = run_subprocess(
        [sys.executable, str(SCRIPT_DIR / "semantic_review.py"), "--help"],
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout or "semantic_review.py --help failed")
    if "Validate semantic review records" not in result.stdout:
        raise RuntimeError("semantic_review.py --help output did not contain the expected description")


def check_unittests() -> None:
    result = run_subprocess(
        [sys.executable, "-m", "unittest", "discover", "-s", str(TESTS_DIR), "-p", "test_cot_sft_*.py"],
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stdout + result.stderr)


def check_benchmark_assets() -> None:
    validate_benchmark_manifest(BENCHMARK_MANIFEST, BENCHMARK_INPUT)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the minimal maintenance smoke checks for experiments/cot_sft_generation."
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip the unittest discovery step.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_check("py_compile", check_py_compile)
    run_check("benchmark_manifest", check_benchmark_assets)
    run_check("semantic_review_help", check_semantic_review_help)
    if not args.skip_tests:
        run_check("unittest", check_unittests)


if __name__ == "__main__":
    main()
