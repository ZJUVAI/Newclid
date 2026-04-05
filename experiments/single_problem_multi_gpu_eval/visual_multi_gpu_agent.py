from __future__ import annotations

import string
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING

import cairosvg
from PIL import Image, ImageOps

from newclid.agent.lm import LMAgent
from newclid.agent.vlm import VLMAgent
from newclid.formulations.problem import ProblemJGEX
from newclid.numerical.draw_clause_figure import draw_clause_figure
from newclid.proof import ProofState

from experiments.single_problem_multi_gpu_eval.base_multi_gpu_agent import BaseMultiGPUAgent

if TYPE_CHECKING:
    from newclid.formulations.rule import Rule


class VisualMultiGPUAgent(BaseMultiGPUAgent):
    def __init__(
        self,
        model_pool,
        decoding_size: int,
        beam_size: int,
        search_depth: int,
        *,
        agent_type: str = "vlm_multi_gpu_experiment",
        max_pending_ddar: int = 128,
        render_root: str | Path = "temp/single_problem_multi_gpu_eval_images",
        render_width: int = 1024,
        trace_writer=None,
    ):
        super().__init__(
            model_pool=model_pool,
            decoding_size=decoding_size,
            beam_size=beam_size,
            search_depth=search_depth,
            agent_type=agent_type,
            max_pending_ddar=max_pending_ddar,
            ddar_returns_proof=True,
            trace_writer=trace_writer,
        )
        self.render_root = Path(render_root)
        self.render_root.mkdir(parents=True, exist_ok=True)
        self.render_width = render_width
        self._render_counter = 0

    def base_ddar_proof(self, proof: ProofState) -> ProofState:
        return deepcopy(proof)

    def seed_state(self, proof: ProofState, base_proof: ProofState) -> tuple[ProblemJGEX, ProofState]:
        del proof
        return self.problemJGEX, base_proof

    def get_problem_from_state(self, state: tuple[ProblemJGEX, ProofState]) -> ProblemJGEX:
        problem, _ = state
        return problem

    def build_request(
        self,
        *,
        request_id: str,
        state: tuple[ProblemJGEX, ProofState],
        proof: ProofState,
        depth: int,
    ) -> dict[str, object]:
        del proof
        problem, current_proof = state
        stem = f"d{depth}_{request_id}_{self._render_counter}"
        self._render_counter += 1
        svg_path = self.render_root / f"{stem}.svg"
        png_path = self.render_root / f"{stem}.png"
        draw_clause_figure(
            current_proof,
            problem,
            str(svg_path),
            current_proof.rng,
            draw_annotations=True,
        )
        cairosvg.svg2png(
            url=str(svg_path),
            write_to=str(png_path),
            output_width=self.render_width,
        )
        with Image.open(png_path) as img:
            if img.mode == "RGBA":
                r, g, b, a = img.split()
                rgb_img = Image.merge("RGB", (r, g, b))
                inverted_rgb = ImageOps.invert(rgb_img)
                r_inv, g_inv, b_inv = inverted_rgb.split()
                img_out = Image.merge("RGBA", (r_inv, g_inv, b_inv, a))
            elif img.mode == "LA":
                lightness, alpha = img.split()
                lightness_inv = ImageOps.invert(lightness)
                img_out = Image.merge("LA", (lightness_inv, alpha))
            else:
                img_out = ImageOps.invert(img.convert("RGB"))
            img_out.save(png_path)

        return {
            "request_id": request_id,
            "query": self.problem_to_dsl(problem, current_proof.defs),
            "img_path": str(png_path),
            "new_point_name": self.get_new_point_name(problem),
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
    ) -> tuple[ProblemJGEX, ProofState] | None:
        del prior_state, proof
        next_proof = ddar_result.get("proof")
        if next_proof is None:
            return None
        return new_problem, next_proof

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

    def problem_to_dsl(self, problem: ProblemJGEX, defs) -> str:
        return VLMAgent.problem_to_dsl(self, problem, defs)

    def run_ddar_c(self, proof: ProofState, rules: list["Rule"], start_time: float, timeout: int = 3600) -> bool:
        return VLMAgent.run_ddar_c(proof, rules, start_time, timeout)
