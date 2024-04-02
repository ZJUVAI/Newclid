import cProfile
import logging
from pathlib import Path
from typing import Optional


from geosolver.ddar import solve
from geosolver.proof import Proof
from geosolver.problem import Definition, Problem, Theorem
from geosolver.proof_writing import write_solution
from geosolver.statement.adder import IntrisicRules

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
        if problem_name != "orthocenter_aux":
            continue
        logging.info(f"Starting problem {problem_name} with ddar only.")
        proof, _ = Proof.build_problem(
            problem,
            DEFINITIONS,
            disabled_intrinsic_rules=[
                IntrisicRules.PARA_FROM_PERP,
                IntrisicRules.CYCLIC_FROM_CONG,
                IntrisicRules.CONG_FROM_EQRATIO,
                IntrisicRules.PARA_FROM_EQANGLE,
            ],
        )
        problem_output_path = out_folder_path / problem_name
        problem_output_path.mkdir(exist_ok=True)

        proof.symbols_graph.draw_figure(
            problem_output_path / f"{problem.url}_construction_figure.png",
        )

        cProfile.runctx(
            "run_ddar(proof, problem, problem_output_path)",
            globals=globals(),
            locals=locals(),
            filename=str(problem_output_path / f"{problem.url}.prof"),
        )

        write_solution(
            proof,
            problem,
            problem_output_path / f"{problem.url}_proof_steps.txt",
        )

        proof.symbols_graph.draw_figure(
            problem_output_path / f"{problem.url}_proof_figure.png",
        )

        proof.symbols_graph.draw_html(
            problem_output_path / f"{problem.url}.symbols_graph.html"
        )

        proof.dependency_graph.show_html(
            problem_output_path / f"{problem.url}.dependency_graph.html",
            RULES,
        )

        proof.dependency_graph.proof_subgraph.show_html(
            problem_output_path / f"{problem.url}.proof_subgraph.html",
            RULES,
        )

        return


def run_ddar(proof: Proof, problem: Problem, out_folder: Optional[Path]) -> bool:
    """Run DD+AR.

    Args:
      proof: Proof state.
      p: Problem statement.
      out_file: path to output file if solution is found.

    Returns:
      Boolean, whether DD+AR finishes successfully.
    """
    solve(proof, RULES, problem, max_level=1000)
    goal_args = proof.symbols_graph.names2nodes(problem.goal.args)
    if not proof.check(problem.goal.name, goal_args):
        logging.info(f"DD+AR failed to solve the problem {problem.url}.")
        return False
    return True


if __name__ == "__main__":
    main()
