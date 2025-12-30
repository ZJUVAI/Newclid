from newclid.agent.ddarn import DDARN
from newclid.algebraic_reasoning.algebraic_manipulator import AlgebraicManipulator
from newclid.generation.goal_filter import GeometryGoalFilter
from newclid.generation.summary import Summary, get_first_predicate
from newclid.proof import ProofState
from newclid.statement import Statement
from newclid.formulations.problem import ProblemJGEX
from newclid.formulations.definition import DefinitionJGEX
from newclid.formulations.clause import Clause, translate_sentence
from newclid.dependencies.symbols import Point
from newclid.dependencies.dependency_graph import DependencyGraph
from newclid.dependencies.dependency import Dependency, IN_PREMISES, NUMERICAL_CHECK
from newclid.configs import default_defs_path
from newclid.api import GeometricSolver, GeometricSolverBuilder, CSolver
from newclid.numerical.draw_figure import draw_with_mapping
from newclid.numerical.draw_clause_figure import draw_clauses
import logging
import re
import itertools
import string
import time
import signal
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

            # print(f"problem: {fl_statement}")

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
            eq_predicates_goals = dict()
            for goal in possible_goals:
                # find essential_clauses
                _, premises, _, _, _, aux, _, _, _ = solver.proof.dep_graph.get_proof_steps([
                    goal])
                if aux_only and len(aux) == 0:
                    continue
                premises = [dep.statement for dep in premises]
                aux = [dep.statement for dep in aux]
                predicates = sorted([statement.to_str()
                                    for statement in premises + aux])
                predicates = '; '.join(sorted([statement.to_str() for statement in premises])) + \
                    ' $$ ' + \
                    '; '.join(sorted([statement.to_str()
                              for statement in aux]))
                eq_predicates_goals.setdefault(
                    predicates, []).append((goal, premises, aux))

            # then, process goal groups
            process_goal_time = time.time()
            generated_data = []
            for _, goal_list in eq_predicates_goals.items():
                goals = [data[0] for data in goal_list]
                premises = goal_list[0][1]
                aux = goal_list[0][2]
                data = GeometryProblemWorker._process_goals_with_same_statement(
                    goals, solver, solver_builder, premises, aux, n_clauses, img, aux_only, draw_annotations)
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
    def _find_minimal_aux_clauses_new(solver, solver_builder, goals_str, premises, aux, aux_only):
        """Find minimal auxiliary clause set"""
        # Iterate through all possible subsets to find the minimal necessary auxiliary clause set
        # Search through subsets from size 0 to len-1 (excluding full set)
        results = []
        for r in range(len(aux)):
            for aux_subset in itertools.combinations(aux, r):
                proof_state = ProofState.build_predicates(
                    predicates=premises + list(aux_subset),
                    defsJGEX=solver_builder.defs,
                    goals_str=goals_str,
                    rng=np.random.default_rng(solver_builder.seed)
                )
                solver_test = GeometricSolver(
                    proof_state,
                    solver_builder.rules,
                    DDARN()
                )
                csolver_test = CSolver(
                    problem='', solver=solver_test, using_log=True)
                csolver_test.run()
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
    def _process_goals_with_same_statement(goals, solver, solver_builder, premises, aux, n_clauses, img, aux_only, draw_annotations=True):
        """Process a single goal"""

        results = []

        res_list = GeometryProblemWorker._find_minimal_aux_clauses_new(
            solver,
            solver_builder,
            [goal.to_str() for goal in goals],
            premises,
            aux,
            aux_only
        )

        for res in res_list:
            goal_new = res['goal']
            solver_new = res['solver']
            solver_new.proof.goals = [goal_new]

            # get new proof
            points, premises, _, _, aux_points, aux, _, _, proof_steps = solver_new.proof.dep_graph.get_proof_steps([
                goal_new])
            # if aux_only and len(aux) == 0:
            #     logging.warning(
            #         "aux_only == True but still generate result with no aux.")
            #     continue
            # all_premises = [dep.statement for dep in premises + aux]
            # n_premises = len(all_premises)

            # # filter proof
            # n_proof_steps = len(proof_steps)
            # # if n_proof_steps < min_proof_steps:
            # #     logging.debug(f"Naive proof with length {n_proof_steps}")
            # #     continue

            # llm data generation
            llm_renamed, clause2basics, clauses, mapping, n_premises, n_proof_steps = GeometryProblemWorker.llm_solution_renamed(
                solver_builder.problemJGEX, solver_new.proof)
            
            if aux_only and 'aux' not in llm_renamed['llm_output']:
                continue

            if 'aux' in llm_renamed['llm_output'] and not GeometryProblemWorker.filter.aux_predicates_valid_check(llm_renamed['llm_output']):
                continue

            expected_dsl = problem_to_dsl(ProblemJGEX.from_text(llm_renamed['fl_problem']), GeometryProblemWorker.defs)
            actual_dsl = llm_renamed['llm_input']
            error_msg = (
                f"\n{'='*20} DSL Conversion Mismatch {'='*20}\n"
                f"Problem: {llm_renamed['fl_problem']}\n"
                f"--- [ACTUAL] ---\n{actual_dsl}\n"
                f"--- [EXPECTED] ---\n{expected_dsl}\n"
                f"{'='*50}"
            )
            assert actual_dsl == expected_dsl, error_msg

            result = {
                # "n_clauses": n_clauses,
                "n_premises": n_premises,
                "fl_problem": llm_renamed['fl_problem'],
                "nl_problem": "",
                "n_proof_steps": n_proof_steps,
                "llm_input_renamed": llm_renamed['llm_input'],
                "llm_output_renamed": llm_renamed['llm_output'],
            }

            if img:
                fig = deepcopy(solver_new.proof.fig)
                draw_clauses(
                    fig.axes[0],
                    clauses,
                    GeometryProblemWorker.defs,
                    goal_new,
                    np.random.default_rng(solver_builder.seed),
                    solver_new.proof.dep_graph,
                    mapping,
                    True,
                )
                result["fig"] = fig

                fig_no_annotations = deepcopy(solver_new.proof.fig)
                draw_clauses(
                    fig_no_annotations.axes[0],
                    clauses,
                    GeometryProblemWorker.defs,
                    goal_new,
                    np.random.default_rng(solver_builder.seed),
                    solver_new.proof.dep_graph,
                    mapping,
                    False,
                )
                result["fig_no_annotations"] = fig_no_annotations

            results.append(result)
        return results
    
    @staticmethod
    def _rediger_new_format(dep, mp, dep_idx) -> str:
        """Generate proof step in new format: statement [id] rule_id [required_statement_ids]"""
        for statement in (dep.statement,) + dep.why:
            statement_str = GeometryProblemWorker._statement2str_with_mapping(
                statement, mp)
            if statement_str not in dep_idx:
                dep_idx[statement_str] = f"{len(dep_idx):03d}"

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
    def llm_solution_renamed(problem: ProblemJGEX, proof_state: ProofState):
        """Refactored main method to generate LLM solution with renamed points"""
        try:
            # Initialize data
            dep_idx: dict[str, str] = {}
            goals = [goal for goal in proof_state.goals if goal.check()]
            (
                points,
                premises,
                numercial_checked_premises,
                trivial_premises,
                aux_points_list,
                aux,
                numercial_checked_aux,
                trivial_aux,
                proof_steps,
            ) = proof_state.dep_graph.get_proof_steps(goals)

            # Get all premises and essential premises/points
            clauses_without_coords: list[Clause] = []
            for clause in problem.constructions:
                clauses_without_coords.append(
                    Clause(
                        points=tuple(p.split('@')[0] for p in clause.points),
                        sentences=clause.sentences,
                    )
                )
            clause2basics, clause2args = GeometryProblemWorker._get_all_premise(
                clauses_without_coords, proof_state
            )
            essential_premise_clauses = GeometryProblemWorker._get_essential_premise_clauses(
                clause2basics,
                clause2args,
                [premise.statement for premise in premises],
                set([p.name for p in points]),
            )
            essential_aux_basics = GeometryProblemWorker._get_aux_basics(
                clause2basics,
                [a.statement for a in aux],
                set([p.name for p in aux_points_list]),
            )

            # Create point name mapping
            essential_premise_point_names: list[str] = []
            for clause in essential_premise_clauses:
                for points, bs in clause2basics[clause]:
                    essential_premise_point_names.extend(points)
            essential_aux_point_names: list[str] = []
            for points, bs in essential_aux_basics:
                essential_aux_point_names.extend(points)
            mp = GeometryProblemWorker._create_point_mapping(
                essential_premise_point_names, essential_aux_point_names
            )

            # Generate each section
            data_problem_clauses = GeometryProblemWorker._generate_problem_clauses_section(
                mp, essential_premise_clauses, goals
            )
            data_problem = GeometryProblemWorker._generate_problem_predicates_section(
                mp, dep_idx, clause2basics, essential_premise_clauses, goals
            )
            n_premises = len(dep_idx)
            data_aux = GeometryProblemWorker._generate_aux_section(
                mp, dep_idx, essential_aux_basics
            )
            numerical_check = GeometryProblemWorker._generate_numerical_check_section(
                mp, dep_idx, numercial_checked_premises, numercial_checked_aux
            )
            trivial_check = GeometryProblemWorker._generate_trivial_section(
                mp, dep_idx, trivial_premises, trivial_aux
            )
            proof = GeometryProblemWorker._generate_proof_section(
                mp, dep_idx, proof_steps
            )

            # Assemble result
            return {
                "fl_problem": data_problem_clauses,
                "llm_input": data_problem,
                "llm_output": data_aux + numerical_check + trivial_check + proof,
            }, clause2basics, essential_premise_clauses, mp, n_premises, len(proof_steps)

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"clauses_without_coords: {clauses_without_coords}")
            print(f"clause2basics: {clause2basics}")
            print(f"essential_clauses: {essential_premise_clauses}")
            print(f"essential_aux_basics: {essential_aux_basics}")
            print(f"mp: {mp}")
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
    def _get_all_premise(clauses: list[Clause], proof_state: ProofState) -> tuple[dict[Clause, list], dict[Clause, set]]:
        """Get all premises from the problem constructions"""
        clause2basics: dict[Clause, list] = defaultdict(list)
        clause2args: dict[Clause, set] = defaultdict(set)
        for clause in clauses:
            points2basics: dict[tuple[str, ...], list[Statement]] = defaultdict(list)
            for constr_sentence in clause.sentences:
                cdef = GeometryProblemWorker.defs[constr_sentence[0]]
                if len(constr_sentence) == len(cdef.declare):
                    mapping = dict(zip(cdef.declare[1:], constr_sentence[1:]))
                else:
                    assert len(constr_sentence) + \
                        len(clause.points) == len(cdef.declare)
                    mapping = dict(
                        zip(cdef.declare[1:], clause.points + constr_sentence[1:]))
                for rely_points in cdef.rely.values():
                    clause2args[clause].update(
                        set([mapping[p] for p in rely_points])
                    )
                for points, bs in cdef.basics:
                    points = tuple([mapping[x] for x in points])
                    bs_statements = []
                    for b in bs:
                        statement = Statement.from_tokens(
                            translate_sentence(mapping, b), proof_state.dep_graph)
                        bs_statements.append(statement)
                    points2basics[points].extend(bs_statements)
            for points, bs_statements in points2basics.items():
                clause2basics[clause].append((points, bs_statements))
        return clause2basics, clause2args
    
    @staticmethod
    def _get_essential_premise_clauses(
        clause2basics: dict[Clause, list],
        clause2args: dict[Clause, set],
        premise_statements: list[Statement],
        essential_point_names: set[str],
    ) -> list[Clause]:
        """
        Get essential clauses according to the premise statements and essential points.
        
        A clause is considered essential if one of the following conditions is met:
        1. any predicate in the clause's basics is in the premise_statements
        2. any point in the clause is in the essential points and the clause has no predicate (e.g. triangle)
        After collecting essential clauses, update the essential points set.
        For non-essential clauses, if any point in the clause is in the essential points, construct the point with a 'free' clause.
        """
        essential_premise_clauses_set: set[Clause] = set()
        new_free_points: list[tuple[Clause, str]] = []
        for clause, basics in clause2basics.items():
            num_of_predicates = sum(len(bs) for _, bs in basics)
            if any(
                statement in premise_statements
                for _, bs in basics
                for statement in bs
            ):
                essential_premise_clauses_set.add(clause)
            elif num_of_predicates == 0 and any(
                p in essential_point_names for p in clause.points
            ):
                essential_premise_clauses_set.add(clause)
        # update essential points
        for clause in essential_premise_clauses_set:
            for point_name in clause2args[clause]:
                essential_point_names.add(point_name)
        # Construct 'free' clauses for non-essential clauses
        essential_premise_clauses: list[Clause] = []
        for clause, basics in clause2basics.items():
            if clause in essential_premise_clauses_set:
                essential_premise_clauses.append(clause)
            else:
                for p in clause.points:
                    if p in essential_point_names:
                        free_clause = Clause(
                            points=(p,),
                            sentences=(('free', p),)
                        )
                        essential_premise_clauses.append(free_clause)
                        new_free_points.append((free_clause, p))
        for free_clause, p in new_free_points:
            clause2basics[free_clause] = [((p,), ())]
        return essential_premise_clauses
    
    @staticmethod
    def _get_aux_basics(
        clause2basics: dict[Clause, list],
        aux: list[Statement],
        aux_point_names: set[str],
    ) -> list[tuple[tuple[str, ...], tuple[Statement, ...]]]:
        """
        Get auxiliary basics according to the auxiliary statements and auxiliary points.
        
        Only reserve basics that contain auxiliary statements or points.
        """
        essential_aux_basics: list[tuple[tuple[str, ...], tuple[Statement, ...]]] = []
        for clause, basics in clause2basics.items():
            for points, bs in basics:
                bs_filtered = [
                    statement for statement in bs
                    if statement in aux
                ]
                if len(bs_filtered) > 0 or any(p in aux_point_names for p in points):
                    essential_aux_basics.append(
                        (
                            tuple(p for p in points if p in aux_point_names),
                            tuple(bs_filtered),
                        )
                    )
        return essential_aux_basics
    
    @staticmethod
    def _create_point_mapping(
        essential_premise_point_names: list[str],
        essential_aux_point_names: list[str],
    ) -> dict[str, str]:
        """Create point name mapping"""
        mp: dict[str, str] = {}
        for idx, p in enumerate(essential_premise_point_names + essential_aux_point_names):
            assert p not in mp
            mp[p] = GeometryProblemWorker._get_apha_geo_solver_var(idx)
        return mp
    
    @staticmethod
    def _generate_problem_clauses_section(
        mp: dict[str, str],
        essential_premise_clauses: list[Clause],
        goals: list[Statement],
    ) -> str:
        """Generate problem clauses section"""
        dep_graph = DependencyGraph(AlgebraicManipulator())
        renamed_clauses = [clause.renamed(mp) for clause in essential_premise_clauses]
        renamed_goal_strs = [
            Statement.from_tokens(
                translate_sentence(mp, goal.to_str().split(' ')),
                dep_graph,
            ).to_str() 
            for goal in goals
        ]
        return '; '.join([str(clause) for clause in renamed_clauses]) + ' ? ' + \
            '; '.join(renamed_goal_strs)

    @staticmethod
    def _generate_problem_predicates_section(
        mp: dict[str, str],
        dep_idx: dict[str, str],
        clause2basics: dict[Clause, list],
        clauses: list[Clause],
        goals: list[Statement],
    ):
        """Generate problem predicates section"""
        renamed_basic_strs_with_idx: list[str] = []
        dep_graph = DependencyGraph(AlgebraicManipulator())
        for clause in clauses:
            basics = clause2basics[clause]
            for points, bs in basics:
                predicate_strs_with_idx: list[str] = []
                for b in bs:
                    # leverage preparsing in Statement.from_tokens to ensure format
                    statement_str = Statement.from_tokens(
                        translate_sentence(mp, b.to_str().split(' ')),
                        dep_graph,
                    ).to_str()
                    assert statement_str not in dep_idx
                    if statement_str not in dep_idx:
                        dep_idx[statement_str] = f"{len(dep_idx):03d}"
                    predicate_strs_with_idx.append(
                        f"{statement_str} [{dep_idx[statement_str]}]")
                if len(predicate_strs_with_idx) > 0:
                    renamed_basic_strs_with_idx.append(
                        ' '.join([mp[p] for p in points]) + ' : ' + ' '.join(predicate_strs_with_idx)
                    )
                else:
                    renamed_basic_strs_with_idx.append(' '.join([mp[p] for p in points]) + ' :')
        renamed_goal_strs = [
            Statement.from_tokens(
                translate_sentence(mp, goal.to_str().split(' ')),
                dep_graph,
            ).to_str()
            for goal in goals
        ]
        return '<problem> ' + ' ; '.join(renamed_basic_strs_with_idx) + ' ? ' + \
            '; '.join(renamed_goal_strs) + ' </problem>'

    @staticmethod
    def _generate_aux_section(
        mp: dict[str, str],
        dep_idx: dict[str, str],
        aux_basics: list[tuple[tuple[str, ...], tuple[Statement, ...]]],
    ):
        """Generate auxiliary information section"""
        renamed_basic_strs_with_idx: list[str] = []
        dep_graph = DependencyGraph(AlgebraicManipulator())
        for points, bs in aux_basics:
            predicate_strs_with_idx: list[str] = []
            for b in bs:
                # leverage preparsing in Statement.from_tokens to ensure format
                statement_str = Statement.from_tokens(
                    translate_sentence(mp, b.to_str().split(' ')),
                    dep_graph,
                ).to_str()
                assert statement_str not in dep_idx
                if statement_str not in dep_idx:
                    dep_idx[statement_str] = f"{len(dep_idx):03d}"
                predicate_strs_with_idx.append(
                    f"{statement_str} [{dep_idx[statement_str]}]")
            renamed_basic_strs_with_idx.append(
                ' '.join([mp[p] for p in points]) + ' : ' + ', '.join(predicate_strs_with_idx)
            )
        if len(renamed_basic_strs_with_idx) == 0:
            return ''
        return '<aux> ' + ' ; '.join(renamed_basic_strs_with_idx) + ' </aux>'

    @staticmethod
    def _generate_numerical_check_section(mp, dep_idx, numercial_checked_premises, numercial_checked_aux):
        """Generate numerical check section"""
        instance = GeometryProblemWorker()
        numerical_check_items = []
        # numercial_checked_premises
        for line in numercial_checked_premises:
            statement_str = instance._statement2str_with_mapping(
                line.statement, mp)
            if statement_str not in dep_idx:
                dep_idx[statement_str] = f"{len(dep_idx):03d}"
        sorted_numercial_checked_premises = sorted(
            numercial_checked_premises, key=lambda line: dep_idx[instance._statement2str_with_mapping(line.statement, mp)])
        for line in sorted_numercial_checked_premises:
            statement_str = instance._statement2str_with_mapping(
                line.statement, mp)
            numerical_check_items.append(
                f"{statement_str} [{dep_idx[statement_str]}]")
        # numercial_checked_premises
        for line in numercial_checked_aux:
            statement_str = instance._statement2str_with_mapping(
                line.statement, mp)
            if statement_str not in dep_idx:
                dep_idx[statement_str] = f"{len(dep_idx):03d}"
        sorted_numercial_checked_aux = sorted(
            numercial_checked_aux, key=lambda line: dep_idx[instance._statement2str_with_mapping(line.statement, mp)])
        for line in sorted_numercial_checked_aux:
            statement_str = instance._statement2str_with_mapping(
                line.statement, mp)
            numerical_check_items.append(
                f"{statement_str} [{dep_idx[statement_str]}]")
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
            statement_str = instance._statement2str_with_mapping(
                line.statement, mp)
            if statement_str not in dep_idx:
                dep_idx[statement_str] = f"{len(dep_idx):03d}"
        sorted_trivial_premises = sorted(
            trivial_premises, key=lambda line: dep_idx[instance._statement2str_with_mapping(line.statement, mp)])
        for line in sorted_trivial_premises:
            statement_str = instance._statement2str_with_mapping(
                line.statement, mp)
            trivial_items.append(
                f"{statement_str} [{dep_idx[statement_str]}]")
        # trivial_premises
        for line in trivial_aux:
            statement_str = instance._statement2str_with_mapping(
                line.statement, mp)
            if statement_str not in dep_idx:
                dep_idx[statement_str] = f"{len(dep_idx):03d}"
        sorted_trivial_aux = sorted(
            trivial_aux, key=lambda line: dep_idx[instance._statement2str_with_mapping(line.statement, mp)])
        for line in sorted_trivial_aux:
            statement_str = instance._statement2str_with_mapping(
                line.statement, mp)
            trivial_items.append(
                f"{statement_str} [{dep_idx[statement_str]}]")
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


from newclid.algebraic_reasoning.algebraic_manipulator import AlgebraicManipulator

def problem_to_dsl(problem: "ProblemJGEX", defs: dict[str, DefinitionJGEX]) -> str:
    """Convert the problem to a DSL string."""
    dep_idx: dict[Statement, str] = {}
    dep_graph = DependencyGraph(AlgebraicManipulator())
    
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
                points = tuple(p.split('@')[0] for p in construction.points)
                mapping = dict(zip(cdef.declare[1:], points + constr_sentence[1:]))
            for points, bs in cdef.basics:
                points = tuple([mapping[x] for x in points])
                for p in points:
                    group[p] = points
                if len(bs) == 0:
                    data_tmp[' '.join(points)] = []
                for b in bs:
                    statement = Statement.from_tokens(translate_sentence(mapping, b), dep_graph)
                    p2deps[points].append(statement)
                    data_tmp[' '.join(points)].append(statement)

        # points = construction.points
        # points = [p.split('@')[0] for p in points]
        # while points:
        #     p = points[0]
        #     gr = group[p]
        #     points = [x for x in points if x not in gr]

        #     deps = []
        #     for dep in p2deps[gr]:
        #         deps.append(dep)
        #     data_tmp[' '.join(gr)] = deps

    # <problem> </problem>
    data_problem = '<problem> '
    string_premise = []
    for k, v in data_tmp.items():
        tmp_string = k + ' : '
        for dep in v:
            if dep not in dep_idx:
                dep_idx[dep] = f"{len(dep_idx):03d}"
            tmp_string += dep.to_str() + f' [{dep_idx[dep]}] '
        string_premise.append(tmp_string)
    data_problem += ' ; '.join([s.strip() for s in string_premise]) + ' ? '
    data_problem += ' ; '.join([
        Statement.from_tokens(goal, dep_graph).to_str()
        for goal in problem.goals
        ])
    data_problem += ' </problem>'
    return data_problem