from __future__ import annotations

import json

from newclid.evaluation.search_trace import AttemptAggregator, AttemptWriter


def _load_attempts(path):
    with open(path, encoding="utf-8") as fp:
        return [json.loads(line) for line in fp]


def test_attempt_aggregator_preserves_construction_fields_across_transitions(tmp_path):
    attempts_path = tmp_path / "attempts.jsonl"
    aggregator = AttemptAggregator(AttemptWriter(attempts_path))

    common = {
        "run_id": "run",
        "route": "route",
        "agent": "lm",
        "problem_name": "problem",
        "problem_index": 0,
        "ts_utc": "2026-01-01T00:00:00Z",
        "elapsed_s": 1.0,
        "attempt_key": "d3_p21-4-2:21",
        "request_id": "d3_p21-4-2",
        "node_id": 8311,
        "parent_node_id": 961,
        "candidate_rank": 21,
        "depth": 3,
        "beam_score_before": -1.0,
        "beam_score_after": -1.4,
        "raw_aux_text": " x21 = on_tline a b c d",
        "construction_text": "x21 = on_tline a b c d",
    }

    aggregator.process(
        {
            **common,
            "event": "candidate_transition",
            "decision": "ddar_submitted",
        }
    )
    aggregator.process(
        {
            **common,
            "event": "ddar_result",
            "status": "unsolved",
            "elapsed_time": 0.2,
            "ddar_build_work_time_s": 0.01,
            "ddar_engine_work_time_s": 0.19,
            "ddar_worker_id": "worker:1",
            "error_type": None,
            "error_message": None,
        }
    )
    aggregator.process(
        {
            **common,
            "event": "candidate_transition",
            "decision": "queued_next_depth",
        }
    )
    aggregator.close()

    attempts = _load_attempts(attempts_path)
    assert len(attempts) == 1
    attempt = attempts[0]
    assert attempt["status"] == "queued_next_depth"
    assert attempt["decision"] == "queued_next_depth"
    assert attempt["ddar_status"] == "unsolved"
    assert attempt["raw_aux_text"] == " x21 = on_tline a b c d"
    assert attempt["construction_text"] == "x21 = on_tline a b c d"


def test_attempt_aggregator_records_parse_failed_raw_text(tmp_path):
    attempts_path = tmp_path / "attempts.jsonl"
    aggregator = AttemptAggregator(AttemptWriter(attempts_path))
    aggregator.process(
        {
            "event": "candidate_transition",
            "run_id": "run",
            "route": "route",
            "agent": "lm",
            "problem_name": "problem",
            "problem_index": 0,
            "ts_utc": "2026-01-01T00:00:00Z",
            "elapsed_s": 1.0,
            "attempt_key": "d0_proot:3",
            "request_id": "d0_proot",
            "node_id": None,
            "parent_node_id": 0,
            "candidate_rank": 3,
            "depth": 0,
            "decision": "parse_failed",
            "beam_score_before": 0.0,
            "beam_score_after": None,
            "raw_aux_text": " nonsense",
            "construction_text": None,
        }
    )
    aggregator.close()

    attempts = _load_attempts(attempts_path)
    assert len(attempts) == 1
    attempt = attempts[0]
    assert attempt["status"] == "parse_failed"
    assert attempt["raw_aux_text"] == " nonsense"
    assert attempt["construction_text"] is None
