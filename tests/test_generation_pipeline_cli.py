import sys
from types import SimpleNamespace

import pytest

from newclid.generation import pipeline as generation_pipeline
from newclid.generation.worker import ProblemWorker


@pytest.mark.parametrize(
    ("argv", "expected_using_log", "expected_using_exp", "expected_direct_png", "expected_img_pixels"),
    [
        (
            ["pipeline.py", "--n_samples", "1", "--dir", "./tmp-datasets"],
            True,
            False,
            True,
            512,
        ),
        (
            [
                "pipeline.py",
                "--n_samples",
                "1",
                "--no-using_log",
                "--using_exp",
                "--no-direct_png",
                "--img_pixels",
                "768",
            ],
            False,
            True,
            False,
            768,
        ),
    ],
)
def test_pipeline_cli_image_render_args(
    monkeypatch,
    argv,
    expected_using_log,
    expected_using_exp,
    expected_direct_png,
    expected_img_pixels,
):
    captured = {}

    class DummyPipeline:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def generate(self):
            captured["generated"] = True

    monkeypatch.setattr(generation_pipeline, "ProblemPipeline", DummyPipeline)
    monkeypatch.setattr(
        generation_pipeline, "load_construction_config", lambda path: None
    )
    monkeypatch.setattr(sys, "argv", argv)

    generation_pipeline.main()

    assert captured["using_log"] is expected_using_log
    assert captured["using_exp"] is expected_using_exp
    assert captured["direct_png"] is expected_direct_png
    assert captured["img_pixels"] == expected_img_pixels
    assert captured["generated"] is True


def test_problem_worker_passes_csolver_equation_flags(monkeypatch):
    captured = {}

    class DummyCSolver:
        def __init__(self, problem, seed=None, solver=None, **kwargs):
            captured["problem"] = problem
            captured["seed"] = seed
            captured["solver"] = solver
            captured["kwargs"] = kwargs

        def run(self, max_level=500):
            captured["max_level"] = max_level
            return True

    dummy_solver = SimpleNamespace(run_infos={"runtime": 0.0}, proof=None)
    dummy_builder = SimpleNamespace(problemJGEX=SimpleNamespace(constructions=[]))

    monkeypatch.setattr("newclid.generation.worker.CSolver", DummyCSolver)
    monkeypatch.setattr(
        ProblemWorker,
        "_build_solver",
        staticmethod(lambda fl_statement, max_attempts=1: (dummy_solver, dummy_builder)),
    )
    monkeypatch.setattr(
        ProblemWorker,
        "_generate_possible_goals",
        staticmethod(lambda solver: ([], 0.0)),
    )
    monkeypatch.setattr(
        ProblemWorker,
        "_get_all_premise",
        staticmethod(lambda clauses, proof: ({}, {})),
    )

    data, summary = ProblemWorker._process_single_problem(
        (
            0,
            123,
            5,
            77,
            False,
            True,
            0,
            0,
            True,
            2,
            True,
            False,
            None,
            "a b c = triangle a b c ? perp a b b c",
        )
    )

    assert data == []
    assert summary["fl_statement"] == "a b c = triangle a b c ? perp a b b c"
    assert captured["max_level"] == 77
    assert captured["kwargs"]["using_log"] is False
    assert captured["kwargs"]["using_exp"] is True
