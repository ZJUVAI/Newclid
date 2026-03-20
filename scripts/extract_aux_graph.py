#!/usr/bin/env python3
"""
Extract and render problems with non-empty aux_points from a results JSON.

Usage:
    python scripts/extract_aux_graph.py <input_json> [output_dir] [max_workers]

Behavior:
    - Produces a sibling file with suffix "_aux.json" containing only results with aux_points.
    - Renders proof graphs from the filtered JSON per problem via SingleProofGraph, optionally in parallel.
"""
from __future__ import annotations

import os
import sys
import json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any, Dict, Tuple

# Defaults (overridable by CLI)
INPUT_JSON = "outputs/r07_problems.results.json"
# INPUT_JSON = "outputs/r07_problems.results.json"
OUTPUT_DIR = "outputs/proof_graphs"
LABEL_MODE = "legend"  # legend | full | short (legend maps to short)
OVERWRITE = True
PROGRESS_EVERY = 10
MAX_WORKERS = 10  # 0/1 => sequential; >1 => ProcessPool parallel

# Add src to sys.path for local runs
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from newclid.proof_scout.core.aux_extractor import AuxExtractor  # noqa: E402
from newclid.proof_scout.core.single_proof_graph import SingleProofGraph  # noqa: E402
from newclid.proof_scout.core.proof_graph_visualizer import ProofGraphVisualizer  # noqa: E402


def _map_label_mode(mode: str) -> str:
    if mode == "legend":
        return "short"
    if mode in {"short", "full"}:
        return mode
    return "short"


def _worker_render_one(rec: Dict[str, Any], out_png: str, label_mode: str) -> Tuple[str, str]:
    try:
        pid_val = rec.get("problem_id")
        if pid_val is None:
            return ("<none>", "skipped")
        pid = str(pid_val)
        if os.path.exists(out_png) and not OVERWRITE:
            return (pid, "skipped")
        spg = SingleProofGraph.build_from_result_record(rec, verbose=False)
        viz = ProofGraphVisualizer()
        viz.render_problem(spg, pid, out_png, label_mode=label_mode)
        return (pid, "ok")
    except Exception:
        return (str(rec.get("problem_id")), "failed")


def main():
    args = sys.argv[1:]
    input_json = args[0] if len(args) >= 1 else INPUT_JSON
    output_dir = args[1] if len(args) >= 2 else OUTPUT_DIR
    mw = MAX_WORKERS
    if len(args) >= 3:
        try:
            mw = int(args[2])
        except Exception:
            mw = MAX_WORKERS

    in_path = Path(input_json)
    if not in_path.exists():
        print(f"[aux] input not found: {in_path}")
        sys.exit(1)

    # Step 1: Filter into *_aux.json next to input
    aux_json = in_path.with_name(in_path.stem + "_aux.json")
    stats = AuxExtractor().filter_results_with_aux(str(in_path), str(aux_json))
    if stats.get("kept", 0) <= 0:
        print("[aux] no items with aux_points; stop after JSON output.")
        return 0

    # Step 2: Render proof graphs using ProofGraphVisualizer
    base_name = aux_json.stem
    out_dir = Path(output_dir) / base_name
    out_dir.mkdir(parents=True, exist_ok=True)

    mapped_label_mode = _map_label_mode(LABEL_MODE)
    if LABEL_MODE == "legend" and mapped_label_mode != LABEL_MODE:
        print("[aux] label_mode 'legend' 不再支持，已映射为 'short'。")

    # 读取过滤后的 JSON（作为对象以便遍历 results）
    with open(aux_json, "r", encoding="utf-8") as f:
        aux_obj = json.load(f)
    results = aux_obj.get("results", []) or []
    # 单题模式：逐题构建 SingleProofGraph 并渲染（可并行）
    pids = [str(r.get("problem_id")) for r in results if isinstance(r, dict) and r.get("problem_id") is not None]
    total = len(pids)
    done = skipped = failed = 0
    print(f"[aux] rendering to: {out_dir}  (total={total})")

    if mw and mw > 1:
        print(f"[aux] parallel rendering with max_workers={mw}")
        with ProcessPoolExecutor(max_workers=mw) as ex:
            futs = []
            for rec in results:
                if not isinstance(rec, dict) or rec.get("problem_id") is None:
                    continue
                pid = str(rec["problem_id"])
                out_png = str(out_dir / f"proof_{pid}.png")
                futs.append(ex.submit(_worker_render_one, rec, out_png, mapped_label_mode))
            for idx, fut in enumerate(as_completed(futs), start=1):
                pid, st = fut.result()
                if st == "ok":
                    done += 1
                elif st == "skipped":
                    skipped += 1
                else:
                    failed += 1
                if PROGRESS_EVERY and (idx % PROGRESS_EVERY == 0):
                    print(f"[aux] {idx}/{total} done={done} skipped={skipped} failed={failed}")
    else:
        print("[aux] sequential rendering")
        idx = 0
        for rec in results:
            if not isinstance(rec, dict) or rec.get("problem_id") is None:
                continue
            pid = str(rec["problem_id"])
            out_png = str(out_dir / f"proof_{pid}.png")
            pid_ret, st = _worker_render_one(rec, out_png, mapped_label_mode)
            if st == "ok":
                done += 1
            elif st == "skipped":
                skipped += 1
            else:
                failed += 1
            idx += 1
            if PROGRESS_EVERY and (idx % PROGRESS_EVERY == 0):
                print(f"[aux] {idx}/{total} done={done} skipped={skipped} failed={failed}")

    print("-" * 30)
    print(f"Input total: {total}")
    print(f"Generated successfully: {done}, Skipped: {skipped}, Failed: {failed}")
    print(f"Output directory: {out_dir}")
    print(f"JSON saved: {aux_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
