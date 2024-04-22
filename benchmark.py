import logging
from pathlib import Path


from geosolver.api import GeometricSolverBuilder
from geosolver.statement.adder import IntrinsicRules


def main():
    logging.basicConfig(level=logging.INFO)

    problem_file = "problems_datasets/examples.txt"
    problem_name = "orthocenter_consequence_aux"
    solver = (
        GeometricSolverBuilder()
        .load_problem_from_file(problem_file, problem_name, translate=False)
        .with_disabled_intrinsic_rules(
            [
                IntrinsicRules.PARA_FROM_PERP,
                IntrinsicRules.CYCLIC_FROM_CONG,
                IntrinsicRules.CONG_FROM_EQRATIO,
                IntrinsicRules.PARA_FROM_EQANGLE,
            ]
        )
        .build()
    )

    out_folder_path = Path("./ddar_results/") / problem_name

    logging.info(f"Starting problem {problem_name} with ddar only.")

    problem_output_path = out_folder_path
    problem_output_path.mkdir(exist_ok=True)

    solver.draw_figure(
        problem_output_path / f"{problem_name}_construction_figure.png",
    )

    max_steps = 100000
    timeout = 600.0
    success = solver.run(max_steps, timeout)

    if success:
        logging.info(f"Solved {problem_name}: {solver.run_infos}")
    else:
        logging.info(f"Failed at problem {problem_name}: {solver.run_infos}")
    solver.write_all_outputs(problem_output_path)


if __name__ == "__main__":
    main()
