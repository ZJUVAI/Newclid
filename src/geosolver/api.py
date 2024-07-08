"""Module containing the facade for the external API that must be maintained."""
# !!! Do not change the external API except if you know what you are doing !!!

from __future__ import annotations
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Type
from typing_extensions import Self


from geosolver.agent.breadth_first_search import BFSDDAR
from geosolver.definition.definition import Definition
from geosolver.numerical.draw_figure import draw_figure
from geosolver.reasoning_engines.algebraic_reasoning.algebraic_manipulator import (
    AlgebraicManipulator,
)
from geosolver.reasoning_engines.engines_interface import ReasoningEngine
from geosolver.theorem import Theorem
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
        deductive_agent: DeductiveAgent,
    ) -> None:
        self.proof = proof
        self.problem = proof.problem
        self.defs = proof.defs
        self.goals = proof.goals
        self.deductive_agent = deductive_agent
        self.run_infos: dict[str, Any] = {}

    def run(
        self,
        max_steps: int = 10000,
        timeout: float = 600.0,
        stop_on_goal: bool = True,
    ) -> bool:
        success, infos = run_loop(
            self.deductive_agent,
            self.proof,
            max_steps=max_steps,
            stop_on_goal=stop_on_goal,
            timeout=timeout,
        )
        self.run_infos = infos
        return success

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


class GeometricSolverBuilder:
    def __init__(self, seed: Optional[int] = None) -> None:
        self.problem: Optional[Problem] = None
        self.defs: Optional[dict[str, Definition]] = None
        self.rules: Optional[list[Theorem]] = None
        self.deductive_agent: Optional[type[DeductiveAgent]] = None
        self.runtime_cache_path: Optional[Path] = None
        self.reasoning_engines: dict[str, Type[ReasoningEngine]] = {
            "AR": AlgebraicManipulator
        }
        self.rng = (
            np.random.default_rng(seed) if seed else np.random.default_rng(998244353)
        )

    def build(self) -> "GeometricSolver":
        if self.problem is None:
            raise ValueError("Did not load problem before building solver.")

        if self.defs is None:
            self.defs = Definition.to_dict(
                Definition.parse_txt_file(default_defs_path())
            )

        if self.rules is None:
            self.rules = Theorem.parse_txt_file(default_rules_path())

        proof_state = Proof.build_problem(
            problem=self.problem,
            defs=self.defs,
            reasoning_engines=self.reasoning_engines,
            runtime_cache_path=self.runtime_cache_path,
            rng=self.rng,
        )

        return GeometricSolver(
            proof_state,
            self.deductive_agent(self.defs, self.rules)
            if self.deductive_agent
            else BFSDDAR(self.defs, self.rules),
        )

    def load_problem_from_file(
        self, problems_path: Path, problem_name: str, translate: bool = True
    ) -> Self:
        """
        `tranlate = True` by default for better LLM training
        """
        problems = Problem.to_dict(Problem.parse_txt_file(problems_path))
        if problem_name not in problems:
            raise ValueError(
                f"Problem name `{problem_name}` not found in {list(problems.keys())}"
            )
        self.problem = problems[problem_name]
        return self

    def del_goal(self) -> Self:
        if self.problem:
            self.problem = Problem(self.problem.url, self.problem.constructions, ())
        return self

    def load_problem_from_txt(self, problem_txt: str) -> Self:
        self.problem = Problem.from_text(problem_txt)
        return self

    def load_rules_from_txt(self, rule_txt: str) -> Self:
        self.rules = Theorem.parse_text(rule_txt)
        return self

    def load_rules_from_file(self, rules_path: Optional[Path | str] = None) -> Self:
        if rules_path is None:
            rules_path = default_rules_path()
        self.rules = Theorem.parse_txt_file(rules_path)
        return self

    def load_defs_from_file(self, defs_path: Optional[Path | str] = None) -> Self:
        if defs_path is None:
            defs_path = default_defs_path()
        self.defs = Definition.to_dict(Definition.parse_txt_file(defs_path))
        return self

    def load_defs_from_txt(self, defs_txt: str) -> Self:
        self.defs = Definition.to_dict(Definition.parse_text(defs_txt))
        return self

    def with_runtime_cache(self, path: Path) -> Self:
        self.runtime_cache_path = path
        return self

    def with_deductive_agent(self, deductive_agent: type[DeductiveAgent]) -> Self:
        self.deductive_agent = deductive_agent
        return self

    def with_additional_reasoning_engine(
        self, reasoning_engine: Type[ReasoningEngine], engine_name: str
    ) -> Self:
        self.reasoning_engines[engine_name] = reasoning_engine
        return self
