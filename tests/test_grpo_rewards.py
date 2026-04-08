import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from newclid.training.aux_dsl import (
    extract_aux_body,
    extract_first_aux_block,
    extract_first_tagged_aux_block,
    try_dsl_to_constructions,
)
from newclid.training.grpo_rewards import AuxRewardEvaluator


SAMPLE_FL_PROBLEM = (
    "a b c = risos a b c; d = eqdistance d a b c, angle_bisector d b a c; "
    "e f g h = centroid e f g h a d c ? perp b e c f"
)
SAMPLE_COMPLETION = (
    "<aux> x00 i : cong a i b c [012] eqangle a b a i a i a c [013] ; </aux> "
    "<numerical_check> ncoll a c e [014] ; </numerical_check>"
)


class TestGRPORewards(unittest.TestCase):
    def test_aux_dsl_helpers_extract_and_translate(self):
        body = extract_aux_body(SAMPLE_COMPLETION)
        self.assertEqual(body, "i : cong a i b c [012] eqangle a b a i a i a c [013] ;")
        self.assertEqual(
            extract_first_aux_block(SAMPLE_COMPLETION),
            "<aux> i : cong a i b c [012] eqangle a b a i a i a c [013] ; </aux>",
        )
        self.assertEqual(
            extract_first_tagged_aux_block(SAMPLE_COMPLETION),
            "<aux> i : cong a i b c [012] eqangle a b a i a i a c [013] ; </aux>",
        )
        self.assertIsNone(extract_first_tagged_aux_block("<proof> no aux here </proof>"))
        self.assertEqual(
            try_dsl_to_constructions(body),
            "i = eqdistance i a b c, angle_bisector i c a b",
        )

    def test_reward_returns_solved_for_real_sample(self):
        evaluator = AuxRewardEvaluator(build_max_attempts=100)

        result = evaluator.evaluate(SAMPLE_COMPLETION, SAMPLE_FL_PROBLEM)

        self.assertTrue(result.format_ok)
        self.assertTrue(result.build_ok)
        self.assertEqual(result.ddar_status, "solved")
        self.assertEqual(result.reward, 1.0)

    def test_reward_returns_format_invalid(self):
        evaluator = AuxRewardEvaluator()

        result = evaluator.evaluate("<aux> x00 i : </aux>", SAMPLE_FL_PROBLEM)

        self.assertFalse(result.format_ok)
        self.assertFalse(result.build_ok)
        self.assertEqual(result.ddar_status, "format_invalid")
        self.assertEqual(result.reward, -1.0)

    def test_reward_returns_build_invalid(self):
        evaluator = AuxRewardEvaluator(build_max_attempts=100)

        result = evaluator.evaluate("<aux> x00 a : coll b c a [001] ; </aux>", SAMPLE_FL_PROBLEM)

        self.assertTrue(result.format_ok)
        self.assertFalse(result.build_ok)
        self.assertEqual(result.ddar_status, "build_invalid")
        self.assertEqual(result.reward, -0.25)

    def test_reward_returns_unsolved_when_ddar_does_not_prove(self):
        evaluator = AuxRewardEvaluator(build_max_attempts=100)
        with mock.patch.object(evaluator, "_run_ddar", return_value=False):
            result = evaluator.evaluate(SAMPLE_COMPLETION, SAMPLE_FL_PROBLEM)

        self.assertTrue(result.format_ok)
        self.assertTrue(result.build_ok)
        self.assertEqual(result.ddar_status, "unsolved")
        self.assertEqual(result.reward, 0.25)

    def test_reward_returns_engine_error_when_ddar_crashes(self):
        evaluator = AuxRewardEvaluator(build_max_attempts=100)
        with mock.patch.object(evaluator, "_run_ddar", side_effect=RuntimeError("ddar crashed")):
            result = evaluator.evaluate(SAMPLE_COMPLETION, SAMPLE_FL_PROBLEM)

        self.assertTrue(result.format_ok)
        self.assertTrue(result.build_ok)
        self.assertEqual(result.ddar_status, "engine_error")
        self.assertEqual(result.reward, 0.0)

    def test_reward_caches_problem_aux_pairs(self):
        evaluator = AuxRewardEvaluator()
        with mock.patch.object(evaluator, "_evaluate_uncached", wraps=evaluator._evaluate_uncached) as wrapped:
            first = evaluator.evaluate("<aux> broken </aux>", SAMPLE_FL_PROBLEM)
            second = evaluator.evaluate("<aux> broken </aux>", SAMPLE_FL_PROBLEM)

        self.assertEqual(first, second)
        self.assertEqual(wrapped.call_count, 1)

    def test_prepare_grpo_aux_dataset(self):
        script_path = Path("scripts/grpo/prepare_grpo_aux_dataset.py")
        spec = importlib.util.spec_from_file_location("prepare_grpo_aux_dataset", script_path)
        module = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "input.jsonl"
            output_path = tmp_path / "output.jsonl"
            record = {
                "fl_problem": SAMPLE_FL_PROBLEM,
                "llm_input_renamed": "<problem> prompt </problem>",
                "llm_output_renamed": SAMPLE_COMPLETION,
            }
            input_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

            kept, skipped = module.convert_dataset(input_path, output_path)

            rows = [
                json.loads(line)
                for line in output_path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual((kept, skipped), (1, 0))
        self.assertEqual(
            rows,
            [
                {
                    "query": "<problem> prompt </problem>",
                    "fl_problem": SAMPLE_FL_PROBLEM,
                    "response": "<aux> i : cong a i b c [012] eqangle a b a i a i a c [013] ; </aux>",
                }
            ],
        )

    def test_prepare_grpo_aux_dataset_drops_rows_without_aux(self):
        script_path = Path("scripts/grpo/prepare_grpo_aux_dataset.py")
        spec = importlib.util.spec_from_file_location("prepare_grpo_aux_dataset", script_path)
        module = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "input.jsonl"
            output_path = tmp_path / "output.jsonl"
            rows = [
                {
                    "fl_problem": SAMPLE_FL_PROBLEM,
                    "llm_input_renamed": "<problem> prompt </problem>",
                    "llm_output_renamed": SAMPLE_COMPLETION,
                },
                {
                    "fl_problem": SAMPLE_FL_PROBLEM,
                    "llm_input_renamed": "<problem> prompt </problem>",
                    "llm_output_renamed": "<proof> no aux here </proof>",
                },
            ]
            input_path.write_text(
                "\n".join(json.dumps(row) for row in rows) + "\n",
                encoding="utf-8",
            )

            kept, skipped = module.convert_dataset(input_path, output_path)
            written_rows = output_path.read_text(encoding="utf-8").splitlines()

        self.assertEqual((kept, skipped), (1, 1))
        self.assertEqual(len(written_rows), 1)

    def test_plugin_registers_reward(self):
        swift_module = types.ModuleType("swift")
        rewards_module = types.ModuleType("swift.rewards")

        class DummyORM:
            pass

        rewards_module.ORM = DummyORM
        rewards_module.orms = {}

        with mock.patch.dict(
            sys.modules,
            {
                "swift": swift_module,
                "swift.rewards": rewards_module,
            },
            clear=False,
        ):
            script_path = Path("scripts/grpo/plugin.py")
            spec = importlib.util.spec_from_file_location("grpo_plugin", script_path)
            module = importlib.util.module_from_spec(spec)
            self.assertIsNotNone(spec.loader)
            spec.loader.exec_module(module)

        self.assertIn("aux_reward", rewards_module.orms)
        reward_cls = rewards_module.orms["aux_reward"]
        self.assertTrue(issubclass(reward_cls, DummyORM))
        reward = reward_cls()
        self.assertEqual(reward(["<aux> broken </aux>"], fl_problem=SAMPLE_FL_PROBLEM), [-1.0])


if __name__ == "__main__":
    unittest.main()
