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
import ray
import numpy as np
import torch
import cairosvg
from PIL import Image, ImageOps
from copy import deepcopy
import torchvision.transforms as T
from torchvision.transforms.functional import InterpolationMode
from transformers import AutoModel, AutoTokenizer

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
from newclid.numerical.draw_figure import draw_figure
from newclid.DDAR.build import DDAR

if TYPE_CHECKING:
    from newclid.formulations.rule import Rule


IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)

class InternVLMAgent(DeductiveAgent):
    def __init__(self, model_path: list[str], decoding_size: int, beam_size: int, search_depth: int):
        self.any_new_statement_has_been_added = True
        self.decoding_size = decoding_size
        self.beam_size = beam_size
        self.search_depth = search_depth
        
        # LLM model
        self.model_path = model_path
        self.models = []
        self.tokenizers = []
        
        # Load all models and tokenizers
        for path in self.model_path:
            # 使用官方建议的加载参数
            model = AutoModel.from_pretrained(
                path,
                torch_dtype=torch.bfloat16,
                load_in_8bit=False,
                low_cpu_mem_usage=True,
                use_flash_attn=True,
                trust_remote_code=True,
                device_map="auto"
            ).eval()
            tokenizer = AutoTokenizer.from_pretrained(path, trust_remote_code=True, use_fast=False)
            
            self.models.append(model)
            self.tokenizers.append(tokenizer)
        
    @torch.no_grad()
    def inference(self, model, tokenizer, query: str, img_path: str, response_prefix: str = '<aux>'):
        print(f"inferencing on query: {query} with image: {img_path}")
        aux_dsl_dict = {}

        # [Step 1: Image Processing] - Directly call load_image from the class
        # Note: load_image returns a Tensor on CPU, needs to be moved to GPU and cast to bf16
        pixel_values = self.load_image(img_path, max_num=12).to(torch.bfloat16).to(model.device)
        num_patches = pixel_values.size(0)

        # [Step 2: Build Prompt] - Simplified to direct string concatenation
        # Kept the original System Prompt logic as optional
        # system_content = "You are a geometric intuition assistant. Use the visual diagram to identify spatial relationships and propose the auxiliary construction."
        system_content = "You are a helpful assistant."

        USER_PROMPT_TEMPLATE = (
            "Refer to the geometric diagram provided above. It visually depicts the current proof state.\n\n"
            "[Formal Geometric Statement]\n"
            "The current problem consists of textual hypotheses and a proof goal (marked with '?') in a symbolic format:\n"
            "{content}\n\n"
            "[Context]\n"
            "The symbolic deduction engine cannot prove the goal solely from the current hypotheses. "
            "It requires an auxiliary construction to bridge the logical gap.\n\n"
            "[Task]\n"
            "1. Integrated Analysis: Analyze the textual hypotheses (known constraints), the proof goal (what to prove), and the visual spatial layout together.\n"
            "2. Gap Identification: Use the diagram to identify geometric relationships that help connect the hypotheses to the goal.\n"
            "3. Proposal: Predict the single most effective auxiliary construction step.\n"
            "Output:"
        )
        formatted_user_text = USER_PROMPT_TEMPLATE.format(content=query)

        num_image_token = model.num_image_token
        print(f"[DEBUG] num_image_token per patch: {num_image_token}")
        img_start_token = "<img>"
        img_end_token = "</img>"
        img_context_token = '<IMG_CONTEXT>'
        model.img_context_token_id = tokenizer.convert_tokens_to_ids(img_context_token)
        image_tokens_str = img_start_token + (img_context_token * num_image_token * num_patches) + img_end_token

        # InternVL ChatML format concatenation: <|im_start|>system\n...\n<|im_start|>user\n<image>\n...\n<|im_start|>assistant\n
        base_prompt = (
            "<|im_start|>system\n"
            f"{system_content}<|im_end|>\n"
            "<|im_start|>user\n"
            # f"{image_tokens_str}\n"
            f"{query}<|im_end|>\n"
            "<|im_start|>assistant\n"
        )
        
        # Append the "forced prefix" to the Prompt
        text_with_prefix = base_prompt + response_prefix

        # [Step 3: Tokenize & Calculate Length]
        model_inputs = tokenizer(text_with_prefix, return_tensors='pt').to(model.device)

        # print("-" * 30)
        # print("[DEBUG] Actual Input sent to model:")
        # debug_decoded = tokenizer.decode(model_inputs.input_ids[0], skip_special_tokens=False)
        # print(debug_decoded)
        # print("-" * 30)
        
        # To slice the Output later, we need to know the length before "Prompt + Prefix"
        # However, generate returns [Input + NewTokens].
        # We want the result to be [Prefix + NewTokens].
        # So we calculate the length of base_prompt (without Prefix).
        base_inputs = tokenizer(base_prompt, return_tensors='pt')
        prompt_len = base_inputs.input_ids.shape[1]

        # [Step 4: Generate (Beam Search)]
        # Although the official code uses model.chat, model.generate is more controllable
        # for Beam Search + Scores and forced prefix decoding.
        generated_output = model.generate(
            input_ids=model_inputs.input_ids,
            attention_mask=model_inputs.attention_mask,
            # pixel_values=pixel_values,
            pixel_values=None,
            max_new_tokens=100,
            num_beams=self.decoding_size,
            num_return_sequences=self.decoding_size,
            pad_token_id=151643,
            eos_token_id=2587,
            return_dict_in_generate=True,
            output_scores=True,
            # stop_strings=target_stop_strings,
            # tokenizer=tokenizer, # 必须传入 tokenizer 才能让 stop_strings 生效
        )

        # print("-" * 30)
        # print("[DEBUG] Actual Outputs by model:")
        # outputs_decoded = tokenizer.batch_decode(generated_output.sequences, skip_special_tokens=True)
        # for output in outputs_decoded:
        #     print(output)
        # print("-" * 30)

        # [Step 5: Decoding and Post-processing]
        scores = generated_output.sequences_scores
        # Slice starting from prompt_len, so the result includes the Prefix (<aux>)
        output_sequences = generated_output.sequences[:, prompt_len:]
        
        # aux_dsls = tokenizer.batch_decode(output_sequences, skip_special_tokens=True)
        aux_dsls = tokenizer.batch_decode(generated_output.sequences, skip_special_tokens=True)

        for aux_dsl, score in zip(aux_dsls, scores):
            aux_dsl = response_prefix + aux_dsl
            aux_dsl_dict[aux_dsl] = score
            print(f"aux_dsl: {aux_dsl}")
            
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
        image_dir = "temp/vlm_images/"
        os.makedirs(image_dir, exist_ok=True)
        
        # Check goals numerically 
        for goal in proof.goals:
            if not goal.check_numerical():
                return infos(False, f"{goal.pretty()} fails numerical check")
        # Run ddar
        # print(f"running first ddar")
        base_proof = deepcopy(proof)
        base_proof = InternVLMAgent.run_ddar_c(base_proof, rules, t0, timeout)
        # print(f"finish first ddar")
        # if proofed by ddar, return
        if base_proof.check_goals():
            return infos(True)
        # else seek help from llm
        else:
            rules_ref = ray.put(rules)
            future_info = dict()
            running_futures = []
            
            beam_queues = []
            for i in range(len(self.model_path)):
                q = BeamQueue(max_size=self.beam_size)
                q.add(node=(self.problemJGEX, base_proof, proof), val=0)
                beam_queues.append(q)

            for depth in range(self.search_depth):
                new_beam_queues = []
                for i, beam_queue in enumerate(beam_queues):
                    new_queue = BeamQueue(max_size=self.beam_size)  # to replace beam_queue.
                    for prev_score, (problem, proof, proof_ori) in beam_queue:
                    # for prev_score, (problem, proof) in beam_queue:
                        if time.time() - t0 > timeout:
                            ray.shutdown()
                            return infos(False, 'Timeout')
                        proof_ref = ray.put(proof)

                        # draw current figure
                        # print("drawing picture")
                        timestamp = int(time.time()*1000)
                        unique_id = uuid.uuid4().hex
                        svg_path = os.path.join(image_dir, f"{timestamp}_{unique_id}.svg")
                        png_path = os.path.join(image_dir, f"{timestamp}_{unique_id}.png")
                        draw_figure(proof=proof_ori, save_to=svg_path, rng=proof.rng)
                        cairosvg.svg2png(
                            url=str(svg_path),
                            write_to=str(png_path),
                            output_width=1024,
                        )
                        # 对生成的 PNG 进行反色处理
                        # with Image.open(png_path) as img:
                        #     if img.mode == 'RGBA':
                        #         r, g, b, a = img.split()
                        #         rgb_img = Image.merge('RGB', (r, g, b))
                        #         inverted_rgb = ImageOps.invert(rgb_img)
                        #         r_inv, g_inv, b_inv = inverted_rgb.split()
                        #         img_out = Image.merge('RGBA', (r_inv, g_inv, b_inv, a))
                        #     elif img.mode == 'LA':
                        #         l, a = img.split()
                        #         l_inv = ImageOps.invert(l)
                        #         img_out = Image.merge('LA', (l_inv, a))
                        #     else:
                        #         img_out = ImageOps.invert(img.convert('RGB'))
                        #     img_out.save(png_path)

                        # 使用纯白图片
                        # with Image.open(png_path) as img:
                        #     img_out = Image.new('RGB', img.size, (255, 255, 255))
                        #     img_out.save(png_path)
                        # print("finish drawing")
                        
                        # Stragety 1: insert the aux string into problem and predict the next aux
                        p_dsl = self.problem_to_dsl(problem, base_proof.defs)
                        aux_dsl_dict = self.inference(
                            model=self.models[i],
                            tokenizer=self.tokenizers[i],
                            query=p_dsl,
                            img_path=png_path,
                            response_prefix='<aux> x00',
                        )
                        for aux_dsl, score in aux_dsl_dict.items():
                            try:
                                aux = self.try_dsl_to_constructions(aux_dsl[len('<aux> x00'):])
                                if aux:
                                    # create new problem as new task
                                    new_problem = problem.with_more_construction(aux)  # will recreate the problem
                                    # sumbit ray task
                                    future = run_ddar_remote.remote(new_problem, proof_ref, aux, rules_ref, t0, timeout)
                                    future_info[future] = (new_problem, prev_score, score)
                                    running_futures.append(future)       
                            except Exception as e:
                                continue
                        # Stragey 2: keep the aux string behind previous '<aux> x00' (AG).
                        # Not implement yet

                        # check any done task. if we find a solution early, we can save time
                        done, running_futures = ray.wait(running_futures, timeout=0)
                        for f in done:
                            res, proof_ori = ray.get(f)
                            if res is None:
                                continue
                            elif res.check_goals():
                                for task in running_futures:
                                    ray.cancel(task, force=True)
                                ray.shutdown()
                                print(f"success with problem: {str(new_problem)}")
                                return infos(True, str(new_problem))
                            elif depth < self.search_depth -1:
                                new_problem, prev_score, score = future_info[f]
                                new_queue.add(node=(new_problem, res, proof_ori), val=prev_score+score)
                    # check remaining tasks
                    while running_futures:
                        done, running_futures = ray.wait(running_futures, num_returns=min(1000, len(running_futures)))
                        for f in done:
                            res, proof_ori = ray.get(f)
                            if res is None:
                                continue
                            elif res.check_goals():
                                new_problem, prev_score, score = future_info[f]
                                for task in running_futures:
                                    ray.cancel(task, force=True)
                                ray.shutdown()
                                print(f"success with problem: {str(new_problem)}")
                                return infos(True, str(new_problem))
                            elif depth < self.search_depth -1:
                                new_problem, prev_score, score = future_info[f]
                                new_queue.add(node=(new_problem, res, proof_ori), val=prev_score+score)
                    new_beam_queues.append(new_queue)
                beam_queues = new_beam_queues

            ray.shutdown()
            return infos(False, 'Tried but failed.')

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
        premises = re.split(r"\s*\[\d+\]", premises) # coll a c e [002] coll b d e [003] 》'coll a c e' , 'coll b d e'
        premises = [seg.strip() for seg in premises if seg.strip()]  # 
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
        # 直线垂直
        if predicate == 'perp':
            return Perp.to_constructive(point, tuple(args))

        # 直线平行
        elif predicate == 'para':
            return Para.to_constructive(point, tuple(args))

        # 全等/等距
        elif predicate == 'cong':
            return Cong.to_constructive(point, tuple(args))

        # 中点
        elif predicate == 'midp':
            return MidPoint.to_constructive(point, tuple(args))

        # 共线
        elif predicate == 'coll':
            return Coll.to_constructive(point, tuple(args))

        # 等角
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
            
        # 四点共圆
        elif predicate == 'cyclic':
            return Cyclic.to_constructive(point, tuple(args))

        elif predicate == 'eqratio':
            return EqRatio.to_constructive(point, tuple(args))

        # 其它直接返回
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
                    for b in bs:
                        statement = Statement.from_tokens(translate_sentence(mapping, b), dep_graph)
                        p2deps[points].append(statement)

            points = construction.points
            points = [p.split('@')[0] for p in points]
            while points:
                p = points[0]
                gr = group[p]
                points = [x for x in points if x not in gr]

                deps = []
                for dep in p2deps[gr]:
                    deps.append(dep)
                data_tmp[' '.join(gr)] = deps

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
    
    @staticmethod
    def run_ddar(proof: "ProofState", rules: list[Rule], start_time: int, timeout: int = 3600): 
        rule_buffer: list[Rule] = []
        application_buffer: list[Dependency] = []
        any_new_statement_has_been_added = True
        proof.dep_graph.obtain_numerical_checked_premises()
        running = True
        while running and time.time() - start_time < timeout:
            if proof.check_goals():
                running = False
            if rule_buffer:
                theorem = rule_buffer.pop()
                logging.debug("ddarn matching" + str(theorem))
                deps = proof.match_theorem(theorem)
                logging.debug("ddarn matched " + str(len(deps)))
                application_buffer.extend(deps)
            elif application_buffer:
                dep = application_buffer.pop()
                logging.debug(f"ddarn : apply {dep}")
                if proof.apply_dep(dep):
                    any_new_statement_has_been_added = True
            else:
                if not any_new_statement_has_been_added:
                    running = False
                any_new_statement_has_been_added = False
                rule_buffer = list(rules)
                logging.debug("ddarn : reload")
            # TODO: add step later..
            # step += 1
        return proof
    
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
        points = InternVLMAgent._extract_points(proof)
        premises = InternVLMAgent._extract_premises(proof)
        goals = InternVLMAgent._extract_goals(proof)
        
        _, dep_graph = DDAR.run_ddar("", points, premises, goals, 500, True, True)

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

        return proof   

    @staticmethod
    def build_transform(input_size):
        MEAN, STD = IMAGENET_MEAN, IMAGENET_STD
        transform = T.Compose([
            T.Lambda(lambda img: img.convert('RGB') if img.mode != 'RGB' else img),
            T.Resize((input_size, input_size), interpolation=InterpolationMode.BICUBIC),
            T.ToTensor(),
            T.Normalize(mean=MEAN, std=STD)
        ])
        return transform

    @staticmethod
    def find_closest_aspect_ratio(aspect_ratio, target_ratios, width, height, image_size):
        best_ratio_diff = float('inf')
        best_ratio = (1, 1)
        area = width * height
        for ratio in target_ratios:
            target_aspect_ratio = ratio[0] / ratio[1]
            ratio_diff = abs(aspect_ratio - target_aspect_ratio)
            if ratio_diff < best_ratio_diff:
                best_ratio_diff = ratio_diff
                best_ratio = ratio
            elif ratio_diff == best_ratio_diff:
                if area > 0.5 * image_size * image_size * ratio[0] * ratio[1]:
                    best_ratio = ratio
        return best_ratio

    @staticmethod
    def dynamic_preprocess(image, min_num=1, max_num=12, image_size=448, use_thumbnail=False):
        orig_width, orig_height = image.size
        aspect_ratio = orig_width / orig_height

        # calculate the existing image aspect ratio
        target_ratios = set(
            (i, j) for n in range(min_num, max_num + 1) for i in range(1, n + 1) for j in range(1, n + 1) if
            i * j <= max_num and i * j >= min_num)
        target_ratios = sorted(target_ratios, key=lambda x: x[0] * x[1])

        # find the closest aspect ratio to the target
        target_aspect_ratio = InternVLMAgent.find_closest_aspect_ratio(
            aspect_ratio, target_ratios, orig_width, orig_height, image_size)

        # calculate the target width and height
        target_width = image_size * target_aspect_ratio[0]
        target_height = image_size * target_aspect_ratio[1]
        blocks = target_aspect_ratio[0] * target_aspect_ratio[1]

        # resize the image
        resized_img = image.resize((target_width, target_height))
        processed_images = []
        for i in range(blocks):
            box = (
                (i % (target_width // image_size)) * image_size,
                (i // (target_width // image_size)) * image_size,
                ((i % (target_width // image_size)) + 1) * image_size,
                ((i // (target_width // image_size)) + 1) * image_size
            )
            # split the image
            split_img = resized_img.crop(box)
            processed_images.append(split_img)
        assert len(processed_images) == blocks
        if use_thumbnail and len(processed_images) != 1:
            thumbnail_img = image.resize((image_size, image_size))
            processed_images.append(thumbnail_img)
        return processed_images
    
    @staticmethod
    def load_image(image_file, input_size=448, max_num=12):
        image = Image.open(image_file).convert('RGB')
        transform = InternVLMAgent.build_transform(input_size=input_size)
        images = InternVLMAgent.dynamic_preprocess(image, image_size=input_size, use_thumbnail=True, max_num=max_num)
        pixel_values = [transform(image) for image in images]
        pixel_values = torch.stack(pixel_values)
        return pixel_values


@ray.remote(num_cpus=1)
def run_ddar_remote(problem, proof, aux, rules: list[Rule], start_time: int, timeout: int = 3600): 
    try:
        InternVLMAgent.add_construction(proof, aux)
    except Exception as e:
        try:
            proof_ori = ProofState.build_problemJGEX(
                problemJGEX=problem,
                defsJGEX=proof.defs,
                rng=np.random.default_rng(998244353),
                max_attempts=100,
                problem_path=None,
            )
        except Exception:
            return None, None
    try:
        proof = deepcopy(proof_ori)
        proof = InternVLMAgent.run_ddar_c(proof, rules, start_time, timeout)
    except Exception:
        return None, None
    return proof, proof_ori


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