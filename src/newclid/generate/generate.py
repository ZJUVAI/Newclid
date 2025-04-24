import multiprocessing
import logging
import os
import argparse
import csv
import random
import time
from typing import Iterator, Dict, Any

from newclid.agent.ddarn import DDARN
from newclid.api import GeometricSolverBuilder
from newclid.configs import default_defs_path, default_rules_path
from newclid.generate.clause_generation import CompoundClauseGen
from newclid.proof_writing import return_proof_steps


class GeometryGenerator:
    def __init__(self, max_clauses=5, search_depth=5, n_threads=1, output_dir="dataset"):
        self.max_clauses = max_clauses
        self.search_depth = search_depth
        self.n_threads = n_threads
        self.output_dir = output_dir
        
        self.clauses_generator = CompoundClauseGen(
            max_comma_sep_clause=2,
            max_single_clause=1,
            max_sets=self.max_clauses,
            seed=0,
            shuffle_var_names=False,
        )

    def write_data(self, all_data: list) -> int:
        """Write all generated data to output files."""
        filename = os.path.join(self.output_dir, f"geometry_depth{self.search_depth}_raw.csv")
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
            os.path.join(self.output_dir, f"geometry_depth{self.search_depth}_pr.txt"), 
            "w", 
            encoding="utf-8"
        ) as out_f:
            for i, row in enumerate(all_data):
                out_f.write(f"{i}\n{row['fl_problem']}\n")

        # Write to dsl.txt
        with open(
            os.path.join(self.output_dir, f"geometry_depth{self.search_depth}_dsl.txt"),
            "w",
            encoding="utf-8",
        ) as out_f:
            for row in all_data:
                out_f.write(row["dsl"] + "\n")

        return len(all_data)

    def process_single_problem(self, args: tuple) -> list:
        """Process a single geometry problem."""
        pid, fl_statement, search_depth = args
        random.seed(pid)

        solver_builder = GeometricSolverBuilder(seed=998244353)
        solver_builder.load_defs_from_file(default_defs_path())
        solver_builder.load_rules_from_file(default_rules_path())
        solver_builder.with_deductive_agent(DDARN())
        solver_builder.load_problem_from_txt(fl_statement)
        
        try:
            solver = solver_builder.build()
        except Exception as e:
            logging.info(f"Error: {e}")
            return []
            
        solver.run()
        goals = solver.proof.dep_graph.conclusions()

        generated_data = []
        for goal in goals:
            solver.proof.goals = [goal]
            essential_clauses, essential_aux_clauses = solver.proof.dep_graph.get_essential_clauses([goal])
            statements = []
            for clause in solver_builder.problemJGEX.constructions:
                if str(clause) in essential_clauses or str(clause) in essential_aux_clauses:
                    statements.append(str(clause))
            shaved_problem = '; '.join(statements) + ' ? ' + goal.predicate.NAME + ' ' + ' '.join([arg.name for arg in goal.args])

            solver_builder_shaved = GeometricSolverBuilder(seed=998244353)
            solver_builder_shaved.load_defs_from_file(default_defs_path())
            solver_builder_shaved.load_rules_from_file(default_rules_path())
            solver_builder_shaved.with_deductive_agent(DDARN())
            solver_builder_shaved.load_problem_from_txt(shaved_problem)
            
            try:
                solver_shaved = solver_builder_shaved.build()
            except Exception as e:
                logging.info(f"Error: {e}")
                continue

            success = solver_shaved.run()
            if success is False:
                logging.info(f"Cannot shave the problem {shaved_problem}")
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

    def generate_problems(self) -> Iterator[Dict[str, Any]]:
        """Generate geometry problems one at a time using a generator."""
        task_generator = (
            (i, self.clauses_generator.generate_clauses(), self.search_depth) 
            for i in range(10**9)
        )

        if self.n_threads == 1:
            task_iterator = iter(task_generator)
            while True:
                result = self.process_single_problem(next(task_iterator))
                if result:
                    for problem in result:
                        yield problem

        else:
            with multiprocessing.Pool(self.n_threads) as pool:
                for result in pool.imap_unordered(self.process_single_problem, task_generator):
                    if result:
                        for problem in result:
                            yield problem


def main():
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
        "--log_level", 
        default="warning", 
        choices=["debug", "info", "warning", "error"],
    )
    args = parser.parse_args()

    log_level = getattr(logging, args.log_level.upper())
    logging.basicConfig(level=log_level)

    generator = GeometryGenerator(
        max_clauses=args.max_clauses,
        search_depth=args.search_depth,
        n_threads=args.n_threads,
        output_dir=args.dir,
    )
    
    # Collect problems using the generator
    all_data = []
    start_time = time.time()
    
    for problem in generator.generate_problems():
        all_data.append(problem)
        logging.info(
            f"Generated {len(all_data)} samples in {time.time() - start_time:.1f}s "
            f"({(time.time() - start_time)/len(all_data):.1f}s/sample)"
        )
        if len(all_data) >= args.n_samples:
            break
    
    # Write the collected data
    generator.write_data(all_data)
    logging.info(f"Generated {len(all_data)} problems successfully")


if __name__ == "__main__":
    main()
