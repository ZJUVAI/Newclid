import logging
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser, Namespace
from pathlib import Path

from geosolver import AGENTS_REGISTRY
from geosolver.api import GeometricSolverBuilder
from geosolver.reasoning_engines.algebraic_reasoning import algebraic_manipulator


def cli_arguments() -> Namespace:
    parser = ArgumentParser("geosolver", formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        "--problem-name",
        required=True,
        type=str,
    )
    parser.add_argument("--exp", default="exp")
    parser.add_argument("--problems-file", default=None)
    parser.add_argument(
        "--agent",
        default="bfsddar",
        type=str,
        help="Name of the agent to use."
        " Register custom agents with `geosolver.register_agent`.",
        choices=AGENTS_REGISTRY.keys(),
    )
    parser.add_argument(
        "--defs",
        default=None,
        help="Path to definition file. Uses default definitions if unspecified.",
    )
    parser.add_argument(
        "--rules",
        default=None,
        help="Path to rules file. Uses default rules if unspecified.",
    )
    parser.add_argument(
        "--seed",
        default=998244353,
        type=int,
        help="Seed for random sampling",
    )
    parser.add_argument(
        "--log-level",
        default=logging.INFO,
        type=int,
        help="Logging level.",
    )
    parser.add_argument("--goal", default=None)
    parser.add_argument(
        "--ar-verbose",
        default="",
        type=str,
        help="Choose one or more from {a, d, r}, to print table of equations of angles (a), distances (d), ratios (r).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
    )
    args, _ = parser.parse_known_args()
    return args


def main():
    args = cli_arguments()
    logging.basicConfig(level=args.log_level)

    seed: int = args.seed
    algebraic_manipulator.config["verbose"] = args.ar_verbose

    solver_builder = GeometricSolverBuilder(seed)

    # problem_name = load_problem(args.problem, solver_builder)
    exppath = Path(args.exp)
    outpath = exppath / args.problem_name
    outpath.mkdir(parents=True, exist_ok=True)

    solver_builder.load_defs_from_file(Path(args.defs) if args.defs else None)
    rules = outpath / "rules.txt"
    rules_exp = exppath / "rules.txt"
    solver_builder.load_rules_from_file(
        Path(args.rules)
        if args.rules
        else rules
        if Path.exists(rules)
        else rules_exp
        if Path.exists(rules_exp)
        else None
    )

    agent = AGENTS_REGISTRY[args.agent]
    solver_builder.with_deductive_agent(agent)

    solver_builder.with_runtime_cache(outpath / "runtime_cache.json")

    ggb = outpath / "geogebra-export.ggb"
    ggb_exp = exppath / "geogebra-export.ggb"
    if Path.exists(ggb):
        logging.info(f"Use geogebra setting {ggb}")
        solver_builder.load_geogebra(ggb)
    elif ggb_exp:
        logging.info(f"Use geogebra setting {ggb_exp}")
        solver_builder.load_geogebra(ggb_exp)
    elif args.problems_file:
        logging.info(f"Use problem description in {args.problems_file}")
        solver_builder.load_problem_from_file(args.problems_file, args.problem_name)
    else:
        logging.warning("No way to find the problem setting")
        return

    goals_file = outpath / "goals.txt"
    if Path.exists(goals_file):
        logging.info(f"Load goals in {goals_file}")
        solver_builder.load_goals_file(goals_file)
    if args.goal:
        logging.info(f"Load goal : {args.goal}")
        solver_builder.load_goal(args.goal)

    solver = solver_builder.build()
    if not args.quiet:
        solver.draw_figure(False, outpath / "construction_figure.png")
    success = solver.run()

    logging.info(f"Run infos: {solver.run_infos}")
    if not args.quiet:
        solver.write_all_outputs(outpath)
    return success


if __name__ == "__main__":
    exit(0 if main() else 1)
