import unittest

from experiments.cot_sft_generation.generate_cot_sft import (
    build_image_coordinate_candidates,
    build_visible_text_facts,
    compute_thinking_total_budget,
    compute_writer_body_budget,
    validate_plan_response,
    validate_raw_plan_response,
    validate_thinking_response,
    validate_writer_body,
)


class CotSftGenerationBudgetsTest(unittest.TestCase):
    def setUp(self):
        self.record = {
            "llm_input_renamed": (
                "<problem>g1: para a b c d [000]; g2: cong a c b d [001] ? cong a d b c</problem>"
            ),
            "llm_output_renamed": (
                "<aux>x00 h : cong a h d h; cong b h c h</aux> "
                "<proof>cong a h b h; cong d h c h; cong a d b c</proof>"
            ),
            "point_coords_grid": {
                "a": [0, 0],
                "b": [4, 0],
                "c": [0, 2],
                "d": [4, 2],
            },
        }
        self.point_coords = {"a": (0, 0), "b": (4, 0), "c": (0, 2), "d": (4, 2)}
        self.visible_goal = "cong a d b c"
        self.aux_part = "<aux>x00 h : cong a h d h; cong b h c h</aux>"
        self.sanitized_rest = "<proof>cong a h b h; cong d h c h; cong a d b c</proof>"
        self.visible_text_facts = build_visible_text_facts(self.record)
        self.coordinate_candidates = build_image_coordinate_candidates(
            self.point_coords,
            self.visible_text_facts,
            max_items=6,
        )
        self.plan = {
            "selected_text_fact_ids": ["T1", "T2"],
            "selected_coordinate_candidate_ids": ["C1"],
            "image_observations": ["point a looks like the midpoint of bc"],
            "coordinate_derivations": [
                {
                    "candidate_id": "C1",
                    "relation": "point a looks like the midpoint of bc",
                    "points": ["a", "b", "c"],
                    "calc_type": "midpoint",
                    "render_mode": "midpoint",
                    "why_it_matters": "this gives one image-based balance check inside the visible triangle before the helper is added.",
                }
            ],
            "goal_bottleneck": "the target still needs one local equality that can transfer the d-side to the c-side.",
            "helper_idea": "a helper should create two local equalities around one new point before the final transfer.",
            "construction": "construct point h such that ah equals dh and bh equals ch.",
            "aux_direct_relations": ["ah equals dh", "bh equals ch"],
            "bridge_steps": [
                {
                    "relation": "ah equals bh",
                    "support_refs": ["T2", "C1"],
                    "why_it_helps": "this creates the first shared equality in the helper frame.",
                    "proof_alignment": "bridge",
                    "focus_points": ["a", "b", "h"],
                },
                {
                    "relation": "dh equals ch",
                    "support_refs": ["B1", "T2"],
                    "why_it_helps": "this transfers the helper equality to the d-side and c-side.",
                    "proof_alignment": "goal_finish",
                    "focus_points": ["c", "d", "h"],
                },
            ],
            "goal_finish": "ad equals bc",
        }
        self.raw_plan = {
            "text_facts_used": ["line ab is parallel to line cd", "ac equals bd"],
            "image_observations": ["points a, b, d appear collinear"],
            "coordinate_derivations": [
                {
                    "relation": "points a, b, d are collinear",
                    "points": ["a", "b", "d"],
                    "calc_type": "collinear",
                    "render_mode": "area",
                    "why_it_matters": "this gives a visible line that can be reused immediately after the helper is introduced.",
                }
            ],
            "goal_bottleneck": "the target still lacks one helper frame that can transfer the d-side to the c-side.",
            "helper_idea": "the helper should create two local equalities around the new point and then pass them back to the old figure.",
            "construction": "construct point h such that ah equals dh and bh equals ch.",
            "aux_direct_relations": ["ah equals dh", "bh equals ch"],
            "bridge_steps": [
                {
                    "relation": "ah equals bh",
                    "supports": ["text_facts_used[2]", "coordinate_derivations[1]"],
                    "why_it_helps": "this creates the first shared helper equality before the final transfer.",
                    "focus_points": ["a", "b", "h"],
                },
                {
                    "relation": "dh equals ch",
                    "supports": ["bridge_steps[1]", "text_facts_used[2]"],
                    "why_it_helps": "this transfers the helper control to the d-side and c-side before the closing relation.",
                    "focus_points": ["c", "d", "h"],
                },
            ],
            "goal_finish": "ad equals bc",
        }

    def test_compute_writer_and_thinking_budgets_return_positive_limits(self):
        total_budget = compute_thinking_total_budget(self.plan)
        body_budget = compute_writer_body_budget(self.plan)

        self.assertGreaterEqual(total_budget, 2200)
        self.assertGreaterEqual(body_budget, 1500)
        self.assertLessEqual(body_budget, total_budget)

    def test_validate_plan_response_accepts_model_evidence_schema(self):
        ok, message, cleaned = validate_plan_response(
            self.plan,
            self.point_coords,
            visible_goal=self.visible_goal,
            aux_part=self.aux_part,
            coordinate_candidates=self.coordinate_candidates,
            sanitized_rest=self.sanitized_rest,
            visible_premise_summaries=[item["relation"] for item in self.visible_text_facts],
            visible_text_facts=self.visible_text_facts,
        )

        self.assertTrue(ok, message)
        self.assertEqual(cleaned["selected_text_fact_ids"], ["T1", "T2"])
        self.assertTrue(cleaned["coordinate_derivations"][0]["rendered_text"])
        self.assertEqual(cleaned["bridge_steps"][0]["id"], "B1")

    def test_validate_plan_response_rejects_unknown_coordinate_candidate(self):
        broken_plan = dict(self.plan)
        broken_plan["selected_coordinate_candidate_ids"] = ["C99"]

        ok, message, _ = validate_plan_response(
            broken_plan,
            self.point_coords,
            visible_goal=self.visible_goal,
            aux_part=self.aux_part,
            coordinate_candidates=self.coordinate_candidates,
            sanitized_rest=self.sanitized_rest,
            visible_premise_summaries=[item["relation"] for item in self.visible_text_facts],
            visible_text_facts=self.visible_text_facts,
        )

        self.assertFalse(ok)
        self.assertIn("unknown C*", message)

    def test_validate_writer_body_requires_explicit_coordinate_computation(self):
        ok, message, cleaned = validate_plan_response(
            self.plan,
            self.point_coords,
            visible_goal=self.visible_goal,
            aux_part=self.aux_part,
            coordinate_candidates=self.coordinate_candidates,
            sanitized_rest=self.sanitized_rest,
            visible_premise_summaries=[item["relation"] for item in self.visible_text_facts],
            visible_text_facts=self.visible_text_facts,
        )
        self.assertTrue(ok, message)

        body = (
            "The obstacle is to transfer the d-side and c-side into one local helper frame before the final equality closes. "
            "Using a=(0,0), b=(4,0), and c=(0,2), the midpoint of bc is (2.0, 1.0), which differs from a by residual 2.2361 and the collinearity residual is 1.7889, so point a looks like the midpoint of bc. "
            "Construct point h such that ah equals dh and bh equals ch. "
            "Because point a looks like the midpoint of bc and ac equals bd, ah equals bh, and this creates the first shared equality in the helper frame. "
            "Because ah equals bh and ac equals bd, dh equals ch, and this transfers the helper equality to the d-side and c-side. "
            "Therefore ad equals bc."
        )
        writer_ok, writer_message = validate_writer_body(
            body,
            visible_goal=self.visible_goal,
            plan=cleaned,
        )
        self.assertTrue(writer_ok, writer_message)

        bad_body = (
            "The obstacle is to transfer the d-side and c-side into one local helper frame before the final equality closes. "
            "Construct point h such that ah equals dh and bh equals ch. "
            "Because point a looks like the midpoint of bc and ac equals bd, ah equals bh, and this creates the first shared equality in the helper frame. "
            "Because ah equals bh and ac equals bd, dh equals ch, and this transfers the helper equality to the d-side and c-side. "
            "Therefore ad equals bc."
        )
        writer_ok, writer_message = validate_writer_body(
            bad_body,
            visible_goal=self.visible_goal,
            plan=cleaned,
        )
        self.assertFalse(writer_ok)
        self.assertIn("explicit coordinate computation", writer_message)

    def test_validate_plan_response_accepts_coordinate_render_mode_alias(self):
        plan = dict(self.plan)
        plan["coordinate_derivations"] = [dict(self.plan["coordinate_derivations"][0])]
        plan["coordinate_derivations"][0]["render_mode"] = "coordinate"

        ok, message, cleaned = validate_plan_response(
            plan,
            self.point_coords,
            visible_goal=self.visible_goal,
            aux_part=self.aux_part,
            coordinate_candidates=self.coordinate_candidates,
            sanitized_rest=self.sanitized_rest,
            visible_premise_summaries=[item["relation"] for item in self.visible_text_facts],
            visible_text_facts=self.visible_text_facts,
        )

        self.assertTrue(ok, message)
        self.assertEqual(cleaned["coordinate_derivations"][0]["render_mode"], "midpoint")

    def test_validate_thinking_response_allows_inline_visible_coordinates(self):
        thinking = (
            "<thinking>"
            "The obstacle is to transfer the d-side and c-side into one local helper frame before the final equality closes. "
            "Using a=(0,0), b=(4,0), and c=(0,2), the midpoint of bc is (2.0, 1.0), which differs from a by residual 2.2361 and the collinearity residual is 1.7889, so point a looks like the midpoint of bc. "
            "Construct point h such that ah equals dh and bh equals ch. "
            "Because line ab is parallel to line cd, ah equals bh, and this creates the first shared equality in the helper frame. "
            "Because ah equals bh, dh equals ch, and this transfers the helper equality to the d-side and c-side. "
            "Therefore ad equals bc."
            "</thinking>"
        )

        ok, message = validate_thinking_response(
            thinking,
            self.point_coords,
            require_coord_tags=False,
            max_total_len=2600,
        )
        self.assertTrue(ok, message)

        bad_thinking = thinking.replace("b=(4,0)", "b=(5,0)")
        ok, message = validate_thinking_response(
            bad_thinking,
            self.point_coords,
            require_coord_tags=False,
            max_total_len=2600,
        )
        self.assertFalse(ok)
        self.assertIn("Inline coordinate mismatch", message)

    def test_validate_raw_plan_response_accepts_relation_first_schema(self):
        ok, message, cleaned = validate_raw_plan_response(
            self.raw_plan,
            self.point_coords,
            visible_goal=self.visible_goal,
            aux_part=self.aux_part,
        )

        self.assertTrue(ok, message)
        self.assertEqual(cleaned["text_facts_used"][0], "line ab is parallel to line cd")
        self.assertEqual(cleaned["bridge_steps"][0]["support_refs"][0], "text_facts_used[2]")
        self.assertTrue(cleaned["coordinate_derivations"][0]["rendered_text"])

    def test_validate_raw_plan_response_rejects_future_bridge_supports(self):
        broken_plan = dict(self.raw_plan)
        broken_steps = [dict(step) for step in self.raw_plan["bridge_steps"]]
        broken_steps[0]["supports"] = ["bridge_steps[1]"]
        broken_plan["bridge_steps"] = broken_steps

        ok, message, _ = validate_raw_plan_response(
            broken_plan,
            self.point_coords,
            visible_goal=self.visible_goal,
            aux_part=self.aux_part,
        )

        self.assertFalse(ok)
        self.assertIn("earlier bridge_steps", message)


if __name__ == "__main__":
    unittest.main()
