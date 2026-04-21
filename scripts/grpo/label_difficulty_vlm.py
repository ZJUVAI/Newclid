#!/usr/bin/env python3
"""Offline difficulty labeling for GRPO candidate pools (VLM version)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, TextIO

from newclid.training.grpo_rewards import AuxRewardEvaluator
from tqdm import tqdm

logger = logging.getLogger(__name__)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def count_jsonl_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def _row_resume_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("_shard_index"),
        row.get("sample_id"),
        row.get("query"),
        row.get("fl_problem"),
    )


def _validate_resume_prefix(
    reference_rows: list[dict[str, Any]], existing_rows: list[dict[str, Any]]
) -> None:
    if len(existing_rows) > len(reference_rows):
        raise ValueError(
            "Resume output has more rows than the shard input; refusing to continue"
        )
    for idx, (existing, reference) in enumerate(zip(existing_rows, reference_rows)):
        if _row_resume_key(existing) != _row_resume_key(reference):
            raise ValueError(
                f"Resume prefix mismatch at row {idx}: "
                f"existing={_row_resume_key(existing)} "
                f"reference={_row_resume_key(reference)}"
            )


def _load_existing_labeled_rows(
    rows: list[dict[str, Any]], output_path: Path | None, resume: bool
) -> list[dict[str, Any]]:
    if not resume or output_path is None or not output_path.exists():
        return []
    existing_rows = load_jsonl(output_path)
    _validate_resume_prefix(rows, existing_rows)
    return existing_rows


def _write_progress(
    progress_output: Path | None,
    *,
    completed_rows: int,
    total_rows: int,
    completed: bool,
    num_samples: int,
    elapsed_seconds: float,
) -> None:
    if progress_output is None:
        return
    write_json(
        progress_output,
        {
            "completed": completed,
            "completed_rows": completed_rows,
            "elapsed_seconds": elapsed_seconds,
            "num_samples": num_samples,
            "total_rows": total_rows,
        },
    )


def _flush_state(
    labeled_rows: list[dict[str, Any]],
    *,
    output_path: Path | None,
    progress_output: Path | None,
    total_rows: int,
    num_samples: int,
    start_time: float,
    completed: bool,
) -> None:
    if output_path is not None:
        write_jsonl(output_path, labeled_rows)
    _write_progress(
        progress_output,
        completed_rows=len(labeled_rows),
        total_rows=total_rows,
        completed=completed,
        num_samples=num_samples,
        elapsed_seconds=time.perf_counter() - start_time,
    )


def _default_work_dir(output: Path) -> Path:
    return output.parent / f"{output.stem}_workdir"


def _shard_dir(work_dir: Path, shard_index: int, num_workers: int) -> Path:
    return work_dir / f"shard_{shard_index:02d}_of_{num_workers:02d}"


def _open_worker_log(path: Path) -> TextIO:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.open("a", encoding="utf-8")


class VLMCompletionGenerator:
    """VLM-compatible completion generator using SWIFT inference."""

    def __init__(
        self,
        model_path: str,
        model_type: str = "qwen3_vl",
        max_new_tokens: int = 160,
        max_batch_size: int = 16,
        attn_implementation: str | None = "flash_attention_2",
        torch_dtype: str | None = "bfloat16",
    ) -> None:
        from swift.infer_engine import InferRequest, RequestConfig, TransformersEngine

        engine_kwargs = {
            "model": model_path,
            "model_type": model_type,
            "max_batch_size": max_batch_size,
        }
        if attn_implementation is not None:
            engine_kwargs["attn_implementation"] = attn_implementation
        if torch_dtype is not None:
            engine_kwargs["torch_dtype"] = torch_dtype

        self.engine = TransformersEngine(**engine_kwargs)
        self.max_new_tokens = max_new_tokens
        self._InferRequest = InferRequest
        self._RequestConfig = RequestConfig

    def _build_messages(self, query: str) -> list[dict]:
        return [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": query},
        ]

    def generate_batch(
        self,
        queries: list[str],
        num_samples: int,
        temperature: float,
        top_p: float,
    ) -> tuple[list[str], list[list[str]]]:
        """Batch inference: returns (greedy_outputs, sampled_outputs_per_query)."""
        reqs = [self._InferRequest(messages=self._build_messages(q)) for q in queries]

        greedy_cfg = self._RequestConfig(
            temperature=0.0, n=1, max_tokens=self.max_new_tokens
        )
        greedy_results = self.engine.infer(reqs, greedy_cfg, use_tqdm=False)
        greedy_outputs = [
            r.choices[0].message.content if r and r.choices else ""
            for r in greedy_results
        ]

        sample_cfg = self._RequestConfig(
            temperature=temperature,
            top_p=top_p,
            n=num_samples,
            max_tokens=self.max_new_tokens,
        )
        sample_results = self.engine.infer(reqs, sample_cfg, use_tqdm=False)
        sampled_outputs = [
            [c.message.content for c in r.choices] if r and r.choices else []
            for r in sample_results
        ]

        return greedy_outputs, sampled_outputs


def _eval_completion_worker(payload: tuple[str, str]) -> dict[str, Any]:
    completion, fl_problem = payload
    evaluator = AuxRewardEvaluator()
    try:
        result = evaluator.evaluate(completion, fl_problem)
    except Exception:
        logger.exception("Worker evaluation crashed; downgrading completion to engine_error")
        result = evaluator.engine_error_result()
    return {
        "normalized_aux": result.normalized_aux,
        "format_ok": result.format_ok,
        "build_ok": result.build_ok,
        "ddar_status": result.ddar_status,
    }


def aggregate_difficulty_metrics(
    sample: dict[str, Any],
    greedy_completion: str,
    sampled_completions: list[str],
    evaluator: AuxRewardEvaluator,
    *,
    num_samples: int,
    ddar_workers: int = 1,
) -> dict[str, Any]:
    def _safe_evaluate(completion: str):
        try:
            result = evaluator.evaluate(completion, sample["fl_problem"])
        except Exception:
            logger.exception(
                "Difficulty labeling evaluation crashed for sample_id=%s; "
                "downgrading completion to engine_error",
                sample.get("sample_id"),
            )
            result = evaluator.engine_error_result()
        return {
            "normalized_aux": result.normalized_aux,
            "format_ok": result.format_ok,
            "build_ok": result.build_ok,
            "ddar_status": result.ddar_status,
        }

    all_completions = [greedy_completion, *sampled_completions]
    if ddar_workers <= 1:
        all_results = [_safe_evaluate(completion) for completion in all_completions]
    else:
        payloads = [(completion, sample["fl_problem"]) for completion in all_completions]
        with ProcessPoolExecutor(max_workers=ddar_workers) as pool:
            all_results = list(pool.map(_eval_completion_worker, payloads))

    greedy_result = all_results[0]
    sampled_results = all_results[1:]
    pass_key = f"pass_at_{num_samples}"
    valid_key = f"valid_at_{num_samples}"
    fmt_key = f"format_valid_at_{num_samples}"

    ddar_valid_count = sum(1 for result in sampled_results if result["build_ok"])
    ddar_solved_count = sum(
        1 for result in sampled_results if result["ddar_status"] == "solved"
    )
    format_valid_count = sum(1 for result in sampled_results if result["format_ok"])
    normalized_aux_values = [
        result["normalized_aux"] for result in sampled_results if result["normalized_aux"]
    ]
    unique_aux_count = len(set(normalized_aux_values))
    duplicate_aux_ratio = 0.0
    if sampled_results:
        duplicate_aux_ratio = 1.0 - (unique_aux_count / len(sampled_results))

    status_counts = Counter(result["ddar_status"] for result in sampled_results)
    n = len(sampled_results) or 1
    return {
        **sample,
        "greedy_success": greedy_result["ddar_status"] == "solved",
        "greedy_status": greedy_result["ddar_status"],
        "greedy_build_ok": greedy_result["build_ok"],
        "greedy_format_ok": greedy_result["format_ok"],
        pass_key: ddar_solved_count / n,
        valid_key: ddar_valid_count / n,
        fmt_key: format_valid_count / n,
        "ddar_valid_count": ddar_valid_count,
        "ddar_solved_count": ddar_solved_count,
        "format_valid_count": format_valid_count,
        "solved_count": status_counts.get("solved", 0),
        "unsolved_count": status_counts.get("unsolved", 0),
        "build_invalid_count": status_counts.get("build_invalid", 0),
        "format_invalid_count": status_counts.get("format_invalid", 0),
        "engine_error_count": status_counts.get("engine_error", 0),
        "ddar_status_counts": dict(sorted(status_counts.items())),
        "unique_aux_count": unique_aux_count,
        "duplicate_aux_ratio": duplicate_aux_ratio,
        "all_invalid": ddar_valid_count == 0,
    }


def build_summary(
    rows: list[dict[str, Any]], *, num_samples: int, elapsed_seconds: float
) -> dict[str, Any]:
    pass_key = f"pass_at_{num_samples}"
    pass_histogram = Counter()
    greedy_success_count = 0
    all_invalid_count = 0
    status_totals = Counter()
    invalidity_totals = Counter()
    duplicate_aux_ratios = []
    unique_aux_counts = []
    for row in rows:
        pass_histogram[f"{float(row.get(pass_key, 0.0)):.4f}"] += 1
        greedy_success_count += int(bool(row.get("greedy_success")))
        all_invalid_count += int(bool(row.get("all_invalid")))
        status_totals.update(row.get("ddar_status_counts", {}))
        invalidity_totals["build_invalid"] += int(row.get("build_invalid_count", 0))
        invalidity_totals["format_invalid"] += int(row.get("format_invalid_count", 0))
        invalidity_totals["engine_error"] += int(row.get("engine_error_count", 0))
        duplicate_aux_ratios.append(float(row.get("duplicate_aux_ratio", 0.0)))
        unique_aux_counts.append(int(row.get("unique_aux_count", 0)))

    total = len(rows)
    return {
        "total_rows": total,
        "num_samples": num_samples,
        "pass_key": pass_key,
        "elapsed_seconds": elapsed_seconds,
        "greedy_success_count": greedy_success_count,
        "greedy_success_rate": greedy_success_count / total if total else 0.0,
        "all_invalid_count": all_invalid_count,
        "all_invalid_rate": all_invalid_count / total if total else 0.0,
        "pass_histogram": dict(
            sorted(pass_histogram.items(), key=lambda item: float(item[0]))
        ),
        "sampled_status_totals": dict(sorted(status_totals.items())),
        "invalidity_totals": dict(sorted(invalidity_totals.items())),
        "avg_duplicate_aux_ratio": (
            sum(duplicate_aux_ratios) / total if duplicate_aux_ratios else 0.0
        ),
        "avg_unique_aux_count": (
            sum(unique_aux_counts) / total if unique_aux_counts else 0.0
        ),
    }


def label_difficulty(
    rows: list[dict[str, Any]],
    generator: VLMCompletionGenerator,
    evaluator: AuxRewardEvaluator,
    num_samples: int,
    temperature: float,
    top_p: float,
    batch_size: int = 8,
    *,
    output_path: Path | None = None,
    progress_output: Path | None = None,
    resume: bool = False,
    flush_every_batches: int = 1,
    ddar_workers: int = 1,
) -> list[dict[str, Any]]:
    labeled_rows = _load_existing_labeled_rows(rows, output_path, resume)
    start_time = time.perf_counter()
    pass_key = f"pass_at_{num_samples}"
    resume_count = len(labeled_rows)
    if resume_count:
        print(
            f"resuming shard from {resume_count}/{len(rows)} rows using {output_path}"
        )
        _write_progress(
            progress_output,
            completed_rows=resume_count,
            total_rows=len(rows),
            completed=resume_count == len(rows),
            num_samples=num_samples,
            elapsed_seconds=0.0,
        )
        if resume_count == len(rows):
            return labeled_rows

    total_batches = (len(rows) + batch_size - 1) // batch_size
    flushed_batches = 0
    for batch_start in tqdm(
        range(resume_count, len(rows), batch_size),
        total=total_batches,
        initial=resume_count // batch_size,
        desc="Labeling difficulty",
    ):
        batch = rows[batch_start : batch_start + batch_size]
        queries = [r["query"] for r in batch]

        greedy_outputs, sampled_outputs = generator.generate_batch(
            queries, num_samples, temperature, top_p
        )

        for i, row in enumerate(batch):
            labeled_rows.append(
                aggregate_difficulty_metrics(
                    row,
                    greedy_outputs[i],
                    sampled_outputs[i],
                    evaluator,
                    num_samples=num_samples,
                    ddar_workers=ddar_workers,
                )
            )

        idx = batch_start + len(batch)
        elapsed = time.perf_counter() - start_time
        avg_time = elapsed / idx
        eta = avg_time * (len(rows) - idx)
        last = labeled_rows[-1]
        print(
            f"[{idx}/{len(rows)}] greedy={last['greedy_status']} "
            f"pass@{num_samples}={last[pass_key]:.2f} "
            f"elapsed={elapsed:.1f}s eta={eta:.1f}s"
        )
        flushed_batches += 1
        if flush_every_batches > 0 and flushed_batches >= flush_every_batches:
            _flush_state(
                labeled_rows,
                output_path=output_path,
                progress_output=progress_output,
                total_rows=len(rows),
                num_samples=num_samples,
                start_time=start_time,
                completed=False,
            )
            flushed_batches = 0

    _flush_state(
        labeled_rows,
        output_path=output_path,
        progress_output=progress_output,
        total_rows=len(rows),
        num_samples=num_samples,
        start_time=start_time,
        completed=True,
    )
    return labeled_rows


def _shard_rows(
    rows: list[dict[str, Any]], shard_index: int, num_shards: int
) -> list[dict[str, Any]]:
    return [r for i, r in enumerate(rows) if i % num_shards == shard_index]


def _merge_shards(shard_paths: list[Path]) -> list[dict[str, Any]]:
    """Merge shard outputs preserving original order via _shard_index field."""
    all_rows: list[dict[str, Any]] = []
    for p in shard_paths:
        all_rows.extend(load_jsonl(p))
    all_rows.sort(key=lambda r: r.pop("_shard_index"))
    return all_rows


def _read_progress_safe(path: Path) -> dict[str, Any]:
    """Read progress JSON, return empty dict if missing/invalid."""
    try:
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def run_workers(args: argparse.Namespace) -> None:
    """Launch --workers subprocesses, each handling one GPU shard, then merge."""
    num_workers = args.workers
    rows = load_jsonl(args.input)
    started = time.perf_counter()
    work_dir = args.work_dir or _default_work_dir(args.output)
    work_dir.mkdir(parents=True, exist_ok=True)

    # Write per-shard input files
    shard_inputs: list[Path] = []
    shard_outputs: list[Path] = []
    shard_progress: list[Path] = []
    shard_logs: list[Path] = []
    for i in range(num_workers):
        shard_rows = _shard_rows(rows, i, num_workers)
        # Tag each row with its original index for merge ordering
        for j, r in enumerate(shard_rows):
            r["_shard_index"] = i + j * num_workers
        shard_dir = _shard_dir(work_dir, i, num_workers)
        shard_dir.mkdir(parents=True, exist_ok=True)
        input_path = shard_dir / "input.jsonl"
        output_path = shard_dir / "output.jsonl"
        progress_path = shard_dir / "progress.json"
        log_path = shard_dir / "worker.log"
        write_jsonl(input_path, shard_rows)
        shard_inputs.append(input_path)
        shard_outputs.append(output_path)
        shard_progress.append(progress_path)
        shard_logs.append(log_path)

    procs: list[subprocess.Popen] = []
    proc_logs: list[TextIO] = []
    launched_workers: list[int] = []
    for i in range(num_workers):
        shard_total = count_jsonl_rows(shard_inputs[i])
        existing_rows = count_jsonl_rows(shard_outputs[i]) if args.resume else 0
        if shard_total == 0:
            write_jsonl(shard_outputs[i], [])
            _write_progress(
                shard_progress[i],
                completed_rows=0,
                total_rows=0,
                completed=True,
                num_samples=args.num_samples,
                elapsed_seconds=0.0,
            )
            print(f"[worker {i}] skip-empty")
            continue
        if args.resume and shard_total > 0 and existing_rows >= shard_total:
            _write_progress(
                shard_progress[i],
                completed_rows=shard_total,
                total_rows=shard_total,
                completed=True,
                num_samples=args.num_samples,
                elapsed_seconds=0.0,
            )
            print(f"[worker {i}] resume-skip ({existing_rows}/{shard_total} rows)")
            continue
        env = os.environ.copy()
        env["CUDA_VISIBLE_DEVICES"] = str(i)
        cmd = [
            sys.executable,
            __file__,
            str(shard_inputs[i]),
            str(shard_outputs[i]),
            "--model-path",
            args.model_path,
            "--model-type",
            args.model_type,
            "--num-samples",
            str(args.num_samples),
            "--temperature",
            str(args.temperature),
            "--top-p",
            str(args.top_p),
            "--batch-size",
            str(args.batch_size),
            "--max-batch-size",
            str(args.max_batch_size),
            "--attn-implementation",
            args.attn_implementation,
            "--torch-dtype",
            args.torch_dtype,
            "--flush-every-batches",
            str(args.flush_every_batches),
            "--ddar-workers",
            str(args.ddar_workers),
            "--progress-output",
            str(shard_progress[i]),
        ]
        if args.resume:
            cmd.append("--resume")
        log_handle = _open_worker_log(shard_logs[i])
        print(
            f"[worker {i}] CUDA_VISIBLE_DEVICES={i} launching ({shard_total} rows) "
            f"log={shard_logs[i]}"
        )
        proc_logs.append(log_handle)
        launched_workers.append(i)
        procs.append(
            subprocess.Popen(
                cmd,
                env=env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
            )
        )

    total_rows = len(rows)
    pbar = tqdm(total=total_rows, desc="Labeling (all workers)", unit="row")
    done_set: set[int] = set()
    prev_completed = 0
    while len(done_set) < len(launched_workers):
        time.sleep(2)
        completed = sum(
            _read_progress_safe(shard_progress[i]).get("completed_rows", 0)
            for i in range(num_workers)
        )
        pbar.update(completed - prev_completed)
        prev_completed = completed
        for worker_id, p in zip(launched_workers, procs):
            if worker_id in done_set:
                continue
            ret = p.poll()
            if ret is not None:
                if ret != 0:
                    pbar.close()
                    raise RuntimeError(
                        f"Worker {worker_id} exited with code {ret}; inspect {shard_logs[worker_id]}"
                    )
                done_set.add(worker_id)
    pbar.update(total_rows - prev_completed)
    pbar.close()
    for handle in proc_logs:
        handle.close()

    merged = _merge_shards(shard_outputs)
    write_jsonl(args.output, merged)
    if args.summary_output is not None:
        summary = build_summary(
            merged,
            num_samples=args.num_samples,
            elapsed_seconds=time.perf_counter() - started,
        )
        write_json(args.summary_output, summary)
    print(f"wrote {len(merged)} labeled rows to {args.output}")
    if args.cleanup_work_dir:
        for p in shard_inputs + shard_outputs + shard_progress + shard_logs:
            p.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Candidate pool JSONL")
    parser.add_argument("output", type=Path, help="Difficulty labels JSONL")
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=None,
        help="Optional summary JSON path",
    )
    parser.add_argument("--model-path", type=str, required=True)
    parser.add_argument("--model-type", type=str, default="qwen3_vl")
    parser.add_argument(
        "--num-samples", type=int, default=16, help="Sampled completions per prompt"
    )
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--top-p", type=float, default=0.95)
    parser.add_argument(
        "--batch-size", type=int, default=8, help="Rows per inference batch"
    )
    parser.add_argument(
        "--max-batch-size",
        type=int,
        default=128,
        help="TransformersEngine max_batch_size for internal batching",
    )
    parser.add_argument(
        "--attn-implementation",
        type=str,
        default="flash_attention_2",
        help="Attention implementation (flash_attention_2, eager, sdpa, or none to skip)",
    )
    parser.add_argument(
        "--torch-dtype",
        type=str,
        default="bfloat16",
        help="Torch dtype (bfloat16, float16, float32, or none to skip)",
    )
    parser.add_argument(
        "--workers", type=int, default=1, help="Number of GPU workers (one per GPU)"
    )
    parser.add_argument(
        "--ddar-workers",
        type=int,
        default=1,
        help="Processes for parallel DDAR evaluation per row (1=sequential)",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help="Persistent shard/log directory for multi-worker runs",
    )
    parser.add_argument(
        "--progress-output",
        type=Path,
        default=None,
        help="Optional JSON progress path for single-worker shard runs",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from an existing output/progress shard state when possible",
    )
    parser.add_argument(
        "--flush-every-batches",
        type=int,
        default=1,
        help="Write intermediate shard outputs every N batches",
    )
    parser.add_argument(
        "--cleanup-work-dir",
        action="store_true",
        help="Delete shard/log files after a successful multi-worker merge",
    )
    # Internal sharding args used by worker subprocesses
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--num-shards", type=int, default=1)
    args = parser.parse_args()

    if args.workers > 1:
        run_workers(args)
        return

    rows = load_jsonl(args.input)
    if args.num_shards > 1:
        rows = _shard_rows(rows, args.shard_index, args.num_shards)

    attn_impl = args.attn_implementation if args.attn_implementation != "none" else None
    dtype = args.torch_dtype if args.torch_dtype != "none" else None
    generator = VLMCompletionGenerator(
        args.model_path,
        args.model_type,
        max_batch_size=args.max_batch_size,
        attn_implementation=attn_impl,
        torch_dtype=dtype,
    )
    evaluator = AuxRewardEvaluator()
    started = time.perf_counter()
    labeled = label_difficulty(
        rows,
        generator=generator,
        evaluator=evaluator,
        num_samples=args.num_samples,
        temperature=args.temperature,
        top_p=args.top_p,
        batch_size=args.batch_size,
        output_path=args.output,
        progress_output=args.progress_output,
        resume=args.resume,
        flush_every_batches=args.flush_every_batches,
        ddar_workers=args.ddar_workers,
    )
    if args.summary_output is not None:
        summary = build_summary(
            labeled,
            num_samples=args.num_samples,
            elapsed_seconds=time.perf_counter() - started,
        )
        write_json(args.summary_output, summary)
    print(f"wrote {len(labeled)} labeled rows to {args.output}")


if __name__ == "__main__":
    main()
