"""Module containing the facade for the external API that must be maintained."""
# !!! Do not change the external API except if you know what you are doing !!!

from __future__ import annotations
from copy import deepcopy
import logging
from pathlib import Path
import traceback
from typing import Optional
from typing_extensions import Self

from geosolver.auxiliary_constructions import insert_aux_to_premise
from geosolver.configs import default_defs_path, default_rules_path
from geosolver.agent.breadth_first_search import BFSDDAR
from geosolver.agent.interface import DeductiveAgent
from geosolver.run_loop import run_loop
from geosolver.problem import Problem, Theorem, Definition, Clause
from geosolver.proof import Proof
from geosolver.proof_writing import write_solution
from geosolver.statement.adder import IntrinsicRules


class GeometricSolver:
    def __init__(
        self,
        proof_state: "Proof",
        problem: "Problem",
        defs: dict[str, "Definition"],
        rules: list["Theorem"],
        deductive_agent: Optional[DeductiveAgent] = None,
    ) -> None:
        self.proof_state = proof_state
        self.problem = problem
        self.defs = defs
        self.rules = rules
        self.problem_string = problem.txt()
        if deductive_agent is None:
            deductive_agent = BFSDDAR()
        self.deductive_agent = deductive_agent
        self.run_infos = None

    @property
    def goal(self):
        return self.problem.goal

    def load_state(self, proof_state: "Proof"):
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

    def run(self, max_steps: int = 10000, timeout: float = 600.0) -> bool:
        success, infos = run_loop(
            self.deductive_agent,
            self.proof_state,
            self.rules,
            self.problem.goal,
            max_steps=max_steps,
            timeout=timeout,
        )
        self.run_infos = infos
        return success

    def write_solution(self, out_file: Path):
        write_solution(self.proof_state, self.problem, out_file)

    def write_all_outputs(self, output_folder_path: Path):
        problem_name = self.problem.url
        self.write_solution(
            output_folder_path / f"{problem_name}_proof_steps.txt",
        )
        self.proof_state.symbols_graph.draw_figure(
            output_folder_path / f"{problem_name}_proof_figure.png",
        )
        self.proof_state.symbols_graph.draw_html(
            output_folder_path / f"{problem_name}.symbols_graph.html"
        )
        self.proof_state.dependency_graph.show_html(
            output_folder_path / f"{problem_name}.dependency_graph.html",
            Theorem.to_dict(self.rules),
        )
        self.proof_state.dependency_graph.proof_subgraph.show_html(
            output_folder_path / f"{problem_name}.proof_subgraph.html",
            Theorem.to_dict(self.rules),
        )

    def draw_figure(self, out_file: Path):
        self.proof_state.symbols_graph.draw_figure(out_file)

    def get_existing_points(self) -> list[str]:
        return [p.name for p in self.proof_state.symbols_graph.all_points()]

    def validate_clause_txt(self, clause_txt: str):
        if clause_txt.startswith("ERROR"):
            return clause_txt
        clause = Clause.from_txt(clause_txt)
        try:
            deepcopy(self.proof_state).add_clause(clause, 0, self.defs)
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
        g_new, _ = Proof.build_problem(p_new, self.defs)

        self.problem = p_new
        self.proof_state = g_new


class GeometricSolverBuilder:
    def __init__(self) -> None:
        self.problem: Optional[Problem] = None
        self.defs: Optional[list[Definition]] = None
        self.rules: Optional[list[Theorem]] = None
        self.proof_state: Optional[Proof] = None
        self.deductive_agent: Optional[DeductiveAgent] = None
        self.disabled_intrinsic_rules: Optional[list[IntrinsicRules]] = None

    def build(self) -> "GeometricSolver":
        if self.problem is None:
            raise ValueError("Did not load problem before building solver.")

        if self.defs is None:
            self.defs = Definition.to_dict(
                Definition.from_txt_file(default_defs_path())
            )

        if self.rules is None:
            self.rules = Theorem.from_txt_file(default_rules_path())

        if self.proof_state is None:
            self.proof_state, _ = Proof.build_problem(
                self.problem, self.defs, self.disabled_intrinsic_rules
            )

        return GeometricSolver(
            self.proof_state, self.problem, self.defs, self.rules, self.deductive_agent
        )

    def load_problem_from_file(
        self, problems_path: Path, problem_name: str, translate: bool = True
    ) -> Self:
        problems = Problem.to_dict(
            Problem.from_txt_file(problems_path, translate=translate)
        )
        if problem_name not in problems:
            raise ValueError(f"Problem name `{problem_name}` not found in `{problems}`")
        self.problem = problems[problem_name]
        return self

    def load_problem_from_txt(
        self, problem_string: str, translate: bool = True
    ) -> Self:
        self.problem = Problem.from_txt(problem_string, translate)
        return self

    def load_rules_from_file(self, rules_path: Optional[Path] = None) -> Self:
        if rules_path is None:
            rules_path = default_rules_path()
        self.rules = Theorem.from_txt_file(rules_path)
        return self

    def load_defs_from_file(self, defs_path: Optional[Path] = None) -> Self:
        if defs_path is None:
            defs_path = default_defs_path()
        self.defs = Definition.to_dict(Definition.from_txt_file(defs_path))
        return self

    def with_deductive_agent(self, deductive_agent: DeductiveAgent):
        self.deductive_agent = deductive_agent
        return self

    def with_disabled_intrinsic_rules(
        self, disabled_intrinsic_rules: list[IntrinsicRules]
    ):
        self.disabled_intrinsic_rules = disabled_intrinsic_rules
        return self
