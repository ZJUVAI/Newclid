from __future__ import annotations

from pathlib import Path

from newclid.evaluation.search_runtime import (
    BeamQueue,
    build_problem_proof,
    extract_goals,
    extract_points,
    extract_premises,
)
from newclid.ddar_build_input import build_ddar_input
from newclid.formulations.definition import DefinitionJGEX
from newclid.formulations.problem import ProblemJGEX
import numpy as np


def _load_defs():
    defs_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "newclid"
        / "default_configs"
        / "defs.txt"
    )
    return DefinitionJGEX.to_dict(DefinitionJGEX.parse_txt_file(defs_path))


def _bad_reused_point_problem() -> ProblemJGEX:
    return ProblemJGEX.from_text(
        "a b c = triangle a b c; d = on_tline d a b c; e = on_tline d a b c"
    )


def _bad_requirement_problem() -> ProblemJGEX:
    return ProblemJGEX.from_text(
        "a b c = triangle a b c; d = on_line d a b; e = on_pline e d a b"
    )


def test_build_ddar_input_matches_full_build_for_all_points():
    defs = _load_defs()
    problem = ProblemJGEX.from_text("a b c = triangle a b c")

    proof = build_problem_proof(problem, defs)
    points, premises, goals = build_ddar_input(
        problem,
        defs,
        np.random.default_rng(998244353),
        max_attempts=100,
        only_useful_points=False,
    )

    assert points == extract_points(proof)
    assert premises == extract_premises(proof)
    assert goals == extract_goals(proof)


def test_build_ddar_input_rejects_reused_existing_point_name():
    defs = _load_defs()
    problem = _bad_reused_point_problem()

    try:
        build_ddar_input(
            problem,
            defs,
            np.random.default_rng(998244353),
            max_attempts=3,
            only_useful_points=False,
        )
    except Exception as exc:
        assert "already used" in str(exc)
    else:
        raise AssertionError("Expected build_ddar_input to reject reused point names")


def test_full_build_rejects_reused_existing_point_name():
    defs = _load_defs()
    problem = _bad_reused_point_problem()

    try:
        build_problem_proof(problem, defs, max_attempts=3)
    except Exception as exc:
        assert "already used" in str(exc)
    else:
        raise AssertionError("Expected full proof build to reject reused point names")


def test_build_ddar_input_rejects_requirement_numerical_failure():
    defs = _load_defs()
    problem = _bad_requirement_problem()

    try:
        build_ddar_input(
            problem,
            defs,
            np.random.default_rng(998244353),
            max_attempts=3,
            only_useful_points=False,
        )
    except Exception as exc:
        assert "Requirement check_numerical failed" in str(exc)
    else:
        raise AssertionError(
            "Expected build_ddar_input to reject invalid construction requirements"
        )


def test_full_build_rejects_requirement_numerical_failure():
    defs = _load_defs()
    problem = _bad_requirement_problem()

    try:
        build_problem_proof(problem, defs, max_attempts=3)
    except Exception as exc:
        assert "Requirement check_numerical failed" in str(exc)
    else:
        raise AssertionError(
            "Expected full proof build to reject invalid construction requirements"
        )


def test_beam_queue_iterates_in_stable_order_independent_of_add_order():
    queue = BeamQueue(max_size=4)
    queue.add(node=("n3",), val=0.5, stable_key=(3,))
    queue.add(node=("n1",), val=1.0, stable_key=(1,))
    queue.add(node=("n2",), val=1.0, stable_key=(2,))
    queue.add(node=("n0",), val=1.0, stable_key=(0,))

    ordered = [node for _, node in queue]

    assert ordered == [("n0",), ("n1",), ("n2",), ("n3",)]
