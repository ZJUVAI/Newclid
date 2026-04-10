from __future__ import annotations

import json

from newclid.formulations.problem import ProblemJGEX
from newclid.problem_db import ProblemDBRuntime, ProblemDBWriter


def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _read_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def test_problem_db_runtime_and_writer_roundtrip(tmp_path):
    problems_path = tmp_path / "imo_ag_30.txt"
    problems_path.write_text(
        "IMO 2000 G1\na b c = triangle a b c ? perp a b c a\n",
        encoding="utf-8",
    )

    base_problem = ProblemJGEX.from_file(problems_path, "IMO 2000 G1").renamed()
    runtime = ProblemDBRuntime(
        db_root=tmp_path / "problem_db",
        problems_path=problems_path,
        base_problem=base_problem,
    )

    augmented_problem = base_problem.with_more_construction("d = midpoint d b c")
    lookup = runtime.lookup_problem(augmented_problem)
    runtime.record_ddar_result(
        lookup,
        {
            "status": "solved",
            "elapsed_time": 1.25,
        },
    )

    writer = ProblemDBWriter(tmp_path / "problem_db", repo_root=tmp_path)
    writer.write_payload(runtime.export_payload())

    problem_dir = tmp_path / "problem_db" / "imo_ag_30" / runtime.problem_dirname
    assert problem_dir.exists()

    meta = _read_json(problem_dir / "meta.json")
    assert meta["dataset_name"] == "imo_ag_30"
    assert meta["problem_name"] == "IMO 2000 G1"
    assert meta["problem_dirname"] == runtime.problem_dirname

    index = _read_json(problem_dir / "index.json")
    assert index["solved"][lookup.strict_key] is True
    assert index["unsolved"] == {}
    assert index["invalid"] == {}

    solved_records = _read_jsonl(problem_dir / "solved.jsonl")
    assert len(solved_records) == 1
    assert solved_records[0] == {
        "elapsed_time": 1.25,
        "normalized_aux": lookup.normalized_aux,
        "strict_key": lookup.strict_key,
    }

    assert not (problem_dir / "sources.jsonl").exists()

    runtime2 = ProblemDBRuntime(
        db_root=tmp_path / "problem_db",
        problems_path=problems_path,
        base_problem=base_problem,
    )
    assert runtime2.lookup(lookup.strict_key) == "solved"
