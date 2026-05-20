import unittest

from experiments.cot_sft_generation.prompt_builders import (
    build_formal_language_guide,
    build_plan_critic_prompt,
    build_plan_prompt,
    build_plan_retry_feedback,
    build_planning_guidance,
    build_raw_plan_retry_feedback,
    build_raw_record_plan_prompt,
    build_supervisor_payload,
    build_write_prompt,
    build_writer_retry_feedback,
)


class CotSftPromptBuildersTest(unittest.TestCase):
    def setUp(self):
        self.record = {
            "nl_problem": "observe the diagram",
            "llm_input_renamed": "<problem>g1: para a b c d; g2: cong a b a c ? eqangle a b c d</problem>",
            "llm_output_renamed": "<aux>x00 h : midp h b c</aux> <proof>proof text</proof>",
            "point_coords_grid": {"a": [0, 0], "b": [4, 0], "c": [0, 2], "d": [4, 2]},
        }
        self.plan = {
            "selected_text_fact_ids": ["T1"],
            "selected_coordinate_candidate_ids": ["C1"],
            "visible_relations": ["line ab is parallel to line cd"],
            "coordinate_relations": ["segments ab and cd look parallel"],
            "coordinate_derivations": [
                {
                    "candidate_id": "C1",
                    "relation": "segments ab and cd look parallel",
                    "points": ["a", "b", "c", "d"],
                    "calc_type": "parallel",
                    "render_mode": "vector",
                    "witness": {"vector_1": [4, 0], "vector_2": [4, 0], "cross": 0},
                    "rendered_text": "a=(0,0), b=(4,0), c=(0,2), d=(4,2); vec(ab)=(4,0) and vec(cd)=(4,0), so the cross product is 0 and segments ab and cd look parallel.",
                    "why_it_matters": "this fixes one direction comparison.",
                }
            ],
            "bridge_steps": [
                {
                    "id": "B1",
                    "relation": "angle abc equals angle cda",
                    "required_supports": ["line ab is parallel to line cd"],
                    "support_refs": ["T1", "C1"],
                    "why_it_helps": "this starts the bridge toward the goal.",
                    "proof_alignment": "bridge",
                    "focus_points": ["a", "b", "c", "d"],
                }
            ],
            "goal_finish": "angle abc equals angle dcb",
        }
        self.visible_text_facts = [
            {"id": "T1", "relation": "line ab is parallel to line cd", "points": ["a", "b", "c", "d"]},
        ]
        self.image_coordinate_candidates = [
            {
                "id": "C1",
                "relation": "segments ab and cd look parallel",
                "relation_type": "parallel",
                "points": ["a", "b", "c", "d"],
                "witness": {"vector_1": [4, 0], "vector_2": [4, 0], "cross": 0},
            }
        ]
        self.hidden_route_hints = {
            "immediate_aux_consequences": ["ah equals dh"],
            "bridge_relations": ["angle abc equals angle cda"],
            "goal_finish_relations": ["angle abc equals angle dcb"],
        }

    def test_build_supervisor_payload_filters_private_fields(self):
        payload = build_supervisor_payload(
            {"public": 1, "_private": 2},
            "<aux>x00 h : midp h b c</aux>",
            "<proof>proof</proof>",
        )

        self.assertIn('"public": 1', payload)
        self.assertNotIn("_private", payload)
        self.assertIn('"exact_aux": "<aux>x00 h : midp h b c</aux>"', payload)

    def test_build_plan_prompt_includes_new_evidence_sections(self):
        prompt = build_plan_prompt(
            self.record,
            "<aux>x00 h : midp h b c</aux>",
            self.visible_text_facts,
            self.image_coordinate_candidates,
            self.hidden_route_hints,
        )

        self.assertIn("[Visible Text Facts]", prompt)
        self.assertIn("[Image / Coordinate Candidates]", prompt)
        self.assertIn("[Hidden Route Hints]", prompt)
        self.assertIn("support_refs may only cite text facts `T*`", prompt)

    def test_build_plan_retry_feedback_mentions_coordinate_derivations(self):
        feedback = build_plan_retry_feedback(
            "coordinate_derivations must contain at least one explicit coordinate computation",
            "<aux>x00 h : coll h a b; x00 k : perp k h a b</aux>",
        )

        self.assertIn("coordinate_derivations entry", feedback)
        self.assertIn("multiple points", feedback)

    def test_build_plan_critic_prompt_requests_boolean_approval(self):
        prompt = build_plan_critic_prompt(
            self.record,
            self.plan,
            self.hidden_route_hints,
        )

        self.assertIn("approved", prompt)
        self.assertIn("issues", prompt)
        self.assertIn("[Candidate Plan]", prompt)

    def test_build_write_prompt_mentions_plain_text_coordinate_computation(self):
        prompt = build_write_prompt(
            self.record,
            self.plan,
            "<aux>x00 h : coll h a d</aux>",
            "- a=(0,0), b=(4,0), c=(0,2), d=(4,2); vec(ab)=(4,0) and vec(cd)=(4,0), so the cross product is 0 and segments ab and cd look parallel.",
        )

        self.assertIn("[Approved Coordinate Derivations]", prompt)
        self.assertIn("You may explicitly write visible-point coordinates", prompt)
        self.assertIn("Output only the plain-text content", prompt)

    def test_build_writer_retry_feedback_mentions_coordinate_computation(self):
        feedback = build_writer_retry_feedback(
            "Writer body must include at least one explicit coordinate computation",
            self.plan,
        )

        self.assertIn("coordinate derivation", feedback)
        self.assertIn("bridge steps", feedback)

    def test_build_raw_record_plan_prompt_uses_raw_sections_and_fixed_guides(self):
        prompt = build_raw_record_plan_prompt(self.record)

        self.assertIn("[Raw Problem Text]", prompt)
        self.assertIn("[Raw Teacher Output]", prompt)
        self.assertIn("[Visible Point Coordinates]", prompt)
        self.assertIn("[Formal Language Guide]", prompt)
        self.assertIn("[Planning Guidance]", prompt)
        self.assertNotIn("[Visible Text Facts]", prompt)
        self.assertNotIn("[Image / Coordinate Candidates]", prompt)

    def test_fixed_guides_cover_formal_translation_and_planning_contracts(self):
        formal_guide = build_formal_language_guide()
        planning_guidance = build_planning_guidance()
        raw_feedback = build_raw_plan_retry_feedback(
            "bridge_steps[1].supports invalid: supports references unknown coordinate_derivations item",
            "<aux>x00 h : midp h b c</aux>",
        )

        self.assertIn("`cong a b c d`", formal_guide)
        self.assertIn("`eqangle a b c d e f g h`", formal_guide)
        self.assertIn("goal_bottleneck -> helper_idea -> construction", planning_guidance)
        self.assertIn("coordinate_derivations", raw_feedback)
        self.assertIn("bridge_steps[i]", raw_feedback)


if __name__ == "__main__":
    unittest.main()
