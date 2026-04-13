from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Any

import numpy as np
import ray

from newclid.DDAR.build import DDAR
from newclid.agent.search_core import extract_goals, extract_points, extract_premises, run_ddar_on_proof
from newclid.ddar_build_input import build_ddar_input
from newclid.problem_db import classify_build_exception
from newclid.proof import ProofState

if TYPE_CHECKING:
    from newclid.formulations.rule import Rule


class BeamQueue:
    """Keep only the top-k nodes according to their scores."""

    def __init__(self, max_size: int = 512):
        self.queue: list[tuple[float, tuple[int, ...], int, Any]] = []
        self.max_size = max_size
        self.counter = 0

    @staticmethod
    def _sort_key(entry: tuple[float, tuple[int, ...], int, Any]) -> tuple[float, tuple[int, ...], int]:
        score, stable_key, insertion_order, _ = entry
        return (-score, stable_key, insertion_order)

    def _sorted_entries(self) -> list[tuple[float, tuple[int, ...], int, Any]]:
        return sorted(self.queue, key=self._sort_key)

    def add(self, node: object, val: float, *, stable_key: tuple[int, ...]) -> None:
        self.queue.append((val, stable_key, self.counter, node))
        self.counter += 1
        if len(self.queue) > self.max_size:
            self.queue = self._sorted_entries()[: self.max_size]

    def __iter__(self):
        for val, _, _, node in self._sorted_entries():
            yield val, node

    def iter_entries(self):
        yield from self._sorted_entries()

    def __len__(self) -> int:
        return len(self.queue)

    def map_nodes(self, func) -> None:
        self.queue = [
            (val, stable_key, insertion_order, func(node))
            for val, stable_key, insertion_order, node in self.queue
        ]


def run_ddar_c(proof: ProofState, rules: list["Rule"], start_time: float, timeout: int = 3600) -> bool:
    del rules, start_time, timeout
    return run_ddar_on_proof(proof)


def build_problem_proof(problem, defs, *, max_attempts: int = 100) -> ProofState:
    return ProofState.build_problemJGEX(
        problemJGEX=problem,
        defsJGEX=defs,
        rng=np.random.default_rng(998244353),
        max_attempts=max_attempts,
        problem_path=None,
    )


@ray.remote(num_cpus=1)
def run_ddar_remote(
    problem,
    defs,
    rules: list["Rule"],
    start_time: float,
    timeout: int = 3600,
    *,
    return_proof: bool = False,
):
    # These timings describe work performed inside one remote DDAR task. They
    # are not main-thread wall-clock timings and can legitimately sum to more
    # than the end-to-end runtime when many DDAR tasks run in parallel.
    eval_start = time.time()
    ddar_worker_id = f"{ray.util.get_node_ip_address()}:{os.getpid()}"
    ddar_started_at_unix_s = eval_start
    ddar_build_work_time_s = 0.0
    try:
        build_start = time.time()
        points, premises, goals = build_ddar_input(
            problem,
            defs,
            np.random.default_rng(998244353),
            max_attempts=100,
            only_useful_points=False,
        )
        ddar_build_finished_at_unix_s = time.time()
        ddar_build_work_time_s = ddar_build_finished_at_unix_s - build_start
    except Exception as exc:
        ddar_finished_at_unix_s = time.time()
        result = {
            "status": "invalid",
            "elapsed_time": ddar_finished_at_unix_s - eval_start,
            "ddar_worker_id": ddar_worker_id,
            "ddar_started_at_unix_s": ddar_started_at_unix_s,
            "ddar_finished_at_unix_s": ddar_finished_at_unix_s,
            "ddar_build_started_at_unix_s": build_start,
            "ddar_build_finished_at_unix_s": ddar_finished_at_unix_s,
            "ddar_engine_started_at_unix_s": None,
            "ddar_engine_finished_at_unix_s": None,
            "ddar_build_work_time_s": ddar_finished_at_unix_s - build_start,
            "ddar_engine_work_time_s": 0.0,
            "error_type": classify_build_exception(exc),
            "error_message": str(exc),
        }
        if return_proof:
            result["proof"] = None
        return result

    try:
        ddar_start = time.time()
        del rules, start_time, timeout
        solved, _ = DDAR.run_ddar("", points, premises, goals, 500, True, True)
        ddar_engine_finished_at_unix_s = time.time()
        ddar_engine_work_time_s = ddar_engine_finished_at_unix_s - ddar_start
    except Exception as exc:
        ddar_finished_at_unix_s = time.time()
        result = {
            "status": "invalid",
            "elapsed_time": ddar_finished_at_unix_s - eval_start,
            "ddar_worker_id": ddar_worker_id,
            "ddar_started_at_unix_s": ddar_started_at_unix_s,
            "ddar_finished_at_unix_s": ddar_finished_at_unix_s,
            "ddar_build_started_at_unix_s": build_start,
            "ddar_build_finished_at_unix_s": ddar_build_finished_at_unix_s,
            "ddar_engine_started_at_unix_s": ddar_start,
            "ddar_engine_finished_at_unix_s": ddar_finished_at_unix_s,
            "ddar_build_work_time_s": ddar_build_work_time_s,
            "ddar_engine_work_time_s": ddar_finished_at_unix_s - ddar_start,
            "error_type": "engine_error",
            "error_message": str(exc),
        }
        if return_proof:
            result["proof"] = None
        return result

    ddar_finished_at_unix_s = time.time()
    result = {
        "status": "solved" if solved else "unsolved",
        "elapsed_time": ddar_finished_at_unix_s - eval_start,
        "ddar_worker_id": ddar_worker_id,
        "ddar_started_at_unix_s": ddar_started_at_unix_s,
        "ddar_finished_at_unix_s": ddar_finished_at_unix_s,
        "ddar_build_started_at_unix_s": build_start,
        "ddar_build_finished_at_unix_s": ddar_build_finished_at_unix_s,
        "ddar_engine_started_at_unix_s": ddar_start,
        "ddar_engine_finished_at_unix_s": ddar_engine_finished_at_unix_s,
        "ddar_build_work_time_s": ddar_build_work_time_s,
        "ddar_engine_work_time_s": ddar_engine_work_time_s,
    }
    if return_proof:
        result["proof"] = build_problem_proof(problem, defs)
    return result
