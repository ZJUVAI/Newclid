from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from experiments.single_problem_multi_gpu_eval.visual_multi_gpu_agent import VisualMultiGPUAgent


def test_prepare_request_renders_depth_zero_locally(monkeypatch, tmp_path: Path) -> None:
    agent = VisualMultiGPUAgent(
        model_pool=None,
        decoding_size=2,
        beam_size=4,
        search_depth=3,
        render_root=tmp_path,
    )

    class FakeProof:
        def __init__(self):
            self.rng = object()
            self.defs = {"dummy": "defs"}

    monkeypatch.setattr(
        "experiments.single_problem_multi_gpu_eval.visual_multi_gpu_agent.ProofState",
        FakeProof,
    )

    render_calls: list[tuple[object, object, object, object, object]] = []

    def fake_render_visual_prompt(*, proof, problem, render_root, stem, render_width):
        render_calls.append((proof, problem, render_root, stem, render_width))
        return (str(tmp_path / f"{stem}.png"), 0.25)

    monkeypatch.setattr(
        "experiments.single_problem_multi_gpu_eval.visual_multi_gpu_agent.render_visual_prompt",
        fake_render_visual_prompt,
    )
    monkeypatch.setattr(agent, "problem_to_dsl", lambda problem, defs: f"query:{problem.name}:{defs['dummy']}")
    monkeypatch.setattr(agent, "get_new_point_name", lambda problem: "x")

    problem = SimpleNamespace(
        name="problem",
        constructions=[SimpleNamespace(points=("A", "B"))],
    )
    current_proof = FakeProof()

    request = agent.prepare_request(
        request_id="d0_n0",
        state=(problem, current_proof),
        proof=current_proof,
        depth=0,
    )

    assert request["query"] == "query:problem:defs"
    assert request["img_path"].endswith("d0_d0_n0.png")
    assert request["_prepare_elapsed_s"] >= 0.0
    assert render_calls == [
        (current_proof, problem, tmp_path, "d0_d0_n0", 1024),
    ]


def test_prepare_request_reuses_remote_image_path_after_depth_zero(monkeypatch) -> None:
    agent = VisualMultiGPUAgent(
        model_pool=None,
        decoding_size=2,
        beam_size=4,
        search_depth=3,
    )

    class FakeProof:
        def __init__(self):
            self.defs = {"dummy": "defs"}

    render_calls: list[object] = []

    def fake_render_visual_prompt(**kwargs):
        render_calls.append(kwargs)
        return ("unused.png", 0.1)

    monkeypatch.setattr(
        "experiments.single_problem_multi_gpu_eval.visual_multi_gpu_agent.render_visual_prompt",
        fake_render_visual_prompt,
    )
    monkeypatch.setattr(agent, "problem_to_dsl", lambda problem, defs: f"query:{problem.name}:{defs['dummy']}")
    monkeypatch.setattr(agent, "get_new_point_name", lambda problem: "x")

    problem = SimpleNamespace(
        name="problem",
        constructions=[SimpleNamespace(points=("A", "B"))],
    )
    base_proof = FakeProof()

    request = agent.prepare_request(
        request_id="d1_n0",
        state=(problem, "/tmp/remote_rendered.png"),
        proof=base_proof,
        depth=1,
    )

    assert request["query"] == "query:problem:defs"
    assert request["img_path"] == "/tmp/remote_rendered.png"
    assert render_calls == []


def test_make_next_state_from_unsolved_ddar_uses_img_path() -> None:
    agent = VisualMultiGPUAgent(
        model_pool=None,
        decoding_size=2,
        beam_size=4,
        search_depth=2,
    )
    problem = SimpleNamespace(name="problem", constructions=[])

    next_state = agent.make_next_state_from_unsolved_ddar(
        new_problem=problem,
        prior_state=None,
        ddar_result={"img_path": "/tmp/next.png"},
        proof=None,
    )

    assert next_state == (problem, "/tmp/next.png")


def test_ddar_task_kwargs_enable_remote_render_before_last_depth(tmp_path: Path) -> None:
    agent = VisualMultiGPUAgent(
        model_pool=None,
        decoding_size=2,
        beam_size=4,
        search_depth=3,
        render_root=tmp_path,
        render_width=768,
    )

    assert agent.ddar_task_kwargs(
        request_id="d0_n1",
        depth=0,
        candidate_rank=0,
        node_id=8,
        state=None,
    ) == {
        "render_visual_prompt_remote": True,
        "render_root": str(tmp_path),
        "render_stem": "d1_d0_n1_8",
        "render_width": 768,
    }
    assert agent.ddar_task_kwargs(
        request_id="d1_n1",
        depth=2,
        candidate_rank=0,
        node_id=9,
        state=None,
    ) == {}


def test_ddar_task_kwargs_use_unique_stems_for_different_nodes(tmp_path: Path) -> None:
    agent = VisualMultiGPUAgent(
        model_pool=None,
        decoding_size=2,
        beam_size=4,
        search_depth=3,
        render_root=tmp_path,
    )

    kwargs_a = agent.ddar_task_kwargs(
        request_id="d0_n1",
        depth=0,
        candidate_rank=0,
        node_id=8,
        state=None,
    )
    kwargs_b = agent.ddar_task_kwargs(
        request_id="d0_n1",
        depth=0,
        candidate_rank=1,
        node_id=9,
        state=None,
    )

    assert kwargs_a["render_stem"] == "d1_d0_n1_8"
    assert kwargs_b["render_stem"] == "d1_d0_n1_9"
    assert kwargs_a["render_stem"] != kwargs_b["render_stem"]
