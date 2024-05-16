import logging
from pathlib import Path
from geosolver import AGENTS_REGISTRY
from geosolver.api import GeometricSolverBuilder
from geosolver.cli import cli_arguments


def main():
    args = cli_arguments()
    logging.basicConfig(level=args.log_level)

    solver_builder = GeometricSolverBuilder()

    load_problem(args.problem, args.translate, solver_builder)

    agent = AGENTS_REGISTRY.load_agent(args.agent)
    solver_builder.with_deductive_agent(agent)

    solver = solver_builder.build()
    success = solver.run(max_steps=args.max_steps, timeout=args.timeout)

    if success:
        logging.info("Successfuly solved problem !")


def load_problem(
    problem_txt_or_file: str,
    translate: bool,
    solver_builder: GeometricSolverBuilder,
) -> None:
    PATH_NAME_SEPARATOR = ":"

    if PATH_NAME_SEPARATOR not in problem_txt_or_file:
        solver_builder.load_problem_from_txt(problem_txt_or_file, translate)
        return

    path, problem_name = problem_txt_or_file.split(PATH_NAME_SEPARATOR)
    solver_builder.load_problem_from_file(Path(path), problem_name, translate)


if __name__ == "__main__":
    main()
