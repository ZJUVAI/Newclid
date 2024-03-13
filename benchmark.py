import logging
from pathlib import Path
from typing import Optional

from networkx import Graph
from pyvis.network import Network

from geosolver.ddar import solve
from geosolver.geometry import Circle, Line, Point, Segment
from geosolver.proof_graph import ProofGraph
from geosolver.numericals import draw
from geosolver.problem import Definition, Problem, Theorem
from geosolver.proof_writing import write_solution

DEFINITIONS = None  # contains definitions of construction actions
RULES = None  # contains rules of deductions


def main():
    global DEFINITIONS
    global RULES

    # definitions of terms used in our domain-specific language.
    DEFINITIONS = Definition.from_txt_file("defs.txt", to_dict=True)
    # load inference rules used in DD.
    RULES = Theorem.from_txt_file("rules.txt", to_dict=True)

    logging.basicConfig(level=logging.INFO)

    # load problems from the problems_file,
    problems = Problem.from_txt_file(
        "problems_datasets/examples.txt", to_dict=True, translate=False
    )
    out_folder_path = Path("./ddar_results/")
    out_folder_path.mkdir(exist_ok=True)
    for problem_name, problem in problems.items():
        if problem_name != "orthocenter_consequence_aux":
            continue
        logging.info(f"Starting problem {problem_name} with ddar only.")
        graph, _ = ProofGraph.build_problem(problem, DEFINITIONS)

        problem_output_path = out_folder_path / problem_name
        run_ddar(graph, problem, problem_output_path)

        draw_elements_graph(
            graph, problem_output_path / f"{problem_name}.elements_graph.html"
        )

        graph.dependency_graph.show_html(
            problem_output_path / f"{problem_name}.dependency_graph.html",
            RULES,
        )
        return


def run_ddar(graph: ProofGraph, problem: Problem, out_folder: Optional[Path]) -> bool:
    """Run DD+AR.

    Args:
      g: Graph object, containing the proof state.
      p: Problem object, containing the problem statement.
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

    draw(
        graph.type2nodes[Point],
        graph.type2nodes[Line],
        graph.type2nodes[Circle],
        graph.type2nodes[Segment],
        save_to=str(out_folder / f"{problem.url}_proof_figure.png"),
        block=False,
    )
    return True


def draw_elements_graph(graph: ProofGraph, html_path: Path):
    nt = Network("1080px")
    # populates the nodes and edges data structures
    nx_graph = Graph()
    for node_type, nodes in graph.type2nodes.items():
        type_name = node_type.__name__
        for node in nodes:
            nx_graph.add_node(node.name, title=type_name, group=type_name)
            for neighbor_type in graph.type2nodes.keys():
                neighbor_type_name = neighbor_type.__name__
                for neighbor in node.neighbors(neighbor_type):
                    nx_graph.add_node(
                        neighbor.name,
                        title=neighbor_type_name,
                        group=neighbor_type_name,
                    )
                    nx_graph.add_edge(neighbor.name, node.name)

    nt.from_nx(nx_graph)
    nt.show(str(html_path), notebook=False)


if __name__ == "__main__":
    main()
