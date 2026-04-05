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

    def close(self) -> None:
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
        repo_root: str | Path | None = None,
    ) -> None:
        dataset_slug = sanitize_filename(Path(dataset_path).stem)
        if isinstance(model_path, list):
            model_repr = "__".join(str(item) for item in model_path)
        else:
            model_repr = str(model_path)
        model_slug = sanitize_filename(Path(model_repr).name or model_repr)
        self.run_id = f"{timestamp_slug()}_{sanitize_filename(route)}_{dataset_slug}_{model_slug}"
        self.run_dir = Path(root_dir) / self.run_id
        self.problem_dir = self.run_dir / "problems"
        self.problem_dir.mkdir(parents=True, exist_ok=True)
        meta = {
            "run_id": self.run_id,
            "route": route,
            "agent": agent,
            "dataset_path": str(dataset_path),
            "model_path": model_path,
            "git_commit": get_git_commit(repo_root),
            "argv": sys.argv,
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
        )
