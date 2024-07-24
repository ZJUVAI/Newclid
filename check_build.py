import os
from pathlib import Path
from sys import stderr

from geosolver.agent.flemmard import Flemmard
from geosolver.api import GeometricSolverBuilder


def run_geosolver(filepath: Path):
    count = 0

    if not os.path.exists(filepath):
        print(f"File {filepath} not found.")
        return

    with open(filepath, "r") as file:
        for line in file:
            count += 1

            if count % 2 == 1:
                problem_name = line.strip()
                try:
                    solver = (
                        GeometricSolverBuilder()
                        .load_problem_from_file(problems_path, problem_name)
                        .with_deductive_agent(Flemmard)
                        .build()
                    )
                    solver.run()
                except Exception as e:
                    print(
                        f"Warning: solver crashed on problem '{problem_name}' : ({type(e)}) {e}",
                        file=stderr,
                    )


problems_path = Path("problems_datasets/new_benchmark_50.txt")
run_geosolver(Path(problems_path))
