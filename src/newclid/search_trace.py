from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from newclid.numerical.geometries import PointNum
from newclid.problem_db import get_git_commit


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sanitize_filename(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value)
    cleaned = cleaned.strip("._")
    return cleaned or "item"


def build_attempt_key(request_id: str | None, candidate_rank: int | None, node_id: int | None) -> str:
    if request_id is not None and candidate_rank is not None:
        return f"{request_id}:{candidate_rank}"
    if node_id is not None:
        return f"node:{node_id}"
    return "unknown"


def proof_to_ddar_input(proof) -> dict[str, Any]:
    points: list[tuple[str, Any, Any]] = []
    for name, point in proof.symbols_graph.name2node.items():
        if isinstance(point.num, PointNum):
            points.append((name, point.num.x, point.num.y))

    premises: list[tuple[str, list[str]]] = []
    for stmt in proof.dep_graph.hyper_graph:
        args: list[str] = []
        for pt in stmt.args:
            if hasattr(pt, "name"):
                args.append(pt.name)
            else:
                args.append(str(pt))
        premises.append((stmt.predicate.NAME, args))

    goals: list[tuple[str, list[str]]] = []
    for stmt in proof.goals:
        args = []
        for pt in stmt.args:
            if hasattr(pt, "name"):
                args.append(pt.name)
            else:
                args.append(str(pt))
        goals.append((stmt.predicate.NAME, args))

    return {
        "points": points,
        "premises": premises,
        "goals": goals,
    }


class AttemptWriter:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = open(self.path, "a", encoding="utf-8")

    def write(self, record: dict[str, Any]) -> None:
        self._fp.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
        self._fp.write("\n")
        self._fp.flush()

    def close(self) -> None:
        self._fp.close()


class AttemptAggregator:
    def __init__(self, writer: AttemptWriter) -> None:
        self.writer = writer
        self.request_context: dict[str, dict[str, Any]] = {}
        self.request_outputs: dict[str, list[dict[str, Any]]] = {}
        self.pending_attempts: dict[str, dict[str, Any]] = {}
        self.node_to_attempt_key: dict[int, str] = {}

    def process(self, record: dict[str, Any]) -> None:
        event = record["event"]
        if event == "model_request":
            self.request_context[record["request_id"]] = {
                "query": record.get("query"),
                "img_path": record.get("img_path"),
                "new_point_name": record.get("new_point_name"),
                "response_prefix": record.get("response_prefix"),
                "with_predicate": record.get("with_predicate"),
                "decoding_size": record.get("decoding_size"),
                "node_id": record.get("node_id"),
                "parent_node_id": record.get("parent_node_id"),
                "depth": record.get("depth"),
            }
            return

        if event == "model_response":
            self.request_outputs[record["request_id"]] = list(record.get("outputs", []))
            return

        if event == "base_ddar":
            attempt_key = record.get("attempt_key") or build_attempt_key(None, None, record.get("node_id"))
            attempt = self._base_attempt(record)
            attempt["attempt_key"] = attempt_key
            self.pending_attempts[attempt_key] = attempt
            node_id = record.get("node_id")
            if node_id is not None:
                self.node_to_attempt_key[node_id] = attempt_key
            return

        if event == "candidate_transition":
            attempt = self.pending_attempts.pop(
                record.get("attempt_key") or build_attempt_key(record.get("request_id"), record.get("candidate_rank"), record.get("node_id")),
                None,
            )
            if attempt is None:
                attempt = self._candidate_attempt(record)
            else:
                attempt.update(
                    {
                        **self._candidate_attempt(record),
                        "ddar_status": attempt.get("ddar_status"),
                        "ddar_elapsed_time": attempt.get("ddar_elapsed_time"),
                        "ddar_input": attempt.get("ddar_input"),
                        "error_type": attempt.get("error_type"),
                        "error_message": attempt.get("error_message"),
                    }
                )
            attempt_key = attempt["attempt_key"]
            node_id = record.get("node_id")
            if node_id is not None:
                self.node_to_attempt_key[node_id] = attempt_key

            decision = record.get("decision")
            if decision == "ddar_submitted":
                self.pending_attempts[attempt_key] = attempt
                return

            self.writer.write(attempt)
            return

        if event == "ddar_result":
            attempt_key = record.get("attempt_key")
            if attempt_key is None and record.get("node_id") is not None:
                attempt_key = self.node_to_attempt_key.get(record["node_id"])
            if attempt_key is None:
                attempt_key = build_attempt_key(None, None, record.get("node_id"))
            attempt = self.pending_attempts.pop(attempt_key, self._base_attempt(record))
            attempt["attempt_key"] = attempt_key
            attempt["ddar_status"] = record.get("status")
            attempt["ddar_elapsed_time"] = record.get("elapsed_time")
            attempt["ddar_build_work_time_s"] = record.get("ddar_build_work_time_s")
            attempt["ddar_engine_work_time_s"] = record.get("ddar_engine_work_time_s")
            attempt["ddar_input"] = record.get("ddar_input")
            attempt["problem_text"] = record.get("problem_text")
            attempt["error_type"] = record.get("error_type")
            attempt["error_message"] = record.get("error_message")
            if attempt.get("attempt_type") == "base_ddar":
                attempt["status"] = record.get("status")
                attempt["decision"] = record.get("status")
                self.writer.write(attempt)
                return

            attempt["status"] = record.get("status")
            if record.get("status") == "solved":
                attempt["decision"] = "solved"
                self.writer.write(attempt)
            elif record.get("status") == "invalid":
                attempt["decision"] = "invalid"
                self.writer.write(attempt)
            else:
                attempt["decision"] = "unsolved"
                self.pending_attempts[attempt_key] = attempt
                return
            self.writer.write(attempt)

    def close(self) -> None:
        for attempt_key in sorted(self.pending_attempts):
            self.writer.write(self.pending_attempts[attempt_key])
        self.pending_attempts.clear()
        self.writer.close()

    def _common_fields(self, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "run_id": record.get("run_id"),
            "route": record.get("route"),
            "agent": record.get("agent"),
            "problem_name": record.get("problem_name"),
            "problem_index": record.get("problem_index"),
            "ts_utc": record.get("ts_utc"),
            "elapsed_s": record.get("elapsed_s"),
        }

    def _base_attempt(self, record: dict[str, Any]) -> dict[str, Any]:
        return {
            **self._common_fields(record),
            "attempt_type": "base_ddar",
            "attempt_id": record.get("node_id"),
            "node_id": record.get("node_id"),
            "parent_node_id": record.get("parent_node_id"),
            "depth": record.get("depth"),
            "request_id": None,
            "candidate_rank": None,
            "query": None,
            "img_path": None,
            "new_point_name": None,
            "raw_aux_text": None,
            "translated_aux": None,
            "beam_score_before": None,
            "beam_score_after": None,
            "status": None,
            "decision": None,
            "ddar_status": None,
            "ddar_elapsed_time": None,
            "ddar_build_work_time_s": None,
            "ddar_engine_work_time_s": None,
            "ddar_input": record.get("ddar_input"),
            "problem_text": record.get("problem_text"),
            "error_type": record.get("error_type"),
            "error_message": record.get("error_message"),
        }

    def _candidate_attempt(self, record: dict[str, Any]) -> dict[str, Any]:
        request_id = record.get("request_id")
        candidate_rank = record.get("candidate_rank")
        node_id = record.get("node_id")
        attempt_key = record.get("attempt_key") or build_attempt_key(request_id, candidate_rank, node_id)
        request = self.request_context.get(request_id, {})
        output = {}
        outputs = self.request_outputs.get(request_id, [])
        if candidate_rank is not None and 0 <= candidate_rank < len(outputs):
            output = outputs[candidate_rank]
        return {
            **self._common_fields(record),
            "attempt_type": "candidate",
            "attempt_key": attempt_key,
            "attempt_id": node_id,
            "node_id": node_id,
            "parent_node_id": record.get("parent_node_id", request.get("node_id")),
            "depth": record.get("depth", request.get("depth")),
            "request_id": request_id,
            "candidate_rank": candidate_rank,
            "query": request.get("query"),
            "img_path": request.get("img_path"),
            "new_point_name": request.get("new_point_name"),
            "raw_aux_text": record.get("raw_aux_text"),
            "translated_aux": record.get("translated_aux"),
            "aux_dsl": output.get("aux_dsl"),
            "model_score": output.get("score"),
            "beam_score_before": record.get("beam_score_before"),
            "beam_score_after": record.get("beam_score_after"),
            "status": record.get("decision"),
            "decision": record.get("decision"),
            "ddar_status": None,
            "ddar_elapsed_time": None,
            "ddar_build_work_time_s": None,
            "ddar_engine_work_time_s": None,
            "ddar_input": None,
            "problem_text": record.get("new_problem_text"),
            "error_type": record.get("error_type"),
            "error_message": record.get("error_message"),
        }


class TraceWriter:
    def __init__(
        self,
        path: str | Path,
        *,
        run_id: str,
        route: str,
        agent: str,
        problem_name: str,
        problem_index: int,
        start_time: float,
        attempts_path: str | Path | None = None,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self.route = route
        self.agent = agent
        self.problem_name = problem_name
        self.problem_index = problem_index
        self.start_time = start_time
        self._fp = open(self.path, "a", encoding="utf-8")
        self._attempt_aggregator = None
        if attempts_path is not None:
            self._attempt_aggregator = AttemptAggregator(AttemptWriter(attempts_path))

    def log(self, event: str, **payload: Any) -> None:
        record = {
            "event": event,
            "run_id": self.run_id,
            "route": self.route,
            "agent": self.agent,
            "problem_name": self.problem_name,
            "problem_index": self.problem_index,
            "ts_utc": utc_now_iso(),
            "elapsed_s": round(time.time() - self.start_time, 6),
            **payload,
        }
        self._fp.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
        self._fp.write("\n")
        self._fp.flush()
        if self._attempt_aggregator is not None:
            self._attempt_aggregator.process(record)

    def close(self) -> None:
        if self._attempt_aggregator is not None:
            self._attempt_aggregator.close()
        self._fp.close()


class TraceRun:
    def __init__(
        self,
        root_dir: str | Path,
        *,
        route: str,
        agent: str,
        dataset_path: str | Path,
        model_path: str | list[str],
        params: dict[str, Any],
        run_name: str | None = None,
        run_timestamp: str | None = None,
        repo_root: str | Path | None = None,
    ) -> None:
        dataset_slug = sanitize_filename(Path(dataset_path).stem)
        if isinstance(model_path, list):
            model_repr = "__".join(str(item) for item in model_path)
        else:
            model_repr = str(model_path)
        model_slug = sanitize_filename(Path(model_repr).name or model_repr)
        if run_name is None:
            run_name = f"{sanitize_filename(route)}_{dataset_slug}_{model_slug}"
        timestamp = run_timestamp or timestamp_slug()
        self.run_id = f"{sanitize_filename(run_name)}_{timestamp}"
        self.run_dir = Path(root_dir) / self.run_id
        self.problem_dir = self.run_dir / "problems"
        self.attempts_dir = self.run_dir / "attempts"
        self.problem_dir.mkdir(parents=True, exist_ok=True)
        self.attempts_dir.mkdir(parents=True, exist_ok=True)
        meta = {
            "run_id": self.run_id,
            "route": route,
            "agent": agent,
            "dataset_path": str(dataset_path),
            "model_path": model_path,
            "git_commit": get_git_commit(repo_root),
            "argv": sys.argv,
            "trace_outputs": ["raw_events", "attempts"],
            **params,
        }
        with open(self.run_dir / "run_meta.json", "w", encoding="utf-8") as fp:
            json.dump(meta, fp, ensure_ascii=False, indent=2, sort_keys=True)
            fp.write("\n")

    def create_problem_writer(
        self,
        *,
        problem_index: int,
        problem_name: str,
        route: str,
        agent: str,
        start_time: float,
    ) -> TraceWriter:
        filename = f"{problem_index:04d}_{sanitize_filename(problem_name)}.jsonl"
        return TraceWriter(
            self.problem_dir / filename,
            run_id=self.run_id,
            route=route,
            agent=agent,
            problem_name=problem_name,
            problem_index=problem_index,
            start_time=start_time,
            attempts_path=self.attempts_dir / filename,
        )
