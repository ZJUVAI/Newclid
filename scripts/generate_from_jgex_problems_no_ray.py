#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate Synthetic Data from JGEX Problems (No Ray Version)

This script generates synthetic discovery data from JGEX format problems
without using Ray for parallel processing. Sequential processing version.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Import from problem_worker
from newclid.generation.problem_worker import GeometryProblemWorker
from newclid.api import CSolver
from newclid.proof import ProofState
from newclid.formulations.clause import Clause
from newclid.dependencies.symbols import Point
from collections import defaultdict
import numpy as np
import re
from newclid.generation.summary import get_first_predicate

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def process_jgex_problem(args: tuple) -> tuple[list, dict]:
    """Process a single JGEX problem (modified version of GeometryProblemWorker)."""
    try:
        pid, fl_statement, seed, max_level, img = args
        start_time = time.time()

        TIMELIMIT = 600  # 10 minutes
        DEADLINE = start_time + TIMELIMIT

        # Skip clause generation - use provided fl_statement directly
        logger.info(f"[{pid}] Processing: {fl_statement[:100]}...")

        # Build solver
        solver, solver_builder = GeometryProblemWorker._build_solver(
            fl_statement,
            max_attempts=100,  # Increased from 1 to handle PointTooCloseError
        )
        if not solver:
            logger.warning(f"[{pid}] Failed to build solver")
            return [], {}

        n_clauses = len(fl_statement.split(';'))

        csolver = CSolver(fl_statement, seed=seed,
                          solver=solver, using_log=True, using_exp=False)

        # Run solver
        csolver.run(max_level=max_level)

        # Generate possible goals
        possible_goals, checkgoals_runtime = GeometryProblemWorker._generate_possible_goals(
            solver)

        logger.info(f"[{pid}] Found {len(possible_goals)} possible goals")

        # Obtain mapping from clauses to basic statements
        proof_state_temp = ProofState(
            rng=np.random.default_rng(seed), defs=solver_builder.defs
        )
        clauses_without_coords: list[Clause] = []
        for clause in solver_builder.problemJGEX.constructions:
            clauses_without_coords.append(
                Clause(
                    points=tuple(p.split('@')[0] for p in clause.points),
                    sentences=clause.sentences,
                )
            )
        clause2basics, clause2args = GeometryProblemWorker._get_all_premise(
            clauses_without_coords, proof_state_temp
        )
        statement_str_idxs = dict()
        pointstr2basicstrs = defaultdict(set)
        basicstr2pointstrs = defaultdict(set)
        for clause in clauses_without_coords:
            for points, basics in clause2basics[clause]:
                for b in basics:
                    b_str = b.to_str()
                    if b_str not in statement_str_idxs:
                        statement_str_idxs[b_str] = len(
                            statement_str_idxs)
                    for pname in points:
                        pointstr2basicstrs[pname].add(b_str)
                        basicstr2pointstrs[b_str].add(pname)

        # Process goals
        # first, group goals by problem key
        group_runtime = time.time()
        eq_predicates_goals = dict()
        for goal in possible_goals:
            if (time.time() > DEADLINE):
                DEADLINE += TIMELIMIT
                break
            # find essential_clauses
            premises, aux = solver.proof.dep_graph.get_premises_and_aux([
                                                                        goal])
            # For ground-truth experiment, we want ALL goals (including those without aux)
            # aux_only = 0
            premises = [dep.statement for dep in premises]
            aux = sorted([dep.statement for dep in aux],
                         key=lambda s: statement_str_idxs[s.to_str()])

            point_names = set()
            for premise in premises:
                for arg in premise.args:
                    if isinstance(arg, Point):
                        point_names.add(arg.name)
            for arg in goal.args:
                if isinstance(arg, Point):
                    point_names.add(arg.name)
            predicates = ' '.join(sorted(point_names)) + ' $$ ' \
                + '; '.join(sorted([statement.to_str() for statement in premises])) + ' $$ ' \
                + '; '.join(sorted([statement.to_str()
                                    for statement in aux]))
            eq_predicates_goals.setdefault(
                predicates, []).append((goal, premises, aux))
        group_runtime = time.time() - group_runtime

        # then, process goal groups
        process_goal_time = time.time()
        generated_data = []
        for _, goal_list in eq_predicates_goals.items():
            if (time.time() > DEADLINE):
                break
            goals = [data[0] for data in goal_list]
            premises = goal_list[0][1]
            aux = goal_list[0][2]
            data = GeometryProblemWorker._process_goals_with_same_statement(
                clause2basics,
                clause2args,
                pointstr2basicstrs,
                basicstr2pointstrs,
                goals,
                solver,
                solver_builder,
                premises,
                aux,
                n_clauses,
                img,
                aux_only=0  # Include all goals
            )
            generated_data.extend(data)
        process_goal_time = time.time() - process_goal_time

        # Inject per-problem seed into each result
        for item in generated_data:
            item["seed"] = seed

        # Create summary
        summary = {
            'total_time': time.time() - start_time,
            'runtime': solver.run_infos['runtime'],
            'checkgoals_runtime': checkgoals_runtime,
            'process_goal_runtime': process_goal_time,
            'group_runtime': group_runtime,
            'n_samples_raw': len(generated_data),
            'goals_raw': [re.search(r'\?\s*(\w+)', d['fl_problem']).group(1) for d in generated_data],
            'first_predicate_raw': [get_first_predicate(d['fl_problem']) for d in generated_data],
            'n_premises_raw': [d['n_premises'] for d in generated_data],
            'n_proof_steps_raw': [d['n_proof_steps'] for d in generated_data],
        }

        logger.info(f"[{pid}] Generated {len(generated_data)} samples in {summary['total_time']:.2f}s")

        return generated_data, summary

    except Exception as e:
        logger.error(f"Error processing problem: {e}")
        import traceback
        traceback.print_exc()
        return [], {}


def load_jgex_problems(input_path: Path) -> List[Dict[str, Any]]:
    """Load JGEX problems from JSONL file."""
    problems = []
    with open(input_path, 'r', encoding='utf-8') as f:
        for line in f:
            data = json.loads(line)
            problems.append({
                'problem_name': data['problem_name'],
                'fl_statement': data['full_problem_with_aux'],
                'seed': abs(hash(data['problem_name'])) % (2**31)
            })
    return problems


def main():
    parser = argparse.ArgumentParser(
        description='Generate synthetic data from JGEX problems'
    )
    parser.add_argument(
        '-i', '--input',
        type=str,
        required=True,
        help='Input JSONL file with JGEX problems'
    )
    parser.add_argument(
        '-o', '--output',
        type=str,
        required=True,
        help='Output JSONL file for synthetic data'
    )
    parser.add_argument(
        '--max-workers',
        type=int,
        default=30,
        help='Maximum number of parallel workers (default: 30)'
    )
    parser.add_argument(
        '--max-level',
        type=int,
        default=500,
        help='Maximum DDAR level (default: 500)'
    )
    parser.add_argument(
        '--img',
        action='store_true',
        help='Generate images for problems'
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        logger.error(f"Input file not found: {input_path}")
        sys.exit(1)

    # Create output directory
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Load problems
    logger.info(f"Loading problems from {input_path}")
    problems = load_jgex_problems(input_path)
    logger.info(f"Loaded {len(problems)} problems")

    # Process problems sequentially (no Ray)
    logger.info("Processing problems sequentially...")
    start_time = time.time()

    all_data = []
    all_summaries = []
    for i, problem in enumerate(problems):
        task_args = (
            i,
            problem['fl_statement'],
            problem['seed'],
            args.max_level,
            args.img
        )
        try:
            data, summary = process_jgex_problem(task_args)
            all_data.extend(data)
            if summary:
                all_summaries.append(summary)
            logger.info(f"Completed {i+1}/{len(problems)}: {len(data)} samples")
        except Exception as e:
            logger.error(f"Failed to process problem {i}: {e}")
            import traceback
            traceback.print_exc()

    # Inject sequential PIDs
    for i, item in enumerate(all_data):
        item['pid'] = f"p{i:06d}"

    # Write output
    logger.info(f"Writing {len(all_data)} samples to {output_path}")
    with open(output_path, 'w', encoding='utf-8') as f:
        for item in all_data:
            json.dump(item, f, ensure_ascii=False)
            f.write('\n')

    # Print summary
    total_time = time.time() - start_time
    logger.info(f"\n{'='*60}")
    logger.info(f"Generation Complete")
    logger.info(f"{'='*60}")
    logger.info(f"  Input problems: {len(problems)}")
    logger.info(f"  Output samples: {len(all_data)}")
    logger.info(f"  Total time: {total_time:.2f}s")
    logger.info(f"  Avg samples/problem: {len(all_data)/len(problems):.1f}")
    logger.info(f"  Output file: {output_path}")


if __name__ == '__main__':
    main()
