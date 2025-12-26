from newclid.agent.ddarn import DDARN
from newclid.generation.goal_filter import GeometryGoalFilter
from newclid.generation.summary import Summary, get_first_predicate
from newclid.proof import ProofState
from newclid.statement import Statement
from newclid.formulations.problem import ProblemJGEX
from newclid.formulations.definition import DefinitionJGEX
from newclid.formulations.clause import translate_sentence, Clause
from newclid.dependencies.symbols import Point
from newclid.dependencies.dependency_graph import DependencyGraph
from newclid.dependencies.dependency import Dependency, IN_PREMISES, NUMERICAL_CHECK
from newclid.configs import default_defs_path
from newclid.api import GeometricSolver, GeometricSolverBuilder, CSolver
from newclid.numerical.draw_figure import draw_with_mapping
import logging
import re
import itertools
import signal
import string
import time
from contextlib import contextmanager
from collections import defaultdict
import ray
import numpy as np
from copy import deepcopy

from newclid.generation.clause_generation import CompoundClauseGen


class TimeoutError(Exception):
    pass


@contextmanager
def time_limit(seconds):
    def handler(signum, frame):
        raise TimeoutError("Timed out")
    signal.signal(signal.SIGALRM, handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)


class GeometryProblemWorker:
    """
    Worker class to process individual geometry problems.
    This class is designed to be used with Ray for parallel processing.
    """
    filter = GeometryGoalFilter()
    defs = DefinitionJGEX.to_dict(
        DefinitionJGEX.parse_txt_file(default_defs_path()))

    @ray.remote(num_cpus=1, max_retries=0)
    def ray_process_single_problem(args):
        try:
            return GeometryProblemWorker._process_single_problem(args)
        except MemoryError as e:
            logging.error(f"⚠️ Worker OOM killed: {e}")
            return [], {'error': 'oom'}
        except Exception as e:
            logging.error(f"Worker error: {e}")
            return [], {'error': str(e)}

    @staticmethod
    def _process_single_problem(args: tuple) -> tuple[list, dict]:
        """Process a single geometry problem with unique seed."""
        try:
            pid, seed, n_clauses, max_level, img, aux_only, add_auxiliary, prune, remove_coords, draw_annotations = args
            start_time = time.time()

            # geneate fl_statement
            clauses_generator = CompoundClauseGen(seed=seed)
            try:
                with time_limit(10):
                    fl_statement = clauses_generator.generate(
                        length=n_clauses,
                        add_auxiliary=add_auxiliary,
                        prune=prune,
                        remove_coords=remove_coords,
                    )
            except TimeoutError:
                return [], {}
            # fl_statement, _ = args
            # seed=42
            # max_level=500
            # img = True
            # aux_only = False
            # start_time = time.time()
            # remove_coords = False
            # draw_annotations = True

            print(f"problem: {fl_statement}")

            # Build solver
            solver, solver_builder = GeometryProblemWorker._build_solver(
                fl_statement,
                max_attempts=10 if remove_coords else 1,
            )
            if not solver:
                return [], {}

            n_clauses = len(fl_statement.split(';'))
            csolver = CSolver(fl_statement, seed=seed,
                              solver=solver, using_log=True)

            # Run solver
            csolver.run(max_level=max_level)

            # Generate possible goals
            possible_goals, checkgoals_runtime = GeometryProblemWorker._generate_possible_goals(
                solver)

            # Process goals
            # first, group goals by problem key
            # eq_predicates_goals = dict()
            eq_clauses_goals = dict()
            for goal in possible_goals:
                # find essential_clauses
                points, _, _, _, aux_points, _, _, _, _ = solver.proof.dep_graph.get_proof_steps([
                    goal])
                if aux_only and len(aux_points) == 0:
                    continue

                # premises = [dep.statement for dep in premises]
                # aux = [dep.statement for dep in aux]
                # predicates = sorted([statement.to_str()
                #                     for statement in premises + aux])
                # predicates = '; '.join(sorted([statement.to_str() for statement in premises])) + \
                #     ' $$ ' + \
                #     '; '.join(sorted([statement.to_str()
                #               for statement in aux]))
                # eq_predicates_goals.setdefault(
                #     predicates, []).append((goal, premises, aux))
                
                premise_clauses, aux_clauses = GeometryProblemWorker._get_clauses_from_points(
                    points, aux_points, solver_builder.problemJGEX
                )
                clauses_str = '; '.join([str(c) for c in premise_clauses]) + ' $$ ' + \
                    '; '.join([str(c) for c in aux_clauses])
                eq_clauses_goals.setdefault(clauses_str, []).append(goal)


            # then, process goal groups
            process_goal_time = time.time()
            generated_data = []
            # for _, goal_list in eq_predicates_goals.items():
            #     goals = [data[0] for data in goal_list]
            #     premises = goal_list[0][1]
            #     aux = goal_list[0][2]
            #     data = GeometryProblemWorker._process_goals_with_same_statement(
            #         goals, solver, solver_builder, premises, aux, n_clauses, img, aux_only, draw_annotations)
            #     generated_data.extend(data)
            # process_goal_time = time.time() - process_goal_time
            for clauses_str, goal_list in eq_clauses_goals.items():
                goals = [data for data in goal_list]
                premise_clauses_str, aux_clauses_str = clauses_str.split(' $$ ')
                data = GeometryProblemWorker._process_goals_with_same_statement(
                    goals, solver, solver_builder, premise_clauses_str, aux_clauses_str, n_clauses, img, aux_only, draw_annotations)
                generated_data.extend(data)
            process_goal_time = time.time() - process_goal_time

            # Create summary
            summary = {
                'total_time': time.time() - start_time,
                'runtime': solver.run_infos['runtime'],
                'checkgoals_runtime': checkgoals_runtime,
                'process_goal_runtime': process_goal_time,
                'n_samples_raw': len(generated_data),
                'goals_raw': [re.search(r'\?\s*(\w+)', d['fl_problem']).group(1) for d in generated_data],
                'first_predicate_raw': [get_first_predicate(d['fl_problem']) for d in generated_data],
                'n_premises_raw': [d['n_premises'] for d in generated_data],
                'n_proof_steps_raw': [d['n_proof_steps'] for d in generated_data],
                'n_filtered_samples': 0,  # This value will be updated in generate.py
            }

            return generated_data, summary

        except Exception as e:
            logging.info(f"Error generating problem: {e}")
            import traceback
            traceback.print_exc()
            return [], {}

    @staticmethod
    def _get_clauses_from_points(
        points: set[Point],
        aux_points: set[Point],
        problemJGEX: ProblemJGEX,
    ) -> tuple[list[Clause], list[Clause]]:
        premise_clauses_set = set([p.clause for p in points])
        aux_clauses_set = set([p.clause for p in aux_points])
        if premise_clauses_set & aux_clauses_set:
            raise Exception("Premise and aux clauses overlap.")
        premise_clauses: list[Clause] = []
        aux_clauses: list[Clause] = []
        for clause in problemJGEX.constructions:
            if clause in premise_clauses_set:
                premise_clauses.append(clause)
            if clause in aux_clauses_set:
                aux_clauses.append(clause)
        return premise_clauses, aux_clauses

    @staticmethod
    def _build_solver(fl_statement, max_attempts=1):
        """Build geometric solver"""
        solver_builder = GeometricSolverBuilder(seed=998244353)
        solver_builder.with_deductive_agent(DDARN())
        solver_builder.load_problem_from_txt(fl_statement)
        try:
            solver = solver_builder.build(max_attempts=max_attempts)
            return solver, solver_builder
        except Exception as e:
            logging.info(f"Error: {e}")
            return None, None

    @staticmethod
    def _generate_possible_goals(solver):
        """Generate possible goals"""
        t = time.time()
        # GeometryProblemWorker.all_possible_goals_by_ar(solver.proof.dep_graph)
        possible_goals = [
            goal for goal in solver.proof.dep_graph.conclusions()]
        possible_goals = GeometryProblemWorker.filter.goal_filter(
            possible_goals, solver.proof.dep_graph)
        checkgoals_runtime = time.time() - t
        return possible_goals, checkgoals_runtime

    @staticmethod
    def all_possible_goals_by_ar(dep_graph: DependencyGraph) -> list[Statement]:
        def extract_points(s):
            return re.findall(r'[a-z][\d]*', s)

        def goal_from_tokens(tokens):
            if GeometryProblemWorker.filter.naive_goal_filter(tokens[0], tokens[1:], dep_graph):
                goal = Statement.from_tokens(tokens, dep_graph)
                if goal:
                    goal.check()

        points_name = sorted(
            [p.name for p in dep_graph.symbols_graph.nodes_of_type(Point)])
        for i, p in enumerate(points_name):
            for q in points_name[i + 1:]:
                ar = dep_graph.ar
                if (p + q) not in ar.atable.v2e:
                    ar.atable.add_free(p + q)
                if f"l({p},{q})" not in ar.rtable.v2e:
                    ar.rtable.add_free(f"l({p},{q})")

        ar = dep_graph.ar

        e2v, e2v_pairs2, e2v_pairs4 = ar.atable.possible_pairs()
        for e in e2v_pairs2.keys():
            for v1, v2 in e2v_pairs2[e]:
                try:
                    v1, v2 = extract_points(v1), extract_points(v2)
                    goal_from_tokens(tuple(['para'] + list(v1 + v2)))
                    goal_from_tokens(tuple(['perp'] + list(v1 + v2)))
                    goal_from_tokens(tuple(['acompute'] + list(v1 + v2)))
                except Exception as e:
                    logging.warning(
                        f"Error in goal_from_tokens: {e} para/perp for {v1}, {v2}")
                    continue
        for v1, v2, v3, v4 in e2v_pairs4:
            try:
                v1, v2, v3, v4 = extract_points(v1), extract_points(
                    v2), extract_points(v3), extract_points(v4)
                goal_from_tokens(tuple(['eqangle'] + list(v1 + v2 + v3 + v4)))
            except Exception as e:
                logging.warning(
                    f"Error in goal_from_tokens: {e} for eqangle {v1}, {v2}, {v3}, {v4}")
                continue

        e2v, e2v_pairs2, e2v_pairs4 = ar.rtable.possible_pairs()
        for e in e2v_pairs2.keys():
            for v1, v2 in e2v_pairs2[e]:
                try:
                    goal_from_tokens(
                        tuple(['cong'] + v1[2:-1].split(',') + v2[2:-1].split(',')))
                    goal_from_tokens(
                        tuple(['rcompute'] + v1[2:-1].split(',') + v2[2:-1].split(',')))
                except Exception as e:
                    logging.warning(
                        f"Error in goal_from_tokens: {e} cong for {v1}, {v2}")
                    continue
        # for v1, v2, v3, v4 in e2v_pairs4:
        #     try:
        #         tokens = tuple(['eqratio'] + list(v1[2:-1].split(',') +
        #                        v2[2:-1].split(',') + v3[2:-1].split(',') + v4[2:-1].split(',')))
        #         goal_from_tokens(tokens)
        #     except Exception as e:
        #         logging.warning(f"Error in goal_from_tokens: {e} for eqratio {v1}, {v2}, {v3}, {v4}")
        #         continue

    @staticmethod
    def _find_minimal_aux_clauses_new(solver, solver_builder, goals_str, premise_clauses_str, aux_clauses_str, aux_only):
        """Find minimal auxiliary clause set"""
        # Iterate through all possible subsets to find the minimal necessary auxiliary clause set
        # Search through subsets from size 0 to len-1 (excluding full set)
        if premise_clauses_str == '':
            raise Exception("Premise clauses cannot be empty.")
        results = []
        aux_clause_strs = aux_clauses_str.split('; ') if aux_clauses_str else []
        for r in range(len(aux_clause_strs)):
            for aux_strs_subset in itertools.combinations(aux_clause_strs, r):
                # proof_state = ProofState.build_predicates(
                #     predicates=premises + list(aux_subset),
                #     defsJGEX=solver_builder.defs,
                #     goals_str=goals_str,
                #     rng=np.random.default_rng(solver_builder.seed)
                # )
                # solver_test = GeometricSolver(
                #     proof_state,
                #     solver_builder.rules,
                #     DDARN()
                # )
                # csolver_test = CSolver(
                #     problem='', solver=solver_test, using_log=True)
                # the element order of aux_strs_subset is the same as the relative order
                # in aux_clauses_str, so we can directly join with '; '
                csolver_test = CSolver(
                    problem=premise_clauses_str + (' ; ' if r > 0 else '') + '; '.join(aux_strs_subset),
                    using_log=True,
                    using_exp=False,
                )
                csolver_test.run()
                solver_test = csolver_test.solver
                for goal in solver_test.goals:
                    # if found new solutions
                    if goal.check():
                        goals_str.remove(goal.to_str())
                        if aux_only and r == 0:
                            continue
                        results.append({
                            "solver": solver_test,
                            "goal": goal
                        })

                if len(goals_str) == 0:
                    break
            if len(goals_str) == 0:
                break

        # goals requiring full aux set or the aux set is empty
        for goal_str in goals_str:
            goal = Statement.from_tokens(
                goal_str.split(" "), solver.proof.dep_graph)
            # problem_new = str(solver_builder.problemJGEX).split(
            #     ' ? ')[0] + ' ? ' + goal_str
            # problem_new = ProblemJGEX.from_text(problem_new)
            results.append({
                "solver": solver,
                "goal": goal
            })
        return results

    @staticmethod
    def _process_goals_with_same_statement(goals, solver, solver_builder, premise_clauses_str, aux_clauses_str, n_clauses, img, aux_only, draw_annotations=True):
        """Process a single goal"""

        results = []

        res_list = GeometryProblemWorker._find_minimal_aux_clauses_new(
            solver,
            solver_builder,
            [goal.to_str() for goal in goals],
            premise_clauses_str,
            aux_clauses_str,
            aux_only
        )

        for res in res_list:
            goal_new = res['goal']
            solver_new = res['solver']
            solver_new.proof.goals = [goal_new]

            # get new proof
            (
                points,
                premises,
                numerical_checked_premises,
                trivial_premises,
                aux_points,
                aux,
                numerical_checked_aux,
                trivial_aux,
                proof_steps
            ) = solver_new.proof.dep_graph.get_proof_steps([goal_new])
            if aux_only and len(aux) == 0:
                continue

            premise_clauses, aux_clauses = GeometryProblemWorker._get_clauses_from_points(
                points, aux_points, solver_builder.problemJGEX
            )

            all_premises = [dep.statement for dep in premises + aux]
            n_premises = len(all_premises)

            # filter proof
            n_proof_steps = len(proof_steps)
            # if n_proof_steps < min_proof_steps:
            #     logging.debug(f"Naive proof with length {n_proof_steps}")
            #     continue

            # llm data generation
            llm_renamed, mapping = GeometryProblemWorker.llm_solution_renamed(
                premise_clauses,
                points,
                premises,
                numerical_checked_premises,
                trivial_premises,
                aux_clauses,
                aux_points,
                aux,
                numerical_checked_aux,
                trivial_aux,
                proof_steps,
                solver_new.proof,
            )

            if len(aux_points) > 0 and not GeometryProblemWorker.filter.aux_predicates_valid_check(llm_renamed['llm_output']):
                continue

            result = {
                "n_clauses": len(premise_clauses),
                "n_premises": n_premises,
                "fl_problem": '; '.join([str(c) for c in premise_clauses]) + ' ? ' + goal_new.to_str(),
                "nl_problem": "",
                "n_proof_steps": n_proof_steps,
                "llm_input_renamed": llm_renamed['llm_input'],
                "llm_output_renamed": llm_renamed['llm_output'],
            }

            if img:
                fig = deepcopy(solver_new.proof.fig)
                draw_with_mapping(
                    fig.axes[0],
                    solver_new.proof.symbols_graph.names2points(
                        list(set(mapping.keys()) & set(
                            [p.name for p in points]))
                    ),
                    [premise.statement for premise in premises],
                    goal_new,
                    np.random.default_rng(solver_builder.seed),
                    mapping,
                    draw_annotations,
                )
                result["fig"] = fig

            results.append(result)
        return results

    @staticmethod
    def _rediger_new_format(dep, mp, dep_idx) -> str:
        """Generate proof step in new format: statement [id] rule_id [required_statement_ids]"""
        for statement in (dep.statement,) + dep.why:
            statemtn_str = GeometryProblemWorker._statement2str_with_mapping(
                statement, mp)
            if statemtn_str not in dep_idx:
                dep_idx[statemtn_str] = f"{len(dep_idx):03d}"

        # Extract rule ID from reason string and handle special cases
        reason = dep.reason
        if "Ratio Chasing" in reason:
            rule_id = "a00"
        elif "Angle Chasing" in reason:
            rule_id = "a01"
        elif "Shortcut Derivation" in reason:
            rule_id = "r99"
        elif "Same Circle" in reason:
            rule_id = "r98"
        elif "Same Line" in reason:
            rule_id = "r97"
        elif reason and ' ' in reason:
            rule_id = reason.split()[0]
        else:
            rule_id = reason if reason else "unknown"

        # Generate new format: statement [statement_id] rule_id [premise_ids]
        premise_ids = ' '.join(
            f"[{dep_idx[GeometryProblemWorker._statement2str_with_mapping(premise, mp)]}]" for premise in dep.why)
        conclusion_str = GeometryProblemWorker._statement2str_with_mapping(
            dep.statement, mp)
        return f"{conclusion_str} [{dep_idx[conclusion_str]}] {rule_id} {premise_ids}".strip()

    @staticmethod
    def llm_solution_renamed(
        premise_clauses: list[Clause],
        points: set[Point],
        premises: list[Dependency],
        numerical_checked_premises: list[Dependency],
        trivial_premises: list[Dependency],
        aux_clauses: list[Clause],
        aux_points: set[Point],
        aux: list[Dependency],
        numerical_checked_aux: list[Dependency],
        trivial_aux: list[Dependency],
        proof_steps: list[Dependency],
        proof_state: ProofState,
    ) -> dict:
        """Refactored main method to generate LLM solution with renamed points"""
        try:
            # Initialize data
            dep_idx: dict[str, str] = {}
            goals = [goal for goal in proof_state.goals if goal.check()]

            # Get all premises and essential premises/points
            all_premises = GeometryProblemWorker._get_all_premise(premise_clauses, proof_state)
            all_aux = GeometryProblemWorker._get_all_premise(aux_clauses, proof_state)
            # essential_points, essential_aux_points, essential_premises = GeometryProblemWorker._get_essential_points_and_premise(
            #     premises+aux, proof_state.dep_graph.proof_deps(goals), points, aux_points_list)

            # Create point name mapping
            # mp = GeometryProblemWorker._create_point_mapping(
            #     essential_points, essential_aux_points, essential_premises, all_premises)
            
            mp: dict[str, str] = {}
            for clause in premise_clauses:
                for p in clause.points:
                    p_name = p.split('@')[0]
                    if p_name in mp:
                        raise ValueError("Duplicated definition of point.")
                    mp[p_name] = GeometryProblemWorker._get_apha_geo_solver_var(len(mp))
            for p in aux_points:
                if p.name in mp:
                    raise ValueError("Premise points and aux points overlap")
                mp[p.name] = GeometryProblemWorker._get_apha_geo_solver_var(len(mp))
                    

            # Generate each section
            data_problem = GeometryProblemWorker._generate_problem_section(
                mp, dep_idx, points, all_premises, premises, goals, 0)
            data_aux = GeometryProblemWorker._generate_aux_section(
                mp, dep_idx, aux_points, aux, all_aux)
            numerical_check = GeometryProblemWorker._generate_numerical_check_section(
                mp, dep_idx, numerical_checked_premises, numerical_checked_aux)
            trivial_check = GeometryProblemWorker._generate_trivial_section(
                mp, dep_idx, trivial_premises, trivial_aux)
            proof = GeometryProblemWorker._generate_proof_section(
                mp, dep_idx, proof_steps)

            # Assemble result
            return {
                "llm_input": data_problem,
                "llm_output": data_aux + numerical_check + trivial_check + proof,
            }, mp

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(mp)
            print(all_premises)
            raise

    @staticmethod
    def _get_apha_geo_solver_var(va_idx):
        """Generate a point name using letters and numbers"""
        letter_part = string.ascii_lowercase[va_idx % 26]
        number_part = va_idx // 26
        return f"{letter_part}{number_part - 1}" if number_part else letter_part

    @staticmethod
    def _statement2str_with_mapping(statement: Statement, mp):
        statement_args_str = statement.to_str().split(' ')[1:]
        res = []
        for arg, arg_str in zip(statement.args, statement_args_str):
            if isinstance(arg, Point):
                res.append(mp[arg_str])
            else:  # isinstance(a, Fraction)
                res.append(arg_str)
        # [mp[arg.name] if isinstance(arg, Point) else str(arg) for arg in statement.args]
        res = [statement.predicate.NAME] + res
        return " ".join(res)

    @staticmethod
    def _get_all_premise(clauses, proof_state):
        """Get all premises from the problem constructions"""
        data_tmp = defaultdict(list)
        for construction in clauses:
            group = {}
            p2deps = defaultdict(list)
            points_in_basic_order = []
            for constr_sentence in construction.sentences:
                cdef = GeometryProblemWorker.defs[constr_sentence[0]]
                if len(constr_sentence) == len(cdef.declare):
                    mapping = dict(zip(cdef.declare[1:], constr_sentence[1:]))
                else:
                    assert len(constr_sentence) + \
                        len(construction.points) == len(cdef.declare)
                    mapping = dict(
                        zip(cdef.declare[1:], construction.points + constr_sentence[1:]))
                for points, bs in cdef.basics:
                    points = tuple([mapping[x] for x in points])
                    for p in points:
                        points_in_basic_order.append(p)
                        group[p] = points
                    for b in bs:
                        statement = Statement.from_tokens(
                            translate_sentence(mapping, b), proof_state.dep_graph)
                        p2deps[points].append(statement)

            points = points_in_basic_order
            while points:
                p = points[0]
                gr = group[p]
                points = [x for x in points if x not in gr]

                deps = []
                for dep in p2deps[gr]:
                    deps.append(dep)
                data_tmp[' '.join(gr)] = deps
        return data_tmp

    @staticmethod
    def _get_essential_points_and_premise(premises, proof_deps, points, aux_points):
        """Get essential points and premises"""
        # essential_premises
        essential_premises = []
        for line in premises:
            essential_premises.append(line.statement)
        # essential_points points
        essential_points = set()
        for line in proof_deps:
            for arg in line.statement.args:
                if isinstance(arg, Point):
                    essential_points.add(arg.name)
        points = set([p.name for p in points]) & essential_points
        aux_points = set([p.name for p in aux_points]) & essential_points
        return points, aux_points, essential_premises

    @staticmethod
    def _create_point_mapping(essential_points, essential_aux_points, essential_premises, all_premise):
        """Create point name mapping"""
        mp = {}
        for k, v in all_premise.items():
            kps = k.split(' ')
            if any(p in essential_points for p in kps):
                # for dep in v:
                #     if dep in essential_premises:
                #         for arg in dep.args:
                #             if isinstance(arg, Point) and arg.name not in mp:
                #                 mp[arg.name] = GeometryProblemWorker._get_apha_geo_solver_var(
                #                     len(mp))
                # for p in kps:
                #     if p not in mp:
                #         mp[p] = GeometryProblemWorker._get_apha_geo_solver_var(
                #             len(mp))
                for p in kps:
                    if p not in mp and p in essential_points:
                        mp[p] = GeometryProblemWorker._get_apha_geo_solver_var(
                            len(mp))

        for k, v in all_premise.items():
            ps = k.split(' ')
            if any(p in essential_aux_points for p in ps):
                for p in ps:
                    # if p not in mp:
                    if p not in mp and p in essential_aux_points:
                        mp[p] = GeometryProblemWorker._get_apha_geo_solver_var(
                            len(mp))
        return mp

    @staticmethod
    def _generate_problem_section(mp, dep_idx, essential_points, all_premise, essential_premises, goals, prune_level=0):
        """
        Generate problem description section
        
        prune_level:
            0: keep all premises and points
            1: remove useless premises, free useless points
            2: remove useless premises, remove useless points
        """
        string_premise = []
        for k, v in all_premise.items():
            tmp_string = ""
            if any(p in essential_points for p in k.split(' ')) or prune_level < 2:
                for dep in v:
                    if dep in essential_premises or prune_level == 0:
                        # only select useful premise and free points withou useful premises
                        dep_str_renamed = GeometryProblemWorker._statement2str_with_mapping(
                            dep, mp)
                        if dep_str_renamed not in dep_idx:
                            dep_idx[dep_str_renamed] = f"{len(dep_idx):03d}"
                        tmp_string += dep_str_renamed + \
                            f' [{dep_idx[dep_str_renamed]}] '
            if tmp_string == "" :
                if prune_level < 2:
                    # if this premise is useless, free all useful points in it
                    for p in k.split(' '):
                        if p in mp:
                            string_premise.append(mp[p] + " : ")
            else:
                k_renamed = " ".join(mp[p]
                                        for p in k.split(' ') if p in mp)
                tmp_string = k_renamed + ' : ' + tmp_string
                string_premise.append(tmp_string)
        data_problem = '<problem> '
        data_problem += ' ; '.join([s.strip()
                                   for s in string_premise]) + ' ? '
        data_problem += ' ;'.join([GeometryProblemWorker._statement2str_with_mapping(goal, mp)
                                  for goal in goals])
        data_problem += ' </problem>'
        return data_problem

    @staticmethod
    def _generate_aux_section(mp, dep_idx, essential_aux_points, essential_premises, all_premise):
        """Generate auxiliary information section"""
        instance = GeometryProblemWorker()
        data_aux = ''
        string_aux = []
        for k, v in all_premise.items():
            if any(p in essential_aux_points for p in k.split(' ')):
                k_renamed = " ".join(mp[p] for p in k.split(' ') if p in mp)
                tmp_string = 'x00 ' + k_renamed + ' : '
                for dep in v:
                    if dep in essential_premises:  # free points withou useful premises
                        dep_str_renamed = instance._statement2str_with_mapping(
                            dep, mp)
                        if dep_str_renamed not in dep_idx:
                            dep_idx[dep_str_renamed] = f"{len(dep_idx):03d}"
                        tmp_string += dep_str_renamed + \
                            f' [{dep_idx[dep_str_renamed]}] '
                string_aux.append(tmp_string)
        if len(string_aux) > 0:
            data_aux += '<aux> '
            data_aux += ' ; '.join([s.strip() for s in string_aux])
            data_aux += ' ; </aux> '
        return data_aux

    @staticmethod
    def _generate_numerical_check_section(mp, dep_idx, numercial_checked_premises, numercial_checked_aux):
        """Generate numerical check section"""
        instance = GeometryProblemWorker()
        numerical_check_items = []
        # numercial_checked_premises
        for line in numercial_checked_premises:
            statemtn_str = instance._statement2str_with_mapping(
                line.statement, mp)
            if statemtn_str not in dep_idx:
                dep_idx[statemtn_str] = f"{len(dep_idx):03d}"
        sorted_numercial_checked_premises = sorted(
            numercial_checked_premises, key=lambda line: dep_idx[instance._statement2str_with_mapping(line.statement, mp)])
        for line in sorted_numercial_checked_premises:
            statemtn_str = instance._statement2str_with_mapping(
                line.statement, mp)
            numerical_check_items.append(
                f"{statemtn_str} [{dep_idx[statemtn_str]}]")
        # numercial_checked_premises
        for line in numercial_checked_aux:
            statemtn_str = instance._statement2str_with_mapping(
                line.statement, mp)
            if statemtn_str not in dep_idx:
                dep_idx[statemtn_str] = f"{len(dep_idx):03d}"
        sorted_numercial_checked_aux = sorted(
            numercial_checked_aux, key=lambda line: dep_idx[instance._statement2str_with_mapping(line.statement, mp)])
        for line in sorted_numercial_checked_aux:
            statemtn_str = instance._statement2str_with_mapping(
                line.statement, mp)
            numerical_check_items.append(
                f"{statemtn_str} [{dep_idx[statemtn_str]}]")
        if len(numerical_check_items) > 0:
            numerical_check = "<numerical_check> " + \
                " ; ".join(numerical_check_items) + \
                " ; </numerical_check> "
        else:
            numerical_check = ""
        return numerical_check

    @staticmethod
    def _generate_trivial_section(mp, dep_idx, trivial_premises, trivial_aux):
        """Generate numerical check section"""
        instance = GeometryProblemWorker()
        trivial_items = []
        # trivial_premises
        for line in trivial_premises:
            statemtn_str = instance._statement2str_with_mapping(
                line.statement, mp)
            if statemtn_str not in dep_idx:
                dep_idx[statemtn_str] = f"{len(dep_idx):03d}"
        sorted_trivial_premises = sorted(
            trivial_premises, key=lambda line: dep_idx[instance._statement2str_with_mapping(line.statement, mp)])
        for line in sorted_trivial_premises:
            statemtn_str = instance._statement2str_with_mapping(
                line.statement, mp)
            trivial_items.append(
                f"{statemtn_str} [{dep_idx[statemtn_str]}]")
        # trivial_premises
        for line in trivial_aux:
            statemtn_str = instance._statement2str_with_mapping(
                line.statement, mp)
            if statemtn_str not in dep_idx:
                dep_idx[statemtn_str] = f"{len(dep_idx):03d}"
        sorted_trivial_aux = sorted(
            trivial_aux, key=lambda line: dep_idx[instance._statement2str_with_mapping(line.statement, mp)])
        for line in sorted_trivial_aux:
            statemtn_str = instance._statement2str_with_mapping(
                line.statement, mp)
            trivial_items.append(
                f"{statemtn_str} [{dep_idx[statemtn_str]}]")
        if len(trivial_items) > 0:
            trivial = "<trivial> " + \
                " ; ".join(trivial_items) + \
                " ; </trivial> "
        else:
            trivial = ""
        return trivial

    @staticmethod
    def _generate_proof_section(mp, dep_idx, proof_steps):
        """Generate proof section"""
        proof = "<proof> "
        proof_steps_formatted = []
        for k, line in enumerate(proof_steps):
            if NUMERICAL_CHECK not in line.reason and IN_PREMISES not in line:
                proof_steps_formatted.append(
                    GeometryProblemWorker._rediger_new_format(line, mp, dep_idx))
        proof += " ; ".join(proof_steps_formatted) + " ; </proof>"
        return proof
