from __future__ import annotations

import unittest
from unittest.mock import patch
from pathlib import Path

from experiments.single_problem_multi_gpu_eval.evaluation_single_problem_multi_gpu import (
    build_eval_output_stem,
    build_timestamped_output_stem,
)
from experiments.single_problem_multi_gpu_eval.lm_actor import resolve_model_path
from experiments.single_problem_multi_gpu_eval.model_pool import GenerationDispatcher, ModelPool
from experiments.single_problem_multi_gpu_eval import model_pool as model_pool_module
from newclid.search_trace import TraceRun


class _FakeGenerateBatch:
    def __init__(self, worker):
        self.worker = worker

    def remote(self, batch):
        self.worker.submitted.append(batch)
        request_ids = ",".join(request["request_id"] for request in batch)
        return f"{self.worker.name}:{request_ids}"


class _FakeWorker:
    def __init__(self, name: str):
        self.name = name
        self.submitted: list[list[dict[str, object]]] = []
        self.generate_batch = _FakeGenerateBatch(self)


class GenerationDispatcherTests(unittest.TestCase):
    def test_generation_dispatcher_refills_idle_workers(self):
        workers = [_FakeWorker("w0"), _FakeWorker("w1")]
        results = {
            "w0:r0": {
                "results": [{"request_id": "r0", "aux_dsl_dict": {}, "inference_time_s": 0.1}],
                "worker_batch_profile": {"worker_inference_time_s": 0.1, "batch_size": 1},
            },
            "w1:r1": {
                "results": [{"request_id": "r1", "aux_dsl_dict": {}, "inference_time_s": 0.2}],
                "worker_batch_profile": {"worker_inference_time_s": 0.2, "batch_size": 1},
            },
            "w0:r2": {
                "results": [{"request_id": "r2", "aux_dsl_dict": {}, "inference_time_s": 0.3}],
                "worker_batch_profile": {"worker_inference_time_s": 0.3, "batch_size": 1},
            },
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

                self.assertEqual(
                    [[request["request_id"] for request in batch] for batch in workers[0].submitted],
                    [["r0"]],
                )
                self.assertEqual(
                    [[request["request_id"] for request in batch] for batch in workers[1].submitted],
                    [["r1"]],
                )
                self.assertEqual(dispatcher.idle_worker_count(), 0)

                first_ref = next(ref for ref in dispatcher.active_refs() if ref.startswith("w0:"))
                first_result = dispatcher.take_done(first_ref)

                self.assertEqual(first_result["results"][0]["request_id"], "r0")
                self.assertEqual(first_result["batch_size"], 1)
                self.assertIn("dispatcher_profile", first_result)
                self.assertIn("worker_batch_profile", first_result)
                self.assertEqual(
                    [[request["request_id"] for request in batch] for batch in workers[0].submitted],
                    [["r0"], ["r2"]],
                )
                self.assertTrue(dispatcher.has_pending())

    def test_generation_dispatcher_emits_submission_events_for_batched_dispatch(self):
        workers = [_FakeWorker("w0")]
        dispatcher = GenerationDispatcher(
            workers,
            [
                {"request_id": "r0"},
                {"request_id": "r1"},
            ],
            gpu_batch_size=2,
            gpu_batch_timeout_ms=0,
        )

        events = dispatcher.take_submission_events()

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["request_ids"], ["r0", "r1"])
        self.assertEqual(events[0]["batch_size"], 2)
        self.assertEqual(dispatcher.take_submission_events(), [])

    def test_model_pool_create_dispatcher_accepts_empty_initial_queue(self):
        workers = [_FakeWorker("solo")]
        pool = ModelPool(workers)

        dispatcher = pool.create_dispatcher()
        self.assertFalse(dispatcher.has_pending())

        dispatcher.enqueue_request({"request_id": "r0"})
        self.assertTrue(dispatcher.has_pending())
        self.assertEqual(
            [[request["request_id"] for request in batch] for batch in workers[0].submitted],
            [["r0"]],
        )


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
        timestamp = "20260409T120000Z"

        with patch("newclid.search_trace.get_git_commit", return_value="deadbeef"):
            trace_run = TraceRun(
                Path("/tmp/traces"),
                route="evaluation_single_problem_multi_gpu",
                agent="lm",
                dataset_path=Path("benchmarks/imo_2004_p1.txt"),
                model_path="models/sft34/checkpoint-25750",
                params={"output_name_stem": stem},
                run_name=stem,
                run_timestamp=timestamp,
                repo_root=Path.cwd(),
            )

        self.assertEqual(trace_run.run_id, f"{stem}_{timestamp}")
        self.assertEqual(trace_run.run_dir.name, f"{stem}_{timestamp}")

    def test_build_timestamped_output_stem_reuses_trace_timestamp_suffix(self):
        stem = "eval_single_problem_multi_gpu_vlm_imo_2008_p1b_model_d32_b512_s4_gbs4_gbt100"
        timestamp = "20260410T120000Z"

        self.assertEqual(
            build_timestamped_output_stem(stem, timestamp),
            f"{stem}_{timestamp}",
        )

    def test_csv_and_profiling_names_align_with_trace_timestamp(self):
        stem = "eval_single_problem_multi_gpu_vlm_imo_2008_p1b_model_d32_b512_s4_gbs4_gbt100"
        timestamp = "20260410T120000Z"
        timestamped_stem = build_timestamped_output_stem(stem, timestamp)

        self.assertEqual(f"{timestamped_stem}.csv", f"{stem}_{timestamp}.csv")
        self.assertEqual(
            f"{timestamped_stem}_profiling.csv",
            f"{stem}_{timestamp}_profiling.csv",
        )


class ModelPathResolutionTests(unittest.TestCase):
    def test_resolve_model_path_raises_for_missing_local_like_path(self):
        with self.assertRaises(FileNotFoundError):
            resolve_model_path("/tmp/definitely_missing_checkpoint")

    def test_resolve_model_path_allows_remote_repo_id(self):
        with patch("modelscope.snapshot_download", return_value="/tmp/remote-model"):
            self.assertEqual(resolve_model_path("Qwen/Qwen3-VL-2B-Instruct"), "/tmp/remote-model")
