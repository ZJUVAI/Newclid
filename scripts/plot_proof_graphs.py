#!/usr/bin/env python3
"""
Plot all proofs (per problem) from a results JSON into PNGs using SingleProofGraph.

Usage:
    python scripts/plot_proof_graphs.py <input_json> [output_dir] [max_workers]

If arguments are omitted, the script uses the constants defined below.
"""
import os
import sys
import json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any, Dict, Tuple

# Defaults (will be overridden by CLI args if provided)
INPUT_JSON = "outputs/r07_expanded_problems_lil.results.json"  # change as needed
OUTPUT_DIR = "outputs/proof_graphs"
LABEL_MODE = "legend"  # legend | full | short
# Whether to overwrite existing PNGs
OVERWRITE = True
# Print a progress line every N items (0 to disable periodic logs)
PROGRESS_EVERY = 10
MAX_WORKERS = 0  # 0 or 1 => disable parallel; >1 enables ProcessPool

# Add src to sys.path for local runs
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from newclid.data_discovery.proof_graph_visualizer import ProofGraphVisualizer  # noqa: E402
from newclid.data_discovery.single_proof_graph import SingleProofGraph  # noqa: E402
import inspect  # noqa: E402


def _short_label(raw: str) -> str:
    try:
        if "(" in raw and raw.endswith(")"):
            return raw.split("(", 1)[0].strip()
        return raw.split()[0]
    except Exception:
        return raw


def _fact_points_from_node(nd: dict) -> list:
    """Extract point names from a fact-node dict (newclid ProofGraph node schema)."""
    if not isinstance(nd, dict):
        return []
    args = list(nd.get("args", []) or [])
    pred = str(nd.get("label", ""))
    # handle aconst/rconst: drop trailing constant arg
    if pred in {"aconst", "rconst"} and len(args) >= 1:
        return [a for a in args[:-1]]
    return args


def _map_label_mode_for_visualizer(mode: str) -> str:
    """Map 'legend' to 'short' if visualizer expects that; keep short/full unchanged."""
    return mode if mode in {"legend", "short", "full"} else "short"


def _worker_render_one(rec: Dict[str, Any], out_png: str, label_mode: str) -> Tuple[str, str]:
    """Worker: build SingleProofGraph for one record and render to PNG.

    Returns (pid, status) with status in {"ok", "skipped", "failed"}.
    """
    try:
        pid_val = rec.get("problem_id")
        if pid_val is None:
            return ("<none>", "skipped")
        pid = str(pid_val)
        # Skip if already exists and not overwrite
        if os.path.exists(out_png) and not OVERWRITE:
            return (pid, "skipped")
        spg = SingleProofGraph.build_from_result_record(rec, verbose=False)
        viz = ProofGraphVisualizer()
        viz.render_problem(spg, pid, out_png, label_mode=_map_label_mode_for_visualizer(label_mode))
        return (pid, "ok")
    except Exception:
        return (str(rec.get("problem_id")), "failed")


def main():
    args = sys.argv[1:]
    input_json = None
    output_dir = None
    if len(args) >= 1:
        input_json = args[0]
    if len(args) >= 2:
        output_dir = args[1]
    if len(args) >= 3:
        try:
            mw = int(args[2])
        except Exception:
            mw = MAX_WORKERS
    else:
        mw = MAX_WORKERS

    input_json = input_json or INPUT_JSON
    output_dir = output_dir or OUTPUT_DIR

    in_path = Path(input_json)
    if not in_path.exists():
        print(f"[plot] input not found: {in_path}")
        sys.exit(1)

    # Compose output under outputs/proof_graphs/<json_basename>
    base_name = in_path.stem
    out_dir = Path(output_dir) / base_name
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[plot] reading results from: {in_path}")
    try:
        with open(in_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            results = data.get("results", []) or []
        elif isinstance(data, list):
            results = data
        else:
            results = []
    except Exception as e:
        print(f"[plot] failed to read input json: {e}")
        sys.exit(1)

    print(f"[plot] rendering to: {out_dir}")
    mapped_label_mode = _map_label_mode_for_visualizer(LABEL_MODE)

    total = sum(1 for r in results if isinstance(r, dict) and r.get("problem_id") is not None)
    done = skipped = failed = 0

    # Parallel or sequential execution
    def submit_all(executor=None):
        tasks = []
        for rec in results:
            if not isinstance(rec, dict) or rec.get("problem_id") is None:
                continue
            pid = str(rec["problem_id"])
            out_png = str(out_dir / f"proof_{pid}.png")
            if executor is None:
                pid_ret, st = _worker_render_one(rec, out_png, mapped_label_mode)
                yield (pid_ret, st)
            else:
                fut = executor.submit(_worker_render_one, rec, out_png, mapped_label_mode)
                tasks.append(fut)
        if executor is not None:
            for fut in as_completed(tasks):
                yield fut.result()

    if mw and mw > 1:
        print(f"[plot] parallel rendering with max_workers={mw}")
        with ProcessPoolExecutor(max_workers=mw) as ex:
            for idx, (pid, st) in enumerate(submit_all(ex), start=1):
                if st == "ok":
                    done += 1
                elif st == "skipped":
                    skipped += 1
                else:
                    failed += 1
                if PROGRESS_EVERY and (idx % PROGRESS_EVERY == 0):
                    print(f"[plot] {idx}/{total} done={done} skipped={skipped} failed={failed}")
    else:
        print("[plot] sequential rendering")
        for idx, (pid, st) in enumerate(submit_all(None), start=1):
            if st == "ok":
                done += 1
            elif st == "skipped":
                skipped += 1
            else:
                failed += 1
            if PROGRESS_EVERY and (idx % PROGRESS_EVERY == 0):
                print(f"[plot] {idx}/{total} done=={done} skipped={skipped} failed={failed}")

    print("-" * 30)
    print(f"Input total: {total}")
    print(f"Generated successfully: {done}, Skipped: {skipped}, Failed: {failed}")
    print(f"Output directory: {out_dir}")


if __name__ == "__main__":
    main()
