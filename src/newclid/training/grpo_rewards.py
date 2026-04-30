"""GRPO rewards for auxiliary-point generation."""

from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass
from fractions import Fraction
from threading import Lock
from typing import Any, Optional

import numpy as np

from newclid.DDAR.build import DDAR
from newclid.configs import default_defs_path, default_rules_path
from newclid.formulations.definition import DefinitionJGEX
from newclid.formulations.problem import ProblemJGEX
from newclid.formulations.rule import Rule
from newclid.numerical.geometries import PointNum
from newclid.agent.runtime.search_runtime import classify_build_exception
from newclid.proof import ProofState
from newclid.training.aux_dsl import (
    extract_aux_body,
    normalize_aux_text,
    try_dsl_to_constructions,
)

logger = logging.getLogger(__name__)
_PROBLEM_BLOCK_RE = re.compile(
    r"<problem>\s*(.*?)\s*</problem>", re.DOTALL | re.IGNORECASE
)


@dataclass(frozen=True)
class AuxEvaluationResult:
    normalized_aux: Optional[str]
    format_ok: bool
    build_ok: bool
    ddar_status: str
    error_type: Optional[str]
    reward: float


def _cache_key(problem_dsl: str, normalized_aux: str) -> str:
    payload = f"{problem_dsl}\n===AUX===\n{normalized_aux}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _coerce_completion_text(completion: Any) -> str:
    if completion is None:
        return ""
    if isinstance(completion, str):
        return completion
    if isinstance(completion, dict):
        if "content" in completion:
            return _coerce_completion_text(completion["content"])
        return str(completion)
    if isinstance(completion, (list, tuple)):
        parts = [_coerce_completion_text(item) for item in completion]
        return "".join(part for part in parts if part)
    return str(completion)


def _coerce_problem_text(problem_dsl: Any) -> str:
    text = "" if problem_dsl is None else str(problem_dsl)
    match = _PROBLEM_BLOCK_RE.search(text)
    return match.group(1).strip() if match else text.strip()


def _resolve_reward_value(
    explicit_value: Optional[float], env_name: str, default_value: float
) -> float:
    if explicit_value is not None:
        return explicit_value
    env_value = os.getenv(env_name)
    if env_value is None:
        return default_value
    return float(env_value)


class AuxRewardEvaluator:
    """Evaluate an aux completion against the geometric engine."""

    def __init__(
        self,
        *,
        solved_reward: Optional[float] = None,
        valid_reward: Optional[float] = None,
        invalid_build_reward: Optional[float] = None,
        invalid_format_reward: Optional[float] = None,
        engine_error_reward: Optional[float] = None,
        build_max_attempts: int = 100,
        ddar_max_level: int = 500,
        random_seed: int = 998244353,
    ) -> None:
        self.solved_reward = _resolve_reward_value(
            solved_reward, "NEWCLID_GRPO_SOLVED_REWARD", 1.0
        )
        self.valid_reward = _resolve_reward_value(
            valid_reward, "NEWCLID_GRPO_VALID_REWARD", 0.25
        )
        self.invalid_build_reward = _resolve_reward_value(
            invalid_build_reward, "NEWCLID_GRPO_INVALID_BUILD_REWARD", -0.25
        )
        self.invalid_format_reward = _resolve_reward_value(
            invalid_format_reward, "NEWCLID_GRPO_INVALID_FORMAT_REWARD", -1.0
        )
        self.engine_error_reward = _resolve_reward_value(
            engine_error_reward, "NEWCLID_GRPO_ENGINE_ERROR_REWARD", 0.0
        )
        self.build_max_attempts = build_max_attempts
        self.ddar_max_level = ddar_max_level
        self.random_seed = random_seed

        self._defs: Optional[dict[str, DefinitionJGEX]] = None
        self._rules: Optional[list[Rule]] = None
        self._cache: dict[str, AuxEvaluationResult] = {}
        self._cache_lock = Lock()
        self._seen_engine_errors: set[str] = set()
        self._seen_parse_errors: set[str] = set()

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

    def evaluate(self, completion: Any, problem_dsl: str) -> AuxEvaluationResult:
        completion_text = _coerce_completion_text(completion)
        aux_body = extract_aux_body(completion_text)
        if aux_body is None:
            return AuxEvaluationResult(
                normalized_aux=None,
                format_ok=False,
                build_ok=False,
                ddar_status="format_invalid",
                error_type="format_invalid",
                reward=self.invalid_format_reward,
            )

        normalized_aux = normalize_aux_text(aux_body)
        key = _cache_key(problem_dsl, normalized_aux)
        with self._cache_lock:
            cached = self._cache.get(key)
        if cached is not None:
            return cached

        result = self._evaluate_uncached(
            aux_body=aux_body, normalized_aux=normalized_aux, problem_dsl=problem_dsl
        )
        with self._cache_lock:
            self._cache[key] = result
        return result

    def engine_error_result(self) -> AuxEvaluationResult:
        return AuxEvaluationResult(
            normalized_aux=None,
            format_ok=False,
            build_ok=False,
            ddar_status="engine_error",
            error_type="engine_error",
            reward=self.engine_error_reward,
        )

    def _evaluate_uncached(
        self, *, aux_body: str, normalized_aux: str, problem_dsl: str
    ) -> AuxEvaluationResult:
        aux_content = aux_body.strip()

        # Remove <aux> tags if present
        if aux_content.startswith("<aux>"):
            aux_content = aux_content[5:]
        if aux_content.endswith("</aux>"):
            aux_content = aux_content[:-6]
        aux_content = aux_content.strip()

        try:
            constructions = try_dsl_to_constructions(aux_content)
        except Exception as exc:
            error_type = "parse_error"
            message = f"{type(exc).__name__}: {exc}"
            if message not in self._seen_parse_errors:
                logger.info("GRPO reward aux parse error: %s", message)
                self._seen_parse_errors.add(message)
            return AuxEvaluationResult(
                normalized_aux=normalized_aux,
                format_ok=False,
                build_ok=False,
                ddar_status="format_invalid",
                error_type=error_type,
                reward=self.invalid_format_reward,
            )
        if not constructions:
            return AuxEvaluationResult(
                normalized_aux=normalized_aux,
                format_ok=False,
                build_ok=False,
                ddar_status="format_invalid",
                error_type="format_invalid",
                reward=self.invalid_format_reward,
            )

        try:
            problem = ProblemJGEX.from_text(_coerce_problem_text(problem_dsl))
            new_problem = problem.with_more_construction(constructions)
            proof = ProofState.build_problemJGEX(
                problemJGEX=new_problem,
                defsJGEX=self.defs,
                rng=np.random.default_rng(self.random_seed),
                max_attempts=self.build_max_attempts,
                problem_path=None,
            )
        except Exception as exc:
            error_type = classify_build_exception(exc)
            return AuxEvaluationResult(
                normalized_aux=normalized_aux,
                format_ok=True,
                build_ok=False,
                ddar_status="build_invalid",
                error_type=error_type,
                reward=self.invalid_build_reward,
            )

        try:
            solved = self._run_ddar(proof)
        except Exception as exc:
            error_type = "engine_error"
            message = f"{type(exc).__name__}: {exc}"
            if message not in self._seen_engine_errors:
                logger.info("GRPO reward DDAR engine error: %s", message)
                self._seen_engine_errors.add(message)
            return AuxEvaluationResult(
                normalized_aux=normalized_aux,
                format_ok=True,
                build_ok=True,
                ddar_status="engine_error",
                error_type=error_type,
                reward=self.engine_error_reward,
            )

        return AuxEvaluationResult(
            normalized_aux=normalized_aux,
            format_ok=True,
            build_ok=True,
            ddar_status="solved" if solved else "unsolved",
            error_type=None,
            reward=self.solved_reward if solved else self.valid_reward,
        )

    def _run_ddar(self, proof: ProofState) -> bool:
        points = self._extract_points(proof)
        premises = self._extract_premises(proof)
        goals = self._extract_goals(proof)
        solved, _ = DDAR.run_ddar(
            "",
            points,
            premises,
            goals,
            self.ddar_max_level,
            True,
            True,
        )
        return solved

    @staticmethod
    def _extract_points(proof: ProofState):
        points = []
        for name, point in proof.symbols_graph.name2node.items():
            if isinstance(point.num, PointNum):
                points.append((name, point.num.x, point.num.y))
        return points

    @staticmethod
    def _extract_premises(proof: ProofState):
        premises = []
        for stmt in proof.dep_graph.hyper_graph:
            predicate = stmt.predicate.NAME
            args = []
            for pt in stmt.args:
                if isinstance(pt, Fraction):
                    args.append(str(pt))
                else:
                    args.append(pt.name)
            premises.append((predicate, args))
        return premises

    @staticmethod
    def _extract_goals(proof: ProofState):
        goals = []
        for stmt in proof.goals:
            predicate = stmt.predicate.NAME
            args = []
            for pt in stmt.args:
                if isinstance(pt, Fraction):
                    args.append(str(pt))
                else:
                    args.append(pt.name)
            goals.append((predicate, args))
        return goals


class AuxReward:
    """Adapter around the evaluator for environments without SWIFT base types."""

    def __init__(self, **kwargs) -> None:
        # Filter out SWIFT-specific kwargs that AuxRewardEvaluator doesn't accept
        kwargs.pop("args", None)
        self.evaluator = AuxRewardEvaluator(**kwargs)

    def evaluate_batch(
        self, completions, fl_problem=None, **kwargs
    ) -> list[AuxEvaluationResult]:
        del kwargs

        if isinstance(completions, str):
            completions = [completions]

        if fl_problem is None:
            raise ValueError("`fl_problem` is required for reward evaluation.")

        if isinstance(fl_problem, str):
            problem_texts = [fl_problem] * len(completions)
        else:
            problem_texts = list(fl_problem)

        if len(problem_texts) != len(completions):
            raise ValueError("`fl_problem` must align with completions.")

        results = []
        for completion, sample_problem_text in zip(completions, problem_texts):
            results.append(self.evaluator.evaluate(completion, sample_problem_text))
        return results

    def __call__(self, completions, fl_problem=None, **kwargs) -> list[float]:
        return [
            result.reward
            for result in self.evaluate_batch(
                completions, fl_problem=fl_problem, **kwargs
            )
        ]
