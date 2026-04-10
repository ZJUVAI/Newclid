from __future__ import annotations
import os

os.environ["TOKENIZERS_PARALLELISM"] = "false"
import time
import logging
from typing import TYPE_CHECKING, Any, List, Tuple
from fractions import Fraction
import re
from collections import defaultdict
import heapq
import string
import ray
import numpy as np
import torch
from transformers import AutoProcessor, Qwen3_5ForConditionalGeneration
from transformers.utils import logging as hf_logging
from qwen_vl_utils import process_vision_info
import cairosvg
from PIL import Image, ImageOps
from copy import deepcopy

from newclid.agent.agents_interface import DeductiveAgent
from newclid.formulations.problem import ProblemJGEX
from newclid.formulations.definition import DefinitionJGEX
from newclid.formulations.clause import translate_sentence
from newclid.statement import Statement
from newclid.proof import ProofState
from newclid.predicates.congruence import Cong
from newclid.predicates.midpoint import MidPoint
from newclid.predicates.parallelism import Para
from newclid.predicates.perpendicularity import Perp
from newclid.predicates.collinearity import Coll
from newclid.predicates.cyclic import Cyclic
from newclid.predicates.equal_angles import EqAngle
from newclid.predicates.equal_ratios import EqRatio
from newclid.dependencies.dependency_graph import DependencyGraph
from newclid.algebraic_reasoning.algebraic_manipulator import AlgebraicManipulator
from newclid.numerical.geometries import PointNum
from newclid.numerical.draw_clause_figure import draw_clause_figure
from newclid.DDAR.build import DDAR
from newclid.problem_db import (
    ProblemDBLookup,
    ProblemDBRuntime,
    classify_build_exception,
    summarize_problem_db_runtime,
)

if TYPE_CHECKING:
    from newclid.formulations.rule import Rule

logger = logging.getLogger(__name__)

# Suppress per-worker Transformers weight-loading progress bars during Ray eval.
hf_logging.disable_progress_bar()
hf_logging.set_verbosity_error()

DEBUG_QWEN35_INPUT = os.environ.get("NEWCLID_DEBUG_QWEN35_INPUT", "").lower() in {
    "1",
    "true",
    "yes",
    "on",
}

AUX_PREDICATES = [
    # "coll",
    # "cong",
    # "cyclic",
    # "eqangle",
    # "eqratio",
    # "midp",
    # "para",
    # "perp",
]


class Qwen35Agent(DeductiveAgent):
    def __init__(
        self,
        model_path: list[str],
        decoding_size: int,
        beam_size: int,
        search_depth: int,
        *,
        problem_db_runtime: ProblemDBRuntime | None = None,
        agent_type: str = "qwen35",
    ):
        self.any_new_statement_has_been_added = True
        self.problemJGEX = None
        self.decoding_size = decoding_size
        self.beam_size = beam_size
        self.search_depth = search_depth
        self.problem_db_runtime = problem_db_runtime
        self.agent_type = agent_type
        # LLM model
        self.model_path = model_path
        self.models = []
        self.processors = []
        # Load all models and processors
        for path in self.model_path:
            model = Qwen3_5ForConditionalGeneration.from_pretrained(
                path,
                torch_dtype="auto",
                device_map="auto",
                attn_implementation="flash_attention_2",
                trust_remote_code=True,
            )
            processor = AutoProcessor.from_pretrained(path, trust_remote_code=True)
            self.models.append(model)
            self.processors.append(processor)

    def _log_input_snapshot(
        self,
        *,
        query: str,
        img_path: str,
        messages: list[dict[str, Any]],
        text_prompt: str,
        final_text: str,
        model_inputs,
        prompt_len: int,
    ) -> None:
        if not DEBUG_QWEN35_INPUT:
            return

        logger.debug("Qwen35 input snapshot: query=%s", query)
        logger.debug("Qwen35 input snapshot: img_path=%s", img_path)
        logger.debug("Qwen35 input snapshot: messages=%s", messages)
        logger.debug("Qwen35 input snapshot: text_prompt=%s", text_prompt)
        logger.debug("Qwen35 input snapshot: final_text=%s", final_text)
        logger.debug(
            "Qwen35 input snapshot: model_input_keys=%s", list(model_inputs.keys())
        )
        if "input_ids" in model_inputs:
            logger.debug(
                "Qwen35 input snapshot: input_ids.shape=%s",
                tuple(model_inputs["input_ids"].shape),
            )
        if "pixel_values" in model_inputs:
            logger.debug(
                "Qwen35 input snapshot: pixel_values.shape=%s",
                tuple(model_inputs["pixel_values"].shape),
            )
        if "image_grid_thw" in model_inputs:
            logger.debug(
                "Qwen35 input snapshot: image_grid_thw=%s",
                model_inputs["image_grid_thw"].tolist(),
            )
        logger.debug("Qwen35 input snapshot: prompt_len=%s", prompt_len)

    def _build_model_inputs(self, processor, text: str, image_inputs, video_inputs):
        return processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
            do_resize=False,
        )

    def _log_model_output(
        self,
        *,
        queue_type: str,
        aux_dsl: str | None = None,
        aux_content: str | None = None,
        aux: str | None = None,
        score: float | None = None,
    ) -> None:
        if score is not None:
            logger.debug("Qwen35 output [%s]: score=%s", queue_type, score)
        if aux_dsl is not None:
            logger.debug("Qwen35 output [%s]: aux_dsl=%s", queue_type, aux_dsl)
        if aux_content is not None:
            logger.debug("Qwen35 output [%s]: aux_content=%s", queue_type, aux_content)
        if aux is not None:
            logger.debug("Qwen35 output [%s]: aux=%s", queue_type, aux)

    @staticmethod
    def _update_ddar_stats(
        ddar_stats: dict[str, int], ddar_result: dict[str, Any]
    ) -> None:
        if ddar_result["status"] == "invalid":
            if ddar_result.get("error_type") == "engine_error":
                ddar_stats["remote_engine_invalid"] += 1
            else:
                ddar_stats["remote_build_invalid"] += 1
            return
        ddar_stats["remote_ddar_calls"] += 1
        ddar_stats[f"remote_{ddar_result['status']}"] += 1

    @torch.no_grad()
    def inference(
        self,
        model,
        processor,
        query: str,
        img_path: str,
        new_point_name: str,
        response_prefix: str = "<aux>",
        with_predicate: bool = True,
    ):
        """
        Args:
            model: Model
            processor: Processor
            query: Query string
            img_path: Path to the image
            new_point_name: Name of the new point
            response_prefix: Response prefix
            with_predicate: Whether to use predicate prefix for inference
        Returns:
            aux_dsl_dict: Dictionary of auxiliary constructions, key is aux_dsl, value is score
        """
        logger.debug("Inferencing on query: %s with image: %s", query, img_path)
        aux_dsl_dict = {}

        # 1. Build the multi-modal message (System + User with Image)
        messages = [
            {
                "role": "system",
                "content": "You are a helpful assistant.",
            },
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": img_path},
                    {"type": "text", "text": query},
                ],
            },
        ]

        # 2. Prepare image input
        # use process_vision_info to parse images/videos from messages
        image_inputs, video_inputs = process_vision_info(messages, image_patch_size=16)

        # 3. Generate the base text Prompt (without response_prefix)
        # add_generation_prompt=True will append "<|im_start|>assistant\n"
        text_prompt = processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )

        # 4. Calculate the input length without the prefix (for subsequent slicing)
        # We need to know the length of the prompt when there is no prefix
        inputs_without_prefix = processor(
            text=[text_prompt],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
            # Note: Since qwen-vl-utils already resizes images/videos, pass do_resize=False to the processor to avoid duplicate resizing.
            do_resize=False,
        )
        prompt_len = inputs_without_prefix.input_ids.shape[1]

        if with_predicate and len(AUX_PREDICATES) > 0:
            # Inference with predicate prefix
            beams_per_predicate = self.decoding_size // len(AUX_PREDICATES)
            if beams_per_predicate:
                for aux_predicate_str in AUX_PREDICATES:
                    # Qwen3.5 chat template already inserts the assistant thinking scaffold.
                    text_with_predicate = (
                        text_prompt
                        + response_prefix
                        + " "
                        + new_point_name
                        + " : "
                        + aux_predicate_str
                    )

                    model_inputs = self._build_model_inputs(
                        processor, text_with_predicate, image_inputs, video_inputs
                    )
                    self._log_input_snapshot(
                        query=query,
                        img_path=img_path,
                        messages=messages,
                        text_prompt=text_prompt,
                        final_text=text_with_predicate,
                        model_inputs=model_inputs,
                        prompt_len=prompt_len,
                    )
                    model_inputs = model_inputs.to(model.device)

                    generated_output = model.generate(
                        **model_inputs,
                        max_new_tokens=100,
                        num_beams=beams_per_predicate,
                        num_return_sequences=beams_per_predicate,
                        pad_token_id=processor.tokenizer.pad_token_id,
                        eos_token_id=processor.tokenizer.encode(
                            " ;", add_special_tokens=False
                        )[0],
                        return_dict_in_generate=True,
                        output_scores=True,
                    )

                    scores = generated_output.sequences_scores
                    output_sequences = generated_output.sequences[:, prompt_len:]
                    aux_dsls = processor.batch_decode(
                        output_sequences, skip_special_tokens=True
                    )

                    for aux_dsl, score in zip(aux_dsls, scores):
                        score = score.item()
                        aux_dsl_dict[aux_dsl] = score

        if not with_predicate:
            text_with_prefix = text_prompt + response_prefix + " " + new_point_name

            model_inputs = self._build_model_inputs(
                processor, text_with_prefix, image_inputs, video_inputs
            )
            self._log_input_snapshot(
                query=query,
                img_path=img_path,
                messages=messages,
                text_prompt=text_prompt,
                final_text=text_with_prefix,
                model_inputs=model_inputs,
                prompt_len=prompt_len,
            )
            model_inputs = model_inputs.to(model.device)

            generated_output = model.generate(
                **model_inputs,
                max_new_tokens=100,
                num_beams=self.decoding_size,
                num_return_sequences=self.decoding_size,
                pad_token_id=processor.tokenizer.pad_token_id,
                eos_token_id=processor.tokenizer.encode(" ;", add_special_tokens=False)[
                    0
                ],
                return_dict_in_generate=True,
                output_scores=True,
            )

            scores = generated_output.sequences_scores
            output_sequences = generated_output.sequences[:, prompt_len:]
            aux_dsls = processor.batch_decode(
                output_sequences, skip_special_tokens=True
            )

            for aux_dsl, score in zip(aux_dsls, scores):
                score = score.item()
                aux_dsl_dict[aux_dsl] = score

        return aux_dsl_dict

    def run(
        self, proof: "ProofState", rules: list[Rule], timeout: int = 3600
    ) -> dict[str, Any]:
        """Run DeductiveAgent until saturation or goal found."""
        ddar_stats = {
            "base_calls": 0,
            "remote_ddar_calls": 0,
            "remote_solved": 0,
            "remote_unsolved": 0,
            "remote_build_invalid": 0,
            "remote_engine_invalid": 0,
        }

        def infos(is_success, error_msg=None):
            infos: dict[str, Any] = {}
            infos["runtime"] = time.time() - t0
            infos["success"] = is_success
            infos["steps"] = step
            infos["ddar_stats"] = ddar_stats
            if self.problem_db_runtime is not None:
                infos["problem_db_payload"] = self.problem_db_runtime.export_payload()
                infos["problem_db_stats"] = summarize_problem_db_runtime(
                    self.problem_db_runtime
                )
            if error_msg:
                infos["error"] = error_msg
            return infos

        def process_completed_futures(done_futures, new_queues, depth: int):
            for future in done_futures:
                ddar_result = ray.get(future)
                future_meta = future_info[future]
                if self.problem_db_runtime is not None:
                    self.problem_db_runtime.record_ddar_result(
                        future_meta["lookup"],
                        ddar_result,
                    )
                Qwen35Agent._update_ddar_stats(ddar_stats, ddar_result)

                if ddar_result["status"] == "solved":
                    new_problem = future_meta["problem"]
                    for task in running_futures:
                        ray.cancel(task, force=True)
                    ray.shutdown()
                    logger.info("Success with problem: %s", new_problem)
                    return infos(True, str(new_problem))

                if (
                    ddar_result["status"] == "unsolved"
                    and depth < self.search_depth - 1
                ):
                    new_queues[future_meta["queue_idx"]].add(
                        node=(future_meta["problem"], ddar_result["proof"]),
                        val=future_meta["prev_score"] + future_meta["score"],
                    )
            return None

        t0 = time.time()
        step = 0
        image_dir = "temp/qwen35_images/"
        os.makedirs(image_dir, exist_ok=True)

        # Check goals numerically
        for goal in proof.goals:
            if not goal.check_numerical():
                return infos(False, f"{goal.pretty()} fails numerical check")
        # Run ddar
        ddar_stats["base_calls"] += 1
        base_proof = deepcopy(proof)
        solved = Qwen35Agent.run_ddar_c(base_proof, rules, t0, timeout)
        # if proofed by ddar, return
        if solved:
            return infos(True)
        # else seek help from llm
        else:
            rules_ref = ray.put(rules)
            future_info = dict()
            running_futures = []

            # Create two BeamQueues for each model: one for with_predicate, one for no_predicate
            beam_queues = []
            for i in range(len(self.models)):
                q_with_pred = BeamQueue(max_size=self.beam_size)
                q_with_pred.add(node=(self.problemJGEX, base_proof), val=0)

                q_no_pred = BeamQueue(max_size=self.beam_size)
                q_no_pred.add(node=(self.problemJGEX, base_proof), val=0)

                beam_queues.append([q_with_pred, q_no_pred])

            for depth in range(self.search_depth):
                new_beam_queues = []

                for i in range(len(self.models)):
                    new_queues = [
                        BeamQueue(max_size=self.beam_size),
                        BeamQueue(max_size=self.beam_size),
                    ]

                    # j=0: with_predicate, j=1: no_predicate
                    for j, with_predicate in enumerate([False]):
                        queue_type = "with_pred" if with_predicate else "no_pred"

                        for prev_score, (problem, current_proof) in beam_queues[i][j]:
                            if time.time() - t0 > timeout:
                                ray.shutdown()
                                return infos(False, "Timeout")

                            # draw current figure
                            timestamp = int(time.time() * 1000)
                            svg_path = os.path.join(image_dir, f"{timestamp}.svg")
                            png_path = os.path.join(image_dir, f"{timestamp}.png")
                            draw_clause_figure(
                                current_proof,
                                problem,
                                svg_path,
                                current_proof.rng,
                                draw_annotations=True,
                            )
                            cairosvg.svg2png(
                                url=str(svg_path),
                                write_to=str(png_path),
                                output_width=1024,
                            )

                            # 对生成的 PNG 进行反色处理
                            with Image.open(png_path) as img:
                                if img.mode == "RGBA":
                                    r, g, b, a = img.split()
                                    rgb_img = Image.merge("RGB", (r, g, b))
                                    inverted_rgb = ImageOps.invert(rgb_img)
                                    r_inv, g_inv, b_inv = inverted_rgb.split()
                                    img_out = Image.merge(
                                        "RGBA", (r_inv, g_inv, b_inv, a)
                                    )
                                elif img.mode == "LA":
                                    lightness, alpha = img.split()
                                    lightness_inv = ImageOps.invert(lightness)
                                    img_out = Image.merge("LA", (lightness_inv, alpha))
                                else:
                                    img_out = ImageOps.invert(img.convert("RGB"))
                                img_out.save(png_path)

                            p_dsl = self.problem_to_dsl(problem, base_proof.defs)
                            logger.debug(
                                "Inferencing on query (%s): %s", queue_type, p_dsl
                            )
                            aux_dsl_dict = self.inference(
                                model=self.models[i],
                                processor=self.processors[i],
                                query=p_dsl,
                                img_path=png_path,
                                new_point_name=self.get_new_point_name(problem),
                                response_prefix="<aux> x00",
                                with_predicate=with_predicate,
                            )

                            for aux_dsl, score in aux_dsl_dict.items():
                                try:
                                    aux_content = aux_dsl[len("<aux> x00") :]
                                    self._log_model_output(
                                        queue_type=queue_type,
                                        aux_dsl=aux_dsl,
                                        aux_content=aux_content,
                                        score=score,
                                    )
                                    if not aux_content:
                                        continue
                                    aux = self.try_dsl_to_constructions(aux_content)
                                    self._log_model_output(
                                        queue_type=queue_type,
                                        aux=aux,
                                    )
                                    if aux:
                                        new_problem = problem.with_more_construction(
                                            aux
                                        )
                                        lookup = (
                                            self.problem_db_runtime.lookup_problem(
                                                new_problem
                                            )
                                            if self.problem_db_runtime is not None
                                            else ProblemDBLookup()
                                        )

                                        if lookup.hit_category == "solved":
                                            ray.shutdown()
                                            logger.info(
                                                "Cache hit success with problem: %s",
                                                new_problem,
                                            )
                                            return infos(True, str(new_problem))

                                        if lookup.hit_category == "unsolved":
                                            if depth < self.search_depth - 1:
                                                try:
                                                    cached_proof = (
                                                        ProofState.build_problemJGEX(
                                                            problemJGEX=new_problem,
                                                            defsJGEX=proof.defs,
                                                            rng=np.random.default_rng(
                                                                998244353
                                                            ),
                                                            max_attempts=100,
                                                            problem_path=None,
                                                        )
                                                    )
                                                except Exception:
                                                    continue
                                                new_queues[j].add(
                                                    node=(new_problem, cached_proof),
                                                    val=prev_score + score,
                                                )
                                            continue

                                        if lookup.hit_category == "invalid":
                                            continue

                                        future = run_ddar_remote_qwen35.remote(
                                            new_problem,
                                            proof.defs,
                                            rules_ref,
                                            t0,
                                            timeout,
                                        )
                                        future_info[future] = {
                                            "problem": new_problem,
                                            "prev_score": prev_score,
                                            "score": score,
                                            "queue_idx": j,
                                            "lookup": lookup,
                                        }
                                        running_futures.append(future)
                                except Exception:
                                    continue

                            # check any done task
                            done, running_futures = ray.wait(running_futures, timeout=0)
                            future_result = process_completed_futures(
                                done, new_queues, depth
                            )
                            if future_result is not None:
                                return future_result

                    # check remaining tasks
                    while running_futures:
                        done, running_futures = ray.wait(
                            running_futures, num_returns=min(1000, len(running_futures))
                        )
                        future_result = process_completed_futures(
                            done, new_queues, depth
                        )
                        if future_result is not None:
                            return future_result

                    new_beam_queues.append(new_queues)

                beam_queues = new_beam_queues

            ray.shutdown()
            return infos(False, "Tried but failed.")

    def get_new_point_name(self, problem: ProblemJGEX) -> str:
        num_points = sum([len(clause.points) for clause in problem.constructions])
        return self._get_alpha_geo_solver_var(num_points)

    def _get_alpha_geo_solver_var(self, va_idx):
        """Generate a point name using letters and numbers"""
        letter_part = string.ascii_lowercase[va_idx % 26]
        number_part = va_idx // 26
        return f"{letter_part}{number_part - 1}" if number_part else letter_part

    def step(self, proof: ProofState, rules: list[Rule]) -> bool:
        return

    def try_dsl_to_constructions(self, content):
        points, premises = content.split(";")[0].split(" : ")

        # points
        points = points.strip().split()
        # currently, we only support one point following alphageometry
        if len(points) == 0 or len(points) > 1:
            return
        points = points[0]

        # premises
        premises = re.split(r"\s*\[\d+\]", premises)
        premises = [seg.strip() for seg in premises if seg.strip()]
        # currently, we only support two premises following alphageometry
        if len(premises) > 2:
            return
        # TODO: should we support free points?
        if len(premises) == 0:
            return f"{points} = free {points}"
        result_constructions = []
        for premise in premises:
            parts = premise.split()
            if not parts[0].isalpha():
                return
            construction = self.translate_dsl_to_construction(
                points, parts[0], parts[1:]
            )
            result_constructions.append(construction)
        return points + " = " + ", ".join(result_constructions)

    def translate_dsl_to_construction(
        self, point: str, predicate: str, args: list[str]
    ) -> tuple[str, list[str]]:
        """Translate a predicate into construction

        Args:
            point: str: name of the new point
            predicate: str: name of the predicates, e.g., perp, para, etc.
            args: list[str]: list of predicate args.

        Return:
            (predicate, args): translated to constructive predicate.
        """
        # Line perpendicularity
        if predicate == "perp":
            return Perp.to_constructive(point, tuple(args))

        # Line parallelism
        elif predicate == "para":
            return Para.to_constructive(point, tuple(args))

        # Congruence/Equal distance
        elif predicate == "cong":
            return Cong.to_constructive(point, tuple(args))

        # Midpoint
        elif predicate == "midp":
            return MidPoint.to_constructive(point, tuple(args))

        # Collinearity
        elif predicate == "coll":
            return Coll.to_constructive(point, tuple(args))

        # Equal angles
        elif predicate == "eqangle":

            def arrange_angle_points(a, b, c, d):
                if a == c:
                    return (b, a, d)
                elif a == d:
                    return (b, a, c)
                elif b == c:
                    return (a, b, d)
                elif b == d:
                    return (a, b, c)
                else:
                    return None

            a, b, c, d, e, f, g, h = args
            if (len(set([a, b, c, d, e, f, g, h]))) == 8:
                if point == h:
                    res1 = f"on_aline0 {h} {a} {b} {c} {d} {e} {f} {g}"
                if point == g:
                    res1 = f"on_aline0 {g} {a} {b} {c} {d} {e} {f} {h}"
                if point == f:
                    res1 = f"on_aline0 {f} {c} {d} {a} {b} {g} {h} {e}"
                if point == e:
                    res1 = f"on_aline0 {e} {c} {d} {a} {b} {g} {h} {f}"
                if point == d:
                    res1 = f"on_aline0 {d} {e} {f} {g} {h} {a} {b} {c}"
                if point == c:
                    res1 = f"on_aline0 {c} {e} {f} {g} {h} {a} {b} {d}"
                if point == b:
                    res1 = f"on_aline0 {b} {g} {h} {e} {f} {c} {d} {a}"
                if point == a:
                    res1 = f"on_aline0 {a} {g} {h} {e} {f} {c} {d} {b}"
            else:
                # Handle diagonal line exchange
                if len(set([a, b, c, d])) == 4 and len(set([a, b, e, f])) == 3:
                    a, b, c, d, e, f, g, h = a, b, e, f, c, d, g, h
                res1 = EqAngle.to_constructive(
                    point,
                    arrange_angle_points(a, b, c, d) + arrange_angle_points(e, f, g, h),
                )
            return res1

        # Cyclic (four points on a circle)
        elif predicate == "cyclic":
            return Cyclic.to_constructive(point, tuple(args))

        elif predicate == "eqratio":
            return EqRatio.to_constructive(point, tuple(args))

        # For others, return directly
        return f"{predicate} {' '.join(args)}"

    def problem_to_dsl(
        self, problem: "ProblemJGEX", defs: dict[str, DefinitionJGEX]
    ) -> str:
        """Convert the problem to a DSL string."""
        dep_idx: dict[Statement, str] = {}
        dep_graph = DependencyGraph(AlgebraicManipulator())

        data_tmp = defaultdict(list)
        for construction in problem.constructions:
            group = {}
            p2deps = defaultdict(list)
            for constr_sentence in construction.sentences:
                cdef = defs[constr_sentence[0]]
                if len(constr_sentence) == len(cdef.declare):
                    mapping = dict(zip(cdef.declare[1:], constr_sentence[1:]))
                else:
                    assert len(constr_sentence) + len(construction.points) == len(
                        cdef.declare
                    )
                    points = tuple(p.split("@")[0] for p in construction.points)
                    mapping = dict(zip(cdef.declare[1:], points + constr_sentence[1:]))
                for points, bs in cdef.basics:
                    points = tuple([mapping[x] for x in points])
                    for p in points:
                        group[p] = points
                    if len(bs) == 0:
                        data_tmp[" ".join(points)] = []
                    for b in bs:
                        statement = Statement.from_tokens(
                            translate_sentence(mapping, b), dep_graph
                        )
                        p2deps[points].append(statement)
                        data_tmp[" ".join(points)].append(statement)

        # <problem> </problem>
        data_problem = "<problem> "
        string_premise = []
        for k, v in data_tmp.items():
            tmp_string = k + " : "
            for dep in v:
                if dep not in dep_idx:
                    dep_idx[dep] = f"{len(dep_idx):03d}"
                tmp_string += dep.to_str() + f" [{dep_idx[dep]}] "
            string_premise.append(tmp_string)
        data_problem += " ; ".join([s.strip() for s in string_premise]) + " ? "
        data_problem += " ; ".join(
            [Statement.from_tokens(goal, dep_graph).to_str() for goal in problem.goals]
        )
        data_problem += " </problem>"
        return data_problem

    def _extract_points(proof: ProofState):
        points: List[Tuple[str, Any, Any]] = []
        for name, point in proof.symbols_graph.name2node.items():
            if isinstance(point.num, PointNum):
                points.append((name, point.num.x, point.num.y))
        return points

    def _extract_premises(proof: ProofState):
        premises: List[Tuple[str, List[str]]] = []
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

    def _extract_goals(proof: ProofState):
        goals: List[Tuple[str, List[str]]] = []
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

    @staticmethod
    def run_ddar_c(
        proof: "ProofState", rules: list[Rule], start_time: int, timeout: int = 3600
    ):
        points = Qwen35Agent._extract_points(proof)
        premises = Qwen35Agent._extract_premises(proof)
        goals = Qwen35Agent._extract_goals(proof)

        solved, _ = DDAR.run_ddar("", points, premises, goals, 500, True, True)

        return solved


@ray.remote(num_cpus=1)
def run_ddar_remote_qwen35(
    problem, defs, rules: list[Rule], start_time: int, timeout: int = 3600
):
    eval_start = time.time()
    try:
        proof = ProofState.build_problemJGEX(
            problemJGEX=problem,
            defsJGEX=defs,
            rng=np.random.default_rng(998244353),
            max_attempts=100,
            problem_path=None,
        )
    except Exception as exc:
        return {
            "status": "invalid",
            "elapsed_time": time.time() - eval_start,
            "error_type": classify_build_exception(exc),
            "error_message": str(exc),
            "proof": None,
        }
    try:
        solved = Qwen35Agent.run_ddar_c(proof, rules, start_time, timeout)
    except Exception as exc:
        return {
            "status": "invalid",
            "elapsed_time": time.time() - eval_start,
            "error_type": "engine_error",
            "error_message": str(exc),
            "proof": None,
        }
    return {
        "status": "solved" if solved else "unsolved",
        "elapsed_time": time.time() - eval_start,
        "proof": proof,
    }


class BeamQueue:
    """Keep only the top k objects according to their values."""

    def __init__(self, max_size: int = 512):
        self.queue = []
        self.max_size = max_size
        self.counter = 0
        self.entry_finder = {}
        self.REMOVED = object()

    def add(self, node: object, val: float) -> None:
        """Add a new node to this queue."""

        if len(self.queue) < self.max_size:
            entry = [val, self.counter, node]
            self.counter += 1
            heapq.heappush(self.queue, entry)
            self.entry_finder[node] = entry
        else:
            # Find the minimum node:
            min_val, _, min_node = self.queue[0]
            # replace it if the new node has higher value.
            if val > min_val:
                self.remove(min_node)
                entry = [val, self.counter, node]
                self.counter += 1
                heapq.heappush(self.queue, entry)
                self.entry_finder[node] = entry

    def remove(self, node: object) -> None:
        """Mark an existing node as REMOVED."""
        entry = self.entry_finder.pop(node, None)
        if entry:
            entry[-1] = self.REMOVED
        self._rebuild_heap()

    def _rebuild_heap(self):
        """Rebuild the heap to remove any invalid entries marked as REMOVED."""
        self.queue = [entry for entry in self.queue if entry[-1] is not self.REMOVED]
        heapq.heapify(self.queue)

    def __iter__(self):
        for val, _, node in self.queue:
            if node is not self.REMOVED:
                yield val, node

    def __len__(self) -> int:
        return len(self.queue)

    def __repr__(self) -> str:
        items = ",\n  ".join(
            f"({val:.4f}, {repr(node)})"
            for val, _, node in self.queue
            if node is not self.REMOVED
        )
        return f"BeamQueue(max_size={self.max_size}, size={len(self.queue)}, items=[\n  {items}\n])"
