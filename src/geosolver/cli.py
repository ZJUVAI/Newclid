from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser, Namespace
import logging

from geosolver import AGENTS_REGISTRY


def cli_arguments() -> Namespace:
    parser = ArgumentParser("alphageo", formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        "--agent",
        default="bfsddar",
        type=str,
        help="Name of the agent to use."
        " Register custom agents with `geosolver.register_agent`.",
        choices=AGENTS_REGISTRY.agents.keys(),
    )
    parser.add_argument(
        "--problem",
        required=True,
        type=str,
        help="Description of the problem to solve."
        " Textual representation or path and name in the format `path:name`.",
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
        "--log-level",
        default=logging.INFO,
        type=float,
        help="Logging level.",
    )
    args, _ = parser.parse_known_args()
    return args
