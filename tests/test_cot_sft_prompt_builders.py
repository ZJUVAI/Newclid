import unittest

from experiments.cot_sft_generation.audits import build_visible_premise_summaries
from experiments.cot_sft_generation.prompt_builders import (
    build_plan_narrative_prompt,
    build_plan_prompt,
    build_plan_retry_feedback,
    build_supervisor_payload,
    build_write_prompt,
    build_writer_retry_feedback,
)


class CotSftPromptBuildersTest(unittest.TestCase):
    def setUp(self):
        self.record = {
            "nl_problem": "observe the diagram",
            "llm_input_renamed": "<problem>g1: para a b c d; g2: cong a b a c ? eqangle a b c d</problem>",
        }
        self.proof_guidance_payload = {
            "immediate_aux_consequences": ["h is the midpoint of bc", "bh equals ch"],
            "aux_bridge_relations": ["ah equals ch"],
            "bridge_relations": ["angle abh equals angle hcd"],
            "goal_finish_relations": ["angle abc equals angle dcb"],
        }
        self.plan = {
            "anchor_points": ["a", "b", "c"],
            "anchor_relation": "triangle abc is the main visible frame",
            "figure_overview": "point d lies on line bc",
            "coordinate_hints": "the near-collinearity of b, c, and d matters",
            "observation_relations": [
                {
                    "relation": "points b, c, and d look nearly collinear",
                    "points": ["b", "c", "d"],
                }
            ],
            "coordinate_relations": ["points b, c, and d look nearly collinear"],
            "visible_relations": ["ab equals ac"],
            "goal_bottleneck": "the target angle still needs a link through d",
            "helper_idea": "a helper should connect d back to the equal sides",
            "construction": "construct point e on line ad",
            "aux_direct_relations": ["a, d, e are collinear"],
            "goal_finish": "angle abc equals angle dce",
            "bridge_steps": [
                {
                    "relation": "de equals ce",
                    "approved_route_relation": "de equals ce",
                    "required_supports": ["a, d, e are collinear"],
                    "min_support_mentions": 1,
                    "focus_points": ["d", "e"],
                    "next_target_purpose": "this supplies the angle comparison needed next.",
                }
            ],
            "coverage_targets": {
                "opening_focus_points": ["d"],
                "bridge_focus_points": ["d", "e"],
                "coordinate_focus_points": ["d"],
                "coordinate_focus_relations": ["points b, c, and d look nearly collinear"],
                "observation_focus_relations": ["points b, c, and d look nearly collinear"],
                "observation_focus_regions": ["around d"],
                "coordinate_reuse_min": 1,
                "opening_sentence_hint": "name d in the opening obstacle",
                "helper_sentence_hint": "name d and e in the helper sentence",
                "coordinate_sentence_hint": "reuse the d-side collinearity early",
            },
        }

    def test_build_visible_premise_summaries_reads_problem_body(self):
        summaries = build_visible_premise_summaries(self.record)

        self.assertTrue(summaries)
        self.assertTrue(any("parallel" in item.lower() for item in summaries))
        self.assertTrue(any("equals" in item.lower() for item in summaries))

    def test_build_supervisor_payload_filters_private_fields(self):
        payload = build_supervisor_payload(
            {"public": 1, "_private": 2},
            "<aux>x00 h : midp h b c</aux>",
            "<proof>proof</proof>",
        )

        self.assertIn('"public": 1', payload)
        self.assertNotIn("_private", payload)
        self.assertIn('"exact_aux": "<aux>x00 h : midp h b c</aux>"', payload)

    def test_build_plan_prompt_includes_route_and_constraint_sections(self):
        prompt = build_plan_prompt(
            self.record,
            "<aux>x00 h : midp h b c</aux>",
            "<proof>midp h b c</proof>",
            point_coords={"a": (0, 0), "b": (2, 0), "c": (1, 2)},
            coordinate_hints="point h would balance the b-c side",
            coordinate_guidance='[{"summary": "points b, c, and d look nearly collinear"}]',
            visible_premise_summaries=["line ab is parallel to line cd"],
            proof_guidance_payload=self.proof_guidance_payload,
        )

        self.assertIn("[Hidden Structured Coordinate Candidates]", prompt)
        self.assertIn("[Approved Ordered Route Checkpoints]", prompt)
        self.assertIn("1. ah equals ch", prompt)
        self.assertIn("Do not use <point> tags", prompt)
        self.assertIn("depends_on list should already name almost all of the segment or ray objects", prompt)
        self.assertIn("depends_on list should reuse concrete items from coordinate_relations", prompt)

    def test_build_plan_narrative_prompt_locks_route_structure(self):
        prompt = build_plan_narrative_prompt(
            self.record,
            "<aux>x00 h : midp h b c</aux>",
            self.plan,
        )

        self.assertIn("[Locked Scripted Plan Skeleton]", prompt)
        self.assertIn("Do not change any bridge route", prompt)
        self.assertIn("bridge_step_unlocks", prompt)
        self.assertIn('"anchor_relation"', prompt)

    def test_build_plan_retry_feedback_adds_multi_point_stage_hint(self):
        feedback = build_plan_retry_feedback(
            "Planner JSON missing keys",
            "<aux>x00 h : coll h a b; x00 k : perp k h a b</aux>",
        )

        self.assertIn("coordinate_hints, bridge_steps, or goal_finish", feedback)
        self.assertIn("first, then, and finally", feedback)

    def test_build_plan_retry_feedback_adds_non_anchor_coordinate_spread_hint(self):
        feedback = build_plan_retry_feedback(
            "coordinate_relations should cover at least 3 visible non-anchor points so the route does not stay trapped on the anchor frame",
            "<aux>x00 k : cyclic b f g k [016] coll c d k [017] ; </aux>",
        )

        self.assertIn("broader visible figure", feedback)
        self.assertIn("same anchor triangle", feedback)
        self.assertIn("do not absorb too many coordinate-rich outer points into anchor_points", feedback)

    def test_build_plan_retry_feedback_mentions_coordinate_relations_as_valid_support_sources(self):
        feedback = build_plan_retry_feedback(
            "bridge_steps[1].depends_on must reuse an earlier visible, coordinate, direct, or bridge relation",
            "<aux>x00 k : cyclic b f g k [016] coll c d k [017] ; </aux>",
        )

        self.assertIn("coordinate_relations, visible_relations, aux_direct_relations", feedback)

    def test_build_plan_retry_feedback_adds_goal_finish_midpoint_shorthand_hint(self):
        feedback = build_plan_retry_feedback(
            "goal_finish contains forbidden pattern: midpoint properties",
            "<aux>x00 k : cyclic b f g k [016] coll c d k [017] ; </aux>",
        )

        self.assertIn("concrete final goal-side relation", feedback)
        self.assertIn("midpoint property", feedback)

    def test_build_plan_retry_feedback_surfaces_missing_segment_objects_for_high_order_bridge(self):
        feedback = build_plan_retry_feedback(
            "bridge_steps[2].relation still introduces unsupported angle/ratio/similar segments before they are grounded by required_supports: ['bd', 'df', 'dk']",
            "<aux>x00 k : cyclic b f g k [016] coll c d k [017] ; </aux>",
        )

        self.assertIn("failed bridge still leaves these segment objects ungrounded", feedback)
        self.assertIn("['bd', 'df', 'dk']", feedback)

    def test_build_plan_retry_feedback_surfaces_named_missing_prerequisite_checkpoint(self):
        feedback = build_plan_retry_feedback(
            "bridge_steps should not skip prerequisite hidden-route checkpoints before higher-order similarity or ratio steps; missing prerequisite: angle bg/df equals angle dg/fk",
            "<aux>x00 k : cyclic b f g k [016] coll c d k [017] ; </aux>",
        )

        self.assertIn("do not skip the earlier approved checkpoint", feedback)
        self.assertIn("angle bg/df equals angle dg/fk", feedback)

    def test_build_write_prompt_includes_writer_handoff_and_compression_target(self):
        prompt = build_write_prompt(
            self.record,
            self.plan,
            "<aux>x00 e : coll e a d</aux>",
            injected_prefix_block="Prefix sentence block.",
            proof_guidance_payload=self.proof_guidance_payload,
        )

        self.assertIn("[Approved Writer Handoff]", prompt)
        self.assertIn("[Compression Target]", prompt)
        self.assertIn("Output only the plain-text body.", prompt)
        self.assertIn("observation-led sentence built from the approved visual checks", prompt)

    def test_build_writer_retry_feedback_surfaces_contract_specific_hints(self):
        feedback = build_writer_retry_feedback(
            "must explicitly realize bridge_steps[0] and must mention at least one approved bridge focus point from its contract",
            self.plan,
            injected_prefix="Prefix sentence block.",
        )

        self.assertIn("bridge_steps[0] stating 'de equals ce'", feedback)
        self.assertIn('["a, d, e are collinear"]', feedback)
        self.assertIn("d and e", feedback)

    def test_build_writer_retry_feedback_surfaces_coordinate_cue_hint(self):
        feedback = build_writer_retry_feedback(
            "Writer body must explicitly reuse at least one approved coordinate relation cue after the prefix",
            self.plan,
            injected_prefix="Prefix sentence block.",
        )

        self.assertIn("approved coordinate relations again", feedback)
        self.assertIn("points b, c, and d look nearly collinear", feedback)
        self.assertIn("preferred early observation cues", feedback)

    def test_build_writer_retry_feedback_surfaces_coordinate_paraphrase_hint_for_overlap(self):
        feedback = build_writer_retry_feedback(
            "Writer body overlaps too much with the injected prefix block; continue from it instead of repeating it",
            self.plan,
            injected_prefix="Prefix sentence block.",
        )

        self.assertIn("apply the same rule to coordinate cues", feedback)
        self.assertIn("midpoint-looking point g on cd", feedback)

    def test_build_writer_retry_feedback_surfaces_early_coordinate_hint(self):
        feedback = build_writer_retry_feedback(
            "Writer early body must connect the bottleneck/helper to at least one approved non-anchor coordinate cue",
            self.plan,
            injected_prefix="Prefix sentence block.",
        )

        self.assertIn("first three body sentences", feedback)
        self.assertIn("preferred early coordinate cues", feedback)
        self.assertIn("preferred non-anchor coordinate region", feedback)

    def test_build_writer_retry_feedback_surfaces_observation_retry_hints(self):
        feedback = build_writer_retry_feedback(
            "Writer early body must continue from at least one approved observation cue instead of restarting from the anchor frame",
            self.plan,
            injected_prefix="Prefix sentence block.",
        )

        self.assertIn("preferred early observation cues", feedback)
        self.assertIn("same local observation region", feedback)


if __name__ == "__main__":
    unittest.main()
