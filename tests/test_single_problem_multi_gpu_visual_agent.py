from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from experiments.single_problem_multi_gpu_eval.visual_multi_gpu_agent import VisualMultiGPUAgent


def test_prepare_request_fetches_proof_ref_lazily(monkeypatch, tmp_path: Path) -> None:
    agent = VisualMultiGPUAgent(
        model_pool=None,
        decoding_size=2,
        beam_size=4,
        search_depth=2,
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

    fetched_proof = FakeProof()
    proof_ref = object()

    def fake_ray_get(ref):
        assert ref is proof_ref
        return fetched_proof

    monkeypatch.setattr(
        "experiments.single_problem_multi_gpu_eval.visual_multi_gpu_agent.ray.get",
        fake_ray_get,
    )

    draw_calls: list[object] = []

    def fake_draw_clause_figure(proof, problem, save_to, rng, draw_annotations=True):
        assert proof is fetched_proof
        assert problem.name == "problem"
        draw_calls.append(save_to)
        Path(save_to).write_text("<svg/>", encoding="utf-8")

    monkeypatch.setattr(
        "experiments.single_problem_multi_gpu_eval.visual_multi_gpu_agent.draw_clause_figure",
        fake_draw_clause_figure,
    )

    def fake_svg2png(*, url, write_to, output_width):
        assert output_width == 1024
        Image.new("RGB", (4, 4), color="white").save(write_to)

    monkeypatch.setattr(
        "experiments.single_problem_multi_gpu_eval.visual_multi_gpu_agent.cairosvg.svg2png",
        fake_svg2png,
    )

    monkeypatch.setattr(agent, "problem_to_dsl", lambda problem, defs: f"query:{problem.name}:{defs['dummy']}")
    monkeypatch.setattr(agent, "get_new_point_name", lambda problem: "x")

    problem = SimpleNamespace(
        name="problem",
        constructions=[SimpleNamespace(points=("A", "B"))],
    )

    request = agent.prepare_request(
        request_id="d0_n0",
        state=(problem, proof_ref),
        proof=None,
        depth=0,
    )

    assert request["query"] == "query:problem:defs"
    assert request["img_path"].endswith(".png")
    assert request["_prepare_profile"]["prepare_proof_fetch_work_time_s"] >= 0.0
    assert len(draw_calls) == 1


def test_make_next_state_from_unsolved_ddar_uses_proof_ref() -> None:
    agent = VisualMultiGPUAgent(
        model_pool=None,
        decoding_size=2,
        beam_size=4,
        search_depth=2,
    )
    proof_ref = object()
    problem = SimpleNamespace(name="problem", constructions=[])

    next_state = agent.make_next_state_from_unsolved_ddar(
        new_problem=problem,
        prior_state=None,
        ddar_result={"proof_ref": proof_ref},
        proof=None,
    )

    assert next_state == (problem, proof_ref)
