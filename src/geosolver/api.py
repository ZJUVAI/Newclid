"""Module containing the facade for the external API that must be maintained."""
# !!! Do not change the external API except if you know what you are doing !!!

from __future__ import annotations
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional
from typing_extensions import Self


from geosolver.agent.breadth_first_search import BFSDDAR
from geosolver.definition.definition import Definition
from geosolver.numerical.draw_figure import draw_figure
from geosolver.rule import Rule
from geosolver.proof import Proof
from geosolver.configs import default_defs_path, default_rules_path
from geosolver.agent.agents_interface import DeductiveAgent
from geosolver.run_loop import run_loop
from geosolver.problem import Problem
from geosolver.proof_writing import write_solution
import numpy as np

if TYPE_CHECKING:
    pass


class GeometricSolver:
    def __init__(
        self,
        proof: "Proof",
        theorems: list[Rule],
        deductive_agent: type[DeductiveAgent],
    ) -> None:
        self.proof = proof
        self.theorems = theorems
        self.problem = proof.problem
        self.defs = proof.defs
        self.goals = proof.goals
        self.deductive_agent = deductive_agent(self.proof, self.theorems)
        self.run_infos: dict[str, Any] = {}

    def run(
        self,
    ) -> bool:
        infos = run_loop(
            self.deductive_agent,
            self.proof,
        )
        self.run_infos = infos
        return infos["success"]

    def write_solution(self, out_file: Optional[Path]):
        write_solution(self.proof, out_file)

    def draw_figure(self, block: bool, out_file: Optional[Path]):
        draw_figure(self.proof.symbols_graph, block, out_file)

    def draw_symbols_graph(self, out_file: Path) -> None:
        raise NotImplementedError()

    def draw_why_graph(self, out_file: Path) -> None:
        raise NotImplementedError()

    def write_all_outputs(self, output_folder_path: Path):
        output_folder_path.mkdir(exist_ok=True, parents=True)
        self.write_solution(output_folder_path / "proof_steps.txt")
        self.draw_figure(False, output_folder_path / "proof_figure.png")
        self.draw_symbols_graph(output_folder_path / "symbols_graph.html")
        logging.info("Written all outputs at %s", output_folder_path)

    def get_setup_string(self) -> str:
        raise NotImplementedError

    def get_proof_state(self) -> str:
        raise NotImplementedError

    def get_problem_string(self) -> str:
        raise NotImplementedError


class GeometricSolverBuilder:
    def __init__(self, seed: Optional[int] = None) -> None:
        self.problem: Optional[Problem] = None
        self._defs: Optional[dict[str, Definition]] = None
        self._rules: Optional[list[Rule]] = None
        self.deductive_agent: Optional[type[DeductiveAgent]] = None
        self.runtime_cache_path: Optional[Path] = None
        self.seed = seed or 998244353

    @property
    def defs(self) -> dict[str, Definition]:
        if self._defs is None:
            self._defs = Definition.to_dict(
                Definition.parse_txt_file(default_defs_path())
            )
        return self._defs

    @property
    def rules(self) -> list[Rule]:
        if self._rules is None:
            self._rules = Rule.parse_txt_file(default_rules_path())
        return self._rules

    def build(self, max_attempts: int = 10000) -> "GeometricSolver":
        if self.problem is None:
            raise ValueError("Did not load problem before building solver.")

        proof_state = Proof.build_problem(
            problem=self.problem,
            defs=self.defs,
            runtime_cache_path=self.runtime_cache_path,
            rng=np.random.default_rng(self.seed),
            max_attempts=max_attempts,
        )

        return GeometricSolver(proof_state, self.rules, self.deductive_agent or BFSDDAR)

    def load_problem_from_file(
        self, problems_path: Path, problem_name: str, rename: bool = False
    ) -> Self:
        """
        `tranlate = True` by default for better LLM training
        """
        self.problem = Problem.from_file(problems_path, problem_name)
        if rename:
            self.problem = self.problem.renamed()
        return self

    def load_problem(self, problem: Problem) -> Self:
        self.problem = problem
        return self

    def del_goal(self) -> Self:
        if self.problem:
            self.problem = Problem(self.problem.name, self.problem.constructions, ())
        return self

    def load_problem_from_txt(self, problem_txt: str) -> Self:
        self.problem = Problem.from_text(problem_txt)
        return self

    def load_rules_from_txt(self, rule_txt: str) -> Self:
        self._rules = Rule.parse_text(rule_txt)
        return self

    def load_rules_from_file(self, rules_path: Optional[Path] = None) -> Self:
        if rules_path is None:
            rules_path = default_rules_path()
        self._rules = Rule.parse_txt_file(rules_path)
        return self

    def load_defs_from_file(self, defs_path: Optional[Path] = None) -> Self:
        if defs_path is None:
            defs_path = default_defs_path()
        self._defs = Definition.to_dict(Definition.parse_txt_file(defs_path))
        return self

    def load_defs_from_txt(self, defs_txt: str) -> Self:
        self._defs = Definition.to_dict(Definition.parse_text(defs_txt))
        return self

    def with_runtime_cache(self, path: Path) -> Self:
        self.runtime_cache_path = path
        return self

    def with_deductive_agent(self, deductive_agent: type[DeductiveAgent]) -> Self:
        self.deductive_agent = deductive_agent
        return self
