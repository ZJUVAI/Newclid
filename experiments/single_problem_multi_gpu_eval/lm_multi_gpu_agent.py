from __future__ import annotations

import string
from typing import TYPE_CHECKING

from newclid.agent.lm import LMAgent
from newclid.formulations.definition import DefinitionJGEX
from newclid.formulations.problem import ProblemJGEX
from newclid.proof import ProofState

from experiments.single_problem_multi_gpu_eval.base_multi_gpu_agent import BaseMultiGPUAgent

if TYPE_CHECKING:
    from newclid.formulations.rule import Rule


class LMMultiGPUAgent(BaseMultiGPUAgent):
    def __init__(
        self,
        model_pool,
        decoding_size: int,
        beam_size: int,
        search_depth: int,
        *,
        agent_type: str = "lm_multi_gpu_experiment",
        max_pending_ddar: int = 128,
        trace_writer=None,
    ):
        super().__init__(
            model_pool=model_pool,
            decoding_size=decoding_size,
            beam_size=beam_size,
            search_depth=search_depth,
            agent_type=agent_type,
            max_pending_ddar=max_pending_ddar,
            ddar_returns_proof=False,
            trace_writer=trace_writer,
        )

    def seed_state(self, proof: ProofState, base_proof: ProofState) -> ProblemJGEX:
        del proof, base_proof
        return self.problemJGEX

    def get_problem_from_state(self, state: ProblemJGEX) -> ProblemJGEX:
        return state

    def build_request(
        self,
        *,
        request_id: str,
        state: ProblemJGEX,
        proof: ProofState,
        depth: int,
    ) -> dict[str, object]:
        del depth
        return {
            "request_id": request_id,
            "query": self.problem_to_dsl(state, proof.defs),
            "new_point_name": self.get_new_point_name(state),
            "response_prefix": "<aux> x00",
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
    ) -> ProblemJGEX:
        del prior_state, ddar_result, proof
        return new_problem

    def get_new_point_name(self, problem: ProblemJGEX) -> str:
        num_points = sum(len(clause.points) for clause in problem.constructions)
        return self._get_alpha_geo_solver_var(num_points)

    def _get_alpha_geo_solver_var(self, va_idx: int) -> str:
        letter_part = string.ascii_lowercase[va_idx % 26]
        number_part = va_idx // 26
        return f"{letter_part}{number_part - 1}" if number_part else letter_part

    def try_dsl_to_constructions(self, content: str):
        return LMAgent.try_dsl_to_constructions(self, content)

    def translate_dsl_to_construction(self, point: str, predicate: str, args: list[str]):
        return LMAgent.translate_dsl_to_construction(self, point, predicate, args)

    def problem_to_dsl(self, problem: ProblemJGEX, defs: dict[str, DefinitionJGEX]) -> str:
        return LMAgent.problem_to_dsl(self, problem, defs)

    def run_ddar_c(self, proof: ProofState, rules: list["Rule"], start_time: float, timeout: int = 3600) -> bool:
        return LMAgent.run_ddar_c(proof, rules, start_time, timeout)
