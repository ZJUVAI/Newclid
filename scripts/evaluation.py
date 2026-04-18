from __future__ import annotations

import argparse
import csv
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import logging
import os
import socket
import sys
import time
import traceback
from pathlib import Path
import re

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
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from newclid.agent.lm import LMAgent
from newclid.agent.vlm import VLMAgent
from newclid.api import GeometricSolverBuilder
from newclid.agent.runtime.model_pool import ModelPool, WorkerHandleWrapper
from newclid.profiling import (
    PROFILE_ROW_FIELDS,
    create_profiling_payload,
    finalize_profiling,
    write_profiling_csv,
)
from newclid.search_trace import TraceRun, timestamp_slug


LOGLEVEL = os.environ.get("LOGLEVEL", "WARNING").upper()


def sanitize_problem_name(problem_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", problem_name).strip("_") or "problem"


def build_eval_output_stem(
    *,
    agent_type: str,
    search_version: str,
    problems_path: Path,
    model_path: str,
    decoding_size: int,
    beam_size: int,
    search_depth: int,
    gpu_batch_size: int,
    gpu_batch_timeout_ms: int,
    torch_seed: int = 123,
) -> str:
    problems_name = problems_path.stem
    path_obj = Path(model_path)
    deepest_folder = path_obj.name
    parent_folder = path_obj.parent.name
    model_name = f"{parent_folder}_{deepest_folder}" if parent_folder else deepest_folder
    return (
        f"eval_single_problem_multi_gpu_{agent_type}_{problems_name}_{model_name}"
        f"_sv{search_version[-1]}"
        f"_d{decoding_size}_b{beam_size}_s{search_depth}"
        f"_gbs{gpu_batch_size}_gbt{gpu_batch_timeout_ms}_seed{torch_seed}"
    )


def build_timestamped_output_stem(output_name_stem: str, timestamp: str) -> str:
    return f"{output_name_stem}_{timestamp}"


def configure_logging(*, force: bool = False) -> None:
    logging.basicConfig(
        level=getattr(logging, LOGLEVEL, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=force,
    )


def reserve_port_across_hosts(hosts: list[str], max_attempts: int = 128) -> int:
    unique_hosts: list[str] = []
    for host in hosts:
        if host and host not in unique_hosts:
            unique_hosts.append(host)
    if not unique_hosts:
        raise ValueError("reserve_port_across_hosts requires at least one host.")

    primary_host = unique_hosts[0]
    last_error: OSError | None = None
    for _ in range(max_attempts):
        sockets: list[socket.socket] = []
        try:
            primary_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            primary_socket.bind((primary_host, 0))
            port = int(primary_socket.getsockname()[1])
            sockets.append(primary_socket)
            for host in unique_hosts[1:]:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.bind((host, port))
                sockets.append(sock)
            return port
        except OSError as exc:
            last_error = exc
        finally:
            for sock in sockets:
                sock.close()
    raise RuntimeError(
        f"Failed to reserve a shared free port across hosts {unique_hosts} after {max_attempts} attempts."
    ) from last_error


def reserve_unused_agent_ports(count: int) -> list[int]:
    from ray._private.services import get_node_ip_address

    node_ip = get_node_ip_address()
    candidate_hosts = [node_ip]
    if node_ip != "127.0.0.1":
        candidate_hosts.append("127.0.0.1")
    ports: list[int] = []
    while len(ports) < count:
        port = reserve_port_across_hosts(candidate_hosts)
        if port not in ports:
            ports.append(port)
    return ports


def ray_init_with_explicit_agent_ports(init_kwargs: dict[str, object]) -> None:
    # Ray still starts a dashboard agent even when include_dashboard=False.
    # On this machine the auto-selected gRPC agent port has been colliding
    # with lingering listeners on 127.0.0.1, so choose explicit free ports.
    from ray._private.parameter import RayParams

    (
        metrics_agent_port,
        dashboard_agent_listen_port,
        runtime_env_agent_port,
    ) = reserve_unused_agent_ports(3)
    logger = logging.getLogger(__name__)
    logger.info(
        "ray.init local port override: metrics_agent_port=%d dashboard_agent_listen_port=%d runtime_env_agent_port=%d",
        metrics_agent_port,
        dashboard_agent_listen_port,
        runtime_env_agent_port,
    )

    original_init = RayParams.__init__

    def patched_init(self, *args, **kwargs):
        kwargs.setdefault("metrics_agent_port", metrics_agent_port)
        kwargs.setdefault("dashboard_agent_listen_port", dashboard_agent_listen_port)
        kwargs.setdefault("runtime_env_agent_port", runtime_env_agent_port)
        return original_init(self, *args, **kwargs)

    RayParams.__init__ = patched_init
    try:
        ray.init(**init_kwargs)
    finally:
        RayParams.__init__ = original_init


def render_table(all_tasks_info, start_time, reorder: bool):
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
    if reorder:
        priority = {"Failed": 0, "Pending": 1, "Success": 2}
        all_tasks_info = sorted(all_tasks_info, key=lambda x: priority.get(x[1], 99))
    for problem_name, status, elapsed_time in all_tasks_info:
        elapsed = "-" if status == "Pending" else f"{elapsed_time:.2f}"
        table.add_row(problem_name, status, elapsed)
    return table

def create_workers(
    *,
    agent_type: str,
    model_path: str,
    num_gpus_for_eval: int,
    torch_seed: int,
):
    if agent_type in {"lm", "qwen35_text"}:
        from newclid.agent.runtime.text_worker import ModelWorker

        return [
            WorkerHandleWrapper(
                ModelWorker.remote(model_path, agent_type, torch_seed, worker_slot),
                worker_trace_id=f"gpu:{worker_slot}",
                worker_device=f"cuda:{worker_slot}",
            )
            for worker_slot in range(num_gpus_for_eval)
        ]
    if agent_type == "qwen3_vl_text":
        from newclid.agent.runtime.vision_worker import Qwen3VLTextWorker

        return [
            WorkerHandleWrapper(
                Qwen3VLTextWorker.remote(model_path, agent_type, torch_seed, worker_slot),
                worker_trace_id=f"gpu:{worker_slot}",
                worker_device=f"cuda:{worker_slot}",
            )
            for worker_slot in range(num_gpus_for_eval)
        ]
    if agent_type in {"vlm", "qwen35_vl"}:
        from newclid.agent.runtime.vision_worker import VisionModelWorker

        return [
            WorkerHandleWrapper(
                VisionModelWorker.remote(model_path, agent_type, torch_seed, worker_slot),
                worker_trace_id=f"gpu:{worker_slot}",
                worker_device=f"cuda:{worker_slot}",
            )
            for worker_slot in range(num_gpus_for_eval)
        ]
    raise ValueError(f"Unsupported agent type: {agent_type}")


def create_agent(
    *,
    agent_type: str,
    search_version: str,
    model_pool: ModelPool,
    decoding_size: int,
    beam_size: int,
    search_depth: int,
    gpu_batch_size: int,
    gpu_batch_timeout_ms: int,
    max_pending_ddar: int,
    prepare_request_workers: int,
    prepare_prefetch_limit: int,
    render_root: Path,
    trace_writer=None,
):
    if agent_type in {"lm", "qwen35_text", "qwen3_vl_text"}:
        return LMAgent(
            model_pool=model_pool,
            decoding_size=decoding_size,
            beam_size=beam_size,
            search_depth=search_depth,
            gpu_batch_size=gpu_batch_size,
            gpu_batch_timeout_ms=gpu_batch_timeout_ms,
            agent_type=f"{agent_type}_parallel",
            max_pending_ddar=max_pending_ddar,
            prepare_request_workers=prepare_request_workers,
            prepare_prefetch_limit=prepare_prefetch_limit,
            search_version=search_version,
            trace_writer=trace_writer,
        )
    if agent_type in {"vlm", "qwen35_vl"}:
        return VLMAgent(
            model_pool=model_pool,
            decoding_size=decoding_size,
            beam_size=beam_size,
            search_depth=search_depth,
            gpu_batch_size=gpu_batch_size,
            gpu_batch_timeout_ms=gpu_batch_timeout_ms,
            agent_type=f"{agent_type}_parallel",
            max_pending_ddar=max_pending_ddar,
            prepare_request_workers=prepare_request_workers,
            prepare_prefetch_limit=prepare_prefetch_limit,
            search_version=search_version,
            render_root=render_root,
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
    gpu_batch_size: int,
    gpu_batch_timeout_ms: int,
    timeout: int,
    max_pending_ddar: int,
    prepare_request_workers: int,
    prepare_prefetch_limit: int,
    render_root: Path,
    trace_writer=None,
):
    start_perf = time.perf_counter()
    logging.getLogger(__name__).info(
        "solve_one_problem start: problem=%s agent=%s problems_path=%s",
        problem_name,
        agent_type,
        problems_path,
    )
    build_start = time.perf_counter()
    builder = GeometricSolverBuilder().load_problem_from_file(problems_path, problem_name, rename=True)

    agent = create_agent(
        agent_type=agent_type,
        search_version=search_version,
        model_pool=model_pool,
        decoding_size=decoding_size,
        beam_size=beam_size,
        search_depth=search_depth,
        gpu_batch_size=gpu_batch_size,
        gpu_batch_timeout_ms=gpu_batch_timeout_ms,
        max_pending_ddar=max_pending_ddar,
        prepare_request_workers=prepare_request_workers,
        prepare_prefetch_limit=prepare_prefetch_limit,
        render_root=render_root,
        trace_writer=trace_writer,
    )
    solver = builder.with_deductive_agent(agent).build()
    entry_setup_wall_time_s = time.perf_counter() - build_start
    is_solved = solver.run(timeout=timeout)
    elapsed_time = time.perf_counter() - start_perf
    profiling = solver.run_infos.get("profiling") or create_profiling_payload()
    profiling["entry_setup_wall_time_s"] = float(profiling.get("entry_setup_wall_time_s", 0.0)) + entry_setup_wall_time_s
    profiling = finalize_profiling(profiling, elapsed_time)
    solver.run_infos["profiling"] = profiling
    logging.getLogger(__name__).info(
        "solve_one_problem done: problem=%s solved=%s elapsed=%.2fs",
        problem_name,
        is_solved,
        elapsed_time,
    )
    return (
        problem_name,
        is_solved,
        elapsed_time,
        solver.run_infos,
    )


def solve_problems_single_problem_multi_gpu(
    *,
    filepath: Path,
    model_path: str,
    num_cpus: int,
    num_gpus_for_eval: int,
    decoding_size: int,
    beam_size: int,
    search_depth: int,
    gpu_batch_size: int,
    gpu_batch_timeout_ms: int,
    torch_seed: int,
    timeout: int,
    agent_type: str,
    search_version: str,
    max_pending_ddar: int | None,
    prepare_request_workers: int | None,
    prepare_prefetch_limit: int | None,
    log_dir: str | None,
    render_root: str | None = None,
    ray_address: str = "local",
    enable_trace: bool = False,
    enable_profiling: bool = False,
):
    if not filepath.exists():
        raise FileNotFoundError(f"File {filepath} not found.")

    with open(filepath, "r", encoding="utf-8") as file:
        lines = file.readlines()
    problem_names = [lines[i].strip() for i in range(0, len(lines), 2)]

    try:
        if max_pending_ddar is None:
            max_pending_ddar = 2 * num_cpus
        elif max_pending_ddar <= 0:
            raise ValueError(f"max_pending_ddar must be positive, got {max_pending_ddar}.")

        if not ray.is_initialized():
            init_kwargs = {
                "address": ray_address,
                "ignore_reinit_error": True,
            }
            if ray_address == "local":
                init_kwargs["num_cpus"] = num_cpus
                # Local eval does not rely on the Ray dashboard, and disabling it
                # avoids startup failures when the dashboard agent cannot bind.
                init_kwargs["include_dashboard"] = False
                ray_init_with_explicit_agent_ports(init_kwargs)
            else:
                ray.init(**init_kwargs)

        available_gpus = int(ray.available_resources().get("GPU", 0))
        if available_gpus <= 0:
            raise RuntimeError("No GPU resource is visible to Ray.")
        if num_gpus_for_eval <= 0:
            num_gpus_for_eval = available_gpus
        if num_gpus_for_eval > available_gpus:
            raise ValueError(
                f"Requested {num_gpus_for_eval} GPUs, but Ray only reports {available_gpus} GPUs."
            )
        if prepare_request_workers is None:
            prepare_request_workers = (
                max(1, max(2 * num_gpus_for_eval, num_gpus_for_eval * gpu_batch_size))
                if num_gpus_for_eval > 0
                else max(2, gpu_batch_size)
            )
        if prepare_request_workers <= 0:
            raise ValueError(
                f"prepare_request_workers must be positive, got {prepare_request_workers}."
            )
        if prepare_prefetch_limit is None:
            prepare_prefetch_limit = max(
                prepare_request_workers,
                2 * num_gpus_for_eval * gpu_batch_size if num_gpus_for_eval > 0 else gpu_batch_size,
            )
        if prepare_prefetch_limit <= 0:
            raise ValueError(
                f"prepare_prefetch_limit must be positive, got {prepare_prefetch_limit}."
            )
        if gpu_batch_size <= 0:
            raise ValueError(f"gpu_batch_size must be positive, got {gpu_batch_size}.")
        if gpu_batch_timeout_ms < 0:
            raise ValueError(f"gpu_batch_timeout_ms must be non-negative, got {gpu_batch_timeout_ms}.")

        workers = create_workers(
            agent_type=agent_type,
            model_path=model_path,
            num_gpus_for_eval=num_gpus_for_eval,
            torch_seed=torch_seed,
        )
        logging.getLogger(__name__).info(
            "Created workers: agent=%s requested_gpus=%d visible_gpus=%d",
            agent_type,
            num_gpus_for_eval,
            available_gpus,
        )
        model_pool = ModelPool(workers)
        warmup_infos = model_pool.warmup()

        output_dir = Path(log_dir) if log_dir else Path("results")
        output_dir.mkdir(parents=True, exist_ok=True)
        visual_render_root = Path(render_root) if render_root else output_dir / "_rendered"
        visual_render_root.mkdir(parents=True, exist_ok=True)
        output_name_stem = build_eval_output_stem(
            agent_type=agent_type,
            search_version=search_version,
            problems_path=filepath,
            model_path=model_path,
            decoding_size=decoding_size,
            beam_size=beam_size,
            search_depth=search_depth,
            gpu_batch_size=gpu_batch_size,
            gpu_batch_timeout_ms=gpu_batch_timeout_ms,
            torch_seed=torch_seed,
        )
        run_timestamp = timestamp_slug()
        timestamped_output_stem = build_timestamped_output_stem(output_name_stem, run_timestamp)
        trace_run = None
        if enable_trace:
            trace_run = TraceRun(
                output_dir,
                route="evaluation_single_problem_multi_gpu",
                agent=agent_type,
                dataset_path=filepath,
                model_path=model_path,
                run_name=output_name_stem,
                run_timestamp=run_timestamp,
                params={
                    "output_name_stem": output_name_stem,
                    "timestamped_output_name_stem": timestamped_output_stem,
                    "decoding_size": decoding_size,
                    "beam_size": beam_size,
                    "search_depth": search_depth,
                    "gpu_batch_size": gpu_batch_size,
                    "gpu_batch_timeout_ms": gpu_batch_timeout_ms,
                    "torch_seed": torch_seed,
                    "timeout": timeout,
                    "search_version": search_version,
                    "max_pending_ddar": max_pending_ddar,
                    "num_gpus_for_eval": num_gpus_for_eval,
                    "prepare_request_workers": prepare_request_workers,
                    "prepare_prefetch_limit": prepare_prefetch_limit,
                },
                repo_root=Path.cwd(),
            )

        print(f"Total problems to solve: {len(problem_names)}")
        print(f"Using agent: {agent_type}")
        print(f"Using search_version={search_version}")
        print(f"Using {num_gpus_for_eval} GPU workers")
        print(f"Using gpu_batch_size={gpu_batch_size}")
        print(f"Using gpu_batch_timeout_ms={gpu_batch_timeout_ms}")
        print(f"Using torch_seed={torch_seed}")
        print(f"Using max_pending_ddar={max_pending_ddar}")
        print(f"Using prepare_request_workers={prepare_request_workers}")
        print(f"Using prepare_prefetch_limit={prepare_prefetch_limit}")
        print(f"Worker warmup: {warmup_infos}")
        if trace_run is not None:
            print(f"Trace run directory: {trace_run.run_dir}")

        all_tasks_info = [(problem_name, "Pending", 0.0) for problem_name in problem_names]
        profiling_rows: list[dict[str, object]] = []
        start_time = time.time()

        with Live(refresh_per_second=1) as live:
            with ThreadPoolExecutor(max_workers=1) as executor:
                for idx, problem_name in enumerate(problem_names):
                    try:
                        logging.getLogger(__name__).info(
                            "Problem loop start: idx=%d/%d problem=%s",
                            idx + 1,
                            len(problem_names),
                            problem_name,
                        )
                        problem_start_wall = time.time()
                        problem_start_perf = time.perf_counter()
                        problem_render_root = visual_render_root / sanitize_problem_name(problem_name)
                        problem_render_root.mkdir(parents=True, exist_ok=True)
                        trace_writer = None
                        if trace_run is not None:
                            trace_writer = trace_run.create_problem_writer(
                                problem_index=idx,
                                problem_name=problem_name,
                                route="evaluation_single_problem_multi_gpu",
                                agent=agent_type,
                                start_time=problem_start_wall,
                            )
                            trace_writer.log(
                                "problem_start",
                                dataset_path=str(filepath),
                                model_path=model_path,
                            )

                        # Run the actual solve in a background thread so the
                        # main thread can keep rebuilding the Live table while
                        # a single problem is being processed.
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
                            gpu_batch_size=gpu_batch_size,
                            gpu_batch_timeout_ms=gpu_batch_timeout_ms,
                            timeout=timeout,
                            max_pending_ddar=max_pending_ddar,
                            prepare_request_workers=prepare_request_workers,
                            prepare_prefetch_limit=prepare_prefetch_limit,
                            render_root=problem_render_root,
                            trace_writer=trace_writer,
                        )
                        while True:
                            try:
                                problem_name, is_solved, elapsed_time, run_infos = problem_future.result(timeout=5.0)
                                break
                            except FuturesTimeoutError:
                                live.update(render_table(all_tasks_info, start_time, True))

                        if trace_writer is not None:
                            trace_writer.log(
                                "problem_end",
                                success=is_solved,
                                runtime=run_infos.get("runtime"),
                                final_error=run_infos.get("error"),
                                final_node_id=run_infos.get("final_node_id"),
                            )
                            trace_writer.close()
                    except Exception as exc:
                        traceback.print_exc()
                        print(f"Warning: experimental solver crashed on problem '{problem_name}' : ({type(exc)}) {exc}")
                        elapsed_time = time.perf_counter() - problem_start_perf
                        is_solved = False
                        run_infos = {
                            "profiling": finalize_profiling(
                                {
                                    **create_profiling_payload(),
                                    "entry_setup_wall_time_s": elapsed_time,
                                },
                                elapsed_time,
                            )
                        }
                        if trace_writer is not None:
                            trace_writer.log(
                                "problem_end",
                                success=False,
                                runtime=time.time() - problem_start_wall,
                                final_error=f"{type(exc).__name__}: {exc}",
                                final_node_id=None,
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
                    gpu_worker_stats = run_infos.get("gpu_worker_stats")
                    if gpu_worker_stats is not None:
                        print(f"[gpu_worker_stats] problem={problem_name} stats={gpu_worker_stats}")
                    logging.getLogger(__name__).info(
                        "Problem loop done: idx=%d/%d problem=%s status=%s elapsed=%.2fs",
                        idx + 1,
                        len(problem_names),
                        problem_name,
                        "Success" if is_solved else "Failed",
                        elapsed_time,
                    )
                    live.update(render_table(all_tasks_info, start_time, True))
                live.update(render_table(all_tasks_info, start_time, False))

        csv_filename = f"{timestamped_output_stem}.csv"

        csv_filepath = output_dir / csv_filename
        total_problems = len(all_tasks_info)
        solved_count = sum(1 for _, status, _ in all_tasks_info if status == "Success")
        total_time = sum(elapsed for _, _, elapsed in all_tasks_info)

        with open(csv_filepath, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([f"Dataset: {filepath.stem}, Solved: {solved_count}/{total_problems}, Total Time: {total_time:.2f}s"])
            writer.writerow(["Problem Name", "Solved", "Time (s)"])
            for problem_name, status, elapsed_time in all_tasks_info:
                writer.writerow([
                    problem_name,
                    "√" if status == "Success" else "x",
                    f"{elapsed_time:.2f}" if status != "Pending" else "",
                ])

        print(f"Results saved to {csv_filepath}")
        if enable_profiling:
            profiling_csv_filepath = csv_filepath.with_name(f"{timestamped_output_stem}_profiling.csv")
            write_profiling_csv(
                profiling_csv_filepath,
                dataset_name=filepath.stem,
                solved_count=solved_count,
                total_problems=total_problems,
                total_time_s=total_time,
                rows=profiling_rows,
            )
            print(f"Profiling results saved to {profiling_csv_filepath}")
    finally:
        if ray.is_initialized():
            ray.shutdown()


def main():
    configure_logging()

    parser = argparse.ArgumentParser(
        description="Single-problem multi-GPU evaluation.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--problems_path",
        type=str,
        required=True,
        help="Benchmark file to evaluate. The script reads every other line as a problem name.",
    )
    parser.add_argument(
        "--model_path",
        type=str,
        required=True,
        help="Local checkpoint/model directory or remote model id understood by ModelScope.",
    )
    parser.add_argument(
        "--agent",
        type=str,
        default="lm",
        choices=["lm", "vlm", "qwen35_text", "qwen35_vl", "qwen3_vl_text"],
        help="Agent backend to use for single-problem multi-GPU evaluation.",
    )
    parser.add_argument(
        "--log_dir",
        type=str,
        default=None,
        help="Directory for the summary CSV. Uses ./results when omitted.",
    )
    parser.add_argument(
        "--render_root",
        type=str,
        default=None,
        help="Optional directory for rendered visual prompts. Uses <log_dir>/_rendered when omitted.",
    )
    parser.add_argument(
        "--enable_trace",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Write per-problem trace JSONL files under <log_dir>/<run_id>/.",
    )
    parser.add_argument(
        "--ray_address",
        type=str,
        default="local",
        help="Ray address to connect to. Use 'local' to force a fresh local runtime, 'auto' to reuse any detected cluster, or an explicit address such as '127.0.0.1:6379'.",
    )
    parser.add_argument(
        "--max_workers",
        type=int,
        default=8,
        help="Ray CPU capacity, mainly affecting concurrent DDAR validation tasks.",
    )
    parser.add_argument(
        "--decoding_size",
        type=int,
        default=8,
        help="Number of model candidates generated for each beam node at one search depth.",
    )
    parser.add_argument(
        "--beam_size",
        type=int,
        default=64,
        help="Maximum number of candidate problems retained between search depths.",
    )
    parser.add_argument(
        "--search_depth",
        type=int,
        default=4,
        help="Number of iterative auxiliary-construction expansion rounds.",
    )
    parser.add_argument(
        "--search_version",
        type=str,
        default="v1",
        choices=["v1", "v2"],
        help="Search/prompt variant for auxiliary construction expansion.",
    )
    parser.add_argument(
        "--gpu_batch_size",
        type=int,
        default=2,
        help="Maximum number of prepared requests grouped into one GPU generate call.",
    )
    parser.add_argument(
        "--gpu_batch_timeout_ms",
        type=int,
        default=100,
        help="Optional wait budget for filling a GPU batch before dispatching a tail batch.",
    )
    parser.add_argument(
        "--torch_seed",
        type=int,
        default=123,
        help="Torch RNG seed applied once per GPU worker process.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=7200,
        help="Per-problem timeout in seconds.",
    )
    parser.add_argument(
        "--num_gpus_for_eval",
        type=int,
        default=0,
        help="Number of GPU workers to start. 0 means all GPUs visible to Ray.",
    )
    parser.add_argument(
        "--max_pending_ddar",
        type=int,
        default=None,
        help="Upper bound on in-flight DDAR Ray tasks for the current problem. Defaults to 2 * max_workers when omitted.",
    )
    parser.add_argument(
        "--prepare_request_workers",
        type=int,
        default=None,
        help="Local ThreadPoolExecutor worker count for parallel request preparation. Defaults to 2 * num_gpus_for_eval.",
    )
    parser.add_argument(
        "--prepare_prefetch_limit",
        type=int,
        default=None,
        help="Maximum combined count of running prepare tasks and ready prepared requests. Defaults to prepare_request_workers.",
    )
    parser.add_argument(
        "--enable_profiling",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Write a sidecar profiling CSV with summary build/inference/DDAR timings.",
    )
    args = parser.parse_args()

    solve_problems_single_problem_multi_gpu(
        filepath=Path(args.problems_path),
        model_path=args.model_path,
        num_cpus=args.max_workers,
        num_gpus_for_eval=args.num_gpus_for_eval,
        decoding_size=args.decoding_size,
        beam_size=args.beam_size,
        search_depth=args.search_depth,
        gpu_batch_size=args.gpu_batch_size,
        gpu_batch_timeout_ms=args.gpu_batch_timeout_ms,
        torch_seed=args.torch_seed,
        timeout=args.timeout,
        agent_type=args.agent,
        search_version=args.search_version,
        max_pending_ddar=args.max_pending_ddar,
        prepare_request_workers=args.prepare_request_workers,
        prepare_prefetch_limit=args.prepare_prefetch_limit,
        log_dir=args.log_dir,
        render_root=args.render_root,
        ray_address=args.ray_address,
        enable_trace=args.enable_trace,
        enable_profiling=args.enable_profiling,
    )


if __name__ == "__main__":
    main()
