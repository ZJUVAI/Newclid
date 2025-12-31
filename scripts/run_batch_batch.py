#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量求解器一键脚本（从仓库根目录运行或在脚本所在目录运行均可）。
- 目的：python run_batch_batch.py 即按脚本内集中超参运行，不必再传命令行参数。
- 支持：遍历 candidate_rules_* 并对同一题目集分别求解，分别输出 results.json。
"""
from __future__ import annotations

import os
import sys
import re
import glob
from typing import Optional

# 计算仓库相关路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, ".."))                 # .../Newclid
SRC_DIR = os.path.normpath(os.path.join(REPO_DIR, "src"))                   # .../Newclid/src
OUTPUTS_DIR = os.path.join(REPO_DIR, "datasets", "c10s50k")

# 确保可以 import newclid.*
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from newclid.solver_utils import solve_problems_batch  # type: ignore

# candidate_rules 目录（你刚刚生成的那批文件）
CANDIDATE_RULES_DIR = os.path.join(
    REPO_DIR, "src", "newclid", "default_configs", "candidate_rules_c10s50k"
)
CANDIDATE_RULES_GLOB = os.path.join(CANDIDATE_RULES_DIR, "rules_*.txt")

# 集中超参（每项均附注释说明用途）
CONFIG = {
    "problems_file": os.path.join(REPO_DIR, "benchmarks", "hageo_224.txt"),
    "max_attempts": 100,               # 构建状态的最大尝试次数
    "timeout": 120,                    # 单题求解超时时间（秒）
    "limit": None,                     # 仅求解前 N 题；None 表示不限制
    "workers": 50,                     # 并行工作数；1 为串行，大于 1 则启用并行
    "backend": "process",              # 并行后端："process"（推荐）或 "thread"
}


def _write_results_json(out_json: str, stats: dict) -> str:
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        import json
        json.dump(stats, f, ensure_ascii=False, indent=2)
    return out_json


def _print_summary(stats: dict) -> None:
    total = int(stats.get("total", 0) or 0)
    solved = int(stats.get("solved", 0) or 0)
    rate = float(stats.get("solve_rate", 0.0) or 0.0)
    results = stats.get("results", []) or []
    fails = []
    for r in results:
        try:
            if not r.get("success"):
                fails.append((r.get("problem_id"), r.get("error")))
        except Exception:
            continue
    print("\n=== Solve Summary ===")
    print(f"Solved: {solved}/{total} ({rate:.2%})")
    print(f"Failed: {len(fails)}")
    if fails:
        print("Examples of failures (up to 10):")
        for pid, err in fails[:10]:
            if err:
                print(f"- {pid}: {err}")
            else:
                print(f"- {pid}")


def _extract_candidate_id(path: str) -> str:
    """
    从 .../candidate_rules_001.txt 提取 '001'
    若提取失败，fallback 为文件名去掉扩展名。
    """
    name = os.path.basename(path)
    m = re.match(r"rules_(\d+)\.txt$", name)
    if m:
        return m.group(1)
    return os.path.splitext(name)[0]


def _solve_with_rules(src_problems: str, rules_file: str, out_json: str) -> None:
    print("\n==============================")
    print("[run-batch] problems_file      =", src_problems)
    print("[run-batch] rules_file         =", rules_file)
    print("[run-batch] outputs_file(json) =", out_json)
    print("[run-batch] workers/backend/max_attempts/timeout/limit =",
          CONFIG["workers"], CONFIG["backend"], CONFIG["max_attempts"], CONFIG["timeout"], CONFIG["limit"])

    stats = solve_problems_batch(
        problems_file=src_problems,
        rules_file=rules_file,
        max_attempts=int(CONFIG["max_attempts"]),
        timeout_sec=int(CONFIG["timeout"]),
        limit=CONFIG["limit"],
        workers=int(CONFIG["workers"]) if CONFIG.get("workers") else 1,
        backend=str(CONFIG["backend"]) if CONFIG.get("backend") else "process",
    )
    _write_results_json(out_json, stats)
    print("[run-batch] wrote results:", out_json)
    _print_summary(stats)


def main(_: Optional[list[str]] = None) -> None:
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    src_problems = os.path.abspath(CONFIG["problems_file"])

    # 枚举 candidates（按文件名排序，保证 id 顺序稳定）
    candidate_rules_files = sorted(glob.glob(CANDIDATE_RULES_GLOB))
    if not candidate_rules_files:
        raise FileNotFoundError(
            f"未找到 candidate rules：{CANDIDATE_RULES_GLOB}\n"
            f"请先生成到目录：{CANDIDATE_RULES_DIR}"
        )

    print("[run-batch] candidate_rules_dir =", CANDIDATE_RULES_DIR)
    print("[run-batch] candidates_count    =", len(candidate_rules_files))

    # 逐个 candidate 跑同一题目集
    for rules_path in candidate_rules_files:
        cid = _extract_candidate_id(rules_path)
        if int(cid) <= 121:
            continue
        out_json = os.path.join(OUTPUTS_DIR, f"hageo_candidate_rules_{cid}_results.json")
        _solve_with_rules(src_problems=src_problems, rules_file=rules_path, out_json=out_json)


if __name__ == "__main__":
    main()