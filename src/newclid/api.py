from __future__ import annotations
import logging
from pathlib import Path
from typing import Any, Optional, List, Tuple, TYPE_CHECKING
from typing_extensions import Self
from fractions import Fraction


from newclid.agent.ddarn import DDARN
from newclid.formulations.definition import DefinitionJGEX
from newclid.dependencies.dependency_graph import DependencyGraph
from newclid.load_geogebra import load_geogebra
from newclid.numerical.draw_figure import draw_figure
from newclid.algebraic_reasoning.algebraic_manipulator import (
    AlgebraicManipulator,
)
from newclid.formulations.rule import Rule
from newclid.proof import ProofState
from newclid.configs import default_defs_path, default_rules_path
from newclid.agent.agents_interface import DeductiveAgent
from newclid.run_loop import run_loop
from newclid.formulations.problem import ProblemJGEX
from newclid.proof_writing import write_proof_steps
import numpy as np

from newclid.statement import Statement
from newclid.tools import atomize
from newclid.webapp import pull_to_server
from newclid.numerical.geometries import PointNum
from newclid.dependencies.dependency import Dependency
from newclid.DDAR.build import DDAR

import time
import multiprocessing as mp


def _is_ml_agent(agent) -> bool:
    """Check if agent is an ML-based agent (LMAgent, VLMAgent, InternVLMAgent).

    Uses string-based type checking to avoid importing ML dependencies.
    """
    return type(agent).__name__ in ('LMAgent', 'VLMAgent', 'InternVLMAgent')


# Worker function for subprocess isolation (must be at module level for pickling)
def _run_ddar_in_subprocess(problem_name, points, premises, goals, max_level, result_queue):
    """Worker function to run DDAR in a subprocess to isolate memory leaks.

    This function runs in a separate process and puts the result in a queue.
    """
    try:
        solved, dep_graph = DDAR.run_ddar(
            problem_name, points, premises, goals, max_level)
        result_queue.put(
            {"success": True, "solved": solved, "dep_graph": dep_graph})
    except Exception as e:
        import traceback
        result_queue.put({"success": False, "error": str(e),
                         "traceback": traceback.format_exc()})


def extract_solver_data(
    problem_txt: str,
    seed: int = 42,
    max_attempts: int = 100,
) -> Tuple[
    List[Tuple[str, float, float]],      # points
    List[Tuple[str, List[str]]],          # premises
    List[Tuple[str, List[str]]],          # goals
]:
    """Extract (points, premises, goals) from a JGEX problem text.

    Builds the problem via JGEX construction to get numerical coordinates,
    then extracts the structured data.

    Args:
        problem_txt: JGEX problem text
        seed: Random seed for problem construction
        max_attempts: Maximum attempts for numerical construction

    Returns:
        Tuple of (points, premises, goals) where:
        - points: [(name, x, y), ...]
        - premises: [(predicate, [arg1, arg2, ...]), ...]
        - goals: [(predicate, [arg1, arg2, ...]), ...]
    """
    builder = GeometricSolverBuilder(seed=seed)
    builder.load_problem_from_txt(problem_txt)
    builder.with_deductive_agent(DDARN())
    solver = builder.build(max_attempts=max_attempts)

    points = []
    premises = []
    goals = []
    useful_points = []

    # Extract premises
    for stmt in solver.proof.dep_graph.hyper_graph:
        predicate = stmt.predicate.NAME
        args = []
        for pt in stmt.args:
            if isinstance(pt, Fraction):
                args.append(str(pt))
            else:
                args.append(pt.name)
                if pt.name not in useful_points:
                    useful_points.append(pt.name)
        premises.append((predicate, args))

    # Extract goals
    for stmt in solver.proof.goals:
        predicate = stmt.predicate.NAME
        args = []
        for pt in stmt.args:
            if isinstance(pt, Fraction):
                args.append(str(pt))
            else:
                args.append(pt.name)
                if pt.name not in useful_points:
                    useful_points.append(pt.name)
        goals.append((predicate, args))

    # Extract point coordinates
    for name, point in solver.proof.symbols_graph.name2node.items():
        if point.num is not None and isinstance(point.num, PointNum) and name in useful_points:
            points.append((name, point.num.x, point.num.y))

    return points, premises, goals


class GeometricSolver:
    def __init__(
        self, proof: "ProofState", rules: list[Rule], deductive_agent: DeductiveAgent
    ) -> None:
        self.proof = proof
        self.rules = rules
        self.goals = proof.goals
        self.rng = proof.rng
        self.deductive_agent = deductive_agent
        self.run_infos: dict[str, Any] = {}

    def run(self, timeout: int = 3600) -> bool:
        infos = self.deductive_agent.run(
            proof=self.proof, rules=self.rules, timeout=timeout)
        self.run_infos = infos
        return infos["success"]

        # infos = run_loop(self.deductive_agent, proof=self.proof, rules=self.rules, timeout=timeout)
        # self.run_infos = infos
        # return infos["success"]

    def write_proof_steps(self, out_file: Optional[Path] = None):
        if out_file is not None:      
            write_proof_steps(self.proof, out_file)
        else:
            return write_proof_steps(self.proof)

    def draw_figure(self, *, out_file: Optional[Path]):
        draw_figure(self.proof, save_to=out_file, rng=self.rng)

    def write_run_infos(self, out_file: Optional[Path]):
        if out_file is None:
            print(self.run_infos)
        else:
            with open(out_file, "w", encoding="utf-8") as f:
                print(self.run_infos, file=f)

    def write_all_outputs(self, out_folder_path: Optional[Path] = None):
        out_folder_path = out_folder_path or self.proof.problem_path
        assert out_folder_path
        out_folder_path.mkdir(exist_ok=True, parents=True)
        self.write_run_infos(out_folder_path / "run_infos.txt")
        self.write_proof_steps(out_folder_path / "proof_steps.txt")
        self.draw_figure(out_file=out_folder_path / "proof_figure.svg")
        pull_to_server(self.proof, server_path=out_folder_path / "html")
        logging.info("Written all outputs at %s", out_folder_path)


class GeometricSolverBuilder:
    def __init__(self, seed: int = None) -> None:
        self.problemJGEX: Optional[ProblemJGEX] = None
        self._defs: Optional[dict[str, DefinitionJGEX]] = None
        self._rules: Optional[list[Rule]] = None
        self.goals: list[Statement] = []
        self.dep_graph = DependencyGraph(AlgebraicManipulator())
        self.deductive_agent: Optional[DeductiveAgent] = None
        self.seed = seed or 998244353
        self.problem_path: Optional[Path] = None
        self._premises_data: Optional[dict] = None  # For premises-based loading

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
        if self._premises_data:
            # Path 3: Build from premises (no JGEX construction)
            logging.debug("Use premises data to build the proof state")
            proof_state = ProofState.build_premises(
                points=self._premises_data["points"],
                premises=self._premises_data["premises"],
                defsJGEX=self.defs,
                goals_str=self._premises_data["goals"],
                rng=np.random.default_rng(self.seed),
            )
        elif self.problemJGEX:
            # Path 1: Build from JGEX (existing)
            logging.debug(
                f"Use problemJGEX {self.problemJGEX} to build the proof state")
            proof_state = ProofState.build_problemJGEX(
                problemJGEX=self.problemJGEX,
                defsJGEX=self.defs,
                problem_path=self.problem_path,
                rng=np.random.default_rng(self.seed),
                max_attempts=max_attempts,
            )
        else:
            # Path 2: Build from dep_graph (existing)
            logging.info("Use dep_graph to build the proof state")
            proof_state = ProofState(
                rng=np.random.default_rng(self.seed),
                dep_graph=self.dep_graph,
                problem_path=self.problem_path,
                goals=self.goals,
                defs=self.defs,
            )
        if self.deductive_agent is None:
            self.deductive_agent = DDARN()

        if _is_ml_agent(self.deductive_agent):
            self.deductive_agent.problemJGEX = self.problemJGEX

        # proof_state.dep_graph.obtain_numerical_checked_eqangle_and_eqratio()
        return GeometricSolver(proof_state, self.rules, self.deductive_agent)

    def load_problem_from_file(
        self, problems_path: Path, problem_name: str, rename: bool = False
    ) -> Self:
        """
        `translate = True` for better LLM training
        """
        self.problemJGEX = ProblemJGEX.from_file(problems_path, problem_name)
        self.rename_mapping: dict[str, str] | None = None
        if rename:
            self.problemJGEX, self.rename_mapping = self.problemJGEX.renamed_with_mapping()
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

    def load_problem_from_premises(
        self,
        points: List[Tuple[str, float, float]],
        premises: List[Tuple[str, List[str]]],
        goals: List[Tuple[str, List[str]]],
    ) -> Self:
        """Load problem directly from points, premises, and goals.

        Unlike load_problem_from_txt, this does NOT use JGEX construction.
        All points are treated as free points with given coordinates.

        Args:
            points: [(name, x, y), ...] - all points with numerical coordinates
            premises: [(predicate, [arg1, arg2, ...]), ...] - all premises
            goals: [(predicate, [arg1, arg2, ...]), ...] - goals to prove

        Returns:
            Self for method chaining
        """
        self._premises_data = {
            "points": points,
            "premises": premises,
            "goals": goals,
        }
        return self

    def load_rules_from_txt(self, rule_txt: str) -> Self:
        self._rules = Rule.parse_text(rule_txt)
        return self

    def append_rules_from_txt(self, rule_txt: str) -> Self:
        """Append rules to the existing rule set (loading defaults first if needed)."""
        new_rules = Rule.parse_text(rule_txt)
        if self._rules is None:
            self._rules = Rule.parse_txt_file(default_rules_path())
        self._rules = self._rules + new_rules
        return self

    def load_rules_from_file(self, rules_path: Optional[Path] = None) -> Self:
        if rules_path is None:
            rules_path = default_rules_path()
        self._rules = Rule.parse_txt_file(rules_path)
        return self

    def load_defs_from_file(self, defs_path: Optional[Path] = None) -> Self:
        if defs_path is None:
            defs_path = default_defs_path()
        self._defs = DefinitionJGEX.to_dict(
            DefinitionJGEX.parse_txt_file(defs_path))
        return self

    def load_defs_from_txt(self, defs_txt: str) -> Self:
        self._defs = DefinitionJGEX.to_dict(
            DefinitionJGEX.parse_text(defs_txt))
        return self

    def with_deductive_agent(self, deductive_agent: DeductiveAgent) -> Self:
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

    def with_problem_path(self, path: Path) -> Self:
        self.problem_path = path
        return self


class CSolver:
    def __init__(self, problem: str=None, problem_name: str = "anonymity", seed: int = 123, solver: GeometricSolver = None, using_log: bool = False, using_exp: bool = False, points: List[Tuple[str, Any, Any]] = None, premises: List[Tuple[str, List[str]]] = None, goals: List[Tuple[str, List[str]]] = None, custom_rules: List[str] = None, engine: str = "full"):
        self.problem = problem
        self.problem_name = problem_name
        self.seed = seed
        self.log_enabled = using_log
        self.exp_enabled = using_exp
        self.custom_rules = custom_rules or []
        self._ddar = self._load_engine(engine)

        # 构建 solver
        if solver is not None:
            self.solver = solver
        elif problem is not None:
            self.solver = (
                GeometricSolverBuilder(self.seed)
                .load_problem_from_txt(self.problem)
                .build()
            )
        elif points is not None and premises is not None and goals is not None:
            # Direct construction from structured data — no solver needed,
            # only points/premises/goals are used by DDAR C++ engine
            self.solver = None
        else:
            raise ValueError("CSolver requires either 'problem' text, a 'solver' instance, or (points, premises, goals)")

        # 提取信息

        if premises is not None:
            self.premises = premises
        else:
            self.premises: List[Tuple[str, List[str]]] = []
            self.useful_points: List[str] = []
            self._extract_premises()
        if goals is not None:
            self.goals = goals
        else:
            self.goals: List[Tuple[str, List[str]]] = []
            self._extract_goals()
        if points is not None:
            self.points = points
        else:
            self.points: List[Tuple[str, Any, Any]] = []
            self._extract_points()
    
    # -------------------- 内部方法 -------------------- #
    @staticmethod
    def _load_engine(engine: str):
        """Load DDAR engine module (full or weak)."""
        if engine == "weak":
            from newclid.DDAR.build_weak import DDAR as _DDAR
        else:
            from newclid.DDAR.build import DDAR as _DDAR
        return _DDAR

    def _extract_points(self):
        """提取几何点"""
        for name, point in self.solver.proof.symbols_graph.name2node.items():
            if isinstance(point.num, PointNum) and name in self.useful_points:
                self.points.append((name, point.num.x, point.num.y))

    def _extract_premises(self):
        """提取前提"""
        for stmt in self.solver.proof.dep_graph.hyper_graph:
            predicate = stmt.predicate.NAME
            args = []
            for pt in stmt.args:
                if isinstance(pt, Fraction):
                    args.append(str(pt))
                else:
                    args.append(pt.name)
                    if pt.name not in self.useful_points:
                        self.useful_points.append(pt.name)
            self.premises.append((predicate, args))

    def _extract_goals(self):
        """提取目标"""
        for stmt in self.solver.proof.goals:
            predicate = stmt.predicate.NAME
            args = []
            for pt in stmt.args:
                if isinstance(pt, Fraction):
                    args.append(str(pt))
                else:
                    args.append(pt.name)
                    if pt.name not in self.useful_points:
                        self.useful_points.append(pt.name)
            self.goals.append((predicate, args))

    # -------------------- 核心方法 -------------------- #
    def run(self, max_level: int = 500, save_path: str | Path | None = None, custom_rules: List[str] = None) -> bool:
        """
        运行 DDAR 并执行求解。
        :param max_level: 最大推理层数
        :param save_path: 可选，保存证明步骤的路径。
        :param custom_rules: 可选，自定义规则列表（pipe 格式: "name|premises|conclusions"）
        :return: bool 表示是否成功求解。
        """
        t0 = time.time()

        # Merge init-time and run-time custom rules
        all_custom_rules = list(self.custom_rules or [])
        if custom_rules:
            all_custom_rules.extend(custom_rules)

        if all_custom_rules:
            solved, dep_graph = self._ddar.run_ddar_with_custom_theorems(
                self.problem_name, self.points, self.premises, self.goals,
                all_custom_rules, max_level, self.log_enabled, self.exp_enabled)
        else:
            solved, dep_graph = self._ddar.run_ddar(
                self.problem_name, self.points, self.premises, self.goals, max_level, self.log_enabled, self.exp_enabled)

        # Update solver proof state if solver is available
        if self.solver is not None:
            for stmt, deps, reason in dep_graph:
                conclusion = Statement.from_tokens(
                    stmt, self.solver.proof.dep_graph)
                why = []
                flag = True
                for dep in deps:
                    premise = Statement.from_tokens(
                        dep, self.solver.proof.dep_graph)
                    if premise == conclusion:
                        flag = False
                        break
                    why.append(premise)
                if not flag:
                    continue
                dep = Dependency.mk(conclusion, reason, tuple(why))
                self.solver.proof.dep_graph.hyper_graph[conclusion] = dep

            self.solver.run_infos['success'] = solved
            self.solver.run_infos['runtime'] = time.time() - t0

            if solved and save_path:
                out_path = Path(save_path)
                self.solver.write_proof_steps(out_path)

        return solved

    def possible_goals(self) -> List[str]:
        ret = []
        tmp_goals = self._ddar.get_possible_goals(self.problem_name, self.points, self.premises)
        while len(tmp_goals) != 0:
            ret.append(tmp_goals[0])
            predicate = tmp_goals[0].split()[0]
            args = tmp_goals[0].split()[1:]
            self.premises.append((predicate, args))
            tmp_goals = self._ddar.get_possible_goals(self.problem_name, self.points, self.premises)
        return ret

    # -------------------- 辅助输出 -------------------- #
    def print_info(self):
        """打印提取的几何点、前提与目标"""
        print("\n[Points]")
        for p in self.points:
            print(p)
        print("\n[Premises]")
        for pr in self.premises:
            print(pr)
        print("\n[Goals]")
        for g in self.goals:
            print(g)

class DirectSolver:
    """Solver that loads problems directly from (points, premises, goals)."""

    def __init__(
        self,
        points: List[Tuple[str, float, float]],
        premises: List[Tuple[str, List[str]]],
        goal: Tuple[str, List[str]],
        problem_name: str = "direct_problem",
        seed: int = 998244353,
        custom_rules: Optional[List[str]] = None,
    ):
        """Initialize DirectSolver.

        Args:
            points: Point coordinates [(name, x, y), ...]
            premises: Premise list [(predicate, [arg1, arg2, ...]), ...]
            goal: Goal (predicate, [arg1, arg2, ...])
            problem_name: Problem name
            seed: Random seed
            custom_rules: Optional list of custom rule texts
        """
        self.points = list(points)
        self.premises = list(premises)
        self.goal = goal
        self.problem_name = problem_name

        builder = GeometricSolverBuilder(seed=seed)
        builder.load_problem_from_premises(
            points=self.points,
            premises=self.premises,
            goals=[self.goal],
        )
        builder.with_deductive_agent(DDARN())
        if custom_rules:
            builder.append_rules_from_txt("\n".join(custom_rules))

        self.solver = builder.build()
        self.run_infos = {}

    def run(self, timeout: int = 3600) -> bool:
        """Run the solver.

        Args:
            timeout: Timeout in seconds

        Returns:
            bool: Whether the problem was solved
        """
        is_solved = self.solver.run(timeout=timeout)
        self.run_infos = self.solver.run_infos
        return is_solved

    def write_proof_steps(self, out_file: Optional[Path] = None):
        """Write proof steps to file or return as string."""
        if out_file is not None:
            return self.solver.write_proof_steps(out_file)
        else:
            return self.solver.write_proof_steps()

    