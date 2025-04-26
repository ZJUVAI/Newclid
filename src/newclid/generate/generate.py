import multiprocessing
import logging
import os
import argparse
import csv
import random
import time
from typing import Iterator, Dict, Any
from pathlib import Path
import itertools

from newclid.agent.ddarn import DDARN
from newclid.api import GeometricSolverBuilder
from newclid.configs import default_defs_path, default_rules_path
from newclid.dependencies.symbols import Point
from newclid.dependencies.dependency_graph import DependencyGraph
from newclid.generate.clause_generation import CompoundClauseGen
from newclid.proof_writing import return_proof_steps
from newclid.statement import Statement
from newclid.formulations.problem import ProblemJGEX
from newclid.formulations.rule import Rule

class GeometryGenerator: 
    def __init__(self, max_clauses=5, search_depth=5, n_threads=1, output_dir="dataset", min_dep_num=10, min_clauses_num=3):
        self.max_clauses = max_clauses
        self.search_depth = search_depth
        self.n_threads = n_threads
        self.output_dir = output_dir
        self.min_dep_num = min_dep_num
        self.min_clauses_num = min_clauses_num
        self.predicates = self.load_predicates()

        self.clauses_generator = CompoundClauseGen(
            max_comma_sep_clause=2,
            max_single_clause=1,
            max_sets=self.max_clauses,
            seed=0,
            shuffle_var_names=False,
        )

    def load_predicates(self, rule_path: Path = default_rules_path()) -> set[tuple[str, int]]:
        predicates: set[tuple[str, int]] = set()
        rules = list(Rule.parse_txt_file(rule_path))

        for theorem in rules:
            for conclusion in theorem.conclusions:
                if conclusion[0] in ['PythagoreanConclusions', 'rconst', 'aconst']:
                    continue
                new_predicate = (conclusion[0], len(conclusion) - 1)
                predicates.add(new_predicate)

        return predicates

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
                "fl_problem_renamed",
                "dsl_problem_renamed"
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
                out_f.write(f"{i}\n{row['fl_problem_renamed']}\n")

        # Write to dsl.txt
        with open(
            os.path.join(self.output_dir, f"geometry_depth{self.search_depth}_dsl.txt"),
            "w",
            encoding="utf-8",
        ) as out_f:
            for row in all_data:
                out_f.write(row["dsl_problem_renamed"] + "\n")

        return len(all_data)

    def is_naive_goal(self, goal):
        predicate = goal.predicate
        args = goal.args
        if args[-1] == '':
            args = args[:-1]
        # case1: cong AB = AB, para AB ∥∥ AB, rconst AB:AB=1, aconst ∠AB AB=0
        if predicate == 'cong' or predicate == 'para' or predicate == 'rconst' or predicate == 'aconst':
            left = {args[0], args[1]}
            right = {args[2], args[3]}
            if left == right:
                return True
        elif predicate == 'eqratio':
            #case2: eqratio AB/CD = DC/BA, eqangle ∠AB CD = ∠DC/BA
            seg_1 = {args[0], args[1]}
            seg_2 = {args[2], args[3]}
            seg_3 = {args[4], args[5]}
            seg_4 = {args[6], args[7]}
            if seg_1 == seg_3 and seg_2 == seg_4:
                return True
            if seg_1 == seg_4 and seg_2 == seg_3:
                return True
        return False

    def all_possible_goals(self, points: list[str], dep_graph: DependencyGraph) -> list[Statement]:
        goals: list[Statement] = []
        for name, num_args in self.predicates:
            for point_list in itertools.product(points, repeat=num_args):
                goal = Statement.from_tokens(tuple([name] + list(point_list)), dep_graph)
                if goal:
                    goals.append(goal)
        return goals

    def process_single_problem(self, args: tuple) -> list:
        """Process a single geometry problem."""
        pid, fl_statement, search_depth = args

        solver_builder = GeometricSolverBuilder(seed=998244353)
        solver_builder.load_defs_from_file(default_defs_path())
        solver_builder.load_rules_from_file(default_rules_path())
        solver_builder.with_deductive_agent(DDARN())
        solver_builder.load_problem_from_txt(fl_statement)

        if len(solver_builder.problemJGEX.constructions) < self.min_clauses_num:
            logging.info(f"Too few clauses: {len(solver_builder.problemJGEX.constructions)}")
            return []
        
        try:
            solver = solver_builder.build(max_attempts=100)
        except Exception as e:
            logging.info(f"Error: {e}")
            return []
        
        solver.run(max_level=self.search_depth)
        points = [p.name for p in solver.proof.dep_graph.symbols_graph.nodes_of_type(Point)]
        goals = self.all_possible_goals(points, solver.proof.dep_graph) + solver.proof.dep_graph.conclusions()
        goals = list(set(goals))

        generated_data = []
        for goal in goals:
            if not goal.check():
                continue
            try:
                if self.is_naive_goal(goal):
                    logging.info(f"Naive goal: {goal}")
                    continue
            except Exception as e:
                logging.info(f"Naive Goal Error: {goal}")
                continue
            try:
                if len(solver.proof.dep_graph.get_proof_steps([goal])) < self.min_dep_num:
                    logging.info(f"Naive proof: {goal}")
                    continue
            except Exception as e:
                logging.info(f"Naive proof Error: {goal}")
                continue
                # connot detect proof of the goal
                # rconst[b,c,c,e,Fraction(2, 1),]
            # fl_problem
            essential_clauses, essential_aux_clauses = solver.proof.dep_graph.get_essential_clauses([goal])
            n_clauses = len(essential_clauses) + len(essential_aux_clauses)
            if n_clauses < self.min_clauses_num:
                logging.debug(f"Naive clauses: {goal}")
                continue
            statements = []
            for clause in solver_builder.problemJGEX.constructions:
                if str(clause) in essential_clauses or str(clause) in essential_aux_clauses:
                    statements.append(str(clause))
            fl_problem = '; '.join(statements) + ' ? ' + goal.predicate.NAME + ' ' + ' '.join([arg.name for arg in goal.args])
            # nl_solution
            solver.proof.goals = [goal]
            nl_solution = return_proof_steps(solver.proof)
            # rename problem
            renamed_problem = ProblemJGEX.from_text(fl_problem).renamed()
            # output
            logging.info(f"fl_problem: {fl_problem}")
            generated_data.append({
                "n_clauses": n_clauses,
                "fl_problem": fl_problem,
                "nl_problem": "",
                "nl_solution": nl_solution,
                "fl_problem_renamed": str(renamed_problem),
                "dsl_problem_renamed": "",
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
    parser.add_argument("--max_clauses", required=True, type=int, default=10)
    parser.add_argument("--min_dep_num", required=False, type=int, default=10)
    parser.add_argument("--min_clauses_num", required=False, type=int, default=6)
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

    logging.basicConfig(level=getattr(logging, args.log_level.upper()))

    generator = GeometryGenerator(
        max_clauses=args.max_clauses,
        search_depth=args.search_depth,
        n_threads=args.n_threads,
        output_dir=args.dir,
        min_dep_num=args.min_dep_num,
        min_clauses_num=args.min_clauses_num,
    )
    
    # Collect problems using the generator
    all_data = []
    start_time = time.time()
    for problem in generator.generate_problems():
        all_data.append(problem)
        print(all_data)
        logging.debug(
            f"Generated {len(all_data)} samples in {time.time() - start_time:.1f}s "
            f"({(time.time() - start_time)/len(all_data):.1f}s/sample)"
        )
        if len(all_data) >= args.n_samples:
            break
    
    # Write the collected data
    generator.write_data(all_data)
    logging.debug(f"Generated {len(all_data)} problems successfully")


if __name__ == "__main__":
    main()
