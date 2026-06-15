from __future__ import annotations

import argparse
import csv
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import logging
import os
from pathlib import Path
import re
import sys
import time
import traceback

import ray

try:
    from rich.live import Live
    from rich.table import Table
except ImportError:
    class Table:  # type: ignore[no-redef]
        def __init__(self):
            self.columns: list[tuple[str, str | None, bool]] = []
            self.rows: list[tuple[str, ...]] = []

        def add_column(self, header: str, justify: str | None = None, no_wrap: bool = False):
            self.columns.append((header, justify, no_wrap))

        def add_row(self, *values: str):
            self.rows.append(tuple(values))

    class Live:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            self.renderable = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def update(self, renderable):
            self.renderable = renderable


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
for path in (str(REPO_ROOT), str(SRC_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from newclid.agent.runtime.model_pool import ModelPool
from newclid.agent.vllm import (
    DEFAULT_VLLM_WORKERS,
    Qwen3Agent,
    Qwen3VLAgent,
    create_vllm_workers,
    discover_served_model,
)
from newclid.api import GeometricSolverBuilder
from newclid.configs import load_solver_config
from newclid.profiling import PROFILE_ROW_FIELDS
from newclid.search_trace import TraceRun, timestamp_slug


LOGLEVEL = os.environ.get("LOGLEVEL", "WARNING").upper()


def parse_bool_arg(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "y", "on"}:
        return True
    if normalized in {"false", "0", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(
        f"Invalid boolean value: {value!r}. Expected true/false."
    )


def sanitize_problem_name(problem_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", problem_name).strip("_") or "problem"


def slugify_served_model_name(served_model_name: str) -> str:
    return Path(served_model_name.rstrip("/")).name or "model"


def build_eval_output_stem(
    *,
    agent_type: str,
    search_version: str,
    problems_path: Path,
    served_model_name: str,
    decoding_size: int,
    beam_size: int,
    search_depth: int,
) -> str:
    search_slug = search_version[1:] if search_version.startswith("v") else search_version
    return (
        f"eval_vllm_{agent_type}_{problems_path.stem}_{slugify_served_model_name(served_model_name)}"
        f"_sv{search_slug}_d{decoding_size}_b{beam_size}_s{search_depth}"
    )


def build_timestamped_output_stem(output_name_stem: str, timestamp: str) -> str:
    return f"{output_name_stem}_{timestamp}"


def configure_logging(*, force: bool = False) -> None:
    logging.basicConfig(
        level=getattr(logging, LOGLEVEL, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=force,
    )


def render_table(all_tasks_info, start_time):
    total_problems = len(all_tasks_info)
    solved_count = sum(status == "Success" for _, status, _ in all_tasks_info)
    processed_count = sum(status != "Pending" for _, status, _ in all_tasks_info)
    table = Table()
    table.add_column(
        f"Problem Names ({solved_count} Solved /{processed_count} Processed /{total_problems} Total)",
        justify="left",
        no_wrap=True,
    )
    table.add_column("Status", justify="center")
    table.add_column(f"Time ({time.time()-start_time:.2f}s)", justify="right")
    priority = {"Failed": 0, "Pending": 1, "Success": 2}
    for problem_name, status, elapsed_time in sorted(
        all_tasks_info, key=lambda item: priority.get(item[1], 99)
    ):
        elapsed = "-" if status == "Pending" else f"{elapsed_time:.2f}"
        table.add_row(problem_name, status, elapsed)
    return table


def create_agent(
    *,
    agent_type: str,
    search_version: str,
    model_pool: ModelPool,
    decoding_size: int,
    beam_size: int,
    search_depth: int,
    max_pending_ddar: int,
    render_root: Path,
    ddar_config: dict[str, bool],
    trace_writer=None,
):
    if agent_type == "qwen3_text":
        return Qwen3Agent(
            model_pool=model_pool,
            decoding_size=decoding_size,
            beam_size=beam_size,
            search_depth=search_depth,
            search_version=search_version,
            max_pending_ddar=max_pending_ddar,
            ddar_config=ddar_config,
            trace_writer=trace_writer,
        )
    if agent_type == "qwen3_vl":
        return Qwen3VLAgent(
            model_pool=model_pool,
            decoding_size=decoding_size,
            beam_size=beam_size,
            search_depth=search_depth,
            search_version=search_version,
            render_root=render_root,
            max_pending_ddar=max_pending_ddar,
            ddar_config=ddar_config,
            trace_writer=trace_writer,
        )
    raise ValueError(f"Unsupported agent type: {agent_type}")


def solve_one_problem(
    *,
    problem_name: str,
    problems_path: Path,
    model_pool: ModelPool,
    agent_type: str,
    search_version: str,
    decoding_size: int,
    beam_size: int,
    search_depth: int,
    timeout: int,
    max_pending_ddar: int,
    render_root: Path,
    ddar_config: dict[str, bool],
    trace_writer=None,
):
    start_perf = time.perf_counter()
    builder = GeometricSolverBuilder().load_problem_from_file(
        problems_path, problem_name, rename=True
    )
    agent = create_agent(
        agent_type=agent_type,
        search_version=search_version,
        model_pool=model_pool,
        decoding_size=decoding_size,
        beam_size=beam_size,
        search_depth=search_depth,
        max_pending_ddar=max_pending_ddar,
        render_root=render_root,
        ddar_config=ddar_config,
        trace_writer=trace_writer,
    )
    solver = builder.with_deductive_agent(agent).build()
    solved = solver.run(timeout=timeout)
    return (
        problem_name,
        solved,
        time.perf_counter() - start_perf,
        solver.run_infos,
    )


def solve_problems_vllm(
    *,
    filepath: Path,
    vllm_base_url: str,
    agent_type: str,
    decoding_size: int,
    beam_size: int,
    search_depth: int,
    search_version: str,
    ray_num_cpus: int | None,
    timeout: int,
    log_dir: str | None,
    enable_trace: bool,
    using_exp: bool = True,
):
    if not filepath.exists():
        raise FileNotFoundError(f"File {filepath} not found.")

    lines = filepath.read_text(encoding="utf-8").splitlines()
    problem_names = [lines[index].strip() for index in range(0, len(lines), 2) if lines[index].strip()]
    ddar_config = load_solver_config(using_exp=using_exp)

    served_model_name, server_models = discover_served_model(vllm_base_url)
    try:
        if not ray.is_initialized():
            ray.init(
                num_cpus=ray_num_cpus,
                include_dashboard=False,
                ignore_reinit_error=True,
            )

        cluster_cpus = int(ray.cluster_resources().get("CPU", 1))
        max_pending_ddar = max(1, 2 * cluster_cpus)
        workers = create_vllm_workers(
            base_url=vllm_base_url,
            served_model_name=served_model_name,
            worker_count=min(DEFAULT_VLLM_WORKERS, max(1, cluster_cpus)),
        )
        model_pool = ModelPool(workers)
        warmup_infos = model_pool.warmup()

        output_dir = Path(log_dir) if log_dir else Path("results")
        output_dir.mkdir(parents=True, exist_ok=True)
        render_root = output_dir / "_rendered"
        render_root.mkdir(parents=True, exist_ok=True)
        output_name_stem = build_eval_output_stem(
            agent_type=agent_type,
            search_version=search_version,
            problems_path=filepath,
            served_model_name=served_model_name,
            decoding_size=decoding_size,
            beam_size=beam_size,
            search_depth=search_depth,
        )
        run_timestamp = timestamp_slug()
        timestamped_output_stem = build_timestamped_output_stem(
            output_name_stem, run_timestamp
        )
        trace_run = None
        if enable_trace:
            trace_run = TraceRun(
                output_dir,
                route="evaluation_vllm",
                agent=agent_type,
                dataset_path=filepath,
                model_path=served_model_name,
                run_name=output_name_stem,
                run_timestamp=run_timestamp,
                params={
                    "output_name_stem": output_name_stem,
                    "timestamped_output_name_stem": timestamped_output_stem,
                    "vllm_base_url": vllm_base_url,
                    "served_model_name": served_model_name,
                    "server_models": server_models,
                    "decoding_size": decoding_size,
                    "beam_size": beam_size,
                    "search_depth": search_depth,
                    "timeout": timeout,
                    "search_version": search_version,
                    "using_exp": ddar_config.get("using_exp"),
                    "ray_num_cpus": ray_num_cpus,
                    "max_pending_ddar": max_pending_ddar,
                },
                repo_root=Path.cwd(),
            )

        print(f"Total problems to solve: {len(problem_names)}")
        print(f"Using agent: {agent_type}")
        print(f"Using search_version={search_version}")
        print(f"Using served_model_name={served_model_name}")
        print(f"Using vllm_base_url={vllm_base_url}")
        print(f"Using using_exp={ddar_config.get('using_exp')}")
        print(f"Using ray_num_cpus={ray_num_cpus}")
        print(f"Using max_pending_ddar={max_pending_ddar}")
        print(f"Worker warmup: {warmup_infos}")
        if trace_run is not None:
            print(f"Trace run directory: {trace_run.run_dir}")

        all_tasks_info = [(problem_name, "Pending", 0.0) for problem_name in problem_names]
        profiling_rows: list[dict[str, object]] = []
        start_time = time.time()

        with Live(refresh_per_second=1) as live:
            with ThreadPoolExecutor(max_workers=1) as executor:
                for idx, problem_name in enumerate(problem_names):
                    problem_start_wall = time.time()
                    problem_start_perf = time.perf_counter()
                    problem_render_root = render_root / sanitize_problem_name(problem_name)
                    problem_render_root.mkdir(parents=True, exist_ok=True)
                    trace_writer = None
                    if trace_run is not None:
                        trace_writer = trace_run.create_problem_writer(
                            problem_index=idx,
                            problem_name=problem_name,
                            route="evaluation_vllm",
                            agent=agent_type,
                            start_time=problem_start_wall,
                        )
                        trace_writer.log(
                            "problem_start",
                            dataset_path=str(filepath),
                            model_path=served_model_name,
                        )

                    try:
                        problem_future = executor.submit(
                            solve_one_problem,
                            problem_name=problem_name,
                            problems_path=filepath,
                            model_pool=model_pool,
                            agent_type=agent_type,
                            search_version=search_version,
                            decoding_size=decoding_size,
                            beam_size=beam_size,
                            search_depth=search_depth,
                            timeout=timeout,
                            max_pending_ddar=max_pending_ddar,
                            render_root=problem_render_root,
                            ddar_config=ddar_config,
                            trace_writer=trace_writer,
                        )
                        while True:
                            try:
                                problem_name, is_solved, elapsed_time, run_infos = problem_future.result(timeout=5.0)
                                break
                            except FuturesTimeoutError:
                                live.update(render_table(all_tasks_info, start_time))
                    except Exception as exc:
                        traceback.print_exc()
                        print(f"Warning: solver crashed on '{problem_name}': {type(exc).__name__}: {exc}")
                        elapsed_time = time.perf_counter() - problem_start_perf
                        is_solved = False
                        run_infos = {"error": f"{type(exc).__name__}: {exc}"}

                    if trace_writer is not None:
                        trace_writer.log(
                            "problem_end",
                            success=is_solved,
                            runtime=run_infos.get("runtime"),
                            final_error=run_infos.get("error"),
                            final_node_id=run_infos.get("final_node_id"),
                        )
                        trace_writer.close()

                    all_tasks_info[idx] = (
                        problem_name,
                        "Success" if is_solved else "Failed",
                        elapsed_time,
                    )
                    profiling = run_infos.get("profiling")
                    if profiling is not None:
                        row = {
                            "problem_name": problem_name,
                            "solved": "√" if is_solved else "x",
                        }
                        for field in PROFILE_ROW_FIELDS + ("avg_gpu_batch_size",):
                            row[field] = profiling.get(field, 0.0)
                        profiling_rows.append(row)
                    live.update(render_table(all_tasks_info, start_time))
                live.update(render_table(all_tasks_info, start_time))

        csv_filepath = output_dir / f"{timestamped_output_stem}.csv"
        total_problems = len(all_tasks_info)
        solved_count = sum(1 for _, status, _ in all_tasks_info if status == "Success")
        total_time = sum(elapsed for _, _, elapsed in all_tasks_info)
        with csv_filepath.open("w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(
                [
                    f"Dataset: {filepath.stem}, Solved: {solved_count}/{total_problems}, Total Time: {total_time:.2f}s"
                ]
            )
            writer.writerow(["Problem Name", "Solved", "Time (s)"])
            for problem_name, status, elapsed_time in all_tasks_info:
                writer.writerow(
                    [
                        problem_name,
                        "√" if status == "Success" else "x",
                        f"{elapsed_time:.2f}" if status != "Pending" else "",
                    ]
                )
        print(f"Results saved to {csv_filepath}")
        return {
            "csv_path": csv_filepath,
            "solved_count": solved_count,
            "total_problems": total_problems,
            "total_time": total_time,
            "served_model_name": served_model_name,
            "profiling_rows": profiling_rows,
        }
    finally:
        if ray.is_initialized():
            ray.shutdown()


def main():
    configure_logging(force=True)
    parser = argparse.ArgumentParser(
        description="vLLM-only evaluation.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--vllm_base_url", type=str, required=True)
    parser.add_argument("--agent", type=str, required=True, choices=["qwen3_text", "qwen3_vl"])
    parser.add_argument("--problems_path", type=str, required=True)
    parser.add_argument("--decoding_size", type=int, default=8)
    parser.add_argument("--beam_size", type=int, default=64)
    parser.add_argument("--search_depth", type=int, default=4)
    parser.add_argument("--search_version", type=str, default="hybrid", choices=["v1", "v2", "hybrid"])
    parser.add_argument("--ray_num_cpus", type=int, default=None)
    parser.add_argument("--timeout", type=int, default=7200)
    parser.add_argument("--log_dir", type=str, default=None)
    parser.add_argument("--using_exp", type=parse_bool_arg, default=True)
    parser.add_argument(
        "--enable_trace",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    args = parser.parse_args()

    solve_problems_vllm(
        filepath=Path(args.problems_path),
        vllm_base_url=args.vllm_base_url,
        agent_type=args.agent,
        decoding_size=args.decoding_size,
        beam_size=args.beam_size,
        search_depth=args.search_depth,
        search_version=args.search_version,
        ray_num_cpus=args.ray_num_cpus,
        timeout=args.timeout,
        log_dir=args.log_dir,
        enable_trace=args.enable_trace,
        using_exp=args.using_exp,
    )


if __name__ == "__main__":
    main()
