import logging
import time
import signal
from contextlib import contextmanager
from collections import defaultdict
from typing import Dict, Set, Tuple

import ray

from newclid.agent.ddarn import DDARN
from newclid.formulations.definition import DefinitionJGEX
from newclid.formulations.clause import translate_sentence
from newclid.statement import Statement
from newclid.dependencies.symbols import Point
from newclid.dependencies.dependency_graph import DependencyGraph
from newclid.configs import default_defs_path

from newclid.generation.clause_generation import CompoundClauseGen
from newclid.api import GeometricSolver, GeometricSolverBuilder, CSolver

class TimeoutError(Exception):
    pass


@contextmanager
def time_limit(seconds: int):
    def handler(signum, frame):
        raise TimeoutError("Timed out")

    signal.signal(signal.SIGALRM, handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)


class GeometryConfigurationWorker:
    """Worker for generating geometry configurations and point dependencies."""

    defs = DefinitionJGEX.to_dict(DefinitionJGEX.parse_txt_file(default_defs_path()))

    @ray.remote(num_cpus=1, max_retries=0)
    def ray_process_single_configuration(args):
        try:
            return GeometryConfigurationWorker._process_single_configuration(args)
        except MemoryError as e:
            logging.error(f"⚠️ Worker OOM killed: {e}")
            return [], {"error": "oom"}
        except Exception as e:
            logging.error(f"Worker error: {e}")
            return [], {"error": str(e)}

    @staticmethod
    def _process_single_configuration(args):
        """Generate a single configuration with points_info.

        Args:
            args: tuple(pid, seed, n_clauses)
        Returns:
            data: list of dict with keys [configuration, points_info]
            summary: dict for logging/metrics (currently minimal)
        """
        pid, seed, n_clauses = args
        start_time = time.time()

        # geneate fl_statement
        clauses_generator = CompoundClauseGen(seed=seed)
        try:
            with time_limit(10):
                fl_statement = clauses_generator.generate(n_clauses)
        except TimeoutError:
            return [], {}

        # Build solver
        solver, solver_builder = GeometryConfigurationWorker._build_solver(
            fl_statement)
        if not solver:
            return [], {}

        csolver = CSolver(fl_statement, seed=seed, solver=solver)
        unsolved_goals_raw = csolver.possible_goals()  # List[str]

        unsolved_goals = []
        for s in unsolved_goals_raw or []:
            s = s.strip()
            if not s:
                continue
            predicate = s.split()[0]
            unsolved_goals.append(
                {
                    "goal_str": s,
                    "predicate": predicate,
                }
            )


        data = [
            {
                "configuration": fl_statement,
                "unsolved_goals": unsolved_goals,
            }
        ]

        summary = {
            "runtime": time.time() - start_time,
        }

        return data, summary

    @staticmethod
    def _build_solver(fl_statement):
        """Build geometric solver"""
        solver_builder = GeometricSolverBuilder(seed=998244353)
        solver_builder.with_deductive_agent(DDARN())
        solver_builder.load_problem_from_txt(fl_statement)
        try:
            solver = solver_builder.build(max_attempts=1)
            return solver, solver_builder
        except Exception as e:
            logging.info(f"Error: {e}")
            return None, None
