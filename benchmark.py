import cProfile
import logging
from pathlib import Path


from geosolver.api import GeometricSolverBuilder
from geosolver.proof import Proof
from geosolver.statement.adder import IntrinsicRules


def main():
    logging.basicConfig(level=logging.INFO)

    # load problems from the problems_file,

    problem_name = "orthocenter_aux"
    solver = (
        GeometricSolverBuilder()
        .load_problem_from_file(
            "problems_datasets/examples.txt", problem_name, translate=False
        )
        .build()
    )
    out_folder_path = Path("./ddar_results/")
    out_folder_path.mkdir(exist_ok=True)

    logging.info(f"Starting problem {problem_name} with ddar only.")
    solver.proof_state, _ = Proof.build_problem(
        solver.problem,
        solver.defs,
        disabled_intrinsic_rules=[
            IntrinsicRules.PARA_FROM_PERP,
            IntrinsicRules.CYCLIC_FROM_CONG,
            IntrinsicRules.CONG_FROM_EQRATIO,
            IntrinsicRules.PARA_FROM_EQANGLE,
        ],
    )
    problem_output_path = out_folder_path / problem_name
    problem_output_path.mkdir(exist_ok=True)

    solver.proof_state.symbols_graph.draw_figure(
        problem_output_path / f"{problem_name}_construction_figure.png",
    )

    cProfile.runctx(
        "solver.run()",
        globals=globals(),
        locals=locals(),
        filename=str(problem_output_path / f"{problem_name}.prof"),
    )

    solver.write_solution(
        problem_output_path / f"{problem_name}_proof_steps.txt",
    )

    solver.proof_state.symbols_graph.draw_figure(
        problem_output_path / f"{problem_name}_proof_figure.png",
    )

    solver.proof_state.symbols_graph.draw_html(
        problem_output_path / f"{problem_name}.symbols_graph.html"
    )

    solver.proof_state.dependency_graph.show_html(
        problem_output_path / f"{problem_name}.dependency_graph.html",
        solver.rules,
    )

    solver.proof_state.dependency_graph.proof_subgraph.show_html(
        problem_output_path / f"{problem_name}.proof_subgraph.html",
        solver.rules,
    )


if __name__ == "__main__":
    main()
