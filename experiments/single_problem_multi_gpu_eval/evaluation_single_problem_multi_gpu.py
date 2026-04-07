from __future__ import annotations

import argparse
import csv
import logging
import os
import re
import sys
import time
import traceback
from pathlib import Path

import ray
from rich.live import Live
from rich.table import Table


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from experiments.single_problem_multi_gpu_eval.model_pool import ModelPool
from newclid.api import GeometricSolverBuilder
from newclid.profiling import finalize_profiling, merge_profiling_payloads, write_profiling_csv
from newclid.search_trace import TraceRun


LOGLEVEL = os.environ.get("LOGLEVEL", "WARNING").upper()


def configure_logging(*, force: bool = False) -> None:
    logging.basicConfig(
        level=getattr(logging, LOGLEVEL, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=force,
    )


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


def sanitize_problem_name(problem_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", problem_name).strip("_") or "problem"


def create_workers(*, agent_type: str, model_path: str, num_gpus_for_eval: int):
    if agent_type == "lm":
        from experiments.single_problem_multi_gpu_eval.lm_actor import ModelWorker

        return [ModelWorker.remote(model_path) for _ in range(num_gpus_for_eval)]
    if agent_type in {"vlm", "qwen35"}:
        from experiments.single_problem_multi_gpu_eval.visual_actor import VisionModelWorker

        return [VisionModelWorker.remote(model_path, agent_type) for _ in range(num_gpus_for_eval)]
    raise ValueError(f"Unsupported agent type: {agent_type}")


def create_agent(
    *,
    agent_type: str,
    model_pool: ModelPool,
    decoding_size: int,
    beam_size: int,
    search_depth: int,
    max_pending_ddar: int,
    render_root: Path,
    trace_writer=None,
):
    if agent_type == "lm":
        from experiments.single_problem_multi_gpu_eval.lm_multi_gpu_agent import LMMultiGPUAgent

        return LMMultiGPUAgent(
            model_pool=model_pool,
            decoding_size=decoding_size,
            beam_size=beam_size,
            search_depth=search_depth,
            agent_type="lm_multi_gpu_experiment",
            max_pending_ddar=max_pending_ddar,
            trace_writer=trace_writer,
        )
    if agent_type in {"vlm", "qwen35"}:
        from experiments.single_problem_multi_gpu_eval.visual_multi_gpu_agent import VisualMultiGPUAgent

        return VisualMultiGPUAgent(
            model_pool=model_pool,
            decoding_size=decoding_size,
            beam_size=beam_size,
            search_depth=search_depth,
            agent_type=f"{agent_type}_multi_gpu_experiment",
            max_pending_ddar=max_pending_ddar,
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
    decoding_size: int,
    beam_size: int,
    search_depth: int,
    timeout: int,
    max_pending_ddar: int,
    render_root: Path,
    trace_writer=None,
):
    start_time = time.time()
    logging.getLogger(__name__).info(
        "solve_one_problem start: problem=%s agent=%s problems_path=%s",
        problem_name,
        agent_type,
        problems_path,
    )
    build_start = time.time()
    builder = GeometricSolverBuilder().load_problem_from_file(problems_path, problem_name, rename=True)

    agent = create_agent(
        agent_type=agent_type,
        model_pool=model_pool,
        decoding_size=decoding_size,
        beam_size=beam_size,
        search_depth=search_depth,
        max_pending_ddar=max_pending_ddar,
        render_root=render_root,
        trace_writer=trace_writer,
    )
    solver = builder.with_deductive_agent(agent).build()
    entry_build_time_s = time.time() - build_start
    is_solved = solver.run(timeout=timeout)
    elapsed_time = time.time() - start_time
    profiling = finalize_profiling(
        merge_profiling_payloads(
            {"build_time_s": entry_build_time_s},
            solver.run_infos.get("profiling"),
        ),
        elapsed_time,
    )
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
    timeout: int,
    agent_type: str,
    max_pending_ddar: int | None,
    log_dir: str | None,
    render_root: str | None = None,
    trace_dir: str | None = None,
    ray_address: str = "local",
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
                "dashboard_host": "0.0.0.0",
                "ignore_reinit_error": True,
            }
            if ray_address == "local":
                init_kwargs["num_cpus"] = num_cpus
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

        workers = create_workers(
            agent_type=agent_type,
            model_path=model_path,
            num_gpus_for_eval=num_gpus_for_eval,
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
        trace_run = None
        if trace_dir:
            trace_run = TraceRun(
                trace_dir,
                route="evaluation_single_problem_multi_gpu",
                agent=agent_type,
                dataset_path=filepath,
                model_path=model_path,
                params={
                    "decoding_size": decoding_size,
                    "beam_size": beam_size,
                    "search_depth": search_depth,
                    "timeout": timeout,
                    "max_pending_ddar": max_pending_ddar,
                    "num_gpus_for_eval": num_gpus_for_eval,
                },
                repo_root=Path.cwd(),
            )

        print(f"Total problems to solve: {len(problem_names)}")
        print(f"Using experimental agent: {agent_type}_multi_gpu_experiment")
        print(f"Using {num_gpus_for_eval} GPU workers")
        print("Using fixed single-request GPU dispatch")
        print(f"Using max_pending_ddar={max_pending_ddar}")
        print(f"Worker warmup: {warmup_infos}")

        all_tasks_info = [(problem_name, "Pending", 0.0) for problem_name in problem_names]
        profiling_rows: list[dict[str, object]] = []
        start_time = time.time()

        with Live(refresh_per_second=1) as live:
            for idx, problem_name in enumerate(problem_names):
                try:
                    logging.getLogger(__name__).info(
                        "Problem loop start: idx=%d/%d problem=%s",
                        idx + 1,
                        len(problem_names),
                        problem_name,
                    )
                    problem_start = time.time()
                    problem_render_root = visual_render_root / sanitize_problem_name(problem_name)
                    problem_render_root.mkdir(parents=True, exist_ok=True)
                    trace_writer = None
                    if trace_run is not None:
                        trace_writer = trace_run.create_problem_writer(
                            problem_index=idx,
                            problem_name=problem_name,
                            route="evaluation_single_problem_multi_gpu",
                            agent=agent_type,
                            start_time=problem_start,
                        )
                        trace_writer.log(
                            "problem_start",
                            dataset_path=str(filepath),
                            model_path=model_path,
                        )
                    problem_name, is_solved, elapsed_time, run_infos = solve_one_problem(
                        problem_name=problem_name,
                        problems_path=filepath,
                        model_pool=model_pool,
                        agent_type=agent_type,
                        decoding_size=decoding_size,
                        beam_size=beam_size,
                        search_depth=search_depth,
                        timeout=timeout,
                        max_pending_ddar=max_pending_ddar,
                        render_root=problem_render_root,
                        trace_writer=trace_writer,
                    )
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
                    elapsed_time = time.time() - problem_start
                    is_solved = False
                    run_infos = {
                        "profiling": finalize_profiling(
                            merge_profiling_payloads({"build_time_s": elapsed_time}),
                            elapsed_time,
                        )
                    }
                    if trace_writer is not None:
                        trace_writer.log(
                            "problem_end",
                            success=False,
                            runtime=time.time() - problem_start,
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
                    profiling_rows.append(
                        {
                            "problem_name": problem_name,
                            "solved": "√" if is_solved else "x",
                            "total_time_s": profiling["total_time_s"],
                            "build_time_s": profiling["build_time_s"],
                            "inference_time_s": profiling["inference_time_s"],
                            "ddar_time_s": profiling["ddar_time_s"],
                            "other_time_s": profiling["other_time_s"],
                        }
                    )
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

        problems_name = filepath.stem
        path_obj = Path(model_path)
        deepest_folder = path_obj.name
        parent_folder = path_obj.parent.name
        model_name = f"{parent_folder}_{deepest_folder}" if parent_folder else deepest_folder
        csv_filename = (
            f"eval_single_problem_multi_gpu_{agent_type}_{problems_name}_{model_name}"
            f"_d{decoding_size}_b{beam_size}_s{search_depth}.csv"
        )

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
            profiling_csv_filepath = csv_filepath.with_name(f"{csv_filepath.stem}_profiling.csv")
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
        description="Experimental single-problem multi-GPU evaluation.",
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
        choices=["lm", "vlm", "qwen35"],
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
        "--trace_dir",
        type=str,
        default=None,
        help="Optional directory for per-problem search trace JSONL files.",
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
        "--enable_profiling",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Write a sidecar profiling CSV with build/inference/DDAR timings.",
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
        timeout=args.timeout,
        agent_type=args.agent,
        max_pending_ddar=args.max_pending_ddar,
        log_dir=args.log_dir,
        render_root=args.render_root,
        trace_dir=args.trace_dir,
        ray_address=args.ray_address,
        enable_profiling=args.enable_profiling,
    )


if __name__ == "__main__":
    main()
