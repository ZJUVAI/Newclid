import os
from pathlib import Path
from sys import stderr

from newclid.agent.ddarn import DDARN
from newclid.api import GeometricSolverBuilder


def run_newclid(filepath: Path):
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
                        GeometricSolverBuilder(8)
                        .load_problem_from_file(problems_path, problem_name)
                        .with_deductive_agent(DDARN())
                        .build()
                    )
                    solver.run()
                    if solver.run():
                        print(f"Solved {problem_name} succesfully.")
                except Exception as e:
                    print(
                        f"Warning: solver crashed on problem '{problem_name}' : ({type(e)}) {e}",
                        file=stderr,
                    )


problems_path = Path("problems_datasets/examples.txt")
run_newclid(Path(problems_path))
