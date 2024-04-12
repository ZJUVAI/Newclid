"""Module containing the facade for the external API that must be maintained."""
# !!! Do not change the external API except if you know what you are doing !!!

from __future__ import annotations
from copy import deepcopy
import logging
from pathlib import Path
import traceback
from typing import Optional

from geosolver.auxiliary_constructions import insert_aux_to_premise
from geosolver.configs import default_defs_path, default_rules_path
from geosolver.graph import Graph
from geosolver.numericals import draw
from geosolver.ddar import solve
from geosolver.problem import Problem, Theorem, Definition, Clause
from geosolver.geometry import Point, Circle, Line, Segment
from geosolver.write_proof import write_solution


class GeometricSolver:
    def __init__(
        self,
        proof_state: "Graph",
        problem: "Problem",
        defs: dict[str, "Definition"],
        rules: list["Theorem"],
    ) -> None:
        self.proof_state = proof_state
        self.problem = problem
        self.defs = defs
        self.rules = rules
        self.problem_string = problem.txt()

    @classmethod
    def build_from_files(
        cls,
        problems_path: Path,
        problem_name: str,
        translate: bool,
        defs_path: Optional[Path] = None,
        rules_path: Optional[Path] = None,
    ):
        if defs_path is None:
            defs_path = default_defs_path()
        defs = Definition.from_txt_file(defs_path, to_dict=True)

        if rules_path is None:
            rules_path = default_rules_path()
        rules = Theorem.from_txt_file(rules_path, to_dict=True)

        problems = Problem.from_txt_file(
            problems_path, to_dict=True, translate=translate
        )
        if problem_name not in problems:
            raise ValueError(f"Problem name `{problem_name}` not found in `{problems}`")

        problem = problems[problem_name]
        proof_state, _ = Graph.build_problem(problem, defs)
        return cls(proof_state, problem, defs, rules)

    def load_state(self, proof_state: Graph):
        self.proof_state = deepcopy(proof_state)

    def load_problem_string(self, problem_string: str):
        self.problem_string = problem_string

    def get_problem_string(self) -> str:
        return self.problem.txt()

    def get_proof_state(self) -> str:
        return deepcopy(self.proof_state)

    def get_defs(self):
        return self.defs

    def get_setup_string(self) -> str:
        return self.problem.setup_str_from_problem(self.defs)

    def run_solver(self) -> bool:
        solve(self.proof_state, self.rules, self.problem, max_level=1000)
        goal = self.problem.goal
        goal_args_names = self.proof_state.names2nodes(goal.args)
        if not self.proof_state.check(goal.name, goal_args_names):
            logging.info("Solver failed to solve the problem.")
            return False
        logging.info("Solved.")
        return True

    def write_solution(self, out_file: Path):
        write_solution(self.proof_state, self.problem, out_file)

    def draw_figure(self, out_file: Path):
        draw(
            self.proof_state.type2nodes[Point],
            self.proof_state.type2nodes[Line],
            self.proof_state.type2nodes[Circle],
            self.proof_state.type2nodes[Segment],
            block=False,
            save_to=out_file,
        )

    def get_existing_points(self) -> list[str]:
        return [p.name for p in self.proof_state.all_points()]

    def validate_clause_txt(self, clause_txt: str):
        if clause_txt.startswith("ERROR"):
            return clause_txt
        clause = Clause.from_txt(clause_txt)
        try:
            self.proof_state.copy().add_clause(clause, 0, self.defs)
        except Exception:
            return "ERROR: " + traceback.format_exc()
        return clause_txt

    def add_auxiliary_construction(self, aux_string: str):
        # Update the constructive statement of the problem with the aux point:
        candidate_pstring = insert_aux_to_premise(self.problem_string, aux_string)
        logging.info('Solving: "%s"', candidate_pstring)
        p_new = Problem.from_txt(candidate_pstring)
        p_new.url = self.problem.url
        # This is the new proof state graph representation:
        g_new, _ = Graph.build_problem(p_new, self.defs)

        self.problem = p_new
        self.proof_state = g_new
