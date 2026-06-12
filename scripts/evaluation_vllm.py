from __future__ import annotations

import argparse
import csv
import logging
import os
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path

from rich.live import Live
from rich.table import Table

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
for path in (str(REPO_ROOT), str(SRC_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from newclid.agent.vllm import VLLMLMAgent
from newclid.api import GeometricSolverBuilder

LOGLEVEL = os.environ.get("LOGLEVEL", "WARNING").upper()


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, LOGLEVEL, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )


def get_git_short_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "nogit"
    commit = result.stdout.strip()
    return commit or "nogit"


@dataclass(frozen=True)
class EvalConfig:
    problems_path: Path
    vllm_base_url: str
    served_model_name: str
    decoding_size: int
    beam_size: int
    search_depth: int
    search_version: str
    timeout: int


@dataclass(frozen=True)
class SolveOutcome:
    solved: bool
    elapsed_s: float
    run_infos: dict


def solve(*, problem_name: str, config: EvalConfig) -> SolveOutcome:
    t0 = time.perf_counter()
    builder = GeometricSolverBuilder().load_problem_from_file(
        config.problems_path, problem_name, rename=True
    )
    agent = VLLMLMAgent(
        base_url=config.vllm_base_url,
        decoding_size=config.decoding_size,
        beam_size=config.beam_size,
        search_depth=config.search_depth,
        served_model_name=config.served_model_name,
        search_version=config.search_version,
    )
    solver = builder.with_deductive_agent(agent).build()
    solved = solver.run(timeout=config.timeout)
    return SolveOutcome(
        solved=solved,
        elapsed_s=time.perf_counter() - t0,
        run_infos=solver.run_infos,
    )


def render_table(
    tasks: list[tuple[str, str, float, int, int, float, float]],
    start_time: float,
) -> Table:
    solved = sum(status == "Success" for _, status, *_ in tasks)
    done = sum(status != "Pending" for _, status, *_ in tasks)
    table = Table()
    table.add_column(
        f"Problem Names ({solved} Solved / {done} Processed / {len(tasks)} Total)",
        justify="left",
        no_wrap=True,
    )
    table.add_column("Status", justify="center")
    table.add_column("Calls (LM/DDAR)", justify="right")
    table.add_column(
        f"Time (LM/DDAR) ({time.time() - start_time:.2f}s)", justify="right"
    )
    priority = {"Failed": 0, "Pending": 1, "Success": 2}
    for name, status, elapsed, llm_calls, ddar_calls, llm_wall, ddar_wall in sorted(
        tasks, key=lambda item: priority.get(item[1], 99)
    ):
        if status == "Pending":
            table.add_row(name, status, "-", "-")
            continue
        table.add_row(
            name,
            status,
            f"{llm_calls} / {ddar_calls}",
            f"{elapsed:.2f}s ({llm_wall:.2f}/{ddar_wall:.2f})",
        )
    return table


def main() -> None:
    configure_logging()
    main_t0 = time.perf_counter()
    parser = argparse.ArgumentParser(
        description="Standalone vLLM evaluation.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--problems_path", type=str, required=True)
    parser.add_argument("--vllm_base_url", type=str, required=True)
    parser.add_argument("--decoding_size", type=int, default=8)
    parser.add_argument("--beam_size", type=int, default=64)
    parser.add_argument("--search_depth", type=int, default=4)
    parser.add_argument(
        "--search_version", choices=("v1", "v2", "hybrid"), default="hybrid"
    )
    parser.add_argument("--timeout", type=int, default=7200)
    parser.add_argument("--log_dir", type=str, default=None)
    parser.add_argument("--ray_num_cpus", type=int, default=None)
    args = parser.parse_args()

    filepath = Path(args.problems_path)
    if not filepath.exists():
        raise FileNotFoundError(f"Problems file not found: {filepath}")

    problem_names = [
        line.strip()
        for line in filepath.read_text(encoding="utf-8").splitlines()[::2]
        if line.strip()
    ]

    import ray

    if not ray.is_initialized():
        ray.init(
            num_cpus=args.ray_num_cpus,
            include_dashboard=False,
            ignore_reinit_error=True,
        )

    probe_agent = VLLMLMAgent(
        base_url=args.vllm_base_url,
        decoding_size=args.decoding_size,
        beam_size=args.beam_size,
        search_depth=args.search_depth,
        search_version=args.search_version,
    )
    warmup_info = probe_agent.server_info()
    served_model_name = str(warmup_info["served_model_name"])
    config = EvalConfig(
        problems_path=filepath,
        vllm_base_url=args.vllm_base_url,
        served_model_name=served_model_name,
        decoding_size=args.decoding_size,
        beam_size=args.beam_size,
        search_depth=args.search_depth,
        search_version=args.search_version,
        timeout=args.timeout,
    )

    print(
        f"Total problems: {len(problem_names)}\n"
        f"served_model_name={served_model_name}\n"
        f"vllm_base_url={args.vllm_base_url}\n"
        f"search_version={args.search_version}\n"
        f"ray_n_cpus={ray.available_resources().get('CPU')}\n"
        f"warmup={warmup_info}"
    , flush=True)

    tasks: list[tuple[str, str, float, int, int, float, float]] = [
        (name, "Pending", 0.0, 0, 0, 0.0, 0.0) for name in problem_names
    ]
    start_time = time.time()

    with Live(refresh_per_second=1) as live:
        for idx, problem_name in enumerate(problem_names):
            print(f"[start] problem={problem_name}", flush=True)
            try:
                outcome = solve(problem_name=problem_name, config=config)
            except Exception as exc:
                traceback.print_exc()
                print(
                    f"Warning: solver crashed on '{problem_name}': {type(exc).__name__}: {exc}",
                    flush=True,
                )
                outcome = SolveOutcome(False, 0.0, {})

            run_infos = outcome.run_infos
            ddar_calls = int(run_infos.get("ddar_calls", 0))
            ddar_wall = float(run_infos.get("ddar_real_time_s", 0.0))
            llm_calls = int(run_infos.get("llm_calls", 0))
            llm_wall = float(run_infos.get("llm_real_time_s", 0.0))
            tasks[idx] = (
                problem_name,
                "Success" if outcome.solved else "Failed",
                outcome.elapsed_s,
                llm_calls,
                ddar_calls,
                llm_wall,
                ddar_wall,
            )
            print(
                f"[stats] problem={problem_name}"
                f" solved={outcome.solved}"
                f" elapsed={outcome.elapsed_s:.2f}s"
                f" llm_calls={llm_calls}"
                f" ddar_calls={ddar_calls}"
                f" llm_wall={llm_wall:.2f}s"
                f" ddar_wall={ddar_wall:.2f}s"
            , flush=True)
            if "error" in run_infos:
                print(
                    f"[error] problem={problem_name} reason={run_infos['error']}",
                    flush=True,
                )
            live.update(render_table(tasks, start_time))
        live.update(render_table(tasks, start_time))

    output_dir = Path(args.log_dir) if args.log_dir else Path("results")
    output_dir.mkdir(parents=True, exist_ok=True)
    model_slug = Path(served_model_name).name
    search_slug = (
        args.search_version[1:]
        if args.search_version.startswith("v")
        else args.search_version
    )
    output_stem = (
        f"eval_vllm_{filepath.stem}_{model_slug}"
        f"_sv{search_slug}"
        f"_d{args.decoding_size}_b{args.beam_size}_s{args.search_depth}"
        f"_{get_git_short_commit()}"
    )
    csv_path = output_dir / f"{output_stem}.csv"
    solved_count = sum(1 for _, status, *_ in tasks if status == "Success")
    total_time = sum(elapsed for _, _, elapsed, *_ in tasks)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                f"Dataset: {filepath.stem}, Solved: {solved_count}/{len(tasks)}, Total Time: {total_time:.2f}s"
            ]
        )
        writer.writerow(
            [
                "Problem Name",
                "Solved",
                "LM Calls",
                "DDAR Calls",
                "LM Time(s)",
                "DDAR Time(s)",
                "Total Time(s)",
            ]
        )
        for name, status, elapsed, llm_calls, ddar_calls, llm_wall, ddar_wall in tasks:
            writer.writerow(
                [
                    name,
                    "√" if status == "Success" else "x",
                    llm_calls,
                    ddar_calls,
                    f"{llm_wall:.2f}",
                    f"{ddar_wall:.2f}",
                    f"{elapsed:.2f}",
                ]
            )

    print(f"Results saved to {csv_path}", flush=True)
    print(f"[session] total_wall_time_s={time.perf_counter() - main_t0:.2f}", flush=True)


if __name__ == "__main__":
    main()
