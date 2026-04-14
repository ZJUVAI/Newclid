from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_python(code: str) -> str:
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def test_extract_aux_block_returns_first_block() -> None:
    code = textwrap.dedent(
        """
        import json
        from experiments.test_frontier_models.run_gemini_multi_attempt import extract_aux_block

        text = "noise <aux> e : coll e a b ; </aux> trailing <aux> x : coll x a c ; </aux>"
        print(json.dumps(extract_aux_block(text)))
        """
    )

    assert json.loads(_run_python(code)) == "e : coll e a b ;"


def test_aux_block_to_constructions_supports_multiple_points() -> None:
    code = textwrap.dedent(
        """
        import json
        from experiments.test_frontier_models.run_gemini_multi_attempt import aux_block_to_constructions

        aux_text = "e : coll e a b ; q : coll q a c para p q a b ;"
        print(json.dumps(aux_block_to_constructions(aux_text)))
        """
    )

    assert json.loads(_run_python(code)) == "e = on_line e a b; q = on_line q a c, on_pline q p a b"


def test_load_problem_names_supports_dataset_and_single_selection(tmp_path: Path) -> None:
    problems_path = tmp_path / "tiny.txt"
    problems_path.write_text(
        "p1\na b c = triangle a b c ? coll a b c\n"
        "p2\na b c = triangle a b c ? cong a b a b\n",
        encoding="utf-8",
    )
    code = textwrap.dedent(
        f"""
        import json
        from pathlib import Path
        from experiments.test_frontier_models.run_gemini_multi_attempt import load_problem_names

        problems_path = Path({str(problems_path)!r})
        print(json.dumps({{
            "all": load_problem_names(problems_path, None),
            "single": load_problem_names(problems_path, "p2"),
        }}))
        """
    )

    result = json.loads(_run_python(code))
    assert result["all"] == ["p1", "p2"]
    assert result["single"] == ["p2"]


def test_run_problem_stops_after_first_success(tmp_path: Path) -> None:
    output_path = tmp_path / "attempts.jsonl"
    image_path = tmp_path / "demo.png"
    code = textwrap.dedent(
        f"""
        import json
        from pathlib import Path

        import experiments.test_frontier_models.run_gemini_multi_attempt as module
        from experiments.test_frontier_models.run_gemini_multi_attempt import (
            AttemptResult,
            ProblemContext,
            run_problem,
        )
        from newclid.formulations.problem import ProblemJGEX

        output_path = Path({str(output_path)!r})
        image_path = Path({str(image_path)!r})
        context = ProblemContext(
            problem_name="demo_problem",
            problem=ProblemJGEX.from_text("a b c = triangle a b c ? coll a b c"),
            proof=None,
            defs={{}},
            rules=[],
            query="<problem> a : ; b : ; c : ? coll a b c </problem>",
            image_path=image_path,
            system_prompt="system",
        )

        module.run_ddar_c = lambda proof, rules, start_time, timeout: False
        calls = []

        def fake_run_single_attempt(**kwargs):
            attempt_idx = kwargs["attempt_idx"]
            calls.append(attempt_idx)
            status = "solved" if attempt_idx == 3 else "unsolved"
            return AttemptResult(
                problem_name="demo_problem",
                attempt_idx=attempt_idx,
                model="google/gemini-3.1-pro-preview",
                actual_model="google/gemini-3.1-pro-preview-20260219",
                query=context.query,
                image_path=str(context.image_path),
                raw_response="<aux> e : coll e a b ; </aux>",
                aux_text="e : coll e a b ;",
                constructed_clauses="e = on_line e a b",
                usage={{"total_tokens": 8, "cost": 5.6e-05}},
                verification_status=status,
                error_message=None,
                elapsed_api_s=0.01,
                elapsed_verify_s=0.02,
                elapsed_total_s=0.03,
            )

        module.run_single_attempt = fake_run_single_attempt

        summary = run_problem(
            client=object(),
            context=context,
            output_path=output_path,
            model="google/gemini-3.1-pro-preview",
            temperature=0.2,
            max_tokens=256,
            max_attempts=5,
            timeout=60,
        )

        lines = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
        print(json.dumps({{
            "calls": calls,
            "solved": summary.solved,
            "solved_attempt_idx": summary.solved_attempt_idx,
            "total_attempts_executed": summary.total_attempts_executed,
            "elapsed_time_s_nonnegative": summary.elapsed_time_s >= 0.0,
            "line_types": [line["type"] for line in lines],
            "actual_model": lines[0]["actual_model"],
            "usage_tokens": lines[0]["usage"]["total_tokens"],
            "summary_solved_attempt_idx": lines[-1]["solved_attempt_idx"],
        }}))
        """
    )

    result = json.loads(_run_python(code))
    assert result["calls"] == [1, 2, 3]
    assert result["solved"] is True
    assert result["solved_attempt_idx"] == 3
    assert result["total_attempts_executed"] == 3
    assert result["elapsed_time_s_nonnegative"] is True
    assert result["line_types"] == ["attempt", "attempt", "attempt", "summary"]
    assert result["actual_model"] == "google/gemini-3.1-pro-preview-20260219"
    assert result["usage_tokens"] == 8
    assert result["summary_solved_attempt_idx"] == 3
