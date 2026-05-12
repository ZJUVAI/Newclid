from __future__ import annotations

import string
from typing import TYPE_CHECKING, Any

from newclid.agent.base import BaseAgent
from newclid.agent.runtime.search_runtime import (
    get_new_point_name,
    problem_to_text_dsl,
    run_ddar_on_proof,
    translate_dsl_to_construction,
    try_dsl_to_constructions,
)
from newclid.formulations.problem import ProblemJGEX
from newclid.proof import ProofState

if TYPE_CHECKING:
    from newclid.formulations.definition import DefinitionJGEX
    from newclid.formulations.rule import Rule


class LMAgent(BaseAgent):
    def __init__(
        self,
        model_pool,
        decoding_size: int,
        beam_size: int,
        search_depth: int,
        *,
        gpu_batch_size: int = 1,
        gpu_batch_timeout_ms: int = 0,
        agent_type: str = "lm_parallel",
        max_pending_ddar: int = 128,
        prepare_request_workers: int = 1,
        prepare_prefetch_limit: int = 1,
        search_version: str = "v1",
        eval_first_aux_only: bool = False,
        trace_writer=None,
    ):
        super().__init__(
            model_pool=model_pool,
            decoding_size=decoding_size,
            beam_size=beam_size,
            search_depth=search_depth,
            gpu_batch_size=gpu_batch_size,
            gpu_batch_timeout_ms=gpu_batch_timeout_ms,
            agent_type=agent_type,
            max_pending_ddar=max_pending_ddar,
            prepare_request_workers=prepare_request_workers,
            prepare_prefetch_limit=prepare_prefetch_limit,
            ddar_returns_proof=False,
            eval_first_aux_only=eval_first_aux_only,
            trace_writer=trace_writer,
        )
        if search_version not in {"v1", "v2"}:
            raise ValueError(f"Unsupported search_version: {search_version}")
        self.search_version = search_version
        self._root_problem_dsl: str | None = None

    def seed_state(
        self, proof: ProofState, base_proof: ProofState
    ) -> ProblemJGEX | tuple[ProblemJGEX, str]:
        del proof
        self._root_problem_dsl = self.problem_to_dsl(self.problemJGEX, base_proof.defs)
        if self.search_version == "v2":
            return self.problemJGEX, ""
        return self.problemJGEX

    def get_problem_from_state(
        self, state: ProblemJGEX | tuple[ProblemJGEX, str]
    ) -> ProblemJGEX:
        if self.search_version == "v2":
            problem, _ = state
            return problem
        return state

    def prepare_request(
        self,
        *,
        request_id: str,
        state: ProblemJGEX | tuple[ProblemJGEX, str],
        proof: ProofState,
        depth: int,
    ) -> dict[str, object]:
        del depth
        if self.search_version == "v2":
            problem, aux_prefix = state
            query = self._root_problem_dsl
            response_prefix = f"<aux>{aux_prefix} x00"
        else:
            problem = state
            query = self.problem_to_dsl(problem, proof.defs)
            response_prefix = "<aux> x00"
        if query is None:
            raise ValueError("Root LM query is unavailable during request preparation.")
        return {
            "request_id": request_id,
            "query": query,
            "new_point_name": self.get_new_point_name(problem),
            "response_prefix": response_prefix,
            "with_predicate": False,
            "decoding_size": self.decoding_size,
        }

    def make_next_state_from_unsolved_ddar(
        self,
        *,
        new_problem: ProblemJGEX,
        prior_state,
        ddar_result: dict[str, object],
        proof: ProofState,
        request: dict[str, Any],
        aux_dsl: str,
        raw_aux_text: str,
        selected_aux_text: str,
    ) -> ProblemJGEX | tuple[ProblemJGEX, str]:
        del ddar_result, proof, aux_dsl
        if self.search_version == "v2":
            del request
            return new_problem, selected_aux_text
        del prior_state, request, raw_aux_text, selected_aux_text
        return new_problem

    def get_new_point_name(self, problem: ProblemJGEX) -> str:
        return get_new_point_name(problem)

    def _get_alpha_geo_solver_var(self, va_idx: int) -> str:
        letter_part = string.ascii_lowercase[va_idx % 26]
        number_part = va_idx // 26
        return f"{letter_part}{number_part - 1}" if number_part else letter_part

    def try_dsl_to_constructions(self, content: str):
        return try_dsl_to_constructions(content)

    def translate_dsl_to_construction(
        self, point: str, predicate: str, args: list[str]
    ):
        return translate_dsl_to_construction(point, predicate, args)

    def problem_to_dsl(
        self, problem: ProblemJGEX, defs: dict[str, DefinitionJGEX]
    ) -> str:
        return problem_to_text_dsl(problem, defs)

    def run_ddar_c(
        self,
        proof: ProofState,
        rules: list["Rule"],
        start_time: float,
        timeout: int = 3600,
    ) -> bool:
        del rules, start_time, timeout
        return run_ddar_on_proof(proof)
