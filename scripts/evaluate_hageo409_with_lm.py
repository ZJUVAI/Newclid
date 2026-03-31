#!/usr/bin/env python3
"""
Evaluate LMAgent + C++ DDAR solver on HAGeo-409 dataset.

This script evaluates the LMAgent with C++ DDAR solver on the HAGeo-409 benchmark.
It loads problems from the JGEX DSL format, runs the solver with auxiliary construction
generation, and outputs successful proofs with auxiliary construction information.

Usage:
    python scripts/evaluate_hageo409_with_lm.py \\
        --model-path /path/to/qwen3 \\
        --output outputs/experiments/20260319_01_hageo409_sft28_csolver_eval \\
        --workers 8 --num-gpus 4 --timeout 600
"""

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


# Known-failing problems to skip (from 20260311_01_hageo409_oom_diagnosis)
SKIP_PROBLEMS = {
    "2011CTSTp10",       # PointTooCloseError
    "2019KoMaLA736",     # AttributeError: 'Point' has no attribute 'num'
    "ShuZhiMiGeo209",    # PointTooCloseError
    "XinXingV35p1",      # PointTooCloseError
}


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
        builder = GeometricSolverBuilder().load_problem_from_file(
            problems_path, problem_name, rename=True
        ).with_deductive_agent(
            LMAgent(model_path, decoding_size=decoding_size, beam_size=beam_size, search_depth=search_depth)
        )
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
            key=lambda x: priority.get(x[1], 99)  # x[1] is status
        )
    for problem_name, status, elapsed_time in all_tasks_info:
        elapsed = "-" if status == "Pending" else f"{elapsed_time:.2f}"
        table.add_row(problem_name, status, elapsed)
    return table


def load_hageo_problems(filepath: Path) -> list[str]:
    """Load problem names from HAGeo-409 JGEX DSL format (alternating lines: id, problem_text)."""
    if not filepath.exists():
        raise FileNotFoundError(f"File {filepath} not found.")

    problem_names = []
    with open(filepath, "r", encoding="utf-8") as file:
        lines = file.readlines()
        for i in range(0, len(lines), 2):
            problem_name = lines[i].strip()
            if problem_name and problem_name not in SKIP_PROBLEMS:
                problem_names.append(problem_name)
            elif problem_name in SKIP_PROBLEMS:
                print(f"Skipping known-failing problem: {problem_name}")

    return problem_names


def solve_problems(
    filepath: Path,
    modelpath: list[str],
    num_cpus: int,
    num_gpus: int,
    decoding_size: int,
    beam_size: int,
    search_depth: int,
    timeout: int,
    output_dir: Path
):
    """
    Main function to solve HAGeo-409 problems using LMAgent + Python solver.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    success_proofs_path = output_dir / "success_proofs.txt"
    aux_path = output_dir / "success_proofs_aux_constructions.jsonl"

    # Load problem names
    problem_names = load_hageo_problems(filepath)
    print(f"Total problems to solve: {len(problem_names)} (skipped {len(SKIP_PROBLEMS)} known-failing)")

    solve_batch = 50
    first_write = True

    for batch_start in range(0, len(problem_names), solve_batch):
        batch_problems = problem_names[batch_start: batch_start + solve_batch]

        # Initialize Ray with specified number of CPUs
        if not ray.is_initialized():
            ray_temp_dir = os.environ.get("RAY_TMPDIR", tempfile.gettempdir())
            ray.init(
                num_cpus=num_cpus,
                num_gpus=num_gpus,
                _temp_dir=ray_temp_dir,
                include_dashboard=False,  # Disable dashboard to avoid port conflicts
            )

        total_time = 0
        start_time = time.time()
        all_tasks_info = []
        pending_tasks = []

        # Open files for incremental writing
        write_mode = "a" if not first_write else "w"
        first_write = False
        proofs_file = open(success_proofs_path, write_mode, encoding="utf-8")
        aux_file = open(aux_path, write_mode, encoding="utf-8")

        # Submit all tasks
        for i, problem_name in enumerate(batch_problems):
            task = ray_solve_problem.remote((i, problem_name, filepath, modelpath, decoding_size, beam_size, search_depth, timeout))
            all_tasks_info.append((problem_name, "Pending", 0))
            pending_tasks.append(task)

        # Process tasks as they complete, writing results incrementally
        with Live(refresh_per_second=1) as live:
            while pending_tasks:
                # Wait for at least one task to complete
                done_tasks, pending_tasks = ray.wait(pending_tasks, num_returns=1, timeout=5)
                # Process completed tasks
                for task in done_tasks:
                    pid, problem_name, is_solved, elapsed_time, aux_info, rename_mapping = ray.get(task)
                    all_tasks_info[pid] = (problem_name, "Success" if is_solved else "Failed", elapsed_time)
                    total_time += elapsed_time

                    # Write result to disk immediately
                    if is_solved:
                        proofs_file.write(problem_name + "\n")
                        proofs_file.flush()

                        original_problem = ProblemJGEX.from_file(Path(filepath), problem_name)
                        original_str = str(original_problem)

                        if aux_info:
                            full_with_aux_renamed = aux_info
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

                            if rename_mapping:
                                inverse_map = {v: k for k, v in rename_mapping.items()}
                                aux_constructions = apply_point_mapping(aux_constructions_renamed, inverse_map)
                                full_with_aux = apply_point_mapping(full_with_aux_renamed, inverse_map)
                            else:
                                aux_constructions = aux_constructions_renamed
                                full_with_aux = full_with_aux_renamed
                        else:
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
                        aux_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                        aux_file.flush()

                live.update(render_table(all_tasks_info, start_time, True))
            live.update(render_table(all_tasks_info, start_time, False))

        proofs_file.close()
        aux_file.close()
        ray.shutdown()
        # Force cleanup Ray processes and wait before next batch
        import subprocess, time as _time
        subprocess.run(["ray", "stop", "--force"], capture_output=True)
        _time.sleep(5)

        print(f"Wrote success proofs for batch at {success_proofs_path}")
        print(f"Wrote auxiliary constructions at {aux_path}")

    print(f"Completed! All success proofs written to {success_proofs_path}")
    print(f"All auxiliary constructions written to {aux_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate LMAgent + Python solver on HAGeo-409 dataset.")
    parser.add_argument("--problems-path", type=str, default="benchmarks/core/hageo_409.txt",
                        help="Path to the HAGeo-409 dataset file")
    parser.add_argument("--model-path", type=str, nargs='+', required=True,
                        help="Path to the model checkpoint(s)")
    parser.add_argument("--output", type=str, required=True,
                        help="Output directory for results")
    parser.add_argument("--workers", type=int, default=8,
                        help="Number of worker processes to use")
    parser.add_argument("--decoding-size", type=int, default=8,
                        help="Decoding size for LMAgent")
    parser.add_argument("--beam-size", type=int, default=64,
                        help="Beam size for LMAgent")
    parser.add_argument("--search-depth", type=int, default=4,
                        help="Search depth for LMAgent")
    parser.add_argument("--timeout", type=int, default=600,
                        help="Timeout for each problem (seconds)")
    parser.add_argument("--num-gpus", type=int, default=4,
                        help="Number of GPUs to use")
    args = parser.parse_args()

    problems_path = Path(args.problems_path)
    output_dir = Path(args.output)

    solve_problems(
        filepath=problems_path,
        modelpath=args.model_path,
        num_cpus=args.workers,
        num_gpus=args.num_gpus,
        decoding_size=args.decoding_size,
        beam_size=args.beam_size,
        search_depth=args.search_depth,
        timeout=args.timeout,
        output_dir=output_dir
    )
