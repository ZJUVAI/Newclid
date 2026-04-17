from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from newclid.agent.runtime.search_runtime import (
    BeamQueue,
    build_problem_proof,
    extract_goals,
    extract_points,
    extract_premises,
)
from newclid.agent.lm import LMAgent
from newclid.agent.vlm import VLMAgent
from newclid.ddar_build_input import build_ddar_input
from newclid.formulations.definition import DefinitionJGEX
from newclid.formulations.problem import ProblemJGEX
import numpy as np
from PIL import Image


class _DummyModelPool:
    def get_worker_stats(self):
        return {}


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


def test_visual_agent_materializes_missing_frontier_proofs():
    defs = _load_defs()
    problem = ProblemJGEX.from_text("a b c = triangle a b c")
    base_proof = build_problem_proof(problem, defs)

    agent = VLMAgent(
        model_pool=_DummyModelPool(),
        decoding_size=1,
        beam_size=4,
        search_depth=2,
    )
    agent.problemJGEX = problem
    seed_problem, seed_proof = agent.seed_state(base_proof, base_proof)
    assert seed_problem == problem
    assert seed_proof is base_proof

    next_queue = BeamQueue(max_size=4)
    next_queue.add(node=(1, 0, (0,), (problem, None)), val=1.0, stable_key=(0,))
    next_queue.add(node=(2, 0, (1,), (problem, base_proof)), val=0.5, stable_key=(1,))

    profiling = {}
    materialized_queue = agent.finalize_next_queue(
        next_queue=next_queue, profiling=profiling
    )
    states = [node[3] for _, node in materialized_queue]

    assert len(states) == 2
    assert all(state[1] is not None for state in states)
    assert profiling["next_frontier_proof_built_count"] == 1


def test_text_agent_v2_uses_root_query_and_accumulates_prefix():
    defs = _load_defs()
    problem = ProblemJGEX.from_text("a b c = triangle a b c")
    next_problem = ProblemJGEX.from_text("a b c = triangle a b c; d = on_line d a b")
    base_proof = build_problem_proof(problem, defs)

    agent = LMAgent(
        model_pool=_DummyModelPool(),
        decoding_size=1,
        beam_size=4,
        search_depth=2,
        search_version="v2",
    )
    agent.problemJGEX = problem
    seed_state = agent.seed_state(base_proof, base_proof)
    root_query = agent.problem_to_dsl(problem, defs)

    request = agent.prepare_request(
        request_id="d0_proot",
        state=seed_state,
        proof=base_proof,
        depth=0,
    )
    assert request["query"] == root_query
    assert request["response_prefix"] == "<aux> x00"

    next_state = agent.make_next_state_from_unsolved_ddar(
        new_problem=next_problem,
        prior_state=seed_state,
        ddar_result={},
        proof=base_proof,
        request=request,
        aux_dsl="<aux> d x00 d : coll a b d [000] ;",
        raw_aux_text=" d x00 d : coll a b d [000] ;",
    )
    next_request = agent.prepare_request(
        request_id="d1_p0",
        state=next_state,
        proof=base_proof,
        depth=1,
    )
    assert next_request["query"] == root_query
    assert next_request["response_prefix"] == "<aux> d x00 d : coll a b d [000] ; x00"


def test_visual_agent_v2_uses_root_query_and_preserves_aux_prefix_during_materialization():
    defs = _load_defs()
    problem = ProblemJGEX.from_text("a b c = triangle a b c")
    next_problem = ProblemJGEX.from_text("a b c = triangle a b c; d = on_line d a b")
    base_proof = build_problem_proof(problem, defs)

    agent = VLMAgent(
        model_pool=_DummyModelPool(),
        decoding_size=1,
        beam_size=4,
        search_depth=2,
        search_version="v2",
    )
    agent.problemJGEX = problem
    seed_state = agent.seed_state(base_proof, base_proof)
    root_query = agent.problem_to_dsl(problem, defs)

    def _fake_draw_clause_figure(proof, problem, save_to, rng, draw_annotations=True):
        del proof, problem, rng, draw_annotations
        Path(save_to).write_text("<svg></svg>", encoding="utf-8")

    def _fake_svg2png(url, write_to, output_width):
        del url, output_width
        Image.new("RGB", (8, 8), color=(255, 255, 255)).save(write_to)

    with patch(
        "newclid.agent.vlm.draw_clause_figure", side_effect=_fake_draw_clause_figure
    ):
        with patch("newclid.agent.vlm.cairosvg.svg2png", side_effect=_fake_svg2png):
            request = agent.prepare_request(
                request_id="d0_proot",
                state=seed_state,
                proof=base_proof,
                depth=0,
            )
    assert request["query"] == root_query
    assert request["response_prefix"] == "<aux> x00"

    next_state = agent.make_next_state_from_unsolved_ddar(
        new_problem=next_problem,
        prior_state=seed_state,
        ddar_result={},
        proof=base_proof,
        request=request,
        aux_dsl="<aux> d x00 d : coll a b d [000] ;",
        raw_aux_text=" d x00 d : coll a b d [000] ;",
    )

    next_queue = BeamQueue(max_size=4)
    next_queue.add(node=(1, 0, (0,), next_state), val=1.0, stable_key=(0,))
    profiling = {}
    materialized_queue = agent.finalize_next_queue(
        next_queue=next_queue, profiling=profiling
    )
    states = [node[3] for _, node in materialized_queue]

    assert len(states) == 1
    assert states[0][1] is not None
    assert states[0][2] == " d x00 d : coll a b d [000] ;"

    with patch(
        "newclid.agent.vlm.draw_clause_figure", side_effect=_fake_draw_clause_figure
    ):
        with patch("newclid.agent.vlm.cairosvg.svg2png", side_effect=_fake_svg2png):
            next_request = agent.prepare_request(
                request_id="d1_p0",
                state=states[0],
                proof=base_proof,
                depth=1,
            )
    assert next_request["query"] == root_query
    assert next_request["response_prefix"] == "<aux> d x00 d : coll a b d [000] ; x00"


def test_visual_agent_skips_invalid_frontier_node_during_materialization():
    defs = _load_defs()
    problem = ProblemJGEX.from_text("a b c = triangle a b c")
    bad_problem = _bad_reused_point_problem()
    base_proof = build_problem_proof(problem, defs)

    agent = VLMAgent(
        model_pool=_DummyModelPool(),
        decoding_size=1,
        beam_size=4,
        search_depth=2,
    )
    agent.problemJGEX = problem
    agent.seed_state(base_proof, base_proof)

    next_queue = BeamQueue(max_size=4)
    next_queue.add(node=(1, 0, (0,), (problem, None)), val=1.0, stable_key=(0,))
    next_queue.add(node=(2, 0, (1,), (bad_problem, None)), val=0.5, stable_key=(1,))

    profiling = {}
    materialized_queue = agent.finalize_next_queue(
        next_queue=next_queue, profiling=profiling
    )
    nodes = [node for _, node in materialized_queue]

    assert len(nodes) == 1
    assert nodes[0][0] == 1
    assert nodes[0][3][1] is not None
    assert profiling["next_frontier_proof_built_count"] == 1
    assert profiling["next_frontier_proof_build_failed_count"] == 1


def test_beam_queue_iterates_in_stable_order_independent_of_add_order():
    queue = BeamQueue(max_size=4)
    queue.add(node=("n3",), val=0.5, stable_key=(3,))
    queue.add(node=("n1",), val=1.0, stable_key=(1,))
    queue.add(node=("n2",), val=1.0, stable_key=(2,))
    queue.add(node=("n0",), val=1.0, stable_key=(0,))

    ordered = [node for _, node in queue]

    assert ordered == [("n0",), ("n1",), ("n2",), ("n3",)]
