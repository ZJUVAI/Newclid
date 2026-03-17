import os
from pathlib import Path
import time
import argparse
import ray
import csv
from rich.live import Live
from rich.table import Table

from newclid.agent.qwen35_text import Qwen35TextAgent
from newclid.api import GeometricSolverBuilder


@ray.remote(num_cpus=0, num_gpus=1)
def ray_solve_problem(args):
    pid, problem_name, problems_path, model_path, decoding_size, beam_size, search_depth, timeout = args
    start_time = time.time()
    try:
        solver = (
            GeometricSolverBuilder()
            .load_problem_from_file(problems_path, problem_name, rename=True)
            .with_deductive_agent(Qwen35TextAgent(model_path, decoding_size=decoding_size, beam_size=beam_size, search_depth=search_depth))
            .build()
        )
        print(f"problem_name: {problem_name}")
        is_solved = solver.run(timeout=timeout)
        elapsed_time = time.time() - start_time
        return (pid, problem_name, is_solved, elapsed_time)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Warning: solver crashed on problem '{problem_name}' : ({type(e)}) {e}")
        elapsed_time = time.time() - start_time
        return (pid, problem_name, False, elapsed_time)


def render_table(all_tasks_info, start_time, reorder: bool):
    total_problems = len(all_tasks_info)
    solved_count = sum(status == "Success" for _, status, _ in all_tasks_info)
    processed_count = sum(status != "Pending" for _, status, _ in all_tasks_info)

    table = Table()
    table.add_column(f"Problem Names ({solved_count} Solved /{processed_count} Processed /{total_problems} Total)", justify="left", no_wrap=True)
    table.add_column("Status", justify="center")
    table.add_column(f"Time ({time.time()-start_time:.2f}s)", justify="right")
    if reorder:
        priority = {"Failed": 0, "Pending": 1, "Success": 2}
        all_tasks_info = sorted(all_tasks_info, key=lambda x: priority.get(x[1], 99))
    for problem_name, status, elapsed_time in all_tasks_info:
        elapsed = "-" if status == "Pending" else f"{elapsed_time:.2f}"
        table.add_row(problem_name, status, elapsed)
    return table


def solve_problems(filepath: Path, modelpath: list[str], num_cpus: int, decoding_size: int, beam_size: int, search_depth: int, timeout: int = 3600, log_dir: str | None = None):
    if not os.path.exists(filepath):
        print(f"File {filepath} not found.")
        return
    problem_names = []
    with open(filepath, "r") as file:
        lines = file.readlines()
        for i in range(0, len(lines), 2):
            problem_names.append(lines[i].strip())

    print(f"Total problems to solve: {len(problem_names)}")

    if not ray.is_initialized():
        ray.init(dashboard_host="0.0.0.0", ignore_reinit_error=True, num_cpus=num_cpus)

    total_time = 0
    start_time = time.time()
    all_tasks_info = []
    pending_tasks = []

    for i, problem_name in enumerate(problem_names):
        task = ray_solve_problem.remote((i, problem_name, filepath, modelpath, decoding_size, beam_size, search_depth, timeout))
        all_tasks_info.append((problem_name, "Pending", 0))
        pending_tasks.append(task)

    with Live(refresh_per_second=1) as live:
        while pending_tasks:
            done_tasks, pending_tasks = ray.wait(pending_tasks, num_returns=1, timeout=5)
            for task in done_tasks:
                pid, problem_name, is_solved, elapsed_time = ray.get(task)
                all_tasks_info[pid] = (problem_name, "Success" if is_solved else "Failed", elapsed_time)
                total_time += elapsed_time
            live.update(render_table(all_tasks_info, start_time, True))
        live.update(render_table(all_tasks_info, start_time, False))
    ray.shutdown()

    problems_name = filepath.stem
    model_name = "default"
    if modelpath:
        first_model_path = modelpath[0] if isinstance(modelpath, list) else modelpath
        path_obj = Path(first_model_path)
        deepest_folder = path_obj.name
        parent_folder = path_obj.parent.name
        model_name = f"{parent_folder}_{deepest_folder}" if parent_folder else deepest_folder

    csv_filename = f"eval_{problems_name}_{model_name}_d{decoding_size}_b{beam_size}_s{search_depth}.csv"
    output_dir = Path(log_dir) if log_dir else Path("results")
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_filepath = output_dir / csv_filename

    with open(csv_filepath, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        solved_count = sum(1 for _, status, _ in all_tasks_info if status == "Success")
        total_problems = len(all_tasks_info)
        writer.writerow([f"Dataset: {filepath.stem}, Solved: {solved_count}/{total_problems}, Total Time: {total_time:.2f}s"])
        writer.writerow(['Problem Name', 'Solved', 'Time (s)'])
        for problem_name, status, elapsed_time in all_tasks_info:
            solved = "√" if status == "Success" else "x"
            time_str = f"{elapsed_time:.2f}" if status != "Pending" else ""
            writer.writerow([problem_name, solved, time_str])

    print(f"Results saved to {csv_filepath}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Newclid pure-text evaluation with Qwen3.5.")
    parser.add_argument("--problems_path", type=str, default="problems_datasets/dev_jgex.txt")
    parser.add_argument("--model_path", type=str, nargs='+')
    parser.add_argument("--max_workers", type=int, default=8)
    parser.add_argument("--decoding_size", type=int, default=8)
    parser.add_argument("--beam_size", type=int, default=64)
    parser.add_argument("--search_depth", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=7200)
    parser.add_argument("--log_dir", type=str, default=None)
    args = parser.parse_args()

    problems_path = Path(args.problems_path)
    solve_problems(
        problems_path,
        args.model_path,
        num_cpus=args.max_workers,
        decoding_size=args.decoding_size,
        beam_size=args.beam_size,
        search_depth=args.search_depth,
        timeout=args.timeout,
        log_dir=args.log_dir,
    )
