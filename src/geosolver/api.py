from __future__ import annotations
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional
from typing_extensions import Self


from geosolver.agent.breadth_first_search import BFSDDAR
from geosolver.definition.definition import DefinitionJGEX
from geosolver.dependency.dependency_graph import DependencyGraph
from geosolver.load_geogebra import load_geogebra
from geosolver.numerical.draw_figure import draw_figure
from geosolver.algebraic_reasoning.algebraic_manipulator import (
    AlgebraicManipulator,
)
from geosolver.rule import Rule
from geosolver.proof import ProofState
from geosolver.configs import default_defs_path, default_rules_path
from geosolver.agent.agents_interface import DeductiveAgent
from geosolver.run_loop import run_loop
from geosolver.problem import ProblemJGEX
from geosolver.proof_writing import write_proof_steps
import numpy as np

from geosolver.statement import Statement
from geosolver.tools import atomize

if TYPE_CHECKING:
    pass


class GeometricSolver:
    def __init__(
        self,
        proof: "ProofState",
        theorems: list[Rule],
        deductive_agent: type[DeductiveAgent],
    ) -> None:
        self.proof = proof
        self.theorems = theorems
        self.goals = proof.goals
        self.rng = proof.rng
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

    def write_proof_steps(self, out_file: Optional[Path]):
        write_proof_steps(self.proof, out_file)

    def draw_figure(self, *, out_file: Optional[Path]):
        draw_figure(self.proof, save_to=out_file, rng=self.rng)

    def write_run_infos(self, out_file: Optional[Path]):
        if out_file is None:
            print(self.run_infos)
        else:
            with open(out_file, "w", encoding="utf-8") as f:
                print(self.run_infos, file=f)

    def write_all_outputs(self, out_folder_path: Path):
        out_folder_path.mkdir(exist_ok=True, parents=True)
        self.write_run_infos(out_folder_path / "run_infos.txt")
        self.write_proof_steps(out_folder_path / "proof_steps.txt")
        self.draw_figure(out_file=out_folder_path / "proof_figure.svg")
        logging.info("Written all outputs at %s", out_folder_path)


class GeometricSolverBuilder:
    def __init__(self, seed: int) -> None:
        self.problemJGEX: Optional[ProblemJGEX] = None
        self._defs: Optional[dict[str, DefinitionJGEX]] = None
        self._rules: Optional[list[Rule]] = None
        self.goals: list[Statement] = []
        self.dep_graph = DependencyGraph(AlgebraicManipulator())
        self.deductive_agent: Optional[type[DeductiveAgent]] = None
        self.runtime_cache_path: Optional[Path] = None
        self.seed = seed or 998244353

    @property
    def defs(self) -> dict[str, DefinitionJGEX]:
        if self._defs is None:
            self._defs = DefinitionJGEX.to_dict(
                DefinitionJGEX.parse_txt_file(default_defs_path())
            )
        return self._defs

    @property
    def rules(self) -> list[Rule]:
        if self._rules is None:
            self._rules = Rule.parse_txt_file(default_rules_path())
        return self._rules

    def build(self, max_attempts: int = 10000) -> "GeometricSolver":
        if self.problemJGEX:
            logging.info(f"Use problemJGEX {self.problemJGEX} to build the proof state")
            proof_state = ProofState.build_problemJGEX(
                problemJGEX=self.problemJGEX,
                defsJGEX=self.defs,
                runtime_cache_path=self.runtime_cache_path,
                rng=np.random.default_rng(self.seed),
                max_attempts=max_attempts,
            )
        else:
            logging.info("Use dep_graph to build the proof state")
            proof_state = ProofState(
                rng=np.random.default_rng(self.seed),
                dep_graph=self.dep_graph,
                runtime_cache_path=self.runtime_cache_path,
                goals=self.goals,
                defs=self.defs,
            )

        return GeometricSolver(proof_state, self.rules, self.deductive_agent or BFSDDAR)

    def load_problem_from_file(
        self, problems_path: Path, problem_name: str, rename: bool = False
    ) -> Self:
        """
        `tranlate = True` for better LLM training
        """
        self.problemJGEX = ProblemJGEX.from_file(problems_path, problem_name)
        if rename:
            self.problemJGEX = self.problemJGEX.renamed()
        return self

    def load_problem(self, problem: ProblemJGEX) -> Self:
        self.problemJGEX = problem
        return self

    def del_goals(self) -> Self:
        if self.problemJGEX:
            self.problemJGEX = ProblemJGEX(
                self.problemJGEX.name, self.problemJGEX.constructions, ()
            )
        self.goals = []
        return self

    def load_problem_from_txt(self, problem_txt: str) -> Self:
        self.problemJGEX = ProblemJGEX.from_text(problem_txt)
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
        self._defs = DefinitionJGEX.to_dict(DefinitionJGEX.parse_txt_file(defs_path))
        return self

    def load_defs_from_txt(self, defs_txt: str) -> Self:
        self._defs = DefinitionJGEX.to_dict(DefinitionJGEX.parse_text(defs_txt))
        return self

    def with_runtime_cache(self, path: Path) -> Self:
        self.runtime_cache_path = path
        return self

    def with_deductive_agent(self, deductive_agent: type[DeductiveAgent]) -> Self:
        self.deductive_agent = deductive_agent
        return self

    def load_geogebra(self, path: Path) -> Self:
        load_geogebra(path, self.dep_graph)
        return self

    def load_goal(self, goal: str) -> Self:
        goal_statement = Statement.from_tokens(atomize(goal), self.dep_graph)
        assert goal_statement, "goal must parse"
        self.goals.append(goal_statement)
        return self

    def load_goals_file(self, path: Path) -> Self:
        for goal in atomize(path.read_text(), "\n"):
            if goal:
                self.load_goal(goal)
        return self
