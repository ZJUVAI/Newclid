from __future__ import annotations

import unittest
from unittest.mock import patch

from experiments.single_problem_multi_gpu_eval.model_pool import GenerationDispatcher, ModelPool
from experiments.single_problem_multi_gpu_eval import model_pool as model_pool_module


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
