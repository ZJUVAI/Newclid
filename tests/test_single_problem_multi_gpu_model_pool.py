from __future__ import annotations

import unittest
from unittest.mock import patch
from pathlib import Path

from experiments.single_problem_multi_gpu_eval.evaluation_single_problem_multi_gpu import build_eval_output_stem
from experiments.single_problem_multi_gpu_eval.model_pool import GenerationDispatcher, ModelPool
from experiments.single_problem_multi_gpu_eval import model_pool as model_pool_module
from newclid.search_trace import TraceRun


class _FakeGenerateOne:
    def __init__(self, worker):
        self.worker = worker

    def remote(self, request):
        self.worker.submitted.append(request)
        return f"{self.worker.name}:{request['request_id']}"


class _FakeWorker:
    def __init__(self, name: str):
        self.name = name
        self.submitted: list[dict[str, object]] = []
        self.generate_one = _FakeGenerateOne(self)


class GenerationDispatcherTests(unittest.TestCase):
    def test_generation_dispatcher_refills_idle_workers(self):
        workers = [_FakeWorker("w0"), _FakeWorker("w1")]
        results = {
            "w0:r0": {"request_id": "r0", "aux_dsl_dict": {}, "inference_time_s": 0.1},
            "w1:r1": {"request_id": "r1", "aux_dsl_dict": {}, "inference_time_s": 0.2},
            "w0:r2": {"request_id": "r2", "aux_dsl_dict": {}, "inference_time_s": 0.3},
        }

        with patch.object(model_pool_module.ray, "get", side_effect=lambda ref: results[ref]):
            with patch.object(model_pool_module.ray, "cancel", side_effect=lambda ref, force=False: None):
                dispatcher = GenerationDispatcher(
                    workers,
                    [
                        {"request_id": "r0"},
                        {"request_id": "r1"},
                        {"request_id": "r2"},
                    ],
                )

                self.assertEqual([request["request_id"] for request in workers[0].submitted], ["r0"])
                self.assertEqual([request["request_id"] for request in workers[1].submitted], ["r1"])
                self.assertEqual(dispatcher.idle_worker_count(), 0)

                first_ref = next(ref for ref in dispatcher.active_refs() if ref.startswith("w0:"))
                first_result = dispatcher.take_done(first_ref)

                self.assertEqual(first_result["request_id"], "r0")
                self.assertEqual([request["request_id"] for request in workers[0].submitted], ["r0", "r2"])
                self.assertTrue(dispatcher.has_pending())

    def test_model_pool_create_dispatcher_accepts_empty_initial_queue(self):
        workers = [_FakeWorker("solo")]
        pool = ModelPool(workers)

        dispatcher = pool.create_dispatcher()
        self.assertFalse(dispatcher.has_pending())

        dispatcher.enqueue_request({"request_id": "r0"})
        self.assertTrue(dispatcher.has_pending())
        self.assertEqual([request["request_id"] for request in workers[0].submitted], ["r0"])


class EvalOutputNamingTests(unittest.TestCase):
    def test_build_eval_output_stem_includes_gpu_batch_params(self):
        stem = build_eval_output_stem(
            agent_type="vlm",
            problems_path=Path("benchmarks/imo_2000_p6.txt"),
            model_path="models/vlm_sft50/checkpoint-19194",
            decoding_size=2,
            beam_size=4,
            search_depth=1,
            gpu_batch_size=3,
            gpu_batch_timeout_ms=250,
        )

        self.assertEqual(
            stem,
            "eval_single_problem_multi_gpu_vlm_imo_2000_p6_vlm_sft50_checkpoint-19194"
            "_d2_b4_s1_gbs3_gbt250",
        )

    def test_trace_run_id_uses_eval_stem_and_timestamp_suffix(self):
        stem = build_eval_output_stem(
            agent_type="lm",
            problems_path=Path("benchmarks/imo_2004_p1.txt"),
            model_path="models/sft34/checkpoint-25750",
            decoding_size=8,
            beam_size=64,
            search_depth=4,
            gpu_batch_size=1,
            gpu_batch_timeout_ms=0,
        )

        with patch("newclid.search_trace.timestamp_slug", return_value="20260409T120000Z"):
            with patch("newclid.search_trace.get_git_commit", return_value="deadbeef"):
                trace_run = TraceRun(
                    Path("/tmp/traces"),
                    route="evaluation_single_problem_multi_gpu",
                    agent="lm",
                    dataset_path=Path("benchmarks/imo_2004_p1.txt"),
                    model_path="models/sft34/checkpoint-25750",
                    params={"output_name_stem": stem},
                    run_name=stem,
                    repo_root=Path.cwd(),
                )

        self.assertEqual(trace_run.run_id, f"{stem}_20260409T120000Z")
        self.assertEqual(trace_run.run_dir.name, f"{stem}_20260409T120000Z")
