from __future__ import annotations
import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"
import time
import uuid
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
from modelscope import snapshot_download
from transformers import AutoProcessor, DynamicCache, Qwen3VLForConditionalGeneration
from PIL import Image, ImageOps
from copy import deepcopy

from newclid.agent.agents_interface import DeductiveAgent
from newclid.formulations.problem import ProblemJGEX
from newclid.formulations.definition import DefinitionJGEX
from newclid.formulations.clause import Clause, translate_sentence
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
from newclid.dependencies.dependency import Dependency
from newclid.numerical.geometries import PointNum
from newclid.numerical.draw_clause_figure import draw_clause_figure
from newclid.DDAR.build import DDAR

if TYPE_CHECKING:
    from newclid.formulations.rule import Rule

logger = logging.getLogger(__name__)
# logger.setLevel(logging.INFO)
from qwen_vl_utils import process_vision_info

DEFAULT_VLM_PROCESSOR_MODEL_ID = os.getenv(
    "GENESISGEO_VLM_PROCESSOR_MODEL_ID",
    "Qwen/Qwen3-VL-2B-Instruct",
)
PROCESSOR_ALLOW_PATTERNS = [
    "processor_config.json",
    "preprocessor_config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "added_tokens.json",
    "chat_template.json",
    "vocab.json",
    "merges.txt",
    "*.model",
    "*.tiktoken",
    "config.json",
    "generation_config.json",
    "*.py",
]

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

class VLMAgent(DeductiveAgent):
    VALID_IMAGE_MODES = ("full", "white", "masked_quadrant", "downsample_upsample")

    def __init__(
        self,
        model_path: list[str],
        decoding_size: int,
        beam_size: int,
        search_depth: int,
        image_mode: str = "full",
    ):
        self.any_new_statement_has_been_added = True
        self.decoding_size = decoding_size
        self.beam_size = beam_size
        self.search_depth = search_depth
        if image_mode not in self.VALID_IMAGE_MODES:
            raise ValueError(
                f"Unsupported image_mode: {image_mode}. "
                f"Expected one of {self.VALID_IMAGE_MODES}"
            )
        self.image_mode = image_mode
        # LLM model
        self.model_path = model_path
        self.models = []
        self.processors = []
        self._process_vision_info = process_vision_info
        # Load all models and processors
        for path in self.model_path:
            resolved_model_path = self._resolve_model_path(path)
            processor_source = self._resolve_processor_path(resolved_model_path)

            model = Qwen3VLForConditionalGeneration.from_pretrained(
                resolved_model_path,
                torch_dtype="auto",
                device_map="auto", #"sequential",
                attn_implementation="flash_attention_2"  # Sliding Window Attention is enabled but not implemented for others
            )
            processor = AutoProcessor.from_pretrained(processor_source)
            self.models.append(model)
            self.processors.append(processor)

    @staticmethod
    def _is_local_model_path(path: str) -> bool:
        return os.path.isdir(path) or os.path.isfile(path)

    @classmethod
    def _download_from_modelscope(
        cls,
        model_id: str,
        allow_patterns: list[str] | None = None,
    ) -> str:
        logger.info("Downloading %s from ModelScope", model_id)
        return snapshot_download(model_id=model_id, allow_patterns=allow_patterns)

    @classmethod
    def _resolve_model_path(cls, path: str) -> str:
        if cls._is_local_model_path(path):
            return path
        return cls._download_from_modelscope(path)

    @classmethod
    def _resolve_processor_path(cls, model_path: str) -> str:
        processor_config = os.path.join(model_path, "processor_config.json")
        tokenizer_config = os.path.join(model_path, "tokenizer_config.json")
        if os.path.exists(processor_config) or os.path.exists(tokenizer_config):
            return model_path
        return cls._download_from_modelscope(
            DEFAULT_VLM_PROCESSOR_MODEL_ID,
            allow_patterns=PROCESSOR_ALLOW_PATTERNS,
        )

    @staticmethod
    def _invert_image(img: Image.Image) -> Image.Image:
        if img.mode == "RGBA":
            r, g, b, a = img.split()
            rgb_img = Image.merge("RGB", (r, g, b))
            inverted_rgb = ImageOps.invert(rgb_img)
            r_inv, g_inv, b_inv = inverted_rgb.split()
            return Image.merge("RGBA", (r_inv, g_inv, b_inv, a))
        if img.mode == "LA":
            l, a = img.split()
            l_inv = ImageOps.invert(l)
            return Image.merge("LA", (l_inv, a))
        return ImageOps.invert(img.convert("RGB"))

    @staticmethod
    def _white_fill_for_mode(mode: str):
        if mode == "RGBA":
            return (255, 255, 255, 255)
        if mode == "LA":
            return (255, 255)
        return (255, 255, 255)

    @staticmethod
    def _pil_resampling(name: str):
        resampling = getattr(Image, "Resampling", Image)
        return getattr(resampling, name)

    def _prepare_eval_image(self, png_path: str, rng: np.random.Generator) -> None:
        with Image.open(png_path) as img:
            img.load()
            processed_img = self._invert_image(img)

        if self.image_mode == "full":
            output_img = processed_img
        elif self.image_mode == "white":
            output_img = Image.new(
                processed_img.mode,
                processed_img.size,
                self._white_fill_for_mode(processed_img.mode),
            )
        elif self.image_mode == "masked_quadrant":
            output_img = processed_img.copy()
            width, height = output_img.size
            mid_x = width // 2
            mid_y = height // 2
            quadrants = (
                (0, 0, mid_x, mid_y),
                (mid_x, 0, width, mid_y),
                (0, mid_y, mid_x, height),
                (mid_x, mid_y, width, height),
            )
            quadrant_idx = int(rng.integers(0, len(quadrants)))
            output_img.paste(
                self._white_fill_for_mode(output_img.mode),
                quadrants[quadrant_idx],
            )
            logger.info(
                "Applied masked_quadrant image mode to %s with quadrant %s",
                png_path,
                quadrant_idx,
            )
        elif self.image_mode == "downsample_upsample":
            original_size = processed_img.size
            low_res_size = (
                max(1, min(128, original_size[0])),
                max(1, min(128, original_size[1])),
            )
            downsampled_img = processed_img.resize(
                low_res_size,
                resample=self._pil_resampling("BOX"),
            )
            output_img = downsampled_img.resize(
                original_size,
                resample=self._pil_resampling("BILINEAR"),
            )
            logger.info(
                "Applied downsample_upsample image mode to %s with low-res size %s",
                png_path,
                low_res_size,
            )
        else:
            raise ValueError(
                f"Unsupported image_mode: {self.image_mode}. "
                f"Expected one of {self.VALID_IMAGE_MODES}"
            )

        output_img.save(png_path)
        
    @torch.no_grad()
    def inference(self, model, processor, query: str, img_path: str, new_point_name: str, response_prefix: str = '<aux>', with_predicate: bool = True):
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
        logger.info(f"inferencing on query: {query} with image: {img_path}")
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
            }
        ]

        # 2. Prepare image input
        # use process_vision_info to parse images/videos from messages
        image_inputs, video_inputs = self._process_vision_info(messages, image_patch_size=16)
        
        # 3. Generate the base text Prompt (without response_prefix)
        # add_generation_prompt=True will append "<|im_start|>assistant\n"
        text_prompt = processor.apply_chat_template(
            messages, 
            tokenize=False, 
            add_generation_prompt=True
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
                    # Build prompt with predicate prefix
                    text_with_predicate = text_prompt + response_prefix + ' ' + new_point_name + ' : ' + aux_predicate_str
                    
                    model_inputs = processor(
                        text=[text_with_predicate],
                        images=image_inputs,
                        videos=video_inputs,
                        padding=True,
                        return_tensors="pt",
                        do_resize=False,
                    ).to(model.device)

                    generated_output = model.generate(
                        **model_inputs,
                        max_new_tokens=100,
                        num_beams=beams_per_predicate,
                        num_return_sequences=beams_per_predicate,
                        pad_token_id=151643,
                        eos_token_id=2587,  # ' ;'
                        return_dict_in_generate=True,
                        output_scores=True,
                    )
                    
                    scores = generated_output.sequences_scores
                    output_sequences = generated_output.sequences[:, prompt_len:]
                    aux_dsls = processor.batch_decode(output_sequences, skip_special_tokens=True)
                    
                    for aux_dsl, score in zip(aux_dsls, scores):
                        score = score.item()
                        aux_dsl_dict[aux_dsl] = score
                        logger.info(f"aux_dsl (with_predicate): {aux_dsl}")
        
        if not with_predicate:
            # Inference without predicate prefix
            text_with_prefix = text_prompt + response_prefix + ' ' + new_point_name
            
            model_inputs = processor(
                text=[text_with_prefix],
                images=image_inputs,
                videos=video_inputs,
                padding=True,
                return_tensors="pt",
                do_resize=False,
            ).to(model.device)

            generated_output = model.generate(
                **model_inputs,
                max_new_tokens=100,
                num_beams=self.decoding_size,
                num_return_sequences=self.decoding_size,
                pad_token_id=151643,
                eos_token_id=2587,  # ' ;'
                return_dict_in_generate=True,
                output_scores=True,
            )

            scores = generated_output.sequences_scores
            output_sequences = generated_output.sequences[:, prompt_len:]
            aux_dsls = processor.batch_decode(output_sequences, skip_special_tokens=True)

            for aux_dsl, score in zip(aux_dsls, scores):
                score = score.item()
                aux_dsl_dict[aux_dsl] = score
                logger.info(f"aux_dsl (no_predicate): {aux_dsl}")
            
        return aux_dsl_dict

    def run(self, proof: "ProofState", rules: list[Rule], timeout: int = 3600
        ) -> dict[str, Any]:
        """Run DeductiveAgent until saturation or goal found."""
        def infos(is_success, error_msg = None):
            infos: dict[str, Any] = {}
            infos["runtime"] = time.time() - t0
            infos["success"] = is_success
            infos["steps"] = step
            if error_msg:
                infos["error"] = error_msg
            return infos
        
        t0 = time.time()
        step = 0
        image_dir = "temp/vlm_images_construction_vlm_test/"
        os.makedirs(image_dir, exist_ok=True)
        
        # Check goals numerically 
        for goal in proof.goals:
            if not goal.check_numerical():
                return infos(False, f"{goal.pretty()} fails numerical check")
        # Run ddar
        # logger.info(f"running first ddar")
        base_proof = deepcopy(proof)
        solved = VLMAgent.run_ddar_c(base_proof, rules, t0, timeout)
        # logger.info(f"finish first ddar")
        # if proofed by ddar, return
        if solved:
            return infos(True)
        # else seek help from llm
        else:
            rules_ref = ray.put(rules)
            future_info = dict()
            running_futures = []
            original_p_dsl = self.problem_to_dsl(self.problemJGEX, base_proof.defs)
            
            # Create two BeamQueues for each model: one for with_predicate, one for no_predicate
            # beam_queues[i][j]: i is the model index, j=0 for with_predicate, j=1 for no_predicate
            # Each queue stores (problem, proof, aux_prefix) tuples
            beam_queues = []
            for i in range(len(self.models)):
                q_with_pred = BeamQueue(max_size=self.beam_size)
                q_with_pred.add(node=(self.problemJGEX, base_proof, ""), val=0)
                
                q_no_pred = BeamQueue(max_size=self.beam_size)
                q_no_pred.add(node=(self.problemJGEX, base_proof, ""), val=0)
                
                beam_queues.append([q_with_pred, q_no_pred])

            for depth in range(self.search_depth):
                new_beam_queues = []
                
                for i in range(len(self.models)):
                    new_queues = [BeamQueue(max_size=self.beam_size), BeamQueue(max_size=self.beam_size)]
                    
                    # j=0: with_predicate, j=1: no_predicate
                    for j, with_predicate in enumerate([False]):
                        queue_type = 'with_pred' if with_predicate else 'no_pred'
                        
                        for prev_score, (problem, current_proof, aux_prefix) in beam_queues[i][j]:
                            if time.time() - t0 > timeout:
                                ray.shutdown()
                                return infos(False, 'Timeout')

                            # draw current figure
                            timestamp = int(time.time()*1000)
                            png_path = os.path.join(image_dir, f"{timestamp}.png")
                            
                            try:
                                draw_clause_figure(
                                    current_proof, problem, png_path, current_proof.rng, draw_annotations=True
                                )

                                # 检查 PNG 文件是否存在且不为空
                                if not os.path.exists(png_path) or os.path.getsize(png_path) == 0:
                                    logger.error(f"PNG file {png_path} is empty or doesn't exist")
                                    continue

                                self._prepare_eval_image(png_path, current_proof.rng)

                            except Exception as e:
                                logger.error(f"Error processing image {png_path}: {e}")
                                continue

                            p_dsl = self.problem_to_dsl(problem, base_proof.defs)
                            logger.info(f"inferencing on query ({queue_type}): {p_dsl}")
                            aux_dsl_dict = self.inference(
                                model=self.models[i],
                                processor=self.processors[i],
                                query=original_p_dsl,
                                img_path=png_path,
                                new_point_name=self.get_new_point_name(problem),
                                response_prefix='<aux>' + aux_prefix + ' x00',
                                with_predicate=with_predicate
                            )
                            
                            for aux_dsl, score in aux_dsl_dict.items():
                                try:
                                    aux = self.try_dsl_to_constructions(aux_dsl[len('<aux>' + aux_prefix + ' x00'):])
                                    if aux:
                                        logger.info(f"parsed aux: {aux} from aux_dsl: {aux_dsl}")
                                        new_problem = problem.with_more_construction(aux)
                                        logger.info(f"new_problem: {str(new_problem)}")
                                        future = run_ddar_remote.remote(new_problem, proof.defs, aux, rules_ref, t0, timeout)
                                        aux_prefix_new = aux_dsl[len("<aux>"):]
                                        future_info[future] = (new_problem, prev_score, score, j, aux_prefix_new)
                                        running_futures.append(future)
                                except Exception as e:
                                    continue
                            
                            # check any done task
                            done, running_futures = ray.wait(running_futures, timeout=0)
                            for f in done:
                                solved, new_proof = ray.get(f)
                                logger.info(f"solved: {solved}")
                                if solved is None:
                                    continue
                                elif solved:
                                    new_problem, prev_score, score, queue_idx, aux_prefix = future_info[f]
                                    for task in running_futures:
                                        ray.cancel(task, force=True)
                                    ray.shutdown()
                                    logger.info(f"success with problem: {str(new_problem)}")
                                    return infos(True, str(new_problem))
                                elif depth < self.search_depth - 1:
                                    new_problem, prev_score, score, queue_idx, aux_prefix = future_info[f]
                                    new_queues[queue_idx].add(node=(new_problem, new_proof, aux_prefix), val=prev_score+score)
                    
                    # check remaining tasks
                    while running_futures:
                        done, running_futures = ray.wait(running_futures, num_returns=min(1000, len(running_futures)))
                        for f in done:
                            solved, new_proof = ray.get(f)
                            if solved is None:
                                continue
                            elif solved:
                                new_problem, prev_score, score, queue_idx, aux_prefix = future_info[f]
                                for task in running_futures:
                                    ray.cancel(task, force=True)
                                ray.shutdown()
                                logger.info(f"success with problem: {str(new_problem)}")
                                return infos(True, str(new_problem))
                            elif depth < self.search_depth - 1:
                                new_problem, prev_score, score, queue_idx, aux_prefix = future_info[f]
                                new_queues[queue_idx].add(node=(new_problem, new_proof, aux_prefix), val=prev_score+score)
                    
                    new_beam_queues.append(new_queues)
                
                beam_queues = new_beam_queues

            ray.shutdown()
            return infos(False, 'Tried but failed.')

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
        points, premises = content.split(';')[0].split(' : ')

        # points
        points = points.strip().split()
        # currently, we only support one point following alphageometry
        if len(points) == 0 or len(points) > 1:
            return
        points = points[0]
    
        # premises
        premises = re.split(r"\s*\[\d+\]", premises) # coll a c e [002] coll b d e [003] => 'coll a c e' , 'coll b d e'
        premises = [seg.strip() for seg in premises if seg.strip()]
        # currently, we only support two premises following alphageometry
        if len(premises) > 2:
            return 
            # segments = segments[:2]
        # TODO: should we support free points?
        if len(premises) == 0:
            return f'{points} = free {points}'
        result_constructions = []
        for premise in premises:
            parts = premise.split()
            if not parts[0].isalpha():
                return
            construction = self.translate_dsl_to_construction(points, parts[0], parts[1:])
            result_constructions.append(construction)
        return points + ' = ' + ', '.join(result_constructions)

    def translate_dsl_to_construction(self, point: str, predicate: str, args: list[str]
        ) -> tuple[str, list[str]]:
        """ Translate a predicate into construction
        
        Args:
            point: str: name of the new point
            predicate: str: name of the predicates, e.g., perp, para, etc.
            args: list[str]: list of predicate args.
        
        Return:
            (predicate, args): translated to constructive predicate.
        """
        # Line perpendicularity
        if predicate == 'perp':
            return Perp.to_constructive(point, tuple(args))

        # Line parallelism
        elif predicate == 'para':
            return Para.to_constructive(point, tuple(args))

        # Congruence/Equal distance
        elif predicate == 'cong':
            return Cong.to_constructive(point, tuple(args))

        # Midpoint
        elif predicate == 'midp':
            return MidPoint.to_constructive(point, tuple(args))

        # Collinearity
        elif predicate == 'coll':
            return Coll.to_constructive(point, tuple(args))

        # Equal angles
        elif predicate == 'eqangle':
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
            if(len(set([a, b, c, d, e, f, g, h]))) == 8:
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
                if(len(set([a, b, c, d])) == 4 and len(set([a, b, e, f])) == 3): 
                    a, b, c, d, e, f, g, h = a, b, e, f, c, d, g, h
                res1 = EqAngle.to_constructive(point, arrange_angle_points(a, b, c, d) + arrange_angle_points(e, f, g, h))
            return res1
            
        # Cyclic (four points on a circle)
        elif predicate == 'cyclic':
            return Cyclic.to_constructive(point, tuple(args))

        elif predicate == 'eqratio':
            return EqRatio.to_constructive(point, tuple(args))

        # For others, return directly
        return f"{predicate} {' '.join(args)}"
    
    def problem_to_dsl(self, problem: "ProblemJGEX", defs: dict[str, DefinitionJGEX]) -> str:
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
                    assert len(constr_sentence) + len(construction.points) == len(cdef.declare)
                    points = tuple(p.split('@')[0] for p in construction.points)
                    mapping = dict(zip(cdef.declare[1:], points + constr_sentence[1:]))
                for points, bs in cdef.basics:
                    points = tuple([mapping[x] for x in points])
                    for p in points:
                        group[p] = points
                    if len(bs) == 0:
                        data_tmp[' '.join(points)] = []
                    for b in bs:
                        statement = Statement.from_tokens(translate_sentence(mapping, b), dep_graph)
                        p2deps[points].append(statement)
                        data_tmp[' '.join(points)].append(statement)

        # <problem> </problem>
        data_problem = '<problem> '
        string_premise = []
        for k, v in data_tmp.items():
            tmp_string = k + ' : '
            for dep in v:
                if dep not in dep_idx:
                    dep_idx[dep] = f"{len(dep_idx):03d}"
                tmp_string += dep.to_str() + f' [{dep_idx[dep]}] '
            string_premise.append(tmp_string)
        data_problem += ' ; '.join([s.strip() for s in string_premise]) + ' ? '
        data_problem += ' ; '.join([
            Statement.from_tokens(goal, dep_graph).to_str()
            for goal in problem.goals
            ])
        data_problem += ' </problem>'
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
    def run_ddar_c(proof: "ProofState", rules: list[Rule], start_time: int, timeout: int = 3600): 
        points = VLMAgent._extract_points(proof)
        premises = VLMAgent._extract_premises(proof)
        goals = VLMAgent._extract_goals(proof)
        
        solved, dep_graph = DDAR.run_ddar("", points, premises, goals, 500, True, True)

        for stmt, deps, reason in dep_graph:
            conclusion = Statement.from_tokens(
                stmt, proof.dep_graph)
            why = []
            for dep in deps:
                premise = Statement.from_tokens(
                    dep, proof.dep_graph)
                why.append(premise)
            dep = Dependency.mk(conclusion, reason, tuple(why))
            proof.dep_graph.hyper_graph[conclusion] = dep

        return solved   


@ray.remote(num_cpus=1)
def run_ddar_remote(problem, defs, aux, rules: list[Rule], start_time: int, timeout: int = 3600): 
    try:
        proof = ProofState.build_problemJGEX(
            problemJGEX=problem,
            defsJGEX=defs,
            rng=np.random.default_rng(998244353),
            max_attempts=100,
            problem_path=None,
        )
    except Exception:
        return None, None
    try:
        solved = VLMAgent.run_ddar_c(proof, rules, start_time, timeout)
    except Exception:
        return None, None
    return solved, proof


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
        # return f'BeamQueue(max_size={self.max_size}, size={len(self.queue)}])'
        items = ',\n  '.join(f'({val:.4f}, {repr(node)})' for val, _, node in self.queue if node is not self.REMOVED)
        return f'BeamQueue(max_size={self.max_size}, size={len(self.queue)}, items=[\n  {items}\n])'
