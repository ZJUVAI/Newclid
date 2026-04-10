from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments.single_problem_multi_gpu_eval.evaluation_single_problem_multi_gpu import (
    build_eval_output_stem,
    build_timestamped_output_stem,
    solve_problems_single_problem_multi_gpu,
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


class _FakeLive:
    def __init__(self, *args, **kwargs):
        self.last_render = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def update(self, renderable):
        self.last_render = renderable


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
            "_d2_b4_s1_gbs3_gbt250_seed123",
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


class SingleProblemEvalRunnerTests(unittest.TestCase):
    def test_single_problem_eval_runner_writes_results_without_torch_seed_thread_arg(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            benchmark_path = tmp_path / "benchmarks.txt"
            benchmark_path.write_text("imo_2008_p1b\nproblem body placeholder\n", encoding="utf-8")
            log_dir = tmp_path / "results"
            fake_workers = [_FakeWorker("w0")]

            def fake_solve_one_problem(**kwargs):
                self.assertNotIn("torch_seed", kwargs)
                return (
                    kwargs["problem_name"],
                    True,
                    1.25,
                    {
                        "profiling": {
                            "entry_setup_wall_time_s": 0.25,
                            "avg_gpu_batch_size": 1.0,
                        }
                    },
                )

            with patch("experiments.single_problem_multi_gpu_eval.evaluation_single_problem_multi_gpu.ray.is_initialized", side_effect=[False, True]):
                with patch("experiments.single_problem_multi_gpu_eval.evaluation_single_problem_multi_gpu.ray.init"):
                    with patch(
                        "experiments.single_problem_multi_gpu_eval.evaluation_single_problem_multi_gpu.ray.available_resources",
                        return_value={"GPU": 1},
                    ):
                        with patch(
                            "experiments.single_problem_multi_gpu_eval.evaluation_single_problem_multi_gpu.create_workers",
                            return_value=fake_workers,
                        ):
                            with patch(
                                "experiments.single_problem_multi_gpu_eval.evaluation_single_problem_multi_gpu.ModelPool"
                            ) as mock_model_pool:
                                mock_model_pool.return_value.warmup.return_value = [{"device": "cuda:0"}]
                                with patch(
                                    "experiments.single_problem_multi_gpu_eval.evaluation_single_problem_multi_gpu.solve_one_problem",
                                    side_effect=fake_solve_one_problem,
                                ):
                                    with patch(
                                        "experiments.single_problem_multi_gpu_eval.evaluation_single_problem_multi_gpu.timestamp_slug",
                                        return_value="20260410T120000Z",
                                    ):
                                        with patch(
                                            "experiments.single_problem_multi_gpu_eval.evaluation_single_problem_multi_gpu.Live",
                                            _FakeLive,
                                        ):
                                            with patch(
                                                "experiments.single_problem_multi_gpu_eval.evaluation_single_problem_multi_gpu.write_profiling_csv"
                                            ) as mock_write_profiling_csv:
                                                with patch(
                                                    "experiments.single_problem_multi_gpu_eval.evaluation_single_problem_multi_gpu.ray.shutdown"
                                                ) as mock_ray_shutdown:
                                                    solve_problems_single_problem_multi_gpu(
                                                        filepath=benchmark_path,
                                                        model_path="/tmp/model",
                                                        num_cpus=2,
                                                        num_gpus_for_eval=1,
                                                        decoding_size=32,
                                                        beam_size=512,
                                                        search_depth=4,
                                                        gpu_batch_size=1,
                                                        gpu_batch_timeout_ms=100,
                                                        torch_seed=42,
                                                        timeout=3600,
                                                        agent_type="vlm",
                                                        max_pending_ddar=2,
                                                        prepare_request_workers=2,
                                                        prepare_prefetch_limit=2,
                                                        log_dir=str(log_dir),
                                                        enable_profiling=True,
                                                    )
                                                mock_ray_shutdown.assert_called_once()
                                                mock_write_profiling_csv.assert_called_once()

            csv_path = (
                log_dir
                / "eval_single_problem_multi_gpu_vlm_benchmarks_tmp_model"
                "_d32_b512_s4_gbs1_gbt100_seed42_20260410T120000Z.csv"
            )
            self.assertTrue(csv_path.exists())
            with csv_path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[1], ["Problem Name", "Solved", "Time (s)"])
            self.assertEqual(rows[2], ["imo_2008_p1b", "√", "1.25"])


class ModelPathResolutionTests(unittest.TestCase):
    def test_resolve_model_path_raises_for_missing_local_like_path(self):
        with self.assertRaises(FileNotFoundError):
            resolve_model_path("/tmp/definitely_missing_checkpoint")

    def test_resolve_model_path_allows_remote_repo_id(self):
        with patch("modelscope.snapshot_download", return_value="/tmp/remote-model"):
            self.assertEqual(resolve_model_path("Qwen/Qwen3-VL-2B-Instruct"), "/tmp/remote-model")
