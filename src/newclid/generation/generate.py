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
from collections import defaultdict

from newclid.agent.ddarn import DDARN
from newclid.api import GeometricSolverBuilder, GeometricSolver
from newclid.configs import default_defs_path, default_rules_path
from newclid.dependencies.symbols import Point
from newclid.dependencies.dependency_graph import DependencyGraph
from newclid.generation.clause_generation import CompoundClauseGen
from newclid.proof_writing import return_proof_steps
from newclid.statement import Statement
from newclid.formulations.rule import Rule
from newclid.formulations.definition import DefinitionJGEX
from newclid.formulations.problem import ProblemJGEX
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
            return False
        else:
            return True
    
    def proof_filter(self, solver: GeometricSolver, goal: Statement) -> bool:
        try:
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
                return False
            else:
                return True
                # connot detect proof of the goal
                # rconst[b,c,c,e,Fraction(2, 1),]
        except Exception as e:
            logging.warning(f"error in get_proof_steps {goal}: {e}. Why?")
            return False
    
    def goal_filter(self, goal):
        predicate = goal.predicate.NAME
        args = goal.args
        if args[-1] == '':
            args = args[:-1]
        # case: cong AB = AB, para AB ∥∥ AB, rconst AB:AB=1, aconst ∠AB AB=0
        if predicate == 'cong' or predicate == 'para':# or predicate == 'rconst' or predicate == 'aconst':
            left = {args[0], args[1]}
            right = {args[2], args[3]}
            if left == right:
                return False
        elif predicate == 'eqratio':
            seg_1 = {args[0], args[1]}
            seg_2 = {args[2], args[3]}
            seg_3 = {args[4], args[5]}
            seg_4 = {args[6], args[7]}
            #case: eqratio AB/CD = DC/BA
            if seg_1 == seg_3 and seg_2 == seg_4:
                return False
            if seg_1 == seg_4 and seg_2 == seg_3:
                return False
            # AB/AB = CD/EF => cong CD = EF
            if seg_1 == seg_2 or seg_3 == seg_4: 
                return False
        elif predicate == 'eqangle':
            #case: eqangle ∠AB CD = ∠DC/BA
            seg_1 = {args[0], args[1]}
            seg_2 = {args[2], args[3]}
            seg_3 = {args[4], args[5]}
            seg_4 = {args[6], args[7]}
            if seg_1 == seg_3 and seg_2 == seg_4:
                return False
            if seg_1 == seg_4 and seg_2 == seg_3:
                return False
        elif predicate == 'simtri':
            #case: simtri △ABC ≅ △ABC
            tri_1 = {args[0], args[1], args[2]}
            tri_2 = {args[3], args[4], args[5]}
            if tri_1 == tri_2:
                return False
        elif predicate == 'aconst' or 'rconst':
            # AG1 do not support aconst and rconst
            return False
        return True

    def dsl(self, problem: ProblemJGEX, aux_points: list[str]) -> str:
        MAP_SYMBOL = {
                'T': 'perp',
                'P': 'para',
                'D': 'cong',
                'S': 'simtri',
                'I': 'circle',
                'M': 'midp',
                'O': 'cyclic',
                'C': 'coll',
                '^': 'eqangle',
                '/': 'eqratio',
                '%': 'eqratio',
                '=': 'contri',
                'X': 'collx',
                'A': 'acompute',
                'R': 'rcompute',
                'Q': 'fixc',
                'E': 'fixl',
                'V': 'fixb',
                'H': 'fixt',
                'Z': 'fixp',
                'Y': 'ind',
            }
        def _gcd(x: int, y: int) -> int:
            while y:
                x, y = y, x % y
            return x
        def simplify(n: int, d: int) -> tuple[int, int]:
            """given fraction n/d, simplify to smallest possible integers"""
            g = _gcd(n, d)
            return (n // g, d // g)
        def hashed_txt(name: str, args: list[str]) -> tuple[str, ...]:
            """Return a tuple unique to name and args up to arg permutation equivariant."""

            if name in ['const', 'aconst', 'rconst']:
                a, b, c, d, y = args
                a, b = sorted([a, b])
                c, d = sorted([c, d])
                return name, a, b, c, d, y

            if name in ['npara', 'nperp', 'para', 'cong', 'perp', 'collx']:
                a, b, c, d = args

                a, b = sorted([a, b])
                c, d = sorted([c, d])
                (a, b), (c, d) = sorted([(a, b), (c, d)])

                return (name, a, b, c, d)

            if name in ['midp', 'midpoint']:
                a, b, c = args
                b, c = sorted([b, c])
                return (name, a, b, c)

            if name in ['coll', 'cyclic', 'ncoll', 'diff', 'triangle']:
                return (name,) + tuple(sorted(list(set(args))))

            if name == 'circle':
                x, a, b, c = args
                return (name, x) + tuple(sorted([a, b, c]))

            if name in ['eqangle', 'eqratio', 'eqangle6', 'eqratio6']:
                a, b, c, d, e, f, g, h = args
                a, b = sorted([a, b])
                c, d = sorted([c, d])
                e, f = sorted([e, f])
                g, h = sorted([g, h])
                if tuple(sorted([a, b, e, f])) > tuple(sorted([c, d, g, h])):
                    a, b, e, f, c, d, g, h = c, d, g, h, a, b, e, f
                if (a, b, c, d) > (e, f, g, h):
                    a, b, c, d, e, f, g, h = e, f, g, h, a, b, c, d

                if name == 'eqangle6':
                    name = 'eqangle'
                if name == 'eqratio6':
                    name = 'eqratio'
                return (name,) + (a, b, c, d, e, f, g, h)

            if name in ['contri', 'simtri', 'simtri2', 'contri2', 'contri*', 'simtri*']:
                a, b, c, x, y, z = args
                (a, x), (b, y), (c, z) = sorted([(a, x), (b, y), (c, z)], key=sorted)
                (a, b, c), (x, y, z) = sorted([(a, b, c), (x, y, z)], key=sorted)
                return (name, a, b, c, x, y, z)

            if name in ['eqratio3']:
                a, b, c, d, o, o = args  # pylint: disable=redeclared-assigned-name
                (a, c), (b, d) = sorted([(a, c), (b, d)], key=sorted)
                (a, b), (c, d) = sorted([(a, b), (c, d)], key=sorted)
                return (name, a, b, c, d, o, o)

            if name in ['sameside', 's_angle']:
                return (name,) + tuple(args)

            raise ValueError(f"invalid construction name '{name}' to hash.")
        def pretty2a(a: str, b: str, c: str, d: str) -> str:
            if b in (c, d):
                a, b = b, a
            if a == d:
                c, d = d, c
            return f'{a} {b} {c} {d}'
        def pretty2r(a: str, b: str, c: str, d: str) -> str:
            if b in (c, d):
                a, b = b, a
            if a == d:
                c, d = d, c
            return f'{a} {b} {c} {d}'
        def pretty(txt: str) -> str:
            """Pretty formating a predicate string.
            
            e.g.
            >>> pretty('acompute Y a b c')
            """
            if isinstance(txt, str):
                txt = txt.split(' ')
            name, *args = txt
            if name == 'ind':
                return 'Y ' + ' '.join(args)
            if name in ['fixc', 'fixl', 'fixb', 'fixt', 'fixp']:
                return map_symbol_inv(name) + ' ' + ' '.join(args)
            if name == 'acompute':
                a, b, c, d = args
                return 'A ' + ' '.join(args)
            if name == 'rcompute':
                a, b, c, d = args
                return 'R ' + ' '.join(args)
            if name == 'aconst':
                a, b, c, d, y = args
                return f'^ {pretty2a(a, b, c, d)} {y}'
            if name == 'rconst':
                a, b, c, d, y = args
                return f'/ {pretty2r(a, b, c, d)} {y}'
            if name == 'coll':
                return 'C ' + ' '.join(args)
            if name == 'collx':
                return 'X ' + ' '.join(args)
            if name == 'cyclic':
                return 'O ' + ' '.join(args)
            if name in ['midp', 'midpoint']:
                x, a, b = args
                return f'M {x} {a} {b}'
            if name == 'eqangle':
                a, b, c, d, e, f, g, h = args
                return f'^ {pretty2a(a, b, c, d)} {pretty2a(e, f, g, h)}'
            if name == 'eqratio':
                a, b, c, d, e, f, g, h = args
                return f'/ {pretty2r(a, b, c, d)} {pretty2r(e, f, g, h)}'
            if name == 'eqratio3':
                a, b, c, d, o, o = args  # pylint: disable=redeclared-assigned-name
                return f'S {o} {a} {b} {o} {c} {d}'
            if name == 'cong':
                a, b, c, d = args
                return f'D {a} {b} {c} {d}'
            if name == 'perp':
                if len(args) == 2:  # this is algebraic derivation.
                    ab, cd = args  # ab = 'd( ... )'
                    return f'T {ab} {cd}'
                a, b, c, d = args
                return f'T {a} {b} {c} {d}'
            if name == 'para':
                if len(args) == 2:  # this is algebraic derivation.
                    ab, cd = args  # ab = 'd( ... )'
                    return f'P {ab} {cd}'
                a, b, c, d = args
                return f'P {a} {b} {c} {d}'
            if name in ['simtri2', 'simtri', 'simtri*']:
                a, b, c, x, y, z = args
                return f'S {a} {b} {c} {x} {y} {z}'
            if name in ['contri2', 'contri', 'contri*']:
                a, b, c, x, y, z = args
                return f'= {a} {b} {c} {x} {y} {z}'
            if name == 'circle':
                o, a, b, c = args
                return f'I {o} {a} {b} {c}'
            if name == 'foot':
                a, b, c, d = args
                return f'F {a} {b} {c} {d}'
            return ' '.join(txt)
        def map_symbol_inv(c: str) -> str:
            return {v: k for k, v in MAP_SYMBOL.items()}[c]
        
        defs = DefinitionJGEX.to_dict(DefinitionJGEX.parse_txt_file(default_defs_path()))
        
        # string = []
        # points_premise = set()
        data_tmp = defaultdict(list)
        for construction in problem.constructions:
            group = {}
            p2deps = defaultdict(list)
            for constr_sentence in construction.sentences:
                cdef = defs[constr_sentence[0]]
                if len(constr_sentence) == len(cdef.declare):
                    mapping = dict(zip(cdef.declare[1:], constr_sentence[1:]))
                else:
                    assert len(constr_sentence) + len(construction.points) == len(cdef.declare)
                    mapping = dict(zip(cdef.declare[1:], construction.points + constr_sentence[1:]))
                for points, bs in cdef.basics:
                    points = tuple([mapping[x] for x in points])
                    for p in points:
                        group[p] = points
                    for b in bs:
                        if b[0] == 'rconst' and constr_sentence[0] == 'triangle12':
                            args = [mapping[a] for a in b[1:][:-1]]
                            args.append(0.5)
                        else:
                            args = [mapping[a] for a in b[1:]]
                        name = b[0]
                        if b[0] in ['s_angle', 'aconst']:
                            x, y, z, v = args
                            name = 'aconst'
                            v = int(v)
                            if v < 0:
                                v = -v
                                x, z = z, x
                            m, n = simplify(int(v), 180)
                            args = [y, z, y, x, f'{m}pi/{n}']

                        p2deps[points].append(hashed_txt(name, args))

            points = construction.points
            while points:
                p = points[0]
                gr = group[p]
                points = [x for x in points if x not in gr]

                deps_str = []
                for dep in p2deps[gr]:
                    dep_str = pretty(dep)

                    if dep[0] == 'aconst':
                        m, n = map(int, dep[-1].split('pi/'))
                        mn = f'{m}. pi / {n}.'
                        dep_str = ' '.join(dep_str.split()[:-1] + [mn])
                    deps_str.append(dep_str)
                
                data_tmp[' '.join(gr)] = deps_str

        data = '{S} '
        ref = 0
        string_premise = []
        for k, v in data_tmp.items():
            if not all(p in aux_points for p in k.split(' ')):
                v = [s + ' {:02}'.format(ref+i) for i, s in enumerate(v)]
                ref += len(v)
                string_premise.append(k + ' : ' + ' '.join(v))
        data += ' ; '.join([s.strip() for s in string_premise]) + ' ? '
        data += '; '.join([
            pretty(goal[0] + ' ' + ' '.join(goal[1:]))  
            for goal in problem.goals
            ])

        string_aux = []
        for k, v in data_tmp.items():
            if all(p in aux_points for p in k.split(' ')):
                v = [s + ' {:02}'.format(ref+i) for i, s in enumerate(v)]
                ref += len(v)
                string_aux.append(k + ' : ' + ' '.join(v))
        if len(string_aux) > 0:
            data += ' {F1} x00 '
            data += ' ; '.join([s.strip() for s in string_aux])
            data += ' ;'
        return data

    def process_single_problem(self, args: tuple) -> list:
        """Process a single geometry problem."""
        pid, fl_statement = args
        
        solver_builder = GeometricSolverBuilder(seed=998244353)
        solver_builder.with_deductive_agent(DDARN())
        solver_builder.load_problem_from_txt(fl_statement)

        if not self.clauses_num_filter(solver_builder.problemJGEX):
            return []
        
        try:
            solver = solver_builder.build(max_attempts=100)
        except Exception as e:
            logging.info(f"Error: {e}")
            return []
        solver.run(max_level=self.search_depth)
        points = [p.name for p in solver.proof.dep_graph.symbols_graph.nodes_of_type(Point)]
        possible_goals = list(self.all_possible_goals(points, solver.proof.dep_graph) | set(solver.proof.dep_graph.conclusions()))
        # possible_goals = list(set(solver.proof.dep_graph.conclusions()))

        generated_data = []
        for goal in possible_goals:
            # filter
            if not goal.check():
                continue
            if not self.goal_filter(goal):
                continue
            if not self.proof_filter(solver, goal):
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

            # dsl
            _, _, _, aux_points, _, _, _ = solver.proof.dep_graph.get_proof_steps([goal])
            mp: dict[str, str] = {}
            for construction in renamed_problem.constructions:
                for point in construction.points:
                    if point not in mp:
                        mp[point] = chr(ord("a") + len(mp))
            if len(aux_points) > 0:
                aux_points = [mp[p] for p in aux_points]
            dsl_problem = self.dsl(renamed_problem, aux_points)

            # output
            generated_data.append({
                "n_clauses": n_clauses,
                "fl_problem": fl_problem,
                "nl_problem": "",
                "nl_solution": nl_solution,
                "fl_problem_renamed": str(renamed_problem),
                "dsl_problem_renamed": dsl_problem,
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
    parser.add_argument("--log_level", default="warning", choices=["debug", "info", "warning", "error"])
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
    data = []
    start_time = time.time()
    for problem in generator.generate_problems():
        data.append(problem)
        logging.info(
            f"Generated {len(data)} samples in {time.time() - start_time:.1f}s "
            f"({(time.time() - start_time)/len(data):.1f}s/sample)"
        )
        if len(data) >= args.n_samples:
            break
    
    # Write the collected data
    generator.write_data(data)
    logging.info(f"Generated {len(data)} problems successfully")


if __name__ == "__main__":
    main()
