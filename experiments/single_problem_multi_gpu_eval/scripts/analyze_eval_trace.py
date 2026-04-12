from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def quantile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int((len(ordered) - 1) * p)
    return float(ordered[index])


def summarize_latency(values: list[float]) -> dict[str, float]:
    if not values:
        return {"count": 0, "mean_s": 0.0, "p50_s": 0.0, "p90_s": 0.0, "p99_s": 0.0, "max_s": 0.0}
    ordered = sorted(float(v) for v in values)
    return {
        "count": len(ordered),
        "mean_s": float(mean(ordered)),
        "p50_s": quantile(ordered, 0.5),
        "p90_s": quantile(ordered, 0.9),
        "p99_s": quantile(ordered, 0.99),
        "max_s": ordered[-1],
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        with open(path, "w", newline="", encoding="utf-8") as fp:
            fp.write("")
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def load_problem_events(run_dir: Path) -> list[dict[str, Any]]:
    problem_files = sorted((run_dir / "problems").glob("*.jsonl"))
    if not problem_files:
        raise FileNotFoundError(f"No problem event files found under {run_dir / 'problems'}")
    events: list[dict[str, Any]] = []
    for path in problem_files:
        events.extend(load_jsonl(path))
    return events


def load_attempts(run_dir: Path) -> list[dict[str, Any]]:
    attempt_files = sorted((run_dir / "attempts").glob("*.jsonl"))
    attempts: list[dict[str, Any]] = []
    for path in attempt_files:
        attempts.extend(load_jsonl(path))
    return attempts


def build_scheduler_occupancy_rows(problem_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scheduler_events = sorted(
        (event for event in problem_events if event.get("event") == "scheduler_state"),
        key=lambda item: float(item.get("elapsed_s", 0.0)),
    )
    if len(scheduler_events) < 2:
        return []
    rows: list[dict[str, Any]] = []
    for index, event in enumerate(scheduler_events[:-1]):
        next_event = scheduler_events[index + 1]
        start_s = float(event["elapsed_s"])
        end_s = float(next_event["elapsed_s"])
        duration_s = max(end_s - start_s, 0.0)
        rows.append(
            {
                "start_s": round(start_s, 6),
                "end_s": round(end_s, 6),
                "duration_s": round(duration_s, 6),
                "depth": int(event.get("depth", -1)),
                "running_prepare": int(event.get("running_prepare", 0)),
                "prepared_requests": int(event.get("prepared_requests", 0)),
                "pending_gpu_requests": int(event.get("pending_gpu_requests", 0)),
                "active_gpu_batches": int(event.get("active_gpu_batches", 0)),
                "idle_gpu_workers": int(event.get("idle_gpu_workers", 0)),
                "pending_ddar_submit": int(event.get("pending_ddar_submit", 0)),
                "running_ddar": int(event.get("running_ddar", 0)),
                "frontier_exhausted": bool(event.get("frontier_exhausted", False)),
            }
        )
    return rows


def build_fallback_occupancy_rows(problem_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    delta_events: list[tuple[float, str, int]] = []
    for event in problem_events:
        name = str(event.get("event"))
        elapsed_s = float(event.get("elapsed_s", 0.0))
        if name == "prepare_request_submitted":
            delta_events.append((elapsed_s, "running_prepare", 1))
        elif name == "prepare_request_ready":
            delta_events.append((elapsed_s, "running_prepare", -1))
        elif name == "gpu_batch_submitted":
            delta_events.append((elapsed_s, "active_gpu_batches", 1))
        elif name == "gpu_batch_done":
            delta_events.append((elapsed_s, "active_gpu_batches", -1))
        elif name == "ddar_submit":
            delta_events.append((elapsed_s, "running_ddar", 1))
        elif name == "ddar_result":
            delta_events.append((elapsed_s, "running_ddar", -1))
    if len(delta_events) < 2:
        return []
    delta_events.sort()
    counts = {
        "running_prepare": 0,
        "prepared_requests": 0,
        "pending_gpu_requests": 0,
        "active_gpu_batches": 0,
        "idle_gpu_workers": 0,
        "pending_ddar_submit": 0,
        "running_ddar": 0,
    }
    rows: list[dict[str, Any]] = []
    last_t = delta_events[0][0]
    for elapsed_s, field, delta in delta_events:
        duration_s = max(elapsed_s - last_t, 0.0)
        if duration_s > 0:
            rows.append(
                {
                    "start_s": round(last_t, 6),
                    "end_s": round(elapsed_s, 6),
                    "duration_s": round(duration_s, 6),
                    "depth": -1,
                    "frontier_exhausted": False,
                    **counts,
                }
            )
        counts[field] = max(counts[field] + delta, 0)
        last_t = elapsed_s
    return rows


def summarize_occupancy(rows: list[dict[str, Any]]) -> dict[str, float]:
    total_duration_s = sum(float(row["duration_s"]) for row in rows)
    if total_duration_s <= 0:
        return {
            "occupancy_window_s": 0.0,
            "avg_prepare_inflight": 0.0,
            "avg_prepared_requests": 0.0,
            "avg_pending_gpu_requests": 0.0,
            "avg_gpu_batches_inflight": 0.0,
            "avg_idle_gpu_workers": 0.0,
            "avg_pending_ddar_submit": 0.0,
            "avg_ddar_inflight": 0.0,
            "peak_prepare_inflight": 0,
            "peak_gpu_batches_inflight": 0,
            "peak_ddar_inflight": 0,
            "prepare_idle_fraction": 0.0,
            "gpu_idle_fraction": 0.0,
            "ddar_idle_fraction": 0.0,
            "ddar_backlog_high_fraction": 0.0,
        }

    def weighted_average(field: str) -> float:
        return sum(float(row[field]) * float(row["duration_s"]) for row in rows) / total_duration_s

    def idle_fraction(field: str) -> float:
        idle_time = sum(float(row["duration_s"]) for row in rows if int(row[field]) == 0)
        return idle_time / total_duration_s

    peak_pending_ddar_submit = max(int(row["pending_ddar_submit"]) for row in rows)
    high_threshold = max(1, peak_pending_ddar_submit // 2) if peak_pending_ddar_submit else 0
    high_backlog_time = sum(
        float(row["duration_s"]) for row in rows if int(row["pending_ddar_submit"]) >= high_threshold and high_threshold > 0
    )
    return {
        "occupancy_window_s": total_duration_s,
        "avg_prepare_inflight": weighted_average("running_prepare"),
        "avg_prepared_requests": weighted_average("prepared_requests"),
        "avg_pending_gpu_requests": weighted_average("pending_gpu_requests"),
        "avg_gpu_batches_inflight": weighted_average("active_gpu_batches"),
        "avg_idle_gpu_workers": weighted_average("idle_gpu_workers"),
        "avg_pending_ddar_submit": weighted_average("pending_ddar_submit"),
        "avg_ddar_inflight": weighted_average("running_ddar"),
        "peak_prepare_inflight": max(int(row["running_prepare"]) for row in rows),
        "peak_gpu_batches_inflight": max(int(row["active_gpu_batches"]) for row in rows),
        "peak_ddar_inflight": max(int(row["running_ddar"]) for row in rows),
        "prepare_idle_fraction": idle_fraction("running_prepare"),
        "gpu_idle_fraction": idle_fraction("active_gpu_batches"),
        "ddar_idle_fraction": idle_fraction("running_ddar"),
        "ddar_backlog_high_fraction": high_backlog_time / total_duration_s if high_threshold > 0 else 0.0,
    }


def summarize_candidate_metrics(
    *,
    problem_events: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
) -> dict[str, float]:
    request_profiles: dict[str, dict[str, float]] = {}
    gpu_generate_time_s = 0.0
    for event in problem_events:
        if event.get("event") != "gpu_batch_done":
            continue
        worker_batch_profile = dict(event.get("worker_batch_profile") or {})
        gpu_generate_time_s += float(worker_batch_profile.get("generate_time_s", 0.0))

    parse_success_count = 0
    build_success_count = 0
    for attempt in attempts:
        if attempt.get("attempt_type") != "candidate":
            continue
        request_id = attempt.get("request_id")
        if request_id is not None and request_id not in request_profiles:
            request_profiles[str(request_id)] = {
                "prompt_token_count": float(attempt.get("prompt_token_count") or 0.0),
                "generated_token_count_sum": float(attempt.get("generated_token_count_sum") or 0.0),
                "generated_sequence_count": float(attempt.get("generated_sequence_count") or 0.0),
                "raw_candidate_count": float(attempt.get("raw_candidate_count") or 0.0),
                "unique_candidate_count": float(attempt.get("unique_candidate_count") or 0.0),
                "duplicate_candidate_count": float(attempt.get("duplicate_candidate_count") or 0.0),
                "first_token_latency_s": float(attempt.get("first_token_latency_s") or 0.0),
                "first_token_latency_observed": 1.0 if attempt.get("first_token_latency_s") is not None else 0.0,
            }
        decision = str(attempt.get("decision"))
        if decision != "parse_failed":
            parse_success_count += 1
        if decision not in {"parse_failed", "build_failed"}:
            build_success_count += 1

    request_count = float(len(request_profiles))
    prompt_token_count_sum = sum(item["prompt_token_count"] for item in request_profiles.values())
    generated_token_count_sum = sum(item["generated_token_count_sum"] for item in request_profiles.values())
    generated_sequence_count = sum(item["generated_sequence_count"] for item in request_profiles.values())
    raw_candidate_count = sum(item["raw_candidate_count"] for item in request_profiles.values())
    unique_candidate_count = sum(item["unique_candidate_count"] for item in request_profiles.values())
    duplicate_candidate_count = sum(item["duplicate_candidate_count"] for item in request_profiles.values())
    first_token_latency_sum_s = sum(item["first_token_latency_s"] for item in request_profiles.values())
    first_token_latency_count = sum(item["first_token_latency_observed"] for item in request_profiles.values())

    return {
        "request_count": request_count,
        "prompt_token_count_sum": prompt_token_count_sum,
        "generated_token_count_sum": generated_token_count_sum,
        "generated_sequence_count": generated_sequence_count,
        "raw_candidate_count": raw_candidate_count,
        "unique_candidate_count": unique_candidate_count,
        "duplicate_candidate_count": duplicate_candidate_count,
        "parse_success_count": float(parse_success_count),
        "build_success_count": float(build_success_count),
        "avg_prompt_tokens_per_request": prompt_token_count_sum / request_count if request_count else 0.0,
        "avg_generated_tokens_per_request": generated_token_count_sum / request_count if request_count else 0.0,
        "avg_generated_tokens_per_sequence": (
            generated_token_count_sum / generated_sequence_count if generated_sequence_count else 0.0
        ),
        "candidate_unique_ratio": unique_candidate_count / raw_candidate_count if raw_candidate_count else 0.0,
        "candidate_parse_success_rate": unique_candidate_count and (parse_success_count / unique_candidate_count) or 0.0,
        "candidate_build_success_rate": parse_success_count and (build_success_count / parse_success_count) or 0.0,
        "generated_tokens_per_gpu_generate_s": (
            generated_token_count_sum / gpu_generate_time_s if gpu_generate_time_s else 0.0
        ),
        "valid_candidates_per_gpu_generate_s": (
            build_success_count / gpu_generate_time_s if gpu_generate_time_s else 0.0
        ),
        "avg_first_token_latency_s": (
            first_token_latency_sum_s / first_token_latency_count if first_token_latency_count else 0.0
        ),
    }


def analyze_run_dir(run_dir: Path) -> dict[str, Any]:
    problem_events = load_problem_events(run_dir)
    attempts = load_attempts(run_dir)

    prepare_submitted: dict[str, float] = {}
    gpu_submitted: dict[str, float] = {}
    ddar_submitted: dict[str, float] = {}
    prepare_latencies: list[float] = []
    gpu_latencies: list[float] = []
    ddar_latencies: list[float] = []
    event_counts = Counter()
    depth_counts: dict[int, Counter[str]] = defaultdict(Counter)
    depth_windows: dict[int, dict[str, float]] = defaultdict(dict)

    for event in sorted(problem_events, key=lambda item: float(item.get("elapsed_s", 0.0))):
        event_name = str(event.get("event"))
        elapsed_s = float(event.get("elapsed_s", 0.0))
        event_counts[event_name] += 1
        depth = event.get("depth")
        if isinstance(depth, int) and depth >= 0:
            depth_counts[depth][event_name] += 1
        if event_name == "depth_start":
            depth_windows[int(event["depth"])]["start_s"] = elapsed_s
        elif event_name == "depth_end":
            depth_windows[int(event["depth"])]["end_s"] = elapsed_s
        elif event_name == "prepare_request_submitted":
            prepare_submitted[str(event["request_id"])] = elapsed_s
        elif event_name == "prepare_request_ready":
            request_id = str(event["request_id"])
            if request_id in prepare_submitted:
                prepare_latencies.append(elapsed_s - prepare_submitted[request_id])
        elif event_name == "gpu_batch_submitted":
            for request_id in event.get("request_ids", []):
                gpu_submitted[str(request_id)] = elapsed_s
        elif event_name == "gpu_batch_done":
            for request_id in event.get("request_ids", []):
                request_key = str(request_id)
                if request_key in gpu_submitted:
                    gpu_latencies.append(elapsed_s - gpu_submitted[request_key])
        elif event_name == "ddar_submit":
            ddar_submitted[str(event["attempt_key"])] = elapsed_s
        elif event_name == "ddar_result":
            attempt_key = str(event.get("attempt_key"))
            if attempt_key in ddar_submitted:
                ddar_latencies.append(elapsed_s - ddar_submitted[attempt_key])

    occupancy_rows = build_scheduler_occupancy_rows(problem_events)
    if not occupancy_rows:
        occupancy_rows = build_fallback_occupancy_rows(problem_events)
    occupancy_summary = summarize_occupancy(occupancy_rows)

    depth_rows: list[dict[str, Any]] = []
    for depth in sorted(set(depth_counts) | set(depth_windows)):
        window = depth_windows.get(depth, {})
        start_s = float(window.get("start_s", 0.0))
        end_s = window.get("end_s")
        duration_s = None if end_s is None else float(end_s) - start_s
        depth_rows.append(
            {
                "depth": depth,
                "start_s": round(start_s, 6),
                "end_s": "" if end_s is None else round(float(end_s), 6),
                "duration_s": "" if duration_s is None else round(duration_s, 6),
                "prepare_request_submitted": depth_counts[depth]["prepare_request_submitted"],
                "prepare_request_ready": depth_counts[depth]["prepare_request_ready"],
                "gpu_batch_submitted": depth_counts[depth]["gpu_batch_submitted"],
                "gpu_batch_done": depth_counts[depth]["gpu_batch_done"],
                "model_response": depth_counts[depth]["model_response"],
                "ddar_submit": depth_counts[depth]["ddar_submit"],
                "ddar_result": depth_counts[depth]["ddar_result"],
            }
        )

    latency_rows = [
        {"stage": "prepare_submit_to_ready", **summarize_latency(prepare_latencies)},
        {"stage": "gpu_submit_to_done", **summarize_latency(gpu_latencies)},
        {"stage": "ddar_submit_to_result", **summarize_latency(ddar_latencies)},
    ]

    candidate_attempts = [attempt for attempt in attempts if attempt.get("attempt_type") == "candidate"]
    ddar_build_times = [float(item["ddar_build_work_time_s"]) for item in candidate_attempts if item.get("ddar_build_work_time_s") is not None]
    ddar_engine_times = [float(item["ddar_engine_work_time_s"]) for item in candidate_attempts if item.get("ddar_engine_work_time_s") is not None]
    candidate_metrics = summarize_candidate_metrics(problem_events=problem_events, attempts=attempts)

    return {
        "summary": {
            **occupancy_summary,
            "event_counts": dict(event_counts),
            "latency": {
                "prepare_submit_to_ready": summarize_latency(prepare_latencies),
                "gpu_submit_to_done": summarize_latency(gpu_latencies),
                "ddar_submit_to_result": summarize_latency(ddar_latencies),
            },
            "ddar_work": {
                "build": summarize_latency(ddar_build_times),
                "engine": summarize_latency(ddar_engine_times),
            },
            "candidate_metrics": candidate_metrics,
        },
        "occupancy_rows": occupancy_rows,
        "latency_rows": latency_rows,
        "depth_rows": depth_rows,
    }


def build_stdout_summary(summary: dict[str, Any]) -> str:
    lines = [
        f"avg_prepare_inflight={summary['avg_prepare_inflight']:.2f}",
        f"avg_gpu_batches_inflight={summary['avg_gpu_batches_inflight']:.2f}",
        f"avg_ddar_inflight={summary['avg_ddar_inflight']:.2f}",
        f"prepare_idle_fraction={summary['prepare_idle_fraction']:.3f}",
        f"gpu_idle_fraction={summary['gpu_idle_fraction']:.3f}",
        f"ddar_idle_fraction={summary['ddar_idle_fraction']:.3f}",
        f"ddar_build_mean_s={summary['ddar_work']['build']['mean_s']:.4f}",
        f"ddar_engine_mean_s={summary['ddar_work']['engine']['mean_s']:.4f}",
        f"avg_prompt_tokens_per_request={summary['candidate_metrics']['avg_prompt_tokens_per_request']:.2f}",
        f"avg_generated_tokens_per_sequence={summary['candidate_metrics']['avg_generated_tokens_per_sequence']:.2f}",
        f"candidate_unique_ratio={summary['candidate_metrics']['candidate_unique_ratio']:.3f}",
        f"valid_candidates_per_gpu_generate_s={summary['candidate_metrics']['valid_candidates_per_gpu_generate_s']:.4f}",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze multi-GPU eval trace output.")
    parser.add_argument("--run_dir", required=True, help="Trace run directory containing problems/, attempts/, run_meta.json")
    parser.add_argument("--output_dir", help="Directory to write analysis outputs. Defaults to <run_dir>/analysis")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    output_dir = Path(args.output_dir) if args.output_dir else run_dir / "analysis"
    output_dir.mkdir(parents=True, exist_ok=True)

    analysis = analyze_run_dir(run_dir)
    summary_path = output_dir / "summary.json"
    occupancy_path = output_dir / "occupancy.csv"
    latency_path = output_dir / "latency.csv"
    depth_path = output_dir / "depths.csv"

    with open(summary_path, "w", encoding="utf-8") as fp:
        json.dump(analysis["summary"], fp, ensure_ascii=False, indent=2, sort_keys=True)
        fp.write("\n")
    write_csv(occupancy_path, analysis["occupancy_rows"])
    write_csv(latency_path, analysis["latency_rows"])
    write_csv(depth_path, analysis["depth_rows"])
    print(build_stdout_summary(analysis["summary"]))


if __name__ == "__main__":
    main()
