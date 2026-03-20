#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""导出 HAGeo 408 题的 solved 矩阵为 CSV（宽表）。

输出格式：
- 表头：file_id, solved, <408道题目的名称(路径)>
- 每行：一个规则结果文件（hageo_candidate_rules_rules_{id}_results.json）
  - file_id: {id}
  - solved: 在 408 列里 success==True 的数量
  - 题目列：0/1（是否 solved）

题目列顺序来自 benchmarks/hageo_408.txt。
该 benchmark 文件格式通常是：
  problem_id.gex
  <题目描述...>
  problem_id.gex
  <题目描述...>
因此本脚本通过“以 .gex 结尾的行”提取题目名。

默认输出到：datasets/hageo_candidate_rules_solved_matrix_408.csv

用法：
  python scripts/export_hageo_candidate_solved_matrix_csv.py
  python scripts/export_hageo_candidate_solved_matrix_csv.py --out datasets/foo.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_FILE_RE = re.compile(r"^hageo_candidate_rules_rules_(\d+)_results\.json$")


@dataclass(frozen=True)
class FileResult:
    rule_id: int
    solved_map: dict[str, int]  # problem_id -> 0/1


def _iter_result_files(datasets_dir: Path) -> list[tuple[int, Path]]:
    if not datasets_dir.exists() or not datasets_dir.is_dir():
        raise FileNotFoundError(f"datasets 目录不存在或不是目录: {datasets_dir}")

    items: list[tuple[int, Path]] = []
    for p in datasets_dir.iterdir():
        if not p.is_file():
            continue
        m = _FILE_RE.match(p.name)
        if not m:
            continue
        items.append((int(m.group(1)), p))

    items.sort(key=lambda x: x[0])
    return items


def _load_benchmark_problem_ids(bench_file: Path) -> list[str]:
    if not bench_file.exists() or not bench_file.is_file():
        raise FileNotFoundError(f"benchmark 文件不存在: {bench_file}")

    problem_ids: list[str] = []
    with bench_file.open("r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            if s.endswith(".gex"):
                problem_ids.append(s)

    # 基本校验：预期 408
    if len(problem_ids) == 0:
        raise ValueError(f"未从 benchmark 中解析出任何 .gex 行: {bench_file}")
    return problem_ids


def _parse_one_result_file(path: Path) -> FileResult:
    m = _FILE_RE.match(path.name)
    if not m:
        raise ValueError(f"文件名不匹配模式: {path.name}")
    rule_id = int(m.group(1))

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        raise RuntimeError(f"读取/解析 JSON 失败: {path} ({e})") from e

    if not isinstance(data, dict):
        raise ValueError(f"JSON 顶层不是 object: {path}")

    results = data.get("results")
    if not isinstance(results, list):
        raise ValueError(f"缺少 results 列表: {path}")

    solved_map: dict[str, int] = {}
    for item in results:
        if not isinstance(item, dict):
            continue
        pid = item.get("problem_id")
        success = item.get("success")
        if isinstance(pid, str):
            solved_map[pid] = 1 if success is True else 0

    return FileResult(rule_id=rule_id, solved_map=solved_map)


def _write_matrix_csv(
    out_path: Path,
    problem_ids: list[str],
    file_results: list[FileResult],
    missing_value: int = 0,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    header = ["file_id", "solved", *problem_ids]
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)

        for fr in file_results:
            row_bits = [fr.solved_map.get(pid, missing_value) for pid in problem_ids]
            solved_cnt = int(sum(row_bits))
            w.writerow([fr.rule_id, solved_cnt, *row_bits])


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="导出 hageo_candidate_rules solved 矩阵（408题）为 CSV")
    parser.add_argument(
        "--datasets",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "datasets",
        help="datasets 目录路径（默认：项目根目录/datasets）",
    )
    parser.add_argument(
        "--bench",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "benchmarks" / "hageo_408.txt",
        help="题目列表文件（默认：benchmarks/hageo_408.txt）",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "datasets" / "hageo_candidate_rules_solved_matrix_408.csv",
        help="输出 CSV 路径（默认：datasets/hageo_candidate_rules_solved_matrix_408.csv）",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="不打印统计信息（只生成 CSV）",
    )

    args = parser.parse_args(argv)

    problem_ids = _load_benchmark_problem_ids(args.bench)

    files = _iter_result_files(args.datasets)
    if not files:
        print(f"未找到匹配文件：{args.datasets}/hageo_candidate_rules_rules_*_results.json", file=sys.stderr)
        return 2

    file_results: list[FileResult] = []
    total_missing = 0
    for rid, path in files:
        fr = _parse_one_result_file(path)
        if fr.rule_id != rid:
            raise RuntimeError(f"rule id 不一致：iter={rid} parse={fr.rule_id} file={path}")
        # 统计缺失题目（results 里不存在该 problem_id）
        total_missing += sum(1 for pid in problem_ids if pid not in fr.solved_map)
        file_results.append(fr)

    _write_matrix_csv(args.out, problem_ids, file_results)

    if not args.quiet:
        print(f"benchmark problems: {len(problem_ids)}")
        print(f"result files: {len(file_results)}")
        print(f"csv written: {args.out}")
        if total_missing:
            avg_missing = total_missing / max(1, len(file_results))
            print(f"warning: missing cells filled with 0, total_missing={total_missing}, avg_missing_per_file={avg_missing:.2f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
