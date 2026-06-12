from __future__ import annotations

import csv
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

import scripts.evaluation as eval_runner_module
from scripts.evaluation import (
    build_eval_output_stem,
    build_timestamped_output_stem,
)
from newclid.agent.runtime.model_pool import GenerationDispatcher, ModelPool
from newclid.agent.runtime import model_pool as model_pool_module
from newclid.agent.runtime.model_resolution import resolve_model_path
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
                "results": [
                    {"request_id": "r0", "aux_dsl_dict": {}, "inference_time_s": 0.1}
                ],
                "worker_batch_profile": {
                    "worker_inference_time_s": 0.1,
                    "batch_size": 1,
                },
            },
            "w1:r1": {
                "results": [
                    {"request_id": "r1", "aux_dsl_dict": {}, "inference_time_s": 0.2}
                ],
                "worker_batch_profile": {
                    "worker_inference_time_s": 0.2,
                    "batch_size": 1,
                },
            },
            "w0:r2": {
                "results": [
                    {"request_id": "r2", "aux_dsl_dict": {}, "inference_time_s": 0.3}
                ],
                "worker_batch_profile": {
                    "worker_inference_time_s": 0.3,
                    "batch_size": 1,
                },
            },
        }

        with patch.object(
            model_pool_module.ray, "get", side_effect=lambda ref: results[ref]
        ):
            with patch.object(
                model_pool_module.ray,
                "cancel",
                side_effect=lambda ref, force=False: None,
            ):
                dispatcher = GenerationDispatcher(
                    workers,
                    [
                        {"request_id": "r0"},
                        {"request_id": "r1"},
                        {"request_id": "r2"},
                    ],
                )

                self.assertEqual(
                    [
                        [request["request_id"] for request in batch]
                        for batch in workers[0].submitted
                    ],
                    [["r0"]],
                )
                self.assertEqual(
                    [
                        [request["request_id"] for request in batch]
                        for batch in workers[1].submitted
                    ],
                    [["r1"]],
                )
                self.assertEqual(dispatcher.idle_worker_count(), 0)

                first_ref = next(
                    ref for ref in dispatcher.active_refs() if ref.startswith("w0:")
                )
                first_result = dispatcher.take_done(first_ref)

                self.assertEqual(first_result["results"][0]["request_id"], "r0")
                self.assertEqual(first_result["batch_size"], 1)
                self.assertIn("dispatcher_profile", first_result)
                self.assertIn("worker_batch_profile", first_result)
                self.assertEqual(
                    [
                        [request["request_id"] for request in batch]
                        for batch in workers[0].submitted
                    ],
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
        self.assertEqual(events[0]["gpu_worker_id"], "w0")
        self.assertEqual(dispatcher.take_submission_events(), [])

    def test_generation_dispatcher_groups_only_compatible_requests(self):
        workers = [_FakeWorker("w0")]
        dispatcher = GenerationDispatcher(
            workers,
            [
                {
                    "request_id": "r0",
                    "decoding_size": 2,
                    "response_prefix": "<aux> x00",
                },
                {
                    "request_id": "r1",
                    "decoding_size": 4,
                    "response_prefix": "<aux> x00",
                },
                {
                    "request_id": "r2",
                    "decoding_size": 2,
                    "response_prefix": "<aux> x00",
                },
            ],
            gpu_batch_size=2,
            gpu_batch_timeout_ms=0,
        )

        self.assertEqual(
            [
                [request["request_id"] for request in batch]
                for batch in workers[0].submitted
            ],
            [["r0", "r2"]],
        )
        self.assertEqual(dispatcher.pending_request_count(), 1)

    def test_generation_dispatcher_prefers_largest_ready_group(self):
        workers = [_FakeWorker("w0")]
        dispatcher = GenerationDispatcher(
            workers,
            [
                {
                    "request_id": "r0",
                    "decoding_size": 2,
                    "response_prefix": "<aux> x00",
                },
                {
                    "request_id": "r1",
                    "decoding_size": 2,
                    "response_prefix": "<aux> x00",
                },
                {
                    "request_id": "r2",
                    "decoding_size": 3,
                    "response_prefix": "<aux> x00",
                },
            ],
            gpu_batch_size=2,
            gpu_batch_timeout_ms=0,
        )

        self.assertEqual(
            [
                [request["request_id"] for request in batch]
                for batch in workers[0].submitted
            ],
            [["r0", "r1"]],
        )
        self.assertEqual(dispatcher.pending_request_count(), 1)

    def test_model_pool_create_dispatcher_accepts_empty_initial_queue(self):
        workers = [_FakeWorker("solo")]
        pool = ModelPool(workers)

        dispatcher = pool.create_dispatcher()
        self.assertFalse(dispatcher.has_pending())

        dispatcher.enqueue_request({"request_id": "r0"})
        self.assertTrue(dispatcher.has_pending())
        self.assertEqual(
            [
                [request["request_id"] for request in batch]
                for batch in workers[0].submitted
            ],
            [["r0"]],
        )


class EvalOutputNamingTests(unittest.TestCase):
    def test_build_eval_output_stem_uses_vllm_fields_only(self):
        stem = build_eval_output_stem(
            agent_type="qwen3_vl",
            search_version="hybrid",
            problems_path=Path("benchmarks/imo_2000_p6.txt"),
            served_model_name="/tmp/models/checkpoint-7049",
            decoding_size=2,
            beam_size=4,
            search_depth=1,
        )

        self.assertEqual(
            stem,
            "eval_vllm_qwen3_vl_imo_2000_p6_checkpoint-7049_svhybrid_d2_b4_s1",
        )

    def test_trace_run_id_uses_eval_stem_and_timestamp_suffix(self):
        stem = build_eval_output_stem(
            agent_type="qwen3_text",
            search_version="v1",
            problems_path=Path("benchmarks/imo_2004_p1.txt"),
            served_model_name="served/checkpoint-25750",
            decoding_size=8,
            beam_size=64,
            search_depth=4,
        )
        timestamp = "20260409T120000Z"

        with patch("newclid.search_trace.get_git_commit", return_value="deadbeef"):
            trace_run = TraceRun(
                Path("/tmp/traces"),
                route="evaluation_vllm",
                agent="qwen3_text",
                dataset_path=Path("benchmarks/imo_2004_p1.txt"),
                model_path="served/checkpoint-25750",
                params={"output_name_stem": stem},
                run_name=stem,
                run_timestamp=timestamp,
                repo_root=Path.cwd(),
            )

        self.assertEqual(trace_run.run_id, f"{stem}_{timestamp}")
        self.assertEqual(trace_run.run_dir.name, f"{stem}_{timestamp}")

    def test_build_timestamped_output_stem_reuses_trace_timestamp_suffix(self):
        stem = "eval_vllm_qwen3_vl_imo_2008_p1b_model_sv2_d32_b512_s4"
        timestamp = "20260410T120000Z"

        self.assertEqual(
            build_timestamped_output_stem(stem, timestamp),
            f"{stem}_{timestamp}",
        )

    def test_csv_name_has_no_seed_suffix(self):
        stem = "eval_vllm_qwen3_vl_imo_2008_p1b_model_sv2_d32_b512_s4"
        timestamp = "20260410T120000Z"
        timestamped_stem = build_timestamped_output_stem(stem, timestamp)

        self.assertEqual(f"{timestamped_stem}.csv", f"{stem}_{timestamp}.csv")
        self.assertNotIn("seed", timestamped_stem)


class SingleProblemEvalRunnerTests(unittest.TestCase):
    def test_create_agent_passes_search_version_to_text_agent(self):
        with patch("scripts.evaluation.Qwen3Agent") as mock_text_agent:
            eval_runner_module.create_agent(
                agent_type="qwen3_text",
                search_version="hybrid",
                model_pool="pool",
                decoding_size=8,
                beam_size=16,
                search_depth=2,
                max_pending_ddar=4,
                render_root=Path("/tmp/render-root"),
            )

        self.assertEqual(mock_text_agent.call_args.kwargs["search_version"], "hybrid")

    def test_create_agent_passes_search_version_to_visual_agent(self):
        with patch("scripts.evaluation.Qwen3VLAgent") as mock_vl_agent:
            eval_runner_module.create_agent(
                agent_type="qwen3_vl",
                search_version="v2",
                model_pool="pool",
                decoding_size=8,
                beam_size=16,
                search_depth=2,
                max_pending_ddar=4,
                render_root=Path("/tmp/render-root"),
            )

        self.assertEqual(mock_vl_agent.call_args.kwargs["search_version"], "v2")

    def test_main_parses_vllm_cli(self):
        captured = {}

        def _fake_solve(**kwargs):
            captured.update(kwargs)

        argv = [
            "evaluation.py",
            "--vllm_base_url",
            "http://127.0.0.1:8000",
            "--agent",
            "qwen3_text",
            "--problems_path",
            "benchmarks/dev_imo.txt",
        ]

        with patch.object(sys, "argv", argv):
            with patch(
                "scripts.evaluation.solve_problems_vllm",
                side_effect=_fake_solve,
            ):
                eval_runner_module.main()

        self.assertEqual(captured["vllm_base_url"], "http://127.0.0.1:8000")
        self.assertEqual(captured["agent_type"], "qwen3_text")

    def test_main_allows_qwen3_vl(self):
        captured = {}

        def _fake_solve(**kwargs):
            captured.update(kwargs)

        argv = [
            "evaluation.py",
            "--vllm_base_url",
            "http://127.0.0.1:8000",
            "--agent",
            "qwen3_vl",
            "--problems_path",
            "benchmarks/dev_imo.txt",
        ]

        with patch.object(sys, "argv", argv):
            with patch(
                "scripts.evaluation.solve_problems_vllm",
                side_effect=_fake_solve,
            ):
                eval_runner_module.main()

        self.assertEqual(captured["agent_type"], "qwen3_vl")

    def test_single_problem_eval_runner_writes_results_for_vllm(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            benchmark_path = tmp_path / "benchmarks.txt"
            benchmark_path.write_text(
                "imo_2008_p1b\nproblem body placeholder\n", encoding="utf-8"
            )
            log_dir = tmp_path / "results"
            fake_workers = [_FakeWorker("w0")]

            def fake_solve_one_problem(**kwargs):
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

            with patch(
                "scripts.evaluation.ray.is_initialized", side_effect=[False, True]
            ):
                with patch("scripts.evaluation.ray.init"):
                    with patch(
                        "scripts.evaluation.discover_served_model",
                        return_value=(
                            "served/checkpoint-7049",
                            ["served/checkpoint-7049"],
                        ),
                    ):
                        with patch(
                            "scripts.evaluation.create_vllm_workers",
                            return_value=fake_workers,
                        ):
                            with patch(
                                "scripts.evaluation.ModelPool"
                            ) as mock_model_pool:
                                mock_model_pool.return_value.warmup.return_value = [
                                    {"device": "http"}
                                ]
                                with patch(
                                    "scripts.evaluation.solve_one_problem",
                                    side_effect=fake_solve_one_problem,
                                ):
                                    with patch(
                                        "scripts.evaluation.timestamp_slug",
                                        return_value="20260410T120000Z",
                                    ):
                                        with patch(
                                            "scripts.evaluation.Live",
                                            _FakeLive,
                                        ):
                                            with patch(
                                                "scripts.evaluation.ray.cluster_resources",
                                                return_value={"CPU": 4},
                                            ):
                                                with patch(
                                                    "scripts.evaluation.ray.shutdown"
                                                ) as mock_ray_shutdown:
                                                    eval_runner_module.solve_problems_vllm(
                                                        filepath=benchmark_path,
                                                        vllm_base_url="http://127.0.0.1:8000",
                                                        agent_type="qwen3_text",
                                                        decoding_size=32,
                                                        beam_size=512,
                                                        search_depth=4,
                                                        search_version="hybrid",
                                                        ray_num_cpus=4,
                                                        timeout=3600,
                                                        log_dir=str(log_dir),
                                                        enable_trace=False,
                                                    )
                                                mock_ray_shutdown.assert_called_once()

            csv_path = (
                log_dir
                / "eval_vllm_qwen3_text_benchmarks_checkpoint-7049_svhybrid_d32_b512_s4_20260410T120000Z.csv"
            )
            self.assertTrue(csv_path.exists())
            with csv_path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[1], ["Problem Name", "Solved", "Time (s)"])
            self.assertEqual(rows[2], ["imo_2008_p1b", "√", "1.25"])

    def test_single_problem_eval_runner_writes_trace_under_log_dir_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            benchmark_path = tmp_path / "benchmarks.txt"
            benchmark_path.write_text(
                "imo_2008_p1b\nproblem body placeholder\n", encoding="utf-8"
            )
            log_dir = tmp_path / "results"
            fake_workers = [_FakeWorker("w0")]

            def fake_solve_one_problem(**kwargs):
                trace_writer = kwargs["trace_writer"]
                self.assertIsNotNone(trace_writer)
                trace_writer.log(
                    "chat_submit",
                    depth=0,
                    request_ids=["d0_proot"],
                    batch_size=1,
                )
                trace_writer.log(
                    "chat_complete",
                    depth=0,
                    request_ids=["d0_proot"],
                    batch_size=1,
                )
                trace_writer.log(
                    "candidate_parse",
                    depth=0,
                    request_id="d0_proot",
                    candidate_rank=0,
                    success=True,
                )
                trace_writer.log(
                    "candidate_build",
                    depth=0,
                    request_id="d0_proot",
                    candidate_rank=0,
                    success=True,
                )
                trace_writer.log(
                    "ddar_result",
                    depth=0,
                    attempt_key="d0_proot:0",
                    ddar_worker_id="127.0.0.1:9999",
                    ddar_started_at_unix_s=12.0,
                    ddar_finished_at_unix_s=12.4,
                    ddar_build_started_at_unix_s=12.0,
                    ddar_build_finished_at_unix_s=12.1,
                    ddar_engine_started_at_unix_s=12.1,
                    ddar_engine_finished_at_unix_s=12.3,
                    status="unsolved",
                    elapsed_time=0.4,
                )
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

            with patch(
                "scripts.evaluation.ray.is_initialized", side_effect=[False, True]
            ):
                with patch("scripts.evaluation.ray.init"):
                    with patch(
                        "scripts.evaluation.discover_served_model",
                        return_value=(
                            "served/checkpoint-7049",
                            ["served/checkpoint-7049"],
                        ),
                    ):
                        with patch(
                            "scripts.evaluation.create_vllm_workers",
                            return_value=fake_workers,
                        ):
                            with patch(
                                "scripts.evaluation.ModelPool"
                            ) as mock_model_pool:
                                mock_model_pool.return_value.warmup.return_value = [
                                    {"device": "http"}
                                ]
                                with patch(
                                    "scripts.evaluation.solve_one_problem",
                                    side_effect=fake_solve_one_problem,
                                ):
                                    with patch(
                                        "scripts.evaluation.timestamp_slug",
                                        return_value="20260410T120000Z",
                                    ):
                                        with patch(
                                            "newclid.search_trace.get_git_commit",
                                            return_value="deadbeef",
                                        ):
                                            with patch(
                                                "scripts.evaluation.Live",
                                                _FakeLive,
                                            ):
                                                with patch(
                                                    "scripts.evaluation.ray.cluster_resources",
                                                    return_value={"CPU": 4},
                                                ):
                                                    with patch(
                                                        "scripts.evaluation.ray.shutdown"
                                                    ):
                                                        eval_runner_module.solve_problems_vllm(
                                                            filepath=benchmark_path,
                                                            vllm_base_url="http://127.0.0.1:8000",
                                                            agent_type="qwen3_vl",
                                                            decoding_size=32,
                                                            beam_size=512,
                                                            search_depth=4,
                                                            search_version="v1",
                                                            ray_num_cpus=4,
                                                            timeout=3600,
                                                            log_dir=str(log_dir),
                                                            enable_trace=True,
                                                        )

            trace_run_dir = (
                log_dir
                / "eval_vllm_qwen3_vl_benchmarks_checkpoint-7049_sv1_d32_b512_s4_20260410T120000Z"
            )
            self.assertTrue((trace_run_dir / "run_meta.json").exists())
            self.assertTrue(
                (trace_run_dir / "problems" / "0000_imo_2008_p1b.jsonl").exists()
            )
            self.assertTrue(
                (trace_run_dir / "attempts" / "0000_imo_2008_p1b.jsonl").exists()
            )


class ModelPathResolutionTests(unittest.TestCase):
    def test_resolve_model_path_raises_for_missing_local_like_path(self):
        with self.assertRaises(FileNotFoundError):
            resolve_model_path("/tmp/definitely_missing_checkpoint")

    def test_resolve_model_path_allows_remote_repo_id(self):
        with patch("modelscope.snapshot_download", return_value="/tmp/remote-model"):
            self.assertEqual(
                resolve_model_path("Qwen/Qwen3-VL-2B-Instruct"), "/tmp/remote-model"
            )
