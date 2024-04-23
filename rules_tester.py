import cProfile
import logging
from pathlib import Path


from geosolver.api import GeometricSolverBuilder
from geosolver.statement.adder import IntrinsicRules


def main():
    logging.basicConfig(level=logging.INFO)

    problem_file = "problems_datasets/testing_minimal_rules.txt"
    problem_name = "r42"
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
        .load_defs_from_file("src/geosolver/default_configs/new_defs.txt")
        .load_rules_from_file("src/geosolver/default_configs/rules.txt")
        .build()
    )

    out_folder_path = Path("./ddar_results/") / problem_name

    logging.info(f"Testing rule {problem_name} with ddar only.")

    problem_output_path = out_folder_path
    problem_output_path.mkdir(exist_ok=True)

    solver.draw_figure(
        problem_output_path / f"{problem_name}_construction_figure.png",
    )

    max_steps = 10000
    timeout = 600.0
    success = False
    cProfile.runctx(
        "solver.run(max_steps, timeout)",
        globals=globals(),
        locals=locals(),
        filename=str(problem_output_path / f"{problem_name}.prof"),
    )

    if solver.run_infos["success"]:
        logging.info(f"Solved {problem_name}: {solver.run_infos}")
    else:
        logging.info(f"Failed at {problem_name}: {solver.run_infos}")

    solver.write_all_outputs(problem_output_path)

    return


if __name__ == "__main__":
    main()
