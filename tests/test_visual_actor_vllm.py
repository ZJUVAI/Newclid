from __future__ import annotations

import tempfile
import types
import unittest
from pathlib import Path
import sys
from unittest import mock

from PIL import Image

fake_modelscope = types.ModuleType("modelscope")
fake_modelscope.AutoProcessor = object
fake_modelscope.Qwen3VLForConditionalGeneration = object
fake_modelscope.snapshot_download = lambda repo_id: repo_id
sys.modules.setdefault("modelscope", fake_modelscope)

fake_qwen_vl_utils = types.ModuleType("qwen_vl_utils")
fake_qwen_vl_utils.process_vision_info = lambda *args, **kwargs: ([], [])
sys.modules.setdefault("qwen_vl_utils", fake_qwen_vl_utils)

fake_transformers = types.ModuleType("transformers")
fake_transformers.AutoProcessor = object
fake_transformers.AutoModelForCausalLM = object
fake_transformers.AutoTokenizer = object
fake_transformers.Qwen3_5ForConditionalGeneration = object
fake_transformers_utils = types.ModuleType("transformers.utils")
fake_transformers_utils_logging = types.ModuleType("transformers.utils.logging")
fake_transformers_utils_logging.disable_progress_bar = lambda: None
fake_transformers_utils_logging.set_verbosity_error = lambda: None
fake_transformers_utils.logging = fake_transformers_utils_logging
fake_transformers.utils = fake_transformers_utils
sys.modules.setdefault("transformers", fake_transformers)
sys.modules.setdefault("transformers.utils", fake_transformers_utils)
sys.modules.setdefault("transformers.utils.logging", fake_transformers_utils_logging)

from experiments.single_problem_multi_gpu_eval.visual_actor import (
    VLLMVisionModelWorker,
    _extract_vllm_continuation_text,
    _effective_vllm_max_logprobs,
    _effective_vllm_max_num_seqs,
    _generate_visual_aux_dsl_dict_batch_vllm,
    _generate_visual_aux_dsl_dict_batch_vllm_sampling,
    _load_visual_processor,
)


class _FakeProcessor:
    class _FakeTokenizer:
        @staticmethod
        def decode(tokens, skip_special_tokens=True):
            del skip_special_tokens
            return "".join(chr(token) for token in tokens)

    def __init__(self):
        self.tokenizer = self._FakeTokenizer()

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True):
        del messages, tokenize, add_generation_prompt
        return "PROMPT"


class _FakeSequence:
    def __init__(
        self,
        text: str,
        cum_logprob: float,
        tokens: list[int] | None = None,
        *,
        orig_prompt: dict | None = None,
    ):
        self.text = text
        self.cum_logprob = cum_logprob
        self.tokens = tokens or []
        self.orig_prompt = orig_prompt or {}


class _FakeBeamOutput:
    def __init__(self, sequences):
        self.sequences = sequences


class _FakeLLM:
    def __init__(self, outputs):
        self.outputs = outputs
        self.calls = []

    def beam_search(self, prompts, params, use_tqdm=False):
        self.calls.append(
            {
                "prompts": prompts,
                "beam_width": params.beam_width,
                "max_tokens": params.max_tokens,
                "use_tqdm": use_tqdm,
            }
        )
        return self.outputs

    def generate(self, prompts, params, use_tqdm=False):
        self.calls.append(
            {
                "prompts": prompts,
                "n": params.n,
                "temperature": params.temperature,
                "top_p": params.top_p,
                "logprobs": params.logprobs,
                "use_tqdm": use_tqdm,
            }
        )
        return self.outputs


class _InitCaptureLLM:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _FakeBeamSearchParams:
    def __init__(self, beam_width: int, max_tokens: int, ignore_eos: bool = False, temperature: float = 0.0):
        self.beam_width = beam_width
        self.max_tokens = max_tokens
        self.ignore_eos = ignore_eos
        self.temperature = temperature


class _FakeSamplingParams:
    def __init__(
        self,
        n: int,
        max_tokens: int,
        temperature: float,
        top_p: float,
        logprobs: int,
        stop_token_ids=None,
        ignore_eos: bool = False,
        detokenize: bool = True,
    ):
        self.n = n
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.logprobs = logprobs
        self.stop_token_ids = stop_token_ids
        self.ignore_eos = ignore_eos
        self.detokenize = detokenize


class _FakeCompletionOutput:
    def __init__(self, text: str, cumulative_logprob: float, token_ids: list[int]):
        self.text = text
        self.cumulative_logprob = cumulative_logprob
        self.token_ids = token_ids


class _FakeRequestOutput:
    def __init__(self, outputs):
        self.outputs = outputs


class VisualActorVLLMTests(unittest.TestCase):
    def test_effective_vllm_max_num_seqs_clamps_to_batch_times_decoding(self):
        self.assertEqual(
            _effective_vllm_max_num_seqs(8, gpu_batch_size=4, decoding_size=32),
            128,
        )
        self.assertEqual(
            _effective_vllm_max_num_seqs(256, gpu_batch_size=4, decoding_size=32),
            256,
        )

    def test_effective_vllm_max_logprobs_matches_strict_beam_requirement(self):
        self.assertEqual(_effective_vllm_max_logprobs(decoding_size=1), 20)
        self.assertEqual(_effective_vllm_max_logprobs(decoding_size=8), 20)
        self.assertEqual(_effective_vllm_max_logprobs(decoding_size=32), 64)
        self.assertEqual(
            _effective_vllm_max_logprobs(decoding_size=32, generation_mode="sample"),
            20,
        )

    def test_vllm_worker_init_passes_effective_max_logprobs_to_llm(self):
        llm_holder = {}
        processor_calls = []

        def _llm_factory(**kwargs):
            llm = _InitCaptureLLM(**kwargs)
            llm_holder["llm"] = llm
            return llm

        processor = types.SimpleNamespace(tokenizer=types.SimpleNamespace(padding_side=None))
        def _processor_factory(path):
            processor_calls.append(path)
            return processor
        worker_cls = VLLMVisionModelWorker.__ray_metadata__.modified_class
        with (
            mock.patch(
                "experiments.single_problem_multi_gpu_eval.visual_actor.resolve_model_path",
                side_effect=lambda path: path,
            ),
            mock.patch(
                "experiments.single_problem_multi_gpu_eval.visual_actor._load_vllm_modules",
                return_value=(
                    _llm_factory,
                    _FakeBeamSearchParams,
                    _FakeSamplingParams,
                    lambda **kwargs: kwargs["cumulative_logprob"],
                ),
            ),
            mock.patch(
                "experiments.single_problem_multi_gpu_eval.visual_actor.ModelScopeAutoProcessor",
                new=types.SimpleNamespace(from_pretrained=lambda path, *args, **kwargs: _processor_factory(path)),
            ),
            mock.patch(
                "experiments.single_problem_multi_gpu_eval.visual_actor._QWEN3_VL_BASE_PROCESSOR_CACHE",
                new=Path("/tmp/does-not-exist-qwen-cache"),
            ),
            mock.patch(
                "experiments.single_problem_multi_gpu_eval.visual_actor.torch.cuda.is_available",
                return_value=False,
            ),
        ):
            worker = worker_cls(
                "model-path",
                "vlm",
                42,
                gpu_memory_utilization=0.9,
                max_num_seqs=128,
                gpu_batch_size=4,
                decoding_size=32,
                enforce_eager=False,
            )

        self.assertIs(worker.llm, llm_holder["llm"])
        self.assertEqual(worker.max_logprobs, 64)
        self.assertEqual(llm_holder["llm"].kwargs["max_logprobs"], 64)
        self.assertEqual(processor_calls, ["Qwen/Qwen3-VL-2B-Instruct"])

    def test_vllm_worker_init_in_sample_mode_uses_lower_logprob_cap(self):
        llm_holder = {}

        def _llm_factory(**kwargs):
            llm = _InitCaptureLLM(**kwargs)
            llm_holder["llm"] = llm
            return llm

        processor = types.SimpleNamespace(tokenizer=types.SimpleNamespace(padding_side=None))
        worker_cls = VLLMVisionModelWorker.__ray_metadata__.modified_class
        with (
            mock.patch(
                "experiments.single_problem_multi_gpu_eval.visual_actor.resolve_model_path",
                side_effect=lambda path: path,
            ),
            mock.patch(
                "experiments.single_problem_multi_gpu_eval.visual_actor._load_vllm_modules",
                return_value=(
                    _llm_factory,
                    _FakeBeamSearchParams,
                    _FakeSamplingParams,
                    lambda **kwargs: kwargs["cumulative_logprob"],
                ),
            ),
            mock.patch(
                "experiments.single_problem_multi_gpu_eval.visual_actor._load_visual_processor",
                return_value=processor,
            ),
            mock.patch(
                "experiments.single_problem_multi_gpu_eval.visual_actor.torch.cuda.is_available",
                return_value=False,
            ),
        ):
            worker = worker_cls(
                "model-path",
                "vlm",
                42,
                gpu_memory_utilization=0.9,
                max_num_seqs=128,
                gpu_batch_size=4,
                decoding_size=32,
                enforce_eager=False,
                generation_mode="sample",
                sampling_temperature=0.7,
                sampling_top_p=0.9,
            )

        self.assertEqual(worker.max_logprobs, 20)
        self.assertEqual(llm_holder["llm"].kwargs["max_logprobs"], 20)
        self.assertEqual(worker.generation_mode, "sample")

    def test_load_visual_processor_prefers_cached_base_model(self):
        processor = object()
        calls = []

        def _processor_factory(path):
            calls.append(path)
            return processor

        with (
            mock.patch(
                "experiments.single_problem_multi_gpu_eval.visual_actor.ModelScopeAutoProcessor",
                new=types.SimpleNamespace(from_pretrained=lambda path, *args, **kwargs: _processor_factory(path)),
            ),
            mock.patch(
                "experiments.single_problem_multi_gpu_eval.visual_actor._QWEN3_VL_BASE_PROCESSOR_CACHE",
                new=Path("/tmp"),
            ),
        ):
            loaded = _load_visual_processor()

        self.assertIs(loaded, processor)
        self.assertEqual(calls, ["/tmp"])

    def test_extract_vllm_continuation_text_strips_full_prompt_prefix(self):
        processor = _FakeProcessor()
        sequence = _FakeSequence(
            "PROMPT<aux> x00 a foo ;",
            -1.0,
            orig_prompt={"prompt": "PROMPT<aux> x00 a"},
        )

        self.assertEqual(_extract_vllm_continuation_text(processor, sequence), " foo ;")

    def test_extract_vllm_continuation_text_falls_back_to_token_suffix_decode(self):
        processor = _FakeProcessor()
        sequence = _FakeSequence(
            "mismatched text",
            -1.0,
            tokens=[1, 2, 32, 102, 111, 111],
            orig_prompt={"prompt_token_ids": [1, 2]},
        )

        self.assertEqual(_extract_vllm_continuation_text(processor, sequence), " foo")

    def test_vllm_batch_result_keeps_first_duplicate_candidate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / "input.png"
            Image.new("RGB", (8, 8), color="white").save(image_path)

            llm = _FakeLLM(
                [
                    _FakeBeamOutput(
                        [
                            _FakeSequence(
                                "PROMPT<aux> x00 a foo",
                                -1.0,
                                [80, 82, 79, 77, 80, 84, 32, 102, 111, 111],
                                orig_prompt={"prompt": "PROMPT<aux> x00 a"},
                            ),
                            _FakeSequence(
                                "PROMPT<aux> x00 a foo",
                                -9.0,
                                [80, 82, 79, 77, 80, 84, 32, 102, 111, 111],
                                orig_prompt={"prompt": "PROMPT<aux> x00 a"},
                            ),
                            _FakeSequence(
                                "PROMPT<aux> x00 a bar",
                                -2.0,
                                [80, 82, 79, 77, 80, 84, 32, 98, 97, 114],
                                orig_prompt={"prompt": "PROMPT<aux> x00 a"},
                            ),
                        ]
                    )
                ]
            )
            requests = [
                {
                    "request_id": "r0",
                    "img_path": str(image_path),
                    "query": "Construct one auxiliary point.",
                    "new_point_name": "a",
                    "response_prefix": "<aux> x00",
                    "with_predicate": False,
                    "decoding_size": 3,
                }
            ]

            results, profile = _generate_visual_aux_dsl_dict_batch_vllm(
                llm,
                _FakeProcessor(),
                requests,
                get_beam_search_score=lambda **kwargs: kwargs["cumulative_logprob"],
                beam_search_params_cls=_FakeBeamSearchParams,
            )

            self.assertEqual(results[0]["request_id"], "r0")
            self.assertEqual(
                list(results[0]["aux_dsl_dict"].items()),
                [
                    ("<aux> x00 a foo", -1.0),
                    ("<aux> x00 a bar", -2.0),
                ],
            )
            self.assertEqual(profile["batch_size"], 1)
            self.assertEqual(llm.calls[0]["beam_width"], 3)

    def test_vllm_sampling_result_dedupes_and_ranks_by_score(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / "input.png"
            Image.new("RGB", (8, 8), color="white").save(image_path)

            llm = _FakeLLM(
                [
                    _FakeRequestOutput(
                        [
                            _FakeCompletionOutput(" foo", -3.0, [11, 12]),
                            _FakeCompletionOutput(" bar", -1.0, [21]),
                            _FakeCompletionOutput(" foo", -1.5, [11, 12]),
                        ]
                    )
                ]
            )
            requests = [
                {
                    "request_id": "r0",
                    "img_path": str(image_path),
                    "query": "Construct one auxiliary point.",
                    "new_point_name": "a",
                    "response_prefix": "<aux> x00",
                    "with_predicate": False,
                    "decoding_size": 3,
                }
            ]

            results, profile = _generate_visual_aux_dsl_dict_batch_vllm_sampling(
                llm,
                _FakeProcessor(),
                requests,
                sampling_params_cls=_FakeSamplingParams,
                temperature=0.8,
                top_p=0.95,
            )

            self.assertEqual(
                list(results[0]["aux_dsl_dict"].items()),
                [
                    ("<aux> x00 a foo", -0.75),
                    ("<aux> x00 a bar", -1.0),
                ],
            )
            self.assertEqual(profile["batch_size"], 1)
            self.assertEqual(llm.calls[0]["n"], 3)
            self.assertEqual(llm.calls[0]["temperature"], 0.8)
            self.assertEqual(llm.calls[0]["top_p"], 0.95)


if __name__ == "__main__":
    unittest.main()
