from __future__ import annotations

import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from newclid.agent.base import BaseAgent
from newclid.agent.vllm import (
    Qwen3Agent,
    Qwen3VLAgent,
    _score_chat_choices,
    build_chat_messages,
)


class _DummyPool:
    def get_worker_stats(self):
        return []


class VLLMHelperTests(unittest.TestCase):
    def test_build_chat_messages_uses_assistant_continuation(self):
        messages = build_chat_messages(
            query="<problem> demo </problem>",
            response_prefix="<aux> x00",
            new_point_name="a",
        )

        self.assertEqual(messages[2]["role"], "assistant")
        self.assertEqual(
            messages[2]["content"],
            "<think>\n\n</think>\n\n<aux> x00 a",
        )

    def test_score_chat_choices_rebuilds_aux_dsl(self):
        aux_dsl_dict, generated_token_counts = _score_chat_choices(
            choices=[
                {
                    "message": {"content": " = free a</aux>"},
                    "token_ids": [17, 99],
                    "logprobs": {"content": [{"logprob": -0.2}, {"logprob": -1.0}]},
                }
            ],
            request={
                "response_prefix": "<aux> x00",
                "new_point_name": "a",
            },
            stop_token_ids=[99],
        )

        self.assertEqual(aux_dsl_dict, {"<aux> x00 a = free a": -0.2})
        self.assertEqual(generated_token_counts, [1])


class Qwen3AgentTests(unittest.TestCase):
    def test_hybrid_search_falls_back_to_v2_after_v1_failure(self):
        agent = Qwen3Agent(
            model_pool=_DummyPool(),
            decoding_size=2,
            beam_size=4,
            search_depth=1,
            search_version="hybrid",
        )
        calls: list[tuple[str, int]] = []

        def fake_base_run(self, proof, rules, timeout):
            calls.append((self._active_search_mode, timeout))
            if self._active_search_mode == "v1":
                return {"success": False, "error": "Tried but failed."}
            return {"success": True}

        with patch.object(BaseAgent, "run", new=fake_base_run):
            result = agent.run(proof=object(), rules=[], timeout=30)

        self.assertEqual(calls[0][0], "v1")
        self.assertEqual(calls[1][0], "v2")
        self.assertTrue(result["success"])

    def test_prepare_request_v2_reuses_root_problem_with_separator(self):
        agent = Qwen3Agent(
            model_pool=_DummyPool(),
            decoding_size=2,
            beam_size=4,
            search_depth=1,
            search_version="v2",
        )
        agent.problemJGEX = object()
        agent._active_search_mode = "v2"
        agent._root_problem_dsl = "<problem> root </problem>"
        with patch.object(agent, "get_new_point_name", return_value="b"):
            request = agent.prepare_request(
                request_id="d0_proot",
                state=(object(), " x00 a = free a"),
                proof=types.SimpleNamespace(defs={}),
                depth=0,
            )

        self.assertEqual(request["query"], "<problem> root </problem>")
        self.assertEqual(request["response_prefix"], "<aux> x00 a = free a ; x00")


class Qwen3VLAgentTests(unittest.TestCase):
    def test_prepare_request_embeds_png_as_base64_data_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            render_root = Path(tmpdir)
            agent = Qwen3VLAgent(
                model_pool=_DummyPool(),
                decoding_size=2,
                beam_size=4,
                search_depth=1,
                search_version="v1",
                render_root=render_root,
            )
            agent.problemJGEX = object()
            agent._active_search_mode = "v1"
            current_proof = types.SimpleNamespace(defs={}, rng=object())
            problem = object()
            with patch.object(agent, "problem_to_dsl", return_value="<problem> visual </problem>"):
                with patch.object(agent, "get_new_point_name", return_value="c"):
                    with patch("newclid.agent.vllm.draw_clause_figure", return_value=object()):
                        with patch("newclid.agent.vllm.save_figure_as_png") as mock_save:
                            def _write_png(fig, png_path, img_pixels, direct_png):
                                Path(png_path).write_bytes(b"\x89PNG\r\n\x1a\nfake")
                            mock_save.side_effect = _write_png
                            request = agent.prepare_request(
                                request_id="d0_proot",
                                state=(problem, current_proof),
                                proof=current_proof,
                                depth=0,
                            )

        self.assertTrue(request["image_data_url"].startswith("data:image/png;base64,"))
        self.assertEqual(request["messages"][1]["content"][0]["type"], "image_url")
