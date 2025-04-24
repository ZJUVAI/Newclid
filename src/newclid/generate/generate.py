import multiprocessing
import logging
import os
import sys
import argparse
import csv
import random
import time

from newclid.agent.ddarn import DDARN
from newclid.api import GeometricSolverBuilder
from newclid.configs import default_defs_path, default_rules_path
from newclid.generate.clause_generation import CompoundClauseGen
from newclid.formulations.definition import DefinitionJGEX
from tests.fixtures import build_until_works
from newclid.proof_writing import return_proof_steps

def write_data(all_data, dir, search_depth):
    """Write all generated data to output files."""
    filename = os.path.join(dir, f"geometry_depth{search_depth}_raw.csv")
    os.makedirs(os.path.dirname(filename), exist_ok=True)

    with open(filename, "w", newline="", encoding="utf-8") as csvfile:
        field_names = [
            "id",
            "n_clauses",
            "fl_problem",
            "nl_problem",
            "nl_solution",
            "dsl",
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
            out_f.write(f"{i}\n{row['fl_problem']}\n")

    # Write to llm.txt
    with open(
        os.path.join(dir, f"geometry_depth{search_depth}_llm.txt"),
        "w",
        encoding="utf-8",
    ) as out_f:
        for row in all_data:
            out_f.write(row["dsl"] + "\n")

    return len(all_data)

def run(args):
    # fl_statement = 'A B C D = trapezoid A B C D; E = on_tline E C B A, eqdistance E A C D; F G = trisegment F G A D; H I J = triangle H I J; K = on_line K B H, angle_bisector K A J I; L = on_bline L J D; M = on_bline M C B, eqangle3 M A F G K E; N = on_circle N G F, on_circle N E F; O = intersection_cc O A F K; P = on_pline P I K N, eqdistance P H F M; Q R = square F G Q R; S T U = r_triangle S T U; V = on_line V P G, on_bline V N O ? eqangle A D S U G Q S T'
    pid, fl_statement, search_depth = args
    random.seed(pid)

    # Create a list to store the generated data
    generated_data = []

    solver_builder = GeometricSolverBuilder(seed=998244353)
    solver_builder.load_defs_from_file(default_defs_path())
    solver_builder.load_rules_from_file(default_rules_path())
    solver_builder.with_deductive_agent(DDARN())
    solver_builder.load_problem_from_txt(fl_statement)
    
    # Find goals
    try:
        solver = build_until_works(builder=solver_builder)
    except Exception as e:
        logging.info(f"Error: {e}")
        return []
    solver.run()
    logging.info(f"Run infos: {solver.run_infos}")
    goals = solver.proof.dep_graph.conclusions()

    # Shave the problem according to the goal
    for goal in goals:
        solver.proof.goals = [goal]
        essential_clauses, essential_aux_clauses = solver.proof.dep_graph.get_essential_clauses([goal])
        statements: list[str] = []
        for clause in solver_builder.problemJGEX.constructions:
            if str(clause) in essential_clauses or str(clause) in essential_aux_clauses:
                statements.append(str(clause))
        shaved_problem = '; '.join(statements) + ' ? ' + goal.predicate.NAME + ' ' + ' '.join([arg.name for arg in goal.args])
        # import pdb; pdb.set_trace()

        # Solve the shaved problem
        solver_builder_shaved = GeometricSolverBuilder(seed=998244353)
        solver_builder_shaved.load_defs_from_file(default_defs_path())
        solver_builder_shaved.load_rules_from_file(default_rules_path())
        solver_builder_shaved.with_deductive_agent(DDARN())
        solver_builder_shaved.load_problem_from_txt(shaved_problem)
        try:
            solver_shaved = solver_builder_shaved.build()
            # solver = build_until_works(builder=solver_builder)
        except Exception as e:
            logging.info(f"Error: {e}")
            continue

        success = solver_shaved.run()
        if success is False:
            logging.info(f"Connot shave the problem {shaved_problem}")
            continue
        else:
            nl_solution = return_proof_steps(solver_shaved.proof)

            generated_data.append({
                "n_clauses": len(solver_builder.problemJGEX.constructions),
                "fl_problem": shaved_problem,
                "nl_problem": "",
                "nl_solution": nl_solution,
                "dsl": "",
            })

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

    cc_gen = CompoundClauseGen(
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
        while len(all_data) < args.n_samples:
            result = run(next(task_iterator))
            all_data.extend(result)
            if result:
                logging.info(
                    f"Generated {len(all_data)} samples in {time.time() - start:.1f}s "
                    f"({(time.time() - start)/len(all_data):.1f}s/sample)"
                )
    else:
        with multiprocessing.Pool(args.n_threads) as pool:
            for result in pool.imap_unordered(run, task_generator):
                all_data.extend(result)
                if result:
                    logging.info(
                        f"Generated {len(all_data)} samples in {time.time() - start:.1f}s "
                        f"({(time.time() - start)/len(all_data):.1f}s/sample)"
                    )
                if len(all_data) >= args.n_samples:
                    pool.terminate()
                    pool.join()
                    break

    # Write results
    n_problems = write_data(all_data, args.dir, args.search_depth)
