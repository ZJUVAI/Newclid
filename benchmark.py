import logging
from pathlib import Path
from typing import Optional


import geosolver.graph as gh
import geosolver.problem as pr
from geosolver.ddar import solve
from geosolver.proof_writing import write_solution

DEFINITIONS = None  # contains definitions of construction actions
RULES = None  # contains rules of deductions


def main():
    global DEFINITIONS
    global RULES

    # definitions of terms used in our domain-specific language.
    DEFINITIONS = pr.Definition.from_txt_file("defs.txt", to_dict=True)
    # load inference rules used in DD.
    RULES = pr.Theorem.from_txt_file("rules.txt", to_dict=True)

    logging.basicConfig(level=logging.INFO)

    # load problems from the problems_file,
    problems = pr.Problem.from_txt_file(
        "problems_datasets/examples.txt", to_dict=True, translate=False
    )
    out_folder_path = Path("./ddar_results/")
    out_folder_path.mkdir(exist_ok=True)
    for problem_name, problem in problems.items():
        if problem_name != "incenter_excenter":
            continue
        logging.info(f"Starting problem {problem_name} with ddar only.")
        graph, _ = gh.Graph.build_problem(problem, DEFINITIONS)

        problem_output_path = out_folder_path / problem_name
        run_ddar(graph, problem, problem_output_path)
        graph.dependency_graph.show_html(
            problem_output_path / f"{problem_name}.dependency_graph.html",
            RULES,
        )
        return


def run_ddar(graph: gh.Graph, problem: pr.Problem, out_folder: Optional[Path]) -> bool:
    """Run DD+AR.

    Args:
      g: gh.Graph object, containing the proof state.
      p: pr.Problem object, containing the problem statement.
      out_file: path to output file if solution is found.

    Returns:
      Boolean, whether DD+AR finishes successfully.
    """
    solve(graph, RULES, problem, max_level=1000)

    goal_args = graph.names2nodes(problem.goal.args)
    if not graph.check(problem.goal.name, goal_args):
        logging.info(f"DD+AR failed to solve the problem {problem.url}.")
        return False

    outfile = (
        out_folder / f"{problem.url}_proof_steps.txt"
        if out_folder is not None
        else None
    )
    write_solution(graph, problem, outfile)

    gh.nm.draw(
        graph.type2nodes[gh.Point],
        graph.type2nodes[gh.Line],
        graph.type2nodes[gh.Circle],
        graph.type2nodes[gh.Segment],
        save_to=str(out_folder / f"{problem.url}_proof_figure.png"),
        block=False,
    )
    return True


if __name__ == "__main__":
    main()
