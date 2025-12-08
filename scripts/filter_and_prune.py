#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一键筛选 + 修剪 + 规则提取（可并行绘图）

用法：
    python scripts/filter_and_prune.py [<input_json>] [<output_dir>] [max_workers]

说明：
    本脚本为薄封装入口，核心逻辑封装在
    newclid.data_discovery.filter_and_prune_engine.FilterAndPruneEngine 中。
"""
from __future__ import annotations

import sys
from pathlib import Path

# ------------------ 默认配置（可通过命令行位置参数覆盖输入/输出根目录） ------------------
INPUT_JSON = "/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/geometry_clauses5_samples20k.jsonl"
OUTPUT_DIR = "/c23474/home/duzhengtong/Discovery-GenesisGeo/datasets/proof_graphs"

# 绘图与运行参数
LABEL_MODE = "legend"
SINGLE_FIGSIZE = (15, 20)
COMBINED_FIGSIZE = (30, 20)
FONT_SIZE = 9
RANKSEP = 2.8
NODESEP = 1.2
OVERWRITE = True
PROGRESS_EVERY = 10
MAX_WORKERS = 50

# ------------------------------------------------------------------------------------
# 追加 sys.path 以便从仓库根目录或脚本目录运行
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from newclid.data_discovery.filter_and_prune_engine import FilterAndPruneEngine  # noqa: E402


def main() -> int:
    args = sys.argv[1:]
    input_json = args[0] if len(args) >= 1 else INPUT_JSON
    output_dir = args[1] if len(args) >= 2 else OUTPUT_DIR
    mw = MAX_WORKERS
    if len(args) >= 3:
        try:
            mw = int(args[2])
        except Exception:
            mw = MAX_WORKERS

    engine = FilterAndPruneEngine(
        label_mode=LABEL_MODE,
        figsize_single=SINGLE_FIGSIZE,
        figsize_combined=COMBINED_FIGSIZE,
        font_size=FONT_SIZE,
        ranksep=RANKSEP,
        nodesep=NODESEP,
        overwrite=OVERWRITE,
        progress_every=PROGRESS_EVERY,
        max_workers=mw,
    )
    try:
        stats = engine.run(input_json, output_dir)
        # 总结输出
        print("-" * 30)
        print(f"Total problems: {stats.get('kept', 0)} kept / {stats.get('total', 0)} total (dropped={stats.get('dropped', 0)})")
        print(f"Combined images: {stats.get('rendered', 0)}, Skipped: {stats.get('skipped', 0)}, Failed: {stats.get('failed', 0)}")
        print(f"Output directory: {stats.get('images_dir', '')}")
        print(f"JSON saved: {stats.get('json', '')}")
        print(f"Rules: {stats.get('rules', 0)} (skipped={stats.get('skipped_rules', 0)})")
        return 0
    except ValueError as exc:
        print(f"[filter+prune] invalid input: {exc}")
        return 1
    except FileNotFoundError as exc:
        print(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
