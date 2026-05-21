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
BENCHMARKS_DIR = SCRIPT_DIR / "benchmarks"
CORE_FILES = [
    SCRIPT_DIR / "generate_cot_sft.py",
    SCRIPT_DIR / "audits.py",
    SCRIPT_DIR / "geometry_text.py",
    SCRIPT_DIR / "prompt_builders.py",
    SCRIPT_DIR / "writer_contracts.py",
    SCRIPT_DIR / "run_artifacts.py",
    SCRIPT_DIR / "semantic_review.py",
]


def count_nonempty_jsonl_lines(path: Path) -> int:
    with open(path, "r", encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def resolve_benchmark_input_path(input_jsonl_path: str, manifest_path: Path) -> Path:
    path = Path(input_jsonl_path)
    candidates = [
        path,
        (REPO_ROOT / path).resolve(),
        (manifest_path.parent / path).resolve(),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return path.resolve()


def validate_benchmark_manifest(manifest_path: Path, input_jsonl_path: Path | None = None) -> dict:
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    benchmark_name = manifest.get("benchmark_name")
    manifest_input = manifest.get("input_jsonl")
    records = manifest.get("records")
    subsets = manifest.get("subsets")
    if not isinstance(benchmark_name, str) or not benchmark_name.strip():
        raise ValueError("benchmark manifest field 'benchmark_name' must be a non-empty string")
    if not isinstance(manifest_input, str) or not manifest_input.strip():
        raise ValueError("benchmark manifest field 'input_jsonl' must be a non-empty string")
    if not isinstance(records, list):
        raise ValueError("benchmark manifest field 'records' must be a list")
    if not isinstance(subsets, dict):
        raise ValueError("benchmark manifest field 'subsets' must be an object")

    if input_jsonl_path is None:
        input_jsonl_path = resolve_benchmark_input_path(manifest_input, manifest_path)
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
        goal_type = record.get("goal_type")
        aux_type = record.get("aux_type")
        focus_tags = record.get("focus_tags")
        if not isinstance(goal_type, str) or not goal_type.strip():
            raise ValueError(f"benchmark manifest record {idx} must include a non-empty string goal_type")
        if not isinstance(aux_type, str) or not aux_type.strip():
            raise ValueError(f"benchmark manifest record {idx} must include a non-empty string aux_type")
        if not isinstance(focus_tags, list) or not focus_tags:
            raise ValueError(f"benchmark manifest record {idx} must include a non-empty focus_tags list")
        for tag in focus_tags:
            if not isinstance(tag, str) or not tag.strip():
                raise ValueError(
                    f"benchmark manifest record {idx} contains an invalid focus tag: {tag!r}"
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
        "benchmark_name": benchmark_name,
        "input_jsonl": str(input_jsonl_path),
        "records": line_count,
        "subsets": len(subsets),
    }


def validate_all_benchmark_manifests(benchmarks_dir: Path) -> dict:
    manifest_paths = sorted(benchmarks_dir.rglob("*_manifest.json"))
    if not manifest_paths:
        raise ValueError(f"no benchmark manifests found in {benchmarks_dir}")

    summaries = [validate_benchmark_manifest(path) for path in manifest_paths]
    return {
        "manifests": len(summaries),
        "records": sum(item["records"] for item in summaries),
        "benchmark_names": [item["benchmark_name"] for item in summaries],
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


def check_generate_cli_help() -> None:
    result = run_subprocess(
        [sys.executable, str(SCRIPT_DIR / "generate_cot_sft.py"), "--help"],
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout or "generate_cot_sft.py --help failed")
    if "Generate geometry CoT SFT data" not in result.stdout:
        raise RuntimeError("generate_cot_sft.py --help output did not contain the expected description")


def check_unittests() -> None:
    result = run_subprocess(
        [sys.executable, "-m", "unittest", "discover", "-s", str(TESTS_DIR), "-p", "test_cot_sft_*.py"],
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stdout + result.stderr)


def check_benchmark_assets() -> None:
    validate_all_benchmark_manifests(BENCHMARKS_DIR)


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
    run_check("generate_cli_help", check_generate_cli_help)
    run_check("semantic_review_help", check_semantic_review_help)
    if not args.skip_tests:
        run_check("unittest", check_unittests)


if __name__ == "__main__":
    main()
