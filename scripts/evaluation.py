import os
import json
import re
from pathlib import Path
import time
import argparse
import tempfile
import ray
from rich.live import Live
from rich.table import Table

from newclid.agent.lm import LMAgent
from newclid.api import GeometricSolverBuilder
from newclid.formulations.problem import ProblemJGEX


def apply_point_mapping(text: str, mapping: dict[str, str]) -> str:
    """Apply point name mapping to a JGEX problem string.

    Replaces point names as whole words, processing longer names first
    to avoid partial replacements.
    """
    # Sort by length descending to avoid partial replacements
    sorted_names = sorted(mapping.keys(), key=len, reverse=True)
    pattern = re.compile(r'\b(' + '|'.join(re.escape(n) for n in sorted_names) + r')\b')
    return pattern.sub(lambda m: mapping[m.group(0)], text)


@ray.remote(num_cpus=0, num_gpus=1)
def ray_solve_problem(args):
    """
    Process a single problem and return whether it was solved successfully along with the time taken.
    """
    pid, problem_name, problems_path, model_path, decoding_size, beam_size, search_depth, timeout = args
    start_time = time.time()
    try:
        builder = GeometricSolverBuilder().load_problem_from_file(problems_path, problem_name, rename=True).with_deductive_agent(LMAgent(model_path, decoding_size=decoding_size,beam_size=beam_size, search_depth=search_depth))
        rename_mapping = builder.rename_mapping
        solver = builder.build(max_attempts=10)
        is_solved = solver.run(timeout=timeout)
        elapsed_time = time.time() - start_time

        # Extract auxiliary construction info if solved by LM
        aux_info = None
        if is_solved and "error" in solver.run_infos:
            # When success=True, "error" field contains str(new_problem) with aux constructions
            aux_info = solver.run_infos["error"]

        return (pid, problem_name, is_solved, elapsed_time, aux_info, rename_mapping)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Warning: solver crashed on problem '{problem_name}' : ({type(e)}) {e}")
        elapsed_time = time.time() - start_time
        return (pid, problem_name, False, elapsed_time, None, None)

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
            key=lambda x: priority.get(x[1], 99)  # x[1] 就是 status
        )
    for problem_name, status, elapsed_time in all_tasks_info:
        elapsed = "-" if status == "Pending" else f"{elapsed_time:.2f}"
        table.add_row(problem_name, status, elapsed)
    return table

def solve_problems(filepath: Path, modelpath: list[str], num_cpus: int, decoding_size: int, beam_size: int, search_depth: int, timeout: int = 3600, success_proofs_path: str = "success_proofs.txt"):
    """
    Main function, read the file and execute tasks using Ray.
    """
    
    # Read all problem names 
    if not os.path.exists(filepath):
        print(f"File {filepath} not found.")
        return
    problem_names = []
    with open(filepath, "r") as file:
        lines = file.readlines()
        for i in range(0, len(lines), 2):
            problem_names.append(lines[i].strip())

    print(f"Total problems to solve: {len(problem_names)}")
    solve_batch = 50
    first_write = True
    for batch_start in range(0, len(problem_names), solve_batch):
        batch_problems = problem_names[batch_start: batch_start + solve_batch]
        
        # Multi-threaded execution using Ray with limited concurrent tasks
        # Initialize Ray with specified number of CPUs
        if not ray.is_initialized():
            ray_temp_dir = os.environ.get("RAY_TMPDIR", tempfile.gettempdir())
            ray.init(
                num_cpus=num_cpus,
                num_gpus=1,
                _temp_dir=ray_temp_dir,
                include_dashboard=False,  # Disable dashboard to avoid port conflicts
            )

        total_time = 0 
        start_time = time.time()
        all_tasks_info = []
        pending_tasks = []
        success_proofs = []
        
        # Submit all tasks
        for i, problem_name in enumerate(batch_problems):
            task = ray_solve_problem.remote((i, problem_name, filepath, modelpath, decoding_size, beam_size, search_depth, timeout))
            all_tasks_info.append((problem_name, "Pending", 0))
            pending_tasks.append(task)
        
        # Process tasks as they complete
        with Live(refresh_per_second=1) as live:
            while pending_tasks:
                # Wait for at least one task to complete
                done_tasks, pending_tasks = ray.wait(pending_tasks, num_returns=1, timeout=5)
                # Process completed tasks
                for task in done_tasks:
                    pid, problem_name, is_solved, elapsed_time, aux_info, rename_mapping = ray.get(task)
                    all_tasks_info[pid] = (problem_name, "Success" if is_solved else "Failed", elapsed_time)
                    total_time += elapsed_time
                    if is_solved:
                        success_proofs.append((problem_name, aux_info, rename_mapping))
                        
                live.update(render_table(all_tasks_info, start_time, True))
            live.update(render_table(all_tasks_info, start_time, False))
        ray.shutdown()
        write_mode = "a"
        if first_write:
            first_write = False
            write_mode = "w"
        with open(success_proofs_path, write_mode, encoding="utf-8") as f:
            for problem_name, _, _ in success_proofs:
                f.write(problem_name + "\n")

        # Write auxiliary constructions to separate JSONL file
        aux_path = success_proofs_path.replace(".txt", "_aux_constructions.jsonl")
        if aux_path == success_proofs_path:
            aux_path = success_proofs_path + ".aux.jsonl"
        with open(aux_path, write_mode, encoding="utf-8") as f:
            for problem_name, aux_info, rename_mapping in success_proofs:
                original_problem = ProblemJGEX.from_file(Path(filepath), problem_name)
                original_str = str(original_problem)

                if aux_info:
                    full_with_aux_renamed = aux_info
                    # Extract renamed auxiliary constructions
                    renamed_problem = original_problem.renamed()
                    renamed_str = str(renamed_problem)
                    renamed_constructions = renamed_str.split(" ? ")[0] if " ? " in renamed_str else renamed_str
                    constructions_part = full_with_aux_renamed.split(" ? ")[0] if " ? " in full_with_aux_renamed else full_with_aux_renamed
                    if constructions_part.startswith(renamed_constructions):
                        aux_constructions_renamed = constructions_part[len(renamed_constructions):].strip()
                        if aux_constructions_renamed.startswith(";"):
                            aux_constructions_renamed = aux_constructions_renamed[1:].strip()
                    else:
                        aux_constructions_renamed = constructions_part

                    # Apply inverse mapping to get original point names
                    if rename_mapping:
                        inverse_map = {v: k for k, v in rename_mapping.items()}
                        aux_constructions = apply_point_mapping(aux_constructions_renamed, inverse_map)
                        full_with_aux = apply_point_mapping(full_with_aux_renamed, inverse_map)
                    else:
                        aux_constructions = aux_constructions_renamed
                        full_with_aux = full_with_aux_renamed
                else:
                    # Solved by DDAR alone (no auxiliary constructions needed)
                    full_with_aux_renamed = str(original_problem.renamed()) if rename_mapping else original_str
                    full_with_aux = original_str
                    aux_constructions = ""
                    aux_constructions_renamed = ""

                record = {
                    "problem_name": problem_name,
                    "original_problem": original_str,
                    "auxiliary_constructions": aux_constructions,
                    "full_problem_with_aux": full_with_aux,
                    "auxiliary_constructions_renamed": aux_constructions_renamed,
                    "full_problem_with_aux_renamed": full_with_aux_renamed,
                    "rename_mapping": rename_mapping,
                    "solved_by": "lm" if aux_info else "ddar"
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        print(f"wrote success proofs / {solve_batch} problems at {success_proofs_path}")
        print(f"wrote auxiliary constructions at {aux_path}")
    print(f"wrote ALL success proofs at {success_proofs_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Newclid evaluation with configurable paths.")
    parser.add_argument("--problems_path", type=str, default="benchmarks/dev/dev_imo.txt",
                        help="Path to the problems dataset file")
    parser.add_argument("--model_path", type=str, nargs='+', help="Path to the model checkpoint")
    parser.add_argument("--max_workers", type=int, default=8, help="Number of worker processes to use")
    parser.add_argument("--decoding_size", type=int, default=8)
    parser.add_argument("--beam_size", type=int, default=64)
    parser.add_argument("--search_depth", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=7200, help="Timeout for each problem")
    parser.add_argument("--success_proofs_path", type=str, default="datasets/success_proofs/hageo_224_remain_results.jsonl", help="Path to save successful proofs")
    args = parser.parse_args()
    
    problems_path = Path(args.problems_path)
    solve_problems(problems_path, args.model_path, num_cpus=args.max_workers, decoding_size=args.decoding_size, beam_size=args.beam_size, search_depth=args.search_depth, timeout=args.timeout, success_proofs_path=args.success_proofs_path)