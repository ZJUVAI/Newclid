import os
from pathlib import Path
import time
import argparse
import ray
import csv
import logging
from rich.live import Live
from rich.table import Table

from newclid.agent.vlm import VLMAgent
from newclid.agent.internvlm import InternVLMAgent
from newclid.agent.qwen35 import Qwen35Agent
from newclid.api import GeometricSolverBuilder
from newclid.generation.problem_worker import GeometryProblemWorker
from newclid.problem_db import ProblemDBRuntime, ProblemDBWriter


LOGLEVEL = os.environ.get("LOGLEVEL", "WARNING").upper()
logger = logging.getLogger(__name__)


def configure_logging(*, force: bool = False) -> None:
    logging.basicConfig(
        level=getattr(logging, LOGLEVEL, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=force,
    )


configure_logging()

@ray.remote(num_cpus=0, num_gpus=1)
def ray_solve_problem(args):
    """
    Process a single problem and return whether it was solved successfully along with the time taken.
    """
    configure_logging(force=True)
    pid, problem_name, problems_path, model_path, decoding_size, beam_size, search_depth, timeout, agent_type, problem_db_root, enable_problem_db = args
    start_time = time.time()
    try:
        builder = GeometricSolverBuilder().load_problem_from_file(problems_path, problem_name, rename=True)
        problem_db_runtime = None
        if enable_problem_db:
            problem_db_runtime = ProblemDBRuntime(
                db_root=problem_db_root,
                problems_path=problems_path,
                base_problem=builder.problemJGEX,
            )
        # print(f"building problem: {problem_name}")
        # Select agent based on agent_type
        if agent_type == "vlm":
            agent = VLMAgent(
                model_path,
                decoding_size=decoding_size,
                beam_size=beam_size,
                search_depth=search_depth,
                problem_db_runtime=problem_db_runtime,
                agent_type="vlm",
            )
        elif agent_type == "internvlm":
            agent = InternVLMAgent(
                model_path,
                decoding_size=decoding_size,
                beam_size=beam_size,
                search_depth=search_depth,
                problem_db_runtime=problem_db_runtime,
                agent_type="internvlm",
            )
        elif agent_type == "qwen35":
            agent = Qwen35Agent(
                model_path,
                decoding_size=decoding_size,
                beam_size=beam_size,
                search_depth=search_depth,
                problem_db_runtime=problem_db_runtime,
                agent_type="qwen35",
            )
        else:
            raise ValueError(f"Unknown agent type: {agent_type}. Must be 'vlm', 'internvlm', or 'qwen35'")
        
        solver = (
            builder
            .with_deductive_agent(agent)
            .build()
        )
        # print(f"problem_name: {problem_name}")
        is_solved = solver.run(timeout=timeout)
        elapsed_time = time.time() - start_time
        problem_db_stats = solver.run_infos.get("problem_db_stats")
        ddar_stats = solver.run_infos.get("ddar_stats")
        if problem_db_stats is not None:
            logger.debug(
                "[problem_db_stats] "
                f"problem={problem_name} "
                f"cache_hits={problem_db_stats['cache_hits']} "
                f"new_records={problem_db_stats['new_records']}"
            )
        if ddar_stats is not None:
            logger.debug(
                "[ddar_stats] "
                f"problem={problem_name} "
                f"base_calls={ddar_stats['base_calls']} "
                f"remote_ddar_calls={ddar_stats['remote_ddar_calls']} "
                f"remote_solved={ddar_stats['remote_solved']} "
                f"remote_unsolved={ddar_stats['remote_unsolved']} "
                f"remote_build_invalid={ddar_stats['remote_build_invalid']} "
                f"remote_engine_invalid={ddar_stats['remote_engine_invalid']}"
            )
        return (pid, problem_name, is_solved, elapsed_time, solver.run_infos.get("problem_db_payload"))
    except Exception as e:
        logger.warning(
            "Solver crashed on problem '%s': (%s) %s",
            problem_name,
            type(e),
            e,
            exc_info=True,
        )
        elapsed_time = time.time() - start_time 
        return (pid, problem_name, False, elapsed_time, None)

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
        all_tasks_info = sorted(
            all_tasks_info,
            key=lambda x: priority.get(x[1], 99)  # x[1] is the status
        )
    for problem_name, status, elapsed_time in all_tasks_info:
        elapsed = "-" if status == "Pending" else f"{elapsed_time:.2f}"
        table.add_row(problem_name, status, elapsed)
    return table

def solve_problems(filepath: Path, modelpath: list[str], num_cpus: int, decoding_size: int, beam_size: int, search_depth: int, timeout: int = 3600, agent_type: str = "vlm", log_dir: str = None, problem_db_root: str = "problem_db", enable_problem_db: bool = False):
    """
    Main function, read the file and execute tasks using Ray.
    """
    
    # Read all problem names
    if not os.path.exists(filepath):
        logger.error("File %s not found.", filepath)
        return
    problem_names = []
    with open(filepath, "r") as file:
        lines = file.readlines()
        for i in range(0, len(lines), 2):
            problem_names.append(lines[i].strip())
 
    logger.info("Total problems to solve: %s", len(problem_names))
    logger.info("Using agent: %s", agent_type)

    # Multi-threaded execution using Ray with limited concurrent tasks
    # Initialize Ray with specified number of CPUs
    if not ray.is_initialized():
        ray.init(
            # local_mode=True,
            # include_dashboard=True, dashboard_host="0.0.0.0", dashboard_port=8265,
            dashboard_host="0.0.0.0",
            ignore_reinit_error=True, num_cpus=num_cpus
        )

    total_time = 0
    start_time = time.time()
    all_tasks_info = []
    pending_tasks = []
    problem_db_writer = ProblemDBWriter(problem_db_root, repo_root=Path.cwd()) if enable_problem_db else None
    
    # Submit all tasks
    for i, problem_name in enumerate(problem_names):
        task = ray_solve_problem.remote((i, problem_name, filepath, modelpath, decoding_size, beam_size, search_depth, timeout, agent_type, problem_db_root, enable_problem_db))
        all_tasks_info.append((problem_name, "Pending", 0))
        pending_tasks.append(task)
    
    # Process tasks as they complete
    with Live(refresh_per_second=1) as live:
        while pending_tasks:
            # Wait for at least one task to complete
            done_tasks, pending_tasks = ray.wait(pending_tasks, num_returns=1, timeout=5)
            # Process completed tasks
            for task in done_tasks:
                pid, problem_name, is_solved, elapsed_time, problem_db_payload = ray.get(task)
                if problem_db_writer is not None:
                    problem_db_writer.write_payload(problem_db_payload)
                all_tasks_info[pid] = (problem_name, "Success" if is_solved else "Failed", elapsed_time)
                total_time += elapsed_time
                    
            live.update(render_table(all_tasks_info, start_time, True))
        live.update(render_table(all_tasks_info, start_time, False))
    ray.shutdown()
    
    # Generate CSV filename based on problems_path and model_path
    problems_name = filepath.stem  # Get the file name without extension
    # Get the deepest folder name from modelpath (assuming it's a list, take the first if not empty)
    model_name = "default"
    if modelpath:
        # If modelpath is a list, take the first element
        first_model_path = modelpath[0] if isinstance(modelpath, list) else modelpath
        # Get the deepest folder name
        # model_name = Path(first_model_path).name
        # Change to use second deepest folder name + deepest folder name
        path_obj = Path(first_model_path)
        deepest_folder = path_obj.name
        parent_folder = path_obj.parent.name
        model_name = f"{parent_folder}_{deepest_folder}" if parent_folder else deepest_folder
    
    # Create CSV filename with parameters
    csv_filename = f"eval_{problems_name}_{model_name}_d{decoding_size}_b{beam_size}_s{search_depth}.csv"
    
    # Ensure output directory exists
    if log_dir:
        output_dir = Path(log_dir)
    else:
        output_dir = Path("results")
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_filepath = output_dir / csv_filename
    
    # Write results to CSV file
    with open(csv_filepath, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        # Write summary header row
        dataset_name = filepath.stem
        solved_count = sum(1 for _, status, _ in all_tasks_info if status == "Success")
        total_problems = len(all_tasks_info)
        writer.writerow([f"Dataset: {dataset_name}, Solved: {solved_count}/{total_problems}, Total Time: {total_time:.2f}s"])
        # Write column headers
        writer.writerow(['Problem Name', 'Solved', 'Time (s)'])
        # Write data
        for problem_name, status, elapsed_time in all_tasks_info:
            solved = "√" if status == "Success" else "x"  # Mark √ if solved, x if not
            time_str = f"{elapsed_time:.2f}" if status != "Pending" else ""  # Show time for processed problems, leave empty for pending
            writer.writerow([problem_name, solved, time_str])
    
    logger.info("Results saved to %s", csv_filepath)
            

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Newclid evaluation with configurable paths.")
    parser.add_argument("--problems_path", type=str, default="problems_datasets/dev_jgex.txt",
                        help="Path to the problems dataset file")
    parser.add_argument("--model_path", type=str, nargs='+', help="Path to the model checkpoint")
    parser.add_argument("--max_workers", type=int, default=8, help="Number of worker processes to use")
    parser.add_argument("--decoding_size", type=int, default=8)
    parser.add_argument("--beam_size", type=int, default=64)
    parser.add_argument("--search_depth", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=7200, help="Timeout for each problem")
    parser.add_argument("--agent", type=str, default="vlm", choices=["vlm", "internvlm", "qwen35"],
                        help="Agent type to use: 'vlm' for VLMAgent, 'internvlm' for InternVLMAgent, or 'qwen35' for Qwen35Agent")
    parser.add_argument("--log_dir", type=str, default=None,
                        help="Directory to save evaluation results (default: results/)")
    parser.add_argument("--problem_db_root", type=str, default="problem_db",
                        help="Directory to store the problem database")
    parser.add_argument("--enable_problem_db", action=argparse.BooleanOptionalAction, default=False,
                        help="Enable problem database cache reads/writes")
    args = parser.parse_args()
    
    problems_path = Path(args.problems_path)
    solve_problems(problems_path, args.model_path, num_cpus=args.max_workers, decoding_size=args.decoding_size, beam_size=args.beam_size, search_depth=args.search_depth, timeout=args.timeout, agent_type=args.agent, log_dir=args.log_dir, problem_db_root=args.problem_db_root, enable_problem_db=args.enable_problem_db)
