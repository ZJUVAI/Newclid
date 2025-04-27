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
from newclid.api import GeometricSolverBuilder, GeometricSolver
from newclid.configs import default_defs_path, default_rules_path
from newclid.dependencies.symbols import Point
from newclid.dependencies.dependency_graph import DependencyGraph
from newclid.generation.clause_generation import CompoundClauseGen
from newclid.proof_writing import return_proof_steps
from newclid.statement import Statement
from newclid.formulations.problem import ProblemJGEX
from newclid.formulations.rule import Rule
from newclid.predicates import NAME_TO_PREDICATE

class GeometryGenerator: 
    def __init__(self, max_clauses=5, search_depth=5, n_threads=1, output_dir="dataset", min_proof_steps=5, min_clauses_num=3):
        self.max_clauses = max_clauses
        self.search_depth = search_depth
        self.n_threads = n_threads
        self.output_dir = output_dir
        self.min_proof_steps = min_proof_steps
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
                if conclusion[0] in ['PythagoreanConclusions', 'rconst', 'aconst', 'eqratio3']:
                    continue
                new_predicate = (conclusion[0], len(conclusion) - 1)
                predicates.add(new_predicate)

        return predicates
    
    def all_possible_goals(self, points: list[str], dep_graph: DependencyGraph) -> set[Statement]:
        goals: set[Statement] = set()
        for name, num_args in self.predicates:
            for point_list in itertools.product(points, repeat=num_args):
                tokens = tuple([name] + list(point_list))
                pred = NAME_TO_PREDICATE[tokens[0]]
                parsed = pred.parse(tokens[1:], dep_graph)
                if parsed:
                    goal = Statement(pred, parsed, dep_graph)
                    if goal and goal.check():
                        goals.add(goal)
        return goals

    def clauses_num_filter(self, problemJGEX: ProblemJGEX) -> bool:
        if len(problemJGEX.constructions) < self.min_clauses_num:
            logging.debug(f"Too few clauses: {len(problemJGEX.constructions)}")
            return True
        else:
            return False
    
    def naive_proof_filter(self, solver: GeometricSolver, goal: Statement) -> bool:
        (
            points,
            premises,
            numercial_checked_premises,
            aux_points,
            aux,
            numercial_checked_aux,
            proof_steps,
        ) = solver.proof.dep_graph.get_proof_steps([goal])
        if len(proof_steps) < self.min_proof_steps:
            logging.debug(f"Naive proof: {goal}")
            return True
        else:
            return False
            # connot detect proof of the goal
            # rconst[b,c,c,e,Fraction(2, 1),]
    
    def naive_goal_filter(self, goal):
        predicate = goal.predicate.NAME
        args = goal.args
        if args[-1] == '':
            args = args[:-1]
        # case: cong AB = AB, para AB ∥∥ AB, rconst AB:AB=1, aconst ∠AB AB=0
        if predicate == 'cong' or predicate == 'para' or predicate == 'rconst' or predicate == 'aconst':
            left = {args[0], args[1]}
            right = {args[2], args[3]}
            if left == right:
                return True
        elif predicate == 'eqratio':
            seg_1 = {args[0], args[1]}
            seg_2 = {args[2], args[3]}
            seg_3 = {args[4], args[5]}
            seg_4 = {args[6], args[7]}
            #case: eqratio AB/CD = DC/BA
            if seg_1 == seg_3 and seg_2 == seg_4:
                return True
            if seg_1 == seg_4 and seg_2 == seg_3:
                return True
            # AB/AB = CD/EF => cong CD = EF
            if seg_1 == seg_2 or seg_3 == seg_4: 
                return True
        elif predicate == 'eqangle':
            #case: eqangle ∠AB CD = ∠DC/BA
            seg_1 = {args[0], args[1]}
            seg_2 = {args[2], args[3]}
            seg_3 = {args[4], args[5]}
            seg_4 = {args[6], args[7]}
            if seg_1 == seg_3 and seg_2 == seg_4:
                return True
            if seg_1 == seg_4 and seg_2 == seg_3:
                return True
        elif predicate == 'simtri':
            #case: simtri △ABC ≅ △ABC
            tri_1 = {args[0], args[1], args[2]}
            tri_2 = {args[3], args[4], args[5]}
            if tri_1 == tri_2:
                return True
        return False

    def process_single_problem(self, args: tuple) -> list:
        """Process a single geometry problem."""
        pid, fl_statement = args
        
        solver_builder = GeometricSolverBuilder(seed=998244353)
        solver_builder.with_deductive_agent(DDARN())
        solver_builder.load_problem_from_txt(fl_statement)

        if self.clauses_num_filter(solver_builder.problemJGEX):
            return []
        
        try:
            solver = solver_builder.build(max_attempts=100)
        except Exception as e:
            logging.info(f"Error: {e}")
            return []
        solver.run(max_level=self.search_depth)
        points = [p.name for p in solver.proof.dep_graph.symbols_graph.nodes_of_type(Point)]
        possible_goals = list(self.all_possible_goals(points, solver.proof.dep_graph) | set(solver.proof.dep_graph.conclusions()))

        generated_data = []
        for goal in possible_goals:
            # filter
            if self.naive_goal_filter(goal):
                continue
            if self.naive_proof_filter(solver, goal):
                continue
            
            # fl_problem
            essential_clauses, essential_aux_clauses = solver.proof.dep_graph.get_essential_clauses([goal])
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
            if self.clauses_num_filter(renamed_problem):
                continue
            n_clauses = len(renamed_problem.constructions)
            
            # output
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
            (i, self.clauses_generator.generate_clauses()) 
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


def main():
    parser = argparse.ArgumentParser(description="Create problem fl - nl dataset")
    parser.add_argument("--max_clauses", required=True, type=int, default=10)
    parser.add_argument("--search_depth", required=True, type=int)
    parser.add_argument("--min_proof_steps", required=False, type=int, default=3)
    parser.add_argument("--min_clauses_num", required=False, type=int, default=2)
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
        min_proof_steps=args.min_proof_steps,
        min_clauses_num=args.min_clauses_num,
    )
    
    # Collect problems using the generator
    all_data = []
    start_time = time.time()
    for problem in generator.generate_problems():
        all_data.append(problem)
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
