from __future__ import annotations

import csv
import time
from concurrent.futures import ThreadPoolExecutor

from newclid.profiling import (
    add_profiling_time,
    create_detailed_profiling_payload,
    create_profiling_payload,
    finalize_detailed_profiling,
    finalize_profiling,
    merge_profiling_payloads,
    write_profiling_csv,
)
from experiments.single_problem_multi_gpu_eval.base_multi_gpu_agent import BaseMultiGPUAgent


class _DummyDispatcher:
    def __init__(self, refs=None):
        self._refs = [] if refs is None else list(refs)

    def active_refs(self):
        return list(self._refs)


class _DummyAgent(BaseMultiGPUAgent):
    def seed_state(self, proof, base_proof):
        return None

    def get_problem_from_state(self, state):
        return None

    def prepare_request(self, *, request_id, state, proof, depth):
        return {"request_id": request_id}

    def make_next_state_from_unsolved_ddar(self, *, new_problem, prior_state, ddar_result, proof):
        return None

    def try_dsl_to_constructions(self, content: str):
        return None


def test_finalize_profiling_computes_other_wall_time() -> None:
    profiling = create_profiling_payload()
    add_profiling_time(profiling, "entry_setup_wall_time_s", 0.2)
    add_profiling_time(profiling, "base_ddar_wall_time_s", 0.3)
    add_profiling_time(profiling, "request_prepare_wall_time_s", 0.4)
    add_profiling_time(profiling, "wait_wall_time_s", 1.2)
    add_profiling_time(profiling, "gpu_result_handle_wall_time_s", 0.6)
    add_profiling_time(profiling, "ddar_submit_wall_time_s", 0.1)
    add_profiling_time(profiling, "ddar_result_handle_wall_time_s", 0.2)
    add_profiling_time(profiling, "scheduler_overhead_wall_time_s", 0.4)

    finalized = finalize_profiling(profiling, 4.0)

    assert finalized["total_time_s"] == 4.0
    assert abs(finalized["other_wall_time_s"] - 0.6) < 1e-9


def test_finalize_profiling_clamps_negative_other_wall_time() -> None:
    profiling = create_profiling_payload()
    add_profiling_time(profiling, "entry_setup_wall_time_s", 2.0)
    add_profiling_time(profiling, "base_ddar_wall_time_s", 2.0)
    add_profiling_time(profiling, "request_prepare_wall_time_s", 2.0)

    finalized = finalize_profiling(profiling, 5.0)

    assert finalized["other_wall_time_s"] == 0.0


def test_merge_profiling_payloads_accumulates_wall_stages_only() -> None:
    merged = merge_profiling_payloads(
        {"entry_setup_wall_time_s": 1.0},
        {"wait_wall_time_s": 5.0, "other_wall_time_s": 99.0},
    )

    assert merged["entry_setup_wall_time_s"] == 1.0
    assert merged["wait_wall_time_s"] == 5.0
    assert merged["total_time_s"] == 0.0
    assert merged["other_wall_time_s"] == 0.0


def test_detailed_helpers_alias_wall_only_payload() -> None:
    profiling = create_detailed_profiling_payload()
    add_profiling_time(profiling, "wait_wall_time_s", 1.5)

    finalized = finalize_detailed_profiling(profiling, 2.0)

    assert finalized["wait_wall_time_s"] == 1.5
    assert finalized["other_wall_time_s"] == 0.5


def test_write_profiling_csv_outputs_wall_summary_and_rows(tmp_path) -> None:
    csv_path = tmp_path / "eval_demo_profiling.csv"
    rows = [
        {
            "problem_name": "p1",
            "solved": "√",
            "total_time_s": 5.0,
            "entry_setup_wall_time_s": 0.5,
            "base_ddar_wall_time_s": 0.4,
            "request_prepare_wall_time_s": 1.2,
            "wait_wall_time_s": 1.6,
            "gpu_result_handle_wall_time_s": 0.3,
            "ddar_submit_wall_time_s": 0.1,
            "ddar_result_handle_wall_time_s": 0.4,
            "scheduler_overhead_wall_time_s": 0.2,
            "other_wall_time_s": 0.3,
        },
        {
            "problem_name": "p2",
            "solved": "x",
            "total_time_s": 2.0,
            "entry_setup_wall_time_s": 0.2,
            "base_ddar_wall_time_s": 0.1,
            "request_prepare_wall_time_s": 0.3,
            "wait_wall_time_s": 0.7,
            "gpu_result_handle_wall_time_s": 0.2,
            "ddar_submit_wall_time_s": 0.0,
            "ddar_result_handle_wall_time_s": 0.1,
            "scheduler_overhead_wall_time_s": 0.1,
            "other_wall_time_s": 0.3,
        },
    ]

    write_profiling_csv(
        csv_path,
        dataset_name="demo",
        solved_count=1,
        total_problems=2,
        total_time_s=7.0,
        rows=rows,
    )

    with open(csv_path, newline="", encoding="utf-8") as f:
        written_rows = list(csv.reader(f))

    assert "Dataset: demo, Solved: 1/2" in written_rows[0][0]
    assert "Total Time: 7.00s" in written_rows[0][0]
    assert "Request Prepare Wall Time: 1.50s" in written_rows[0][0]
    assert written_rows[1] == [
        "Problem Name",
        "Solved",
        "Total Time (s)",
        "Entry Setup Wall Time (s)",
        "Base DDAR Wall Time (s)",
        "Request Prepare Wall Time (s)",
        "Wait Wall Time (s)",
        "GPU Result Handle Wall Time (s)",
        "DDAR Submit Wall Time (s)",
        "DDAR Result Handle Wall Time (s)",
        "Scheduler Overhead Wall Time (s)",
        "Other Wall Time (s)",
    ]
    assert written_rows[2] == [
        "p1",
        "√",
        "5.00",
        "0.50",
        "0.40",
        "1.20",
        "1.60",
        "0.30",
        "0.10",
        "0.40",
        "0.20",
        "0.30",
    ]


def test_parallel_prepare_wait_is_attributed_to_prepare_wall_time() -> None:
    profiling = create_profiling_payload()
    agent = _DummyAgent(
        model_pool=None,
        decoding_size=1,
        beam_size=1,
        search_depth=1,
        agent_type="dummy",
    )

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(lambda: (time.sleep(0.03), {"request_id": "r1"})[1])
        running_prepare_futures = {future: {"request_id": "r1", "depth": 0}}
        agent._wait_for_next_event(
            dispatcher=_DummyDispatcher(),
            running_futures=[],
            running_prepare_futures=running_prepare_futures,
            profiling=profiling,
        )

    assert profiling["request_prepare_wall_time_s"] > 0.0
    assert profiling["wait_wall_time_s"] == 0.0


def test_gpu_or_ddar_wait_is_attributed_to_wait_wall_time(monkeypatch) -> None:
    profiling = create_profiling_payload()
    agent = _DummyAgent(
        model_pool=None,
        decoding_size=1,
        beam_size=1,
        search_depth=1,
        agent_type="dummy",
    )

    def fake_ray_wait(*args, **kwargs):
        time.sleep(0.02)
        return [], []

    monkeypatch.setattr(
        "experiments.single_problem_multi_gpu_eval.base_multi_gpu_agent.ray.wait",
        fake_ray_wait,
    )

    agent._wait_for_next_event(
        dispatcher=_DummyDispatcher(refs=["gpu-ref"]),
        running_futures=[],
        running_prepare_futures={},
        profiling=profiling,
    )

    assert profiling["wait_wall_time_s"] > 0.0
    assert profiling["request_prepare_wall_time_s"] == 0.0
