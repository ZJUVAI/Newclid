import os
os.environ["RAY_DEDUP_LOGS"] = "0"
os.environ["RAY_LOG_LEVEL"] = "WARNING"
from pathlib import Path
import time
import argparse 
import ray
import csv
from rich.live import Live
from rich.table import Table

from newclid.agent.ddarn import DDARN
from newclid.agent.human_agent import HumanAgent
from newclid.agent.lm import LMAgent
from newclid.api import GeometricSolverBuilder


def solve_problem(args):
    """
    Process a single problem and return whether it was solved successfully along with the time taken.
    """
    problem_name, problems_path, model_path, decoding_size, beam_size, search_depth = args
    start_time = time.time()
    try:
        solver = (
            GeometricSolverBuilder()
            .load_problem_from_file(problems_path, problem_name, rename=True)
            .with_deductive_agent(LMAgent(model_path, decoding_size=decoding_size,beam_size=beam_size, search_depth=search_depth))
            .build()
        )
        is_solved = solver.run(timeout=3600*2)
        elapsed_time = time.time() - start_time
        return (problem_name, is_solved, elapsed_time) 
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Warning: solver crashed on problem '{problem_name}' : ({type(e)}) {e}")
        elapsed_time = time.time() - start_time 
        return (problem_name, False, elapsed_time)

@ray.remote(num_cpus=1, num_gpus=0.125)
def ray_solve_problem(args):
    """
    Ray remote function to process a single problem.
    """
    return solve_problem(args)

def run_newclid(filepath: Path, modelpath: list[Path], num_cpus: int, decoding_size: int, beam_size: int, search_depth: int):
    """
    Main function, read the file and execute tasks using Ray.
    """

    if not os.path.exists(filepath):
        print(f"File {filepath} not found.")
        return

    # Read all problem names (every other line starting from index 0)
    problem_names = []
    with open(filepath, "r") as file:
        lines = file.readlines()
        for i in range(0, len(lines), 2):
            problem_names.append(lines[i].strip())

    total_problems = len(problem_names)
    print(f"Total problems to solve: {total_problems}")

    # Use Ray to process problems concurrently
    solved_count = 0
    processed_count = 0  
    total_time = 0 
    total_real_time = time.time()   


    # Multi-threaded execution using Ray with limited concurrent tasks
    # Initialize Ray with specified number of CPUs
    if not ray.is_initialized():
        ray.init(log_to_driver=False, ignore_reinit_error=True, num_cpus=num_cpus)

    pending_tasks = {}
    completed_tasks = set()
    
    # Submit all tasks
    for i, problem_name in enumerate(problem_names):
        task = ray_solve_problem.remote((problem_name, filepath, modelpath, decoding_size, beam_size, search_depth))
        pending_tasks[task] = problem_name
    
    # Process tasks as they complete
    while pending_tasks:
        # Wait for at least one task to complete
        done_tasks, _ = ray.wait(list(pending_tasks.keys()), timeout=0)
        
        # Process completed tasks
        for task in done_tasks:
            problem_name = pending_tasks.pop(task)
            completed_tasks.add(problem_name)
            problem_name, is_solved, elapsed_time = ray.get(task)
            solved_count += 1 if is_solved else 0
            processed_count += 1  
            total_time += elapsed_time 
            print(
                f"Progress: {processed_count}/{total_problems} processed, "  
                f"Solved: {solved_count}, "
                f"Current: {problem_name} "
                f"({'Success' if is_solved else 'Failed'}), "
                f"Time: {elapsed_time:.2f}s"
            )
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
    
    # Ensure results directory exists
    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)
    csv_filepath = results_dir / csv_filename
    
    # Write results to CSV file
    with open(csv_filepath, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        # Write header
        writer.writerow(['Problem Name', 'Solved', 'Time (s)'])  # Column 1: problem name, Column 2: solved status, Column 3: time taken
        # Write data
        for problem_name, status, elapsed_time in all_tasks_info:
            solved = "√" if status == "Success" else "x"  # Mark √ if solved, x if not
            time_str = f"{elapsed_time:.2f}" if status != "Pending" else ""  # Show time for processed problems, leave empty for pending
            writer.writerow([problem_name, solved, time_str])
    
    print(f"Results saved to {csv_filepath}")
            

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Newclid evaluation with configurable paths.")
    parser.add_argument("--problems_path", type=str, default="problems_datasets/dev_jgex.txt",
                        help="Path to the problems dataset file")
    parser.add_argument("--model_path", type=str, nargs='+', help="Path to the model checkpoint")
    parser.add_argument("--max_workers", type=int, default=8, help="Number of worker processes to use")
    parser.add_argument("--decoding_size", type=int, default=8)
    parser.add_argument("--beam_size", type=int, default=64)
    parser.add_argument("--search_depth", type=int, default=4)
    args = parser.parse_args()
    
    problems_path = Path(args.problems_path)
    model_path = [Path(path).resolve() for path in args.model_path]
    run_newclid(problems_path, model_path, num_cpus=args.max_workers, decoding_size=args.decoding_size, beam_size=args.beam_size, search_depth=args.search_depth)