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
from transformers import AutoModelForCausalLM, AutoTokenizer, DynamicCache

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
# logger.setLevel(logging.INFO)

DEBUG_LM_INPUT = os.environ.get("NEWCLID_DEBUG_LM_INPUT", "").lower() in {
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

class LMAgent(DeductiveAgent):
    def __init__(
        self,
        model_path: list[str],
        decoding_size: int,
        beam_size: int,
        search_depth: int,
        *,
        problem_db_runtime: ProblemDBRuntime | None = None,
        agent_type: str = "lm",
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
        self.tokenizers = []
        # Load all models and tokenizers
        for path in self.model_path:
            model = AutoModelForCausalLM.from_pretrained(
                path,
                torch_dtype="auto",
                device_map="auto", #"sequential",
                attn_implementation="flash_attention_2"  # Sliding Window Attention is enabled but not implemented for others
            )
            tokenizer = AutoTokenizer.from_pretrained(path)
            self.models.append(model)
            self.tokenizers.append(tokenizer)

    def _log_input_snapshot(
        self,
        *,
        query: str,
        messages: list[dict[str, Any]],
        text_prompt: str,
        final_text: str,
        model_inputs,
        prompt_len: int,
    ) -> None:
        if not DEBUG_LM_INPUT:
            return

        logger.debug("LM input snapshot: query=%s", query)
        logger.debug("LM input snapshot: messages=%s", messages)
        logger.debug("LM input snapshot: text_prompt=%s", text_prompt)
        logger.debug("LM input snapshot: final_text=%s", final_text)
        logger.debug("LM input snapshot: model_input_keys=%s", list(model_inputs.keys()))
        if "input_ids" in model_inputs:
            logger.debug("LM input snapshot: input_ids.shape=%s", tuple(model_inputs["input_ids"].shape))
        if "attention_mask" in model_inputs:
            logger.debug("LM input snapshot: attention_mask.shape=%s", tuple(model_inputs["attention_mask"].shape))
        logger.debug("LM input snapshot: prompt_len=%s", prompt_len)

    def _log_model_output(
        self,
        *,
        queue_type: str,
        aux_dsl: str | None = None,
        score: float | None = None,
        aux: str | None = None,
    ) -> None:
        if score is not None:
            logger.debug("LM output [%s]: score=%s", queue_type, score)
        if aux_dsl is not None:
            logger.debug("LM output [%s]: aux_dsl=%s", queue_type, aux_dsl)
        if aux is not None:
            logger.debug("LM output [%s]: aux=%s", queue_type, aux)

    @staticmethod
    def _update_ddar_stats(ddar_stats: dict[str, int], ddar_result: dict[str, Any]) -> None:
        if ddar_result["status"] == "invalid":
            if ddar_result.get("error_type") == "engine_error":
                ddar_stats["remote_engine_invalid"] += 1
            else:
                ddar_stats["remote_build_invalid"] += 1
            return
        ddar_stats["remote_ddar_calls"] += 1
        ddar_stats[f"remote_{ddar_result['status']}"] += 1
        
    @torch.no_grad()
    def inference(self, model, tokenizer, query: str, new_point_name: str, response_prefix: str = '<aux>', with_predicate: bool = True):
        aux_dsl_dict = {}
        # Process each model/tokenizer pair
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": query}
        ]
        text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        text += "<think>\n\n</think>\n\n"
        model_prompt_inputs = tokenizer([text], return_tensors="pt")
        pad_token_id = tokenizer.pad_token_id
        eos_token_id = tokenizer.encode(' ;', add_special_tokens=False)[0]
        
        if with_predicate and len(AUX_PREDICATES) > 0:
            # Inference with predicate prefix
            beams_per_predicate = self.decoding_size // len(AUX_PREDICATES)
            if beams_per_predicate:
                for aux_predicate_str in AUX_PREDICATES:
                    prompt_with_predicate = text + response_prefix + ' ' + new_point_name + ' : ' + aux_predicate_str
                    model_inputs = tokenizer([prompt_with_predicate], return_tensors="pt")
                    self._log_input_snapshot(
                        query=query,
                        messages=messages,
                        text_prompt=text,
                        final_text=prompt_with_predicate,
                        model_inputs=model_inputs,
                        prompt_len=model_prompt_inputs.input_ids.shape[1],
                    )
                    model_inputs = model_inputs.to(model.device)
                    
                    generated_output = model.generate(
                        **model_inputs,
                        max_new_tokens=100,
                        num_beams=beams_per_predicate,
                        num_return_sequences=beams_per_predicate,
                        pad_token_id=pad_token_id,
                        eos_token_id=eos_token_id,
                        return_dict_in_generate=True, 
                        output_scores=True,
                    )
                    scores = generated_output.sequences_scores
                    generated_output = generated_output.sequences[:, model_prompt_inputs.input_ids.shape[1]:]
                    aux_dsls = tokenizer.batch_decode(generated_output, skip_special_tokens=True)
                    
                    for aux_dsl, score in zip(aux_dsls, scores):
                        score = score.item()
                        aux_dsl_dict[aux_dsl] = score
        
        if not with_predicate:
            # Inference without predicate prefix
            prompt_no_predicate = text + response_prefix + ' ' + new_point_name
            model_inputs = tokenizer([prompt_no_predicate], return_tensors="pt")
            self._log_input_snapshot(
                query=query,
                messages=messages,
                text_prompt=text,
                final_text=prompt_no_predicate,
                model_inputs=model_inputs,
                prompt_len=model_prompt_inputs.input_ids.shape[1],
            )
            model_inputs = model_inputs.to(model.device)

            generated_output = model.generate(
                **model_inputs,
                max_new_tokens=100,
                num_beams=self.decoding_size,
                num_return_sequences=self.decoding_size,
                pad_token_id=pad_token_id,
                eos_token_id=eos_token_id,
                return_dict_in_generate=True, 
                output_scores=True,
            )
            scores = generated_output.sequences_scores
            generated_output = generated_output.sequences[:, model_prompt_inputs.input_ids.shape[1]:]
            aux_dsls = tokenizer.batch_decode(generated_output, skip_special_tokens=True)

            for aux_dsl, score in zip(aux_dsls, scores):
                score = score.item()
                aux_dsl_dict[aux_dsl] = score
            
        return aux_dsl_dict

    def run(self, proof: "ProofState", rules: list[Rule], timeout: int = 3600
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

        def infos(is_success, error_msg = None):
            infos: dict[str, Any] = {}
            infos["runtime"] = time.time() - t0
            infos["success"] = is_success
            infos["steps"] = step
            infos["ddar_stats"] = ddar_stats
            if self.problem_db_runtime is not None:
                infos["problem_db_payload"] = self.problem_db_runtime.export_payload()
                infos["problem_db_stats"] = summarize_problem_db_runtime(self.problem_db_runtime)
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
                LMAgent._update_ddar_stats(ddar_stats, ddar_result)

                if ddar_result["status"] == "solved":
                    new_problem = future_meta["problem"]
                    for task in running_futures:
                        ray.cancel(task, force=True)
                    ray.shutdown()
                    logger.info("Success with problem: %s", new_problem)
                    return infos(True, str(new_problem))

                if ddar_result["status"] == "unsolved" and depth < self.search_depth - 1:
                    new_queues[future_meta["queue_idx"]].add(
                        node=future_meta["problem"],
                        val=future_meta["prev_score"] + future_meta["score"],
                    )
            return None
        
        t0 = time.time()
        step = 0
        
        # Check goals numerically 
        for goal in proof.goals:
            if not goal.check_numerical():
                return infos(False, f"{goal.pretty()} fails numerical check")
        # Run ddar
        ddar_stats["base_calls"] += 1
        solved = LMAgent.run_ddar_c(proof, rules, t0, timeout)
        # if proofed by ddar, return
        if solved:
            return infos(True)
        # else seek help from llm
        else:
            rules_ref = ray.put(rules)
            future_info = dict()
            running_futures = []
            
            # Create two BeamQueues for each model: one for with_predicate, one for no_predicate
            # beam_queues[i][j]: i is the model index, j=0 for with_predicate, j=1 for no_predicate
            beam_queues = []
            for i in range(len(self.models)):
                q_with_pred = BeamQueue(max_size=self.beam_size)
                q_with_pred.add(node=self.problemJGEX, val=0)
                
                q_no_pred = BeamQueue(max_size=self.beam_size)
                q_no_pred.add(node=self.problemJGEX, val=0)
                
                beam_queues.append([q_with_pred, q_no_pred])

            for depth in range(self.search_depth):
                new_beam_queues = []
                
                for i in range(len(self.models)):
                    new_queues = [BeamQueue(max_size=self.beam_size), BeamQueue(max_size=self.beam_size)]
                    
                    # j=0: with_predicate, j=1: no_predicate
                    for j, with_predicate in enumerate([True, False]):
                        queue_type = 'with_pred' if with_predicate else 'no_pred'

                        for prev_score, problem in beam_queues[i][j]:
                            if time.time() - t0 > timeout:
                                ray.shutdown()
                                return infos(False, 'Timeout')
                            
                            p_dsl = self.problem_to_dsl(problem, proof.defs)
                            logger.debug("Inferencing on query (%s): %s", queue_type, p_dsl)
                            aux_dsl_dict = self.inference(
                                self.models[i], self.tokenizers[i], p_dsl, 
                                self.get_new_point_name(problem), '<aux> x00',
                                with_predicate=with_predicate
                            )
                            
                            for aux_dsl, score in aux_dsl_dict.items():
                                try:
                                    self._log_model_output(queue_type=queue_type, aux_dsl=aux_dsl, score=score)
                                    raw_aux_text = aux_dsl[len('<aux> x00'):]
                                    aux = self.try_dsl_to_constructions(raw_aux_text)
                                    self._log_model_output(queue_type=queue_type, aux=aux)
                                    if aux:
                                        new_problem = problem.with_more_construction(aux)
                                        lookup = (
                                            self.problem_db_runtime.lookup_problem(new_problem)
                                            if self.problem_db_runtime is not None
                                            else ProblemDBLookup()
                                        )

                                        if lookup.hit_category == "solved":
                                            ray.shutdown()
                                            logger.info("Cache hit success with problem: %s", new_problem)
                                            return infos(True, str(new_problem))

                                        if lookup.hit_category == "unsolved":
                                            if depth < self.search_depth - 1:
                                                new_queues[j].add(node=new_problem, val=prev_score + score)
                                            continue

                                        if lookup.hit_category == "invalid":
                                            continue

                                        future = run_ddar_remote.remote(new_problem, proof.defs, rules_ref, t0, timeout)
                                        future_info[future] = {
                                            "problem": new_problem,
                                            "prev_score": prev_score,
                                            "score": score,
                                            "queue_idx": j,
                                            "lookup": lookup,
                                        }
                                        running_futures.append(future)
                                except Exception as e:
                                    continue
                            
                            # check any done task
                            done, running_futures = ray.wait(running_futures, timeout=0)
                            future_result = process_completed_futures(done, new_queues, depth)
                            if future_result is not None:
                                return future_result
                    
                    # check remaining tasks
                    while running_futures:
                        done, running_futures = ray.wait(running_futures, num_returns=min(1000, len(running_futures)))
                        future_result = process_completed_futures(done, new_queues, depth)
                        if future_result is not None:
                            return future_result
                    
                    new_beam_queues.append(new_queues)
                
                beam_queues = new_beam_queues

            ray.shutdown()
            return infos(False, 'Tried but failed.')

    def get_new_point_name(self, problem: ProblemJGEX) -> str:
        num_points = sum([len(clause.points) for clause in problem.constructions])
        return self._get_apha_geo_solver_var(num_points)
    
    def _get_apha_geo_solver_var(self, va_idx):
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
        points = LMAgent._extract_points(proof)
        premises = LMAgent._extract_premises(proof)
        goals = LMAgent._extract_goals(proof)
        
        solved, dep_graph = DDAR.run_ddar("", points, premises, goals, 500, True, True)

        return solved


@ray.remote(num_cpus=1)
def run_ddar_remote(problem, defs, rules: list[Rule], start_time: int, timeout: int = 3600): 
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
        }
    try:
        solved = LMAgent.run_ddar_c(proof, rules, start_time, timeout)
    except Exception as exc:
        return {
            "status": "invalid",
            "elapsed_time": time.time() - eval_start,
            "error_type": "engine_error",
            "error_message": str(exc),
        }
    return {
        "status": "solved" if solved else "unsolved",
        "elapsed_time": time.time() - eval_start,
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
        # return f'BeamQueue(max_size={self.max_size}, size={len(self.queue)}])'
        items = ',\n  '.join(f'({val:.4f}, {repr(node)})' for val, _, node in self.queue if node is not self.REMOVED)
        return f'BeamQueue(max_size={self.max_size}, size={len(self.queue)}, items=[\n  {items}\n])'
