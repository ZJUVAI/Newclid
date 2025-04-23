from newclid.agent.ddarn import DDARN
from newclid.api import GeometricSolverBuilder
from newclid.generate.clause_generation import CompoundClauseGen
from newclid.formulations.definition import DefinitionJGEX
from newclid.generate.shave import find_essential_clauses
from tests.fixtures import build_until_works
from newclid.proof_writing import return_proof_steps

import multiprocessing
import logging
import os

import argparse
import csv
import random
import time

logger = logging.getLogger("generation")


def write_data(all_data, dir, search_depth):
    """Write all generated data to output files."""
    filename = os.path.join(dir, f"geometry_depth{search_depth}_raw.csv")
    os.makedirs(os.path.dirname(filename), exist_ok=True)

    with open(filename, "w", newline="", encoding="utf-8") as csvfile:
        field_names = [
            "id",
            "n_clauses",
            "fl_statement",
            "nl_statement",
            "nl_solution",
            "data",
        ]
        writer = csv.DictWriter(
            csvfile, fieldnames=field_names, quoting=csv.QUOTE_MINIMAL, quotechar='"'
        )
        writer.writeheader()

        for i, row in enumerate(all_data):
            row["id"] = i
            writer.writerow(row)

    # Write to pr.txt
    with open(
        os.path.join(dir, f"geometry_depth{search_depth}_pr.txt"), "w", encoding="utf-8"
    ) as out_f:
        for i, row in enumerate(all_data):
            out_f.write(f"{i}\n{row['fl_statement']}\n")

    # Write to llm.txt
    with open(
        os.path.join(dir, f"geometry_depth{search_depth}_llm.txt"),
        "w",
        encoding="utf-8",
    ) as out_f:
        for row in all_data:
            out_f.write(row["data"] + "\n")

    return len(all_data)


def format_statement(stmt):
    """将Statement对象的字符串表示格式化为所需格式"""
    stmt_str = str(stmt)
    # 提取谓词名称（如"simtri"）
    predicate = stmt_str.split("[")[0]
    # 提取参数并去除方括号和逗号
    if "[" in stmt_str and "]" in stmt_str:
        args = stmt_str.split("[")[1].split("]")[0]
        args = args.replace(",", " ").replace("  ", " ").strip()
        return f"{predicate} {args}"
    else:
        return stmt_str  # 保留原始格式


def run(args):
    # fl_statement = 'A B C D = trapezoid A B C D; E = on_tline E C B A, eqdistance E A C D; F G = trisegment F G A D; H I J = triangle H I J; K = on_line K B H, angle_bisector K A J I; L = on_bline L J D; M = on_bline M C B, eqangle3 M A F G K E; N = on_circle N G F, on_circle N E F; O = intersection_cc O A F K; P = on_pline P I K N, eqdistance P H F M; Q R = square F G Q R; S T U = r_triangle S T U; V = on_line V P G, on_bline V N O ? eqangle A D S U G Q S T'
    pid, fl_statement, search_depth = args
    random.seed(pid)
    # Set up logging
    # Load definitions and rules
    # logging.basicConfig(level=logging.WARNING)
    solver_builder = GeometricSolverBuilder(seed=998244353)
    solver_builder.load_defs_from_file("../default_configs/defs.txt")
    solver_builder.load_rules_from_file("../default_configs/rules.txt")
    # agent = AGENTS_REGISTRY['ddarn']
    # solver_builder.with_deductive_agent(agent())
    # Create a list to store the generated data
    generated_data = []

    # Find goals
    # agent = AGENTS_REGISTRY["ddarn"]
    solver_builder.with_deductive_agent(DDARN())
    solver_builder.load_problem_from_txt(fl_statement)
    try:
        solver = build_until_works(builder=solver_builder)
    except Exception as e:
        logger.info(f"Error: {e}")
        return []

    # solver.draw_figure(out_file="test/construction_figure.svg")
    solver.run()
    logging.info(f"Run infos: {solver.run_infos}")

    # solver.write_all_outputs(Path('test/'))
    goals = solver.proof.dep_graph.conclusions()
    formatted_goals = [format_statement(goal) for goal in goals]
    for goal in formatted_goals:
        fl_problem = fl_statement + " ? " + str(goal)
        solver_builder.load_problem_from_txt(fl_problem)
        try:
            solver = build_until_works(builder=solver_builder)
        except Exception as e:
            logger.info(f"Error: {e}")
            continue

        success = solver.run()
        if success is False:
            logging.info(f"Connot shave the problem {fl_problem}")
            continue
        main_clauses, else_clauses = solver.proof.dep_graph.get_essential_clauses(
            solver.goals
        )

        essential_aux_clauses = find_essential_clauses(
            solver.proof.dep_graph, solver_builder.problemJGEX, solver.goals
        )

        n_clauses = len(main_clauses) + len(essential_aux_clauses)
        nl_solution = return_proof_steps(solver.proof)

        generated_data.append(
            {
                "n_clauses": n_clauses,
                "fl_statement": fl_problem,
                "nl_statement": "",
                "nl_solution": nl_solution.strip('"'),
                "data": "",
            }
        )

    return generated_data


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Create problem fl - nl dataset")
    parser.add_argument("--max_clauses", required=True, type=int, default=5)
    parser.add_argument(
        "--search_depth",
        required=True,
        type=int,
        help="How many steps will the DDAR search through.",
    )
    parser.add_argument("--n_threads", required=False, type=int, default=1)
    parser.add_argument("--n_samples", required=False, type=int, default=5)
    parser.add_argument("--dir", default="dataset")
    parser.add_argument(
        "--log_level", default="info", choices=["debug", "info", "warning", "error"]
    )
    args = parser.parse_args()

    definitions = DefinitionJGEX.to_dict(
        DefinitionJGEX.parse_txt_file("../default_configs/defs.txt")
    )

    cc_gen = CompoundClauseGen(
        definitions,
        max_comma_sep_clause=2,  # setting max_comma_sep_clause > 3 is meaningless
        max_single_clause=1,
        max_sets=args.max_clauses,
        seed=0,
        shuffle_var_names=False,
    )

    # Create task generator
    task_generator = (
        (i, cc_gen.generate_clauses(), args.search_depth) for i in range(10**9)
    )

    # Generate data
    all_data = []
    start = time.time()
    if args.n_threads == 1:
        task_iterator = iter(task_generator)
        # while len(all_data) < args.n_samples:
        for _ in range(args.n_samples):
            result = run(next(task_iterator))
            all_data.extend(result)
            if result:
                logger.info(
                    f"Generated {len(all_data)} samples in {time.time() - start:.1f}s "
                    f"({(time.time() - start)/len(all_data):.1f}s/sample)"
                )
    else:
        with multiprocessing.Pool(args.n_threads) as pool:
            idx = 0
            for result in pool.imap_unordered(run, task_generator):
                idx += 1
                all_data.extend(result)
                if result:
                    logger.info(
                        f"Generated {len(all_data)} samples in {time.time() - start:.1f}s "
                        f"({(time.time() - start)/len(all_data):.1f}s/sample)"
                    )
                # if len(all_data) >= args.n_samples:
                if idx >= args.n_samples:
                    pool.terminate()
                    pool.join()
                    break

    # Write results
    n_problems = write_data(all_data, args.dir, args.search_depth)
