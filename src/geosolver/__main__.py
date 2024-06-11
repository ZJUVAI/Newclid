import logging
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser, Namespace
from pathlib import Path
import time
from typing import Optional

from geosolver import AGENTS_REGISTRY
from geosolver.api import GeometricSolverBuilder
from geosolver.configs import default_configs_path


def cli_arguments() -> Namespace:
    parser = ArgumentParser("geosolver", formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        "--problem",
        required=True,
        type=str,
        help="Description of the problem to solve."
        " Textual representation or path and name"
        " in the format `path/to/problems.txt:name`.",
    )
    parser.add_argument(
        "--agent",
        default="bfsddar",
        type=str,
        help="Name of the agent to use."
        " Register custom agents with `geosolver.register_agent`.",
        choices=AGENTS_REGISTRY.agents.keys(),
    )
    parser.add_argument(
        "--defs",
        type=str,
        default=None,
        help="Path to definition file. Uses default definitions if unspecified.",
    )
    parser.add_argument(
        "--rules",
        type=str,
        default=None,
        help="Path to rules file. Uses default rules if unspecified.",
    )
    parser.add_argument(
        "--translate",
        default=False,
        action="store_true",
        help="Translate the problem points names to alphabetical order.",
    )
    parser.add_argument(
        "--max-steps",
        default=100000,
        type=int,
        help="Maximum number of solving steps before forced termination.",
    )
    parser.add_argument(
        "--timeout",
        default=6000.0,
        type=float,
        help="Time (in seconds) before forced termination.",
    )
    parser.add_argument(
        "--seed",
        default=None,
        type=int,
        help="Seed for random sampling",
    )
    parser.add_argument(
        "-o",
        "--output-folder",
        default=None,
        help="Path to the folder in which to save outputs."
        " Defaults to 'run_results/problem_name'."
        " Will override existing outputs if any.",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        default=False,
        action="store_true",
        help="Do a quiet run without any outputs.",
    )
    parser.add_argument(
        "-ag",
        "--all-graphs",
        default=False,
        action="store_true",
        help="Draw and display all available graphs of the proof state.",
    )
    parser.add_argument(
        "-wg",
        "--why-graph",
        default=False,
        action="store_true",
        help="Draw and display the WhyGraph of the proof state.",
    )
    parser.add_argument(
        "-dg",
        "--dependency-graph",
        default=False,
        action="store_true",
        help="Draw and display the dependency graph of the proof state.",
    )
    parser.add_argument(
        "-pg",
        "--proof-subgraph",
        default=False,
        action="store_true",
        help="Draw and display the proof subgraph (of the dependency graph)"
        " of the proof state.",
    )
    parser.add_argument(
        "-sg",
        "--symbols-graph",
        default=False,
        action="store_true",
        help="Draw and display the symbols graph of the proof state.",
    )
    parser.add_argument(
        "--log-level",
        default=logging.INFO,
        type=float,
        help="Logging level.",
    )
    parser.add_argument(
        "--just-draw-figure",
        default=False,
        action="store_true",
        help="Only do the figure drawing "
        "withut running the solving process and removing the goal.",
    )
    args, _ = parser.parse_known_args()
    return args


def main():
    import seaborn as sns

    args = cli_arguments()
    logging.basicConfig(level=args.log_level)

    quiet: bool = args.quiet
    just_draw: bool = args.just_draw_figure
    seed: Optional[int] = args.seed

    solver_builder = GeometricSolverBuilder(seed=seed, no_goal=just_draw)

    load_problem(args.problem, args.translate, solver_builder)

    solver_builder.load_defs_from_file(resolve_config_path(args.defs))
    solver_builder.load_rules_from_file(resolve_config_path(args.rules))

    agent = AGENTS_REGISTRY.load_agent(args.agent)
    solver_builder.with_deductive_agent(agent)

    solver = solver_builder.build()
    outpath = resolve_output_path(args.output_folder, problem_name=solver.problem.url)

    if not quiet:
        outpath.mkdir(parents=True, exist_ok=True)
        solver.draw_figure(outpath / "construction_figure.png")
    if just_draw:
        return

    success = solver.run(max_steps=args.max_steps, timeout=args.timeout, seed=args.seed)

    if not success:
        logging.info(f"Failed to solved the problem.\nInfos:{solver.run_infos}")
        return

    logging.info(f"Successfuly solved problem !\nInfos:{solver.run_infos}")
    if quiet:
        return

    solver.write_solution(outpath / "proof_steps.txt")
    solver.draw_figure(outpath / "proof_figure.png")

    if args.all_graphs or args.symbols_graph:
        solver.draw_symbols_graph(outpath / "symbols_graph.html")
    if args.all_graphs or args.dependency_graph:
        solver.draw_dependency_graph(outpath / "dependency_graph.html")
    if args.all_graphs or args.proof_subgraph:
        solver.draw_proof_subgraph(outpath / "proof_subgraph.html")
    if args.all_graphs or args.why_graph:
        sns.color_palette()
        solver.draw_why_graph(outpath / "why_hypergraph.html")


def resolve_output_path(path_str: Optional[str], problem_name: str) -> Path:
    if path_str is None:
        if problem_name:
            return Path("run_results") / problem_name
        return Path("run_results") / str(time.strftime("%Y%m%d_%H%M%S"))
    return Path(path_str)


def resolve_config_path(path_str: Optional[str]) -> Optional[Path]:
    if path_str is None:
        return path_str

    path = Path(path_str)
    if path.exists():
        return path

    path = default_configs_path().joinpath(path_str)
    if path.exists():
        return path

    raise FileNotFoundError(
        f"Could not find file for path {path} nor under default_configs"
    )


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
