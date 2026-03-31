#!/usr/bin/env python3
"""Render extracted-rule figures in parallel with a simple three-panel layout."""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import matplotlib

matplotlib.use("Agg")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fig_rule_extraction import (
    build_full_graph_from_record,
    build_pruned_render_from_record,
    create_three_panel_figure_from_data,
)


def count_premises(rule_text: str) -> int:
    left, _, _ = rule_text.partition("=>")
    parts = [part.strip() for part in left.split(",") if part.strip()]
    return len(parts)


def parse_args() -> argparse.Namespace:
    default_exp = PROJECT_ROOT / "outputs/experiments/20260309_10k_rule_extraction_no_eqpoint_constline"
    default_render_exp = PROJECT_ROOT / "outputs/experiments/20260309_10k_rule_render_parallel_general"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-jsonl",
        type=Path,
        default=PROJECT_ROOT / "outputs/datasets/synthetic_10k_aux_only/geometry_clauses15_samples10k.jsonl",
    )
    parser.add_argument(
        "--pruned-json",
        type=Path,
        default=PROJECT_ROOT / "outputs/experiments/20260309_10k_rule_extraction_no_eqpoint_constline/geometry_clauses15_samples10k_pruned.json",
    )
    parser.add_argument(
        "--rules-stats",
        type=Path,
        default=default_exp / "intermediates/step1e_rules_stats.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_render_exp / "geometry_clauses15_samples10k_aux_combo",
    )
    parser.add_argument("--workers", type=int, default=30)
    parser.add_argument("--progress-every", type=int, default=50)
    parser.add_argument("--dpi", type=int, default=250)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def load_rule_entries(path: Path) -> List[dict]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    entries = data.get("entries", [])
    if not entries:
        raise ValueError(f"No rule entries found in {path}")
    return entries


def load_pruned_map(path: Path, allowed_pids: Iterable[str]) -> Dict[str, dict]:
    if not path.exists():
        return {}
    allow = set(allowed_pids)
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    pruned_map: Dict[str, dict] = {}
    for rec in data.get("results", []):
        pid = str(rec.get("problem_id", ""))
        if pid in allow and isinstance(rec.get("rendered"), dict):
            pruned_map[pid] = rec["rendered"]
    return pruned_map


def load_source_records(path: Path, allowed_pids: Iterable[str]) -> Dict[str, dict]:
    allow = {str(pid) for pid in allowed_pids}
    target_by_idx = {int(pid.split(":")[1]): pid for pid in allow}
    records: Dict[str, dict] = {}

    with open(path, "r", encoding="utf-8") as fh:
        for idx, line in enumerate(fh):
            pid = target_by_idx.get(idx)
            if pid is None:
                continue
            records[pid] = json.loads(line)
            if len(records) == len(target_by_idx):
                break
    return records


def render_one(task: Tuple[str, str, str, dict, dict | None, str, int]) -> Tuple[str, str, str]:
    rid, pid, rule_text, rec, pruned_rendered, out_png, dpi = task
    try:
        import matplotlib.pyplot as plt

        full_raw = build_full_graph_from_record(pid, rec)
        if pruned_rendered is None:
            pruned_rendered = build_pruned_render_from_record(pid, rec, rule_text=rule_text)
        fig = create_three_panel_figure_from_data(
            full_raw,
            pruned_rendered,
            rule_text,
            show_arrows=False,
            figsize=(16, 7),
            node_size=320,
            pid_text=f"pid: {pid}",
            verbose=False,
        )
        Path(out_png).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_png, format="png", bbox_inches="tight", dpi=dpi)
        plt.close(fig)
        return rid, "ok", ""
    except Exception as exc:
        return rid, "failed", str(exc)


def main() -> int:
    args = parse_args()
    entries = load_rule_entries(args.rules_stats)
    if args.limit and args.limit > 0:
        entries = entries[:args.limit]
    pids = [str(entry.get("pid", "")) for entry in entries]

    pruned_map = load_pruned_map(args.pruned_json, pids)
    source_records = load_source_records(args.input_jsonl, pids)

    args.output_dir.mkdir(parents=True, exist_ok=True)

    rid_map_path = args.output_dir / "rid_map.txt"
    with open(rid_map_path, "w", encoding="utf-8") as fh:
        for entry in entries:
            rule = str(entry.get("rule"))
            premise_count = count_premises(rule)
            file_name = f"{entry.get('rid')}_prem{premise_count}.png"
            fh.write(
                f"file={file_name} rid={entry.get('rid')} pid={entry.get('pid')} premises={premise_count} rule={rule}\n"
            )

    skipped: List[Tuple[str, str]] = []
    tasks: List[Tuple[str, str, str, dict, dict | None, str, int]] = []
    for entry in entries:
        rid = str(entry.get("rid", ""))
        pid = str(entry.get("pid", ""))
        rule_text = str(entry.get("rule", ""))
        premise_count = count_premises(rule_text)
        out_png = args.output_dir / f"{rid}_prem{premise_count}.png"
        if out_png.exists() and not args.overwrite:
            skipped.append((rid, "exists_overwrite_false"))
            continue
        if pid not in source_records:
            skipped.append((rid, "missing_source_record"))
            continue
        tasks.append((
            rid,
            pid,
            rule_text,
            source_records[pid],
            pruned_map.get(pid),
            str(out_png),
            args.dpi,
        ))

    done = failed = 0
    failures: List[Tuple[str, str]] = []

    if args.workers > 1:
        print(f"[render] parallel rendering with workers={args.workers} tasks={len(tasks)}")
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(render_one, task) for task in tasks]
            for idx, fut in enumerate(as_completed(futs), start=1):
                rid, status, detail = fut.result()
                if status == "ok":
                    done += 1
                else:
                    failed += 1
                    failures.append((rid, detail))
                if args.progress_every and idx % args.progress_every == 0:
                    print(f"[render] {idx}/{len(tasks)} done={done} failed={failed} skipped={len(skipped)}")
    else:
        print(f"[render] sequential rendering tasks={len(tasks)}")
        for idx, task in enumerate(tasks, start=1):
            rid, status, detail = render_one(task)
            if status == "ok":
                done += 1
            else:
                failed += 1
                failures.append((rid, detail))
            if args.progress_every and idx % args.progress_every == 0:
                print(f"[render] {idx}/{len(tasks)} done={done} failed={failed} skipped={len(skipped)}")

    if skipped:
        with open(args.output_dir / "rid_render_skipped.txt", "w", encoding="utf-8") as fh:
            for rid, reason in skipped:
                fh.write(f"rid={rid}\treason={reason}\n")

    if failures:
        with open(args.output_dir / "rid_render_failed.txt", "w", encoding="utf-8") as fh:
            for rid, reason in failures:
                fh.write(f"rid={rid}\treason={reason}\n")

    total_pngs = len(list(args.output_dir.glob("*.png")))

    summary = {
        "input_entries": len(entries),
        "scheduled": len(tasks),
        "rendered": done,
        "skipped": len(skipped),
        "failed": failed,
        "total_pngs_in_output_dir": total_pngs,
        "workers": args.workers,
        "limit": args.limit,
        "input_jsonl": str(args.input_jsonl),
        "pruned_json": str(args.pruned_json),
        "rules_stats": str(args.rules_stats),
        "output_dir": str(args.output_dir),
    }
    with open(args.output_dir / "render_summary.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)

    print("=" * 60)
    print("RENDER SUMMARY")
    print("=" * 60)
    print(f"Input entries: {len(entries)}")
    print(f"Scheduled:     {len(tasks)}")
    print(f"Rendered:      {done}")
    print(f"Skipped:       {len(skipped)}")
    print(f"Failed:        {failed}")
    print(f"Total PNGs:     {total_pngs}")
    print(f"Output dir:    {args.output_dir}")
    return 0 if failed == 0 and total_pngs == len(entries) else 1


if __name__ == "__main__":
    raise SystemExit(main())