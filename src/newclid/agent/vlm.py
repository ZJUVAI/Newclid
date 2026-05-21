from __future__ import annotations

import string
import time
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING, Any

import cairosvg
from PIL import Image, ImageOps

from newclid.agent.base import BaseAgent
from newclid.agent.runtime.search_runtime import (
    get_new_point_name,
    problem_to_visual_dsl,
    run_ddar_on_proof,
    translate_dsl_to_construction,
    try_dsl_to_constructions,
)
from newclid.formulations.problem import ProblemJGEX
from newclid.profiling import increment_profiling_count
from newclid.numerical.draw_clause_figure import draw_clause_figure
from newclid.proof import ProofState

from newclid.agent.runtime.search_runtime import BeamQueue, build_problem_proof

if TYPE_CHECKING:
    from newclid.formulations.rule import Rule


class VLMAgent(BaseAgent):
    def __init__(
        self,
        model_pool,
        decoding_size: int,
        beam_size: int,
        search_depth: int,
        *,
        gpu_batch_size: int = 1,
        gpu_batch_timeout_ms: int = 0,
        agent_type: str = "vlm_parallel",
        max_pending_ddar: int = 128,
        prepare_request_workers: int = 1,
        prepare_prefetch_limit: int = 1,
        search_version: str = "v1",
        eval_first_aux_only: bool = False,
        render_root: str | Path = "temp/eval_rendered_images",
        render_width: int = 1024,
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
        self.render_root = Path(render_root)
        self.render_root.mkdir(parents=True, exist_ok=True)
        self.render_width = render_width
        self._proof_defs: dict[str, Any] | None = None
        self._root_problem_dsl: str | None = None

    def base_ddar_proof(self, proof: ProofState) -> ProofState:
        return deepcopy(proof)

    def seed_state(
        self, proof: ProofState, base_proof: ProofState
    ) -> (
        tuple[ProblemJGEX, ProofState | None]
        | tuple[ProblemJGEX, ProofState | None, str]
    ):
        del proof
        self._proof_defs = base_proof.defs
        self._root_problem_dsl = self.problem_to_dsl(self.problemJGEX, base_proof.defs)
        if self.search_version == "v2":
            return self.problemJGEX, base_proof, ""
        return self.problemJGEX, base_proof

    def get_problem_from_state(
        self,
        state: tuple[ProblemJGEX, ProofState | None]
        | tuple[ProblemJGEX, ProofState | None, str],
    ) -> ProblemJGEX:
        problem = state[0]
        return problem

    def prepare_request(
        self,
        *,
        request_id: str,
        state: tuple[ProblemJGEX, ProofState | None]
        | tuple[ProblemJGEX, ProofState | None, str],
        proof: ProofState,
        depth: int,
    ) -> dict[str, object]:
        del proof
        if self.search_version == "v2":
            problem, current_proof, aux_prefix = state
            query = self._root_problem_dsl
            response_prefix = f"<aux>{aux_prefix} x00"
        else:
            problem, current_proof = state
            query = self.problem_to_dsl(problem, current_proof.defs)
            response_prefix = "<aux> x00"
        if current_proof is None:
            raise ValueError(
                "Visual frontier state is missing the materialized proof for request preparation."
            )
        if query is None:
            raise ValueError(
                "Root VLM query is unavailable during request preparation."
            )
        stem = f"d{depth}_{request_id}"
        svg_path = self.render_root / f"{stem}.svg"
        png_path = self.render_root / f"{stem}.png"

        render_start = time.perf_counter()
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

        # The model is trained on inverted prompts, so keep the image
        # post-processing cost separate from the raw rendering work.
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
            "query": query,
            "img_path": str(png_path),
            "new_point_name": self.get_new_point_name(problem),
            "response_prefix": response_prefix,
            "with_predicate": False,
            "decoding_size": self.decoding_size,
            "_prepare_elapsed_s": time.perf_counter() - render_start,
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
    ) -> (
        tuple[ProblemJGEX, ProofState | None]
        | tuple[ProblemJGEX, ProofState | None, str]
        | None
    ):
        del ddar_result, proof, request, aux_dsl
        if self.search_version == "v2":
            return new_problem, None, selected_aux_text
        del prior_state, raw_aux_text, selected_aux_text
        return new_problem, None

    def finalize_next_queue(
        self,
        *,
        next_queue: BeamQueue,
        profiling: dict[str, Any],
    ) -> BeamQueue:
        if self._proof_defs is None:
            raise ValueError(
                "Visual agent definitions are unavailable for frontier materialization."
            )

        materialized_queue = BeamQueue(max_size=next_queue.max_size)
        for val, stable_key, _, node in next_queue.iter_entries():
            node_id, parent_node_id, path_key, state = node
            if self.search_version == "v2":
                problem, current_proof, aux_prefix = state
            else:
                problem, current_proof = state
                aux_prefix = None
            if current_proof is None:
                try:
                    current_proof = build_problem_proof(problem, self._proof_defs)
                except Exception as exc:
                    increment_profiling_count(
                        profiling, "next_frontier_proof_build_failed_count"
                    )
                    self._trace(
                        "next_frontier_proof_build_failed",
                        node_id=node_id,
                        parent_node_id=parent_node_id,
                        path_key=path_key,
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                    )
                    continue
                increment_profiling_count(profiling, "next_frontier_proof_built_count")
            if self.search_version == "v2":
                next_state = (problem, current_proof, aux_prefix)
            else:
                next_state = (problem, current_proof)
            materialized_queue.add(
                node=(node_id, parent_node_id, path_key, next_state),
                val=val,
                stable_key=stable_key,
            )

        return materialized_queue

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

    def problem_to_dsl(self, problem: ProblemJGEX, defs) -> str:
        return problem_to_visual_dsl(problem, defs)

    def run_ddar_c(
        self,
        proof: ProofState,
        rules: list["Rule"],
        start_time: float,
        timeout: int = 3600,
    ) -> bool:
        del rules, start_time, timeout
        return run_ddar_on_proof(proof)
