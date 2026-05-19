import unittest
from unittest.mock import patch

from experiments.cot_sft_generation.generate_cot_sft import (
    build_scripted_plan_skeleton,
    build_hidden_proof_guidance,
    choose_required_supports_for_bridge_step,
    compute_bridge_step_required_support_cap,
    compute_plan_complexity_limits,
    compute_bridge_step_min_support_mentions,
    compute_thinking_total_budget,
    compute_writer_body_budget,
    find_skipped_prerequisite_route_checkpoint,
    find_unsupported_bridge_relation_segments,
    merge_plan_skeleton_and_narrative,
    normalize_model_name_list,
    rebalance_anchor_points_for_coordinate_coverage,
    run_plan_stage,
    should_extend_plan_retry_budget,
    validate_plan_response,
    validate_writer_body,
    validate_thinking_response,
)
from experiments.cot_sft_generation.audits import build_visible_premise_summaries, get_point_coords
from experiments.cot_sft_generation.geometry_text import build_hidden_coordinate_candidates


class CotSftGenerationBudgetsTest(unittest.TestCase):
    def test_normalize_model_name_list_deduplicates_and_trims(self):
        self.assertEqual(
            normalize_model_name_list(" qwen/qwen2.5-vl-72b-instruct , gpt-4.1-mini, , qwen/qwen2.5-vl-72b-instruct "),
            ["qwen/qwen2.5-vl-72b-instruct", "gpt-4.1-mini"],
        )

    def test_compute_plan_complexity_limits_keeps_simple_budget_tight(self):
        limits = compute_plan_complexity_limits(
            point_coords={"a": (0, 0), "b": (2, 0), "c": (1, 2), "d": (3, 2)},
            visible_goal="eqangle a b c d",
            aux_part="<aux>x00 h : coll h a b</aux>",
        )

        self.assertFalse(limits["extended_budget"])
        self.assertEqual(limits["anchor_max"], 4)
        self.assertEqual(limits["coordinate_relations_max"], 3)
        self.assertEqual(limits["bridge_steps_max"], 4)
        self.assertEqual(limits["depends_on_max"], 3)
        self.assertEqual(limits["coordinate_coverage_min"], 3)

    def test_compute_plan_complexity_limits_expands_complex_budget(self):
        limits = compute_plan_complexity_limits(
            point_coords={
                "a": (0, 0),
                "b": (2, 0),
                "c": (1, 2),
                "d": (3, 2),
                "e": (4, 1),
                "f": (5, 2),
            },
            visible_goal="eqratio a b e f",
            aux_part="<aux>x00 h : coll h a b; x00 k : perp k h a b</aux>",
        )

        self.assertTrue(limits["extended_budget"])
        self.assertEqual(limits["anchor_max"], 5)
        self.assertEqual(limits["coordinate_relations_max"], 4)
        self.assertEqual(limits["visible_relations_max"], 5)
        self.assertEqual(limits["aux_direct_relations_max"], 4)
        self.assertEqual(limits["bridge_steps_max"], 5)
        self.assertEqual(limits["depends_on_max"], 4)
        self.assertEqual(limits["coordinate_coverage_min"], 4)

    def test_compute_writer_body_budget_grows_with_complex_plan(self):
        simple_budget = compute_writer_body_budget(
            plan={
                "anchor_points": ["a", "b", "c"],
                "coordinate_relations": ["ab looks equal to ac", "b, c, d look collinear"],
                "aux_direct_relations": ["ah equals dh"],
                "bridge_steps": [{"relation": "dh equals ch"}],
            },
            injected_prefix="prefix",
        )
        complex_budget = compute_writer_body_budget(
            plan={
                "anchor_points": ["a", "b", "c", "d", "e"],
                "coordinate_relations": ["r1", "r2", "r3", "r4"],
                "aux_direct_relations": ["x1", "x2", "x3", "x4"],
                "bridge_steps": [
                    {"relation": "s1"},
                    {"relation": "s2"},
                    {"relation": "s3"},
                    {"relation": "s4"},
                    {"relation": "s5"},
                ],
            },
            injected_prefix="prefix",
        )

        self.assertGreater(complex_budget, simple_budget)
        self.assertGreater(complex_budget, 1500)

    def test_compute_thinking_total_budget_grows_with_complex_plan(self):
        total_budget = compute_thinking_total_budget(
            {
                "anchor_points": ["a", "b", "c", "d", "e"],
                "coordinate_relations": ["r1", "r2", "r3", "r4"],
                "aux_direct_relations": ["x1", "x2", "x3", "x4"],
                "bridge_steps": [
                    {"relation": "s1"},
                    {"relation": "s2"},
                    {"relation": "s3"},
                    {"relation": "s4"},
                    {"relation": "s5"},
                ],
            }
        )

        self.assertGreater(total_budget, 2200)

    def test_validate_thinking_response_allows_extended_budget_and_five_tags(self):
        thinking = (
            "<thinking>"
            "<point>a</point><coord>(0,0)</coord> "
            "<point>b</point><coord>(1,0)</coord> "
            "<point>c</point><coord>(0,1)</coord> "
            "<point>d</point><coord>(1,1)</coord> "
            "<point>e</point><coord>(2,1)</coord> "
            + ("therefore the outer frame keeps the visible bridge active. " * 30)
            + "</thinking>"
        )

        ok, message = validate_thinking_response(
            thinking,
            point_coords={
                "a": (0, 0),
                "b": (1, 0),
                "c": (0, 1),
                "d": (1, 1),
                "e": (2, 1),
            },
            require_coord_tags=True,
            max_total_len=2600,
            max_coord_tags=5,
        )

        self.assertTrue(ok, message)

    def test_validate_writer_body_requires_coordinate_cue_reuse(self):
        plan = {
            "coordinate_relations": [
                "xy equals zw",
                "uv equals rs",
            ],
            "anchor_points": ["a", "b", "c", "d"],
            "coverage_targets": {
                "opening_focus_points": ["e", "f", "j"],
                "bridge_focus_points": ["f", "g"],
                "goal_points": ["a", "e", "f", "c", "j"],
                "non_anchor_points": ["f", "g", "j"],
                "coordinate_focus_points": ["g"],
                "coordinate_focus_relations": ["uv equals rs"],
                "coordinate_reuse_min": 1,
                "early_coordinate_reuse_min": 1,
            },
            "bridge_steps": [{"relation": "c, g, k are collinear", "required_supports": [], "focus_points": ["f", "g"]}],
            "goal_finish": "ratio ae to af equals ratio ce to cj",
        }
        body = (
            "The target ratio around e, f, and j still needs a helper through the outer frame. "
            "A helper on the right side can reconnect the missing route around f and g. "
            "Because c, d, k are collinear, c, g, k are collinear, and this prepares the final ratio. "
            "Therefore ratio ae to af equals ratio ce to cj."
        )

        ok, message = validate_writer_body(
            body,
            visible_goal="eqratio a e a f c e c j",
            injected_prefix="prefix",
            plan=plan,
        )

        self.assertFalse(ok)
        self.assertIn("coordinate relation cue", message)

    def test_validate_writer_body_requires_observation_cue_reuse(self):
        plan = {
            "observation_relations": [
                {
                    "relation": "points d, e, and f look nearly collinear",
                    "points": ["d", "e", "f"],
                }
            ],
            "coordinate_relations": [],
            "anchor_points": ["a", "b", "c"],
            "coverage_targets": {
                "opening_focus_points": ["d", "e"],
                "bridge_focus_points": ["f", "g"],
                "goal_points": ["d", "e", "f", "g"],
                "non_anchor_points": ["d", "e", "f", "g"],
                "observation_focus_relations": ["points d, e, and f look nearly collinear"],
                "observation_focus_regions": ["around d, e, and f"],
            },
            "bridge_steps": [{"relation": "fg equals dg", "required_supports": [], "focus_points": ["f", "g"]}],
            "goal_finish": "de equals fg",
        }
        body = (
            "The d-side obstacle still has to be tied back to e and f before the target equality can close. "
            "A helper around f and g is needed to reconnect the outer structure. "
            "Construct point k on the outer side. "
            "Because fg equals dg, this prepares the final equality. "
            "Therefore de equals fg."
        )

        ok, message = validate_writer_body(
            body,
            visible_goal="cong d e f g",
            injected_prefix="prefix",
            plan=plan,
        )

        self.assertFalse(ok)
        self.assertIn("observation cue", message)

    def test_validate_writer_body_requires_early_observation_cue_reuse(self):
        plan = {
            "observation_relations": [
                {
                    "relation": "points d, e, and f look nearly collinear",
                    "points": ["d", "e", "f"],
                }
            ],
            "coordinate_relations": [],
            "anchor_points": ["a", "b", "c"],
            "coverage_targets": {
                "opening_focus_points": ["d", "e"],
                "bridge_focus_points": ["f", "g"],
                "goal_points": ["d", "e", "f", "g"],
                "non_anchor_points": ["d", "e", "f", "g"],
                "observation_focus_relations": ["points d, e, and f look nearly collinear"],
                "observation_focus_regions": ["around d, e, and f"],
            },
            "bridge_steps": [{"relation": "fg equals dg", "required_supports": [], "focus_points": ["f", "g"]}],
            "goal_finish": "de equals fg",
        }
        body = (
            "The d-side obstacle still has to be tied back to e and f before the target equality can close. "
            "A helper around f and g is needed to reconnect the outer structure. "
            "Construct point k on the outer side. "
            "Because points d, e, and f stay nearly collinear, fg equals dg, and this prepares the final equality. "
            "Therefore de equals fg."
        )

        ok, message = validate_writer_body(
            body,
            visible_goal="cong d e f g",
            injected_prefix="prefix",
            plan=plan,
        )

        self.assertFalse(ok)
        self.assertIn("approved observation cue", message)
        self.assertIn("early body", message)

    def test_validate_writer_body_requires_multiple_coordinate_cues_when_requested(self):
        plan = {
            "coordinate_relations": [
                "points d, e, and f look nearly collinear",
                "line gk looks parallel to line bc",
            ],
            "anchor_points": ["a", "b", "c"],
            "coverage_targets": {
                "opening_focus_points": ["d", "e"],
                "bridge_focus_points": ["f", "g"],
                "goal_points": ["d", "e", "f", "g"],
                "non_anchor_points": ["d", "e", "f", "g"],
                "coordinate_focus_points": ["d", "e", "f", "g"],
                "coordinate_focus_relations": [
                    "points d, e, and f look nearly collinear",
                    "line gk looks parallel to line bc",
                ],
                "coordinate_reuse_min": 2,
                "early_coordinate_reuse_min": 1,
            },
            "bridge_steps": [{"relation": "fg equals dg", "required_supports": [], "focus_points": ["f", "g"]}],
            "goal_finish": "de equals fg",
        }
        body = (
            "The d-side obstacle still has to be tied back to e and f before the target equality can close. "
            "A helper around f and g can use the nearly collinear d, e, and f alignment to start that route. "
            "Construct point k on the outer side. "
            "Because fg equals dg, this prepares the final equality. "
            "Therefore de equals fg."
        )

        ok, message = validate_writer_body(
            body,
            visible_goal="cong d e f g",
            injected_prefix="prefix",
            plan=plan,
        )

        self.assertFalse(ok)
        self.assertIn("at least 2 approved coordinate relation cues", message)

    def test_validate_writer_body_requires_early_non_anchor_coordinate_cue(self):
        plan = {
            "coordinate_relations": [
                "points d, e, and f look nearly collinear",
            ],
            "anchor_points": ["a", "b", "c"],
            "coverage_targets": {
                "opening_focus_points": ["d", "e"],
                "bridge_focus_points": ["f", "g"],
                "goal_points": ["d", "e", "f", "g"],
                "non_anchor_points": ["d", "e", "f", "g"],
                "coordinate_focus_points": ["d", "e", "f"],
                "coordinate_focus_relations": [
                    "points d, e, and f look nearly collinear",
                ],
                "coordinate_reuse_min": 1,
                "early_coordinate_reuse_min": 1,
            },
            "bridge_steps": [{"relation": "fg equals dg", "required_supports": [], "focus_points": ["f", "g"]}],
            "goal_finish": "de equals fg",
        }
        body = (
            "The d-side obstacle still has to be tied back to e and f before the target equality can close. "
            "A helper around f and g is needed to reconnect the outer structure. "
            "Construct point k on the outer side. "
            "Because points d, e, and f stay nearly collinear, fg equals dg, and this prepares the final equality. "
            "Therefore de equals fg."
        )

        ok, message = validate_writer_body(
            body,
            visible_goal="cong d e f g",
            injected_prefix="prefix",
            plan=plan,
        )

        self.assertFalse(ok)
        self.assertIn("early body", message)

    def test_validate_writer_body_reports_exact_support_count_when_two_supports_are_required(self):
        plan = {
            "anchor_points": ["a", "b", "c"],
            "coordinate_relations": ["points d, e, and f look nearly collinear"],
            "coverage_targets": {
                "opening_focus_points": ["d"],
                "bridge_focus_points": ["g"],
                "goal_points": ["d", "g", "k"],
                "non_anchor_points": ["d", "g", "k"],
                "coordinate_focus_points": ["d", "e", "f"],
                "coordinate_focus_relations": ["points d, e, and f look nearly collinear"],
                "coordinate_reuse_min": 1,
                "early_coordinate_reuse_min": 1,
            },
            "bridge_steps": [
                {
                    "relation": "c, g, k are collinear",
                    "required_supports": [
                        "c, d, g are collinear",
                        "c, d, k are collinear",
                    ],
                    "min_support_mentions": 2,
                    "focus_points": ["g", "k"],
                }
            ],
            "goal_finish": "dg equals ck",
        }
        body = (
            "The d-side obstacle still has to be tied to g and k before the target equality can close. "
            "Because points d, e, and f stay nearly collinear, a helper around g is needed on that outer line. "
            "Construct point k on the outer side. "
            "Because c, d, k are collinear, c, g, k are collinear, and this prepares the final equality. "
            "Therefore dg equals ck."
        )

        ok, message = validate_writer_body(
            body,
            visible_goal="cong d g c k",
            injected_prefix="prefix",
            plan=plan,
        )

        self.assertFalse(ok)
        self.assertIn("at least 2 approved supporting relations", message)

    def test_choose_required_supports_prefers_collinear_dependencies_for_collinear_bridge(self):
        step = {
            "relation": "c, g, k are collinear",
            "depends_on": [
                "c, d, k are collinear",
                "b, f, g, k are concyclic",
                "c, d, g are collinear",
            ],
            "next_target_relation": "angle bd/bg equals angle fk/dk",
        }

        required_supports = choose_required_supports_for_bridge_step(
            step,
            ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k"],
            max_supports=2,
        )

        self.assertEqual(
            required_supports,
            ["c, d, g are collinear", "c, d, k are collinear"],
        )

    def test_choose_required_supports_uses_single_exact_coordinate_match_for_low_level_bridge(self):
        step = {
            "relation": "b, d, f are collinear",
            "depends_on": [
                "points b, d, and f look nearly collinear",
                "b, f, g, k are concyclic",
                "c, d, k are collinear",
                "ab is parallel to cd",
            ],
            "next_target_relation": "angle bd/bg equals angle fk/dk",
        }

        required_supports = choose_required_supports_for_bridge_step(
            step,
            ["a", "b", "c", "d", "f", "g", "k"],
            max_supports=2,
        )

        self.assertEqual(
            required_supports,
            ["points b, d, and f look nearly collinear"],
        )

    def test_validate_plan_response_promotes_exact_coordinate_support_for_low_level_bridge_step(self):
        plan = {
            "anchor_points": ["a", "b", "c", "e"],
            "anchor_relation": "triangle abc is the visible frame and point e sits on the lower side of the wider figure.",
            "figure_overview": (
                "points d, f, g, and j sit outside the anchor frame, so the target ratio must be "
                "transferred through the outer right side."
            ),
            "coordinate_relations": [
                "point f looks like the midpoint of ac",
                "point g looks like the midpoint of cd",
                "points b, d, and f look nearly collinear",
            ],
            "visible_relations": [
                "ab is parallel to cd",
                "ad is parallel to bc",
                "ab equals bc",
            ],
            "coordinate_hints": (
                "point f looks like the midpoint of ac, point g looks like the midpoint of cd, "
                "and points b, d, and f look nearly collinear."
            ),
            "goal_bottleneck": (
                "the target ratio still needs a route from the outer d-side configuration back to ae, af, ce, and cj."
            ),
            "helper_idea": (
                "a helper through k should connect the outer line through d and g to the cyclic relation "
                "around b, f, and g."
            ),
            "construction": "construct point k such that b, f, g, k are concyclic and c, d, k are collinear.",
            "aux_direct_relations": [
                "b, f, g, k are concyclic",
                "c, d, k are collinear",
            ],
            "bridge_steps": [
                {
                    "relation": "c, g, k are collinear",
                    "depends_on": [
                        "b, f, g, k are concyclic",
                        "c, d, k are collinear",
                        "c, d, g are collinear",
                    ],
                    "why_it_helps": "this aligns k with the outer d-g line before the angle transfer.",
                },
                {
                    "relation": "b, d, f are collinear",
                    "depends_on": [
                        "b, f, g, k are concyclic",
                        "c, d, k are collinear",
                        "ab is parallel to cd",
                        "f is the midpoint of ac",
                    ],
                    "why_it_helps": "this fixes the line needed for the upcoming angle comparison.",
                },
                {
                    "relation": "angle bd/bg equals angle fk/dk",
                    "depends_on": [
                        "b, f, g, k are concyclic",
                        "b, d, f are collinear",
                        "c, d, k are collinear",
                    ],
                    "why_it_helps": "this supplies the angle alignment needed before the final ratio route.",
                },
            ],
            "goal_finish": "ratio ae to af equals ratio ce to cj",
        }
        point_coords = {
            "a": (0, -2),
            "b": (-1, -3),
            "c": (2, 0),
            "d": (4, 2),
            "e": (0, 3),
            "f": (1, -1),
            "g": (3, 1),
            "j": (5, -1),
        }
        coordinate_candidates = [
            {"relation_type": "midpoint", "points": ["f", "a", "c"], "summary": "point f looks like the midpoint of ac"},
            {"relation_type": "midpoint", "points": ["g", "c", "d"], "summary": "point g looks like the midpoint of cd"},
            {"relation_type": "collinear", "points": ["b", "d", "f"], "summary": "points b, d, and f look nearly collinear"},
        ]
        aux_part = "<aux> x00 k : cyclic b f g k [016] coll c d k [017] ; </aux>"
        sanitized_rest = "<proof>coll c g k; coll b d f; eqangle b d b g f k d k; eqratio a e a f c e c j;</proof>"

        ok, message, cleaned = validate_plan_response(
            plan,
            point_coords,
            visible_goal="eqratio a e a f c e c j",
            aux_part=aux_part,
            coordinate_candidates=coordinate_candidates,
            sanitized_rest=sanitized_rest,
        )

        self.assertTrue(ok, message)
        self.assertEqual(
            cleaned["bridge_steps"][1]["depends_on"][0],
            "points b, d, and f look nearly collinear",
        )
        self.assertEqual(
            cleaned["bridge_steps"][1]["required_supports"],
            ["points b, d, and f look nearly collinear"],
        )

    def test_build_scripted_plan_skeleton_produces_valid_ratio_plan(self):
        record = {
            "llm_input_renamed": (
                "<problem> a : ; b : ; c : perp a b b c [000] cong a b b c [001] ; "
                "d : para a b c d [002] para a d b c [003] ; "
                "e : coll a d e [004] cong a e d e [005] ; "
                "f : coll a c f [006] cong a f c f [007] ; "
                "g : coll c d g [008] cong c g d g [009] ; "
                "j : coll b d j [015] ? eqratio a e a f c e c j </problem>"
            ),
            "llm_output_renamed": (
                "<aux> x00 k : cyclic b f g k [016] coll c d k [017] ; </aux> "
                "<proof>coll c g k; eqangle b f b g f k g k; coll b d f; "
                "eqangle b d b g f k d k; eqangle b g d f d g f k; "
                "simtrir b d g k d f; eqratio b f c f d g d e; "
                "simtrir b c f g e d; eqratio a e a f c e c j;</proof>"
            ),
            "point_coords_grid": {
                "a": [191, 71],
                "b": [98, 12],
                "c": [38, 105],
                "d": [132, 165],
                "e": [162, 118],
                "f": [115, 88],
                "g": [85, 135],
                "j": [148, 241],
            },
        }
        point_coords = get_point_coords(record)
        visible_goal = "eqratio a e a f c e c j"
        aux_part = "<aux> x00 k : cyclic b f g k [016] coll c d k [017] ; </aux>"
        sanitized_rest = (
            "<proof>coll c g k; eqangle b f b g f k g k; coll b d f; "
            "eqangle b d b g f k d k; eqangle b g d f d g f k; "
            "simtrir b d g k d f; eqratio b f c f d g d e; "
            "simtrir b c f g e d; eqratio a e a f c e c j;</proof>"
        )
        coordinate_candidates = build_hidden_coordinate_candidates(
            point_coords,
            max_items=64,
            relax_type_limits=True,
        )
        visible_premise_summaries = build_visible_premise_summaries(record)

        skeleton = build_scripted_plan_skeleton(
            record,
            aux_part,
            sanitized_rest,
            point_coords,
            coordinate_candidates,
            visible_premise_summaries,
            visible_goal,
        )
        ok, message, cleaned = validate_plan_response(
            skeleton,
            point_coords,
            visible_goal=visible_goal,
            aux_part=aux_part,
            coordinate_candidates=coordinate_candidates,
            sanitized_rest=sanitized_rest,
            visible_premise_summaries=visible_premise_summaries,
        )

        self.assertTrue(ok, message)
        self.assertTrue(cleaned["bridge_steps"])
        self.assertIn("k", cleaned["bridge_steps"][0]["relation"].lower())
        self.assertTrue(cleaned["observation_relations"])
        self.assertEqual(
            cleaned["coordinate_relations"],
            [item["relation"] for item in cleaned["observation_relations"]],
        )

    def test_merge_plan_skeleton_and_narrative_keeps_locked_relations(self):
        plan_skeleton = {
            "anchor_points": ["a", "b", "c"],
            "anchor_relation": "old anchor relation",
            "figure_overview": "old figure overview",
            "coordinate_hints": "old coordinate hints",
            "goal_bottleneck": "old bottleneck",
            "helper_idea": "old helper",
            "construction": "old construction",
            "bridge_steps": [
                {"relation": "c, g, k are collinear", "why_it_helps": "old unlock"},
                {"relation": "angle bf/bg equals angle fk/gk", "why_it_helps": "old unlock 2"},
            ],
        }
        narrative = {
            "anchor_relation": "new anchor relation",
            "bridge_step_unlocks": ["new unlock", "new unlock 2"],
            "bridge_steps": [{"relation": "tampered relation"}],
        }

        merged = merge_plan_skeleton_and_narrative(plan_skeleton, narrative)

        self.assertEqual(merged["anchor_relation"], "new anchor relation")
        self.assertEqual(merged["bridge_steps"][0]["relation"], "c, g, k are collinear")
        self.assertEqual(merged["bridge_steps"][0]["why_it_helps"], "new unlock")

    def test_validate_plan_response_derives_observation_relations_from_coordinate_relations(self):
        plan = {
            "anchor_points": ["a", "b", "c"],
            "anchor_relation": "points a, b, and c form the main visible frame.",
            "figure_overview": "beyond the anchor points, the broader figure also involves d, f, and g.",
            "coordinate_relations": [
                "point f looks like the midpoint of ac",
                "points b, d, and f look nearly collinear",
                "point g looks like the midpoint of cd",
            ],
            "visible_relations": [
                "ab equals bc",
                "ab is perpendicular to bc",
            ],
            "coordinate_hints": (
                "the clearest visual cues are that point f looks like the midpoint of ac "
                "and that points b, d, and f look nearly collinear."
            ),
            "goal_bottleneck": "the target ratio still lacks a concrete bridge.",
            "helper_idea": "a helper is needed that places the helper on a useful circle so the missing ratio relation can be connected.",
            "construction": "construct point k such that b, f, g, and k are concyclic and c, d, and k are collinear.",
            "aux_direct_relations": [
                "b, f, g, k are concyclic",
                "c, d, k are collinear",
            ],
            "bridge_steps": [
                {
                    "relation": "c, g, k are collinear",
                    "depends_on": ["c, d, g are collinear", "c, d, k are collinear"],
                    "why_it_helps": "this is required to prove angle bf/bg equals angle fk/gk next.",
                },
                {
                    "relation": "angle bf/bg equals angle fk/gk",
                    "depends_on": ["b, f, g, k are concyclic", "c, g, k are collinear"],
                    "why_it_helps": "this is required to prove ratio ae to af equals ratio ce to cj next.",
                },
            ],
            "goal_finish": "ratio ae to af equals ratio ce to cj",
        }
        point_coords = {
            "a": (191, 71),
            "b": (98, 12),
            "c": (38, 105),
            "d": (132, 165),
            "e": (162, 118),
            "f": (115, 88),
            "g": (85, 135),
            "j": (148, 241),
        }
        coordinate_candidates = [
            {"relation_type": "midpoint", "points": ["f", "a", "c"], "summary": "point f looks like the midpoint of ac"},
            {"relation_type": "collinear", "points": ["b", "d", "f"], "summary": "points b, d, and f look nearly collinear"},
            {"relation_type": "midpoint", "points": ["g", "c", "d"], "summary": "point g looks like the midpoint of cd"},
        ]
        aux_part = "<aux> x00 k : cyclic b f g k [016] coll c d k [017] ; </aux>"
        sanitized_rest = "<proof>coll c g k; eqangle b f b g f k g k; eqratio a e a f c e c j;</proof>"

        ok, message, cleaned = validate_plan_response(
            plan,
            point_coords,
            visible_goal="eqratio a e a f c e c j",
            aux_part=aux_part,
            coordinate_candidates=coordinate_candidates,
            sanitized_rest=sanitized_rest,
        )

        self.assertTrue(ok, message)
        self.assertEqual(len(cleaned["observation_relations"]), 3)
        self.assertEqual(cleaned["observation_relations"][0]["relation"], "point f looks like the midpoint of ac")

    def test_validate_writer_body_rejects_bridge_sentence_that_uses_conclusion_as_its_own_support(self):
        plan = {
            "anchor_points": ["a", "b", "c", "e"],
            "coordinate_relations": [
                "point f looks like the midpoint of ac",
                "point g looks like the midpoint of cd",
                "points b, d, and f look nearly collinear",
            ],
            "coverage_targets": {
                "opening_focus_points": ["f", "j"],
                "bridge_focus_points": ["f", "j", "d", "g"],
                "goal_points": ["a", "e", "f", "c", "j"],
                "non_anchor_points": ["f", "j", "d", "g"],
                "coordinate_focus_points": ["f", "d", "g"],
                "coordinate_focus_relations": [
                    "point f looks like the midpoint of ac",
                    "point g looks like the midpoint of cd",
                ],
                "coordinate_reuse_min": 1,
                "early_coordinate_reuse_min": 1,
            },
            "bridge_steps": [
                {
                    "relation": "c, g, k are collinear",
                    "required_supports": [
                        "c, d, g are collinear",
                        "c, d, k are collinear",
                    ],
                    "min_support_mentions": 2,
                    "focus_points": ["f", "g", "d"],
                },
                {
                    "relation": "b, d, f are collinear",
                    "required_supports": ["points b, d, and f look nearly collinear"],
                    "min_support_mentions": 1,
                    "focus_points": ["f", "d", "g"],
                },
                {
                    "relation": "angle bd/bg equals angle fk/dk",
                    "required_supports": [
                        "b, f, g, k are concyclic",
                        "b, d, f are collinear",
                    ],
                    "min_support_mentions": 1,
                    "focus_points": ["f", "j", "d", "g"],
                },
            ],
            "goal_finish": "ratio ae to af equals ratio ce to cj",
        }
        body = (
            "The remaining obstacle is to connect ae, af, ce, and cj, so points f and j must be tied back to the outer d-side configuration before the target ratio can close. "
            "Since point f looks like the midpoint of ac and point g looks like the midpoint of cd, a helper through k can track the outer line through d and g without losing the f-side comparison. "
            "Because c, d, g are collinear and c, d, k are collinear, c, g, k are collinear, and this places k on the outer d-g line for the next step. "
            "Because b, f, g, k are concyclic and c, d, k are collinear, b, d, f are collinear, and this fixes the line needed for the angle transfer. "
            "Because b, f, g, k are concyclic and b, d, f are collinear, angle bd/bg equals angle fk/dk, and this supplies the last angle comparison before the target ratio. "
            "Therefore, ratio ae to af equals ratio ce to cj."
        )

        ok, message = validate_writer_body(
            body,
            visible_goal="eqratio a e a f c e c j",
            injected_prefix="prefix",
            plan=plan,
        )

        self.assertFalse(ok)
        self.assertIn("bridge_steps[1]", message)

    def test_compute_bridge_step_min_support_mentions_requires_two_for_collinear_and_ratio_steps(self):
        collinear_step = {
            "relation": "c, g, k are collinear",
            "required_supports": [
                "c, d, g are collinear",
                "c, d, k are collinear",
            ],
        }
        ratio_step = {
            "relation": "ratio bc to cf equals ratio eg to de",
            "required_supports": [
                "angle bd/bg equals angle fk/dk",
                "triangles bdg and kdf are similar",
            ],
        }
        equality_step = {
            "relation": "de equals ce",
            "required_supports": ["a, d, e are collinear"],
        }

        self.assertEqual(compute_bridge_step_min_support_mentions(collinear_step), 2)
        self.assertEqual(compute_bridge_step_min_support_mentions(ratio_step), 2)
        self.assertEqual(compute_bridge_step_min_support_mentions(equality_step), 1)

    def test_compute_bridge_step_required_support_cap_allows_three_for_high_order_steps(self):
        self.assertEqual(
            compute_bridge_step_required_support_cap({"relation": "angle bd/bg equals angle fk/dk"}),
            3,
        )
        self.assertEqual(
            compute_bridge_step_required_support_cap({"relation": "triangles bdg and kdf are similar"}),
            3,
        )
        self.assertEqual(
            compute_bridge_step_required_support_cap({"relation": "c, g, k are collinear"}),
            2,
        )

    def test_old_sample0_like_bridge_sentence_fails_under_stricter_support_matching(self):
        plan = {
            "anchor_points": ["a", "b", "c", "d"],
            "coordinate_relations": [
                "point f looks like the midpoint of ac",
                "point g looks like the midpoint of cd",
                "point e looks like the midpoint of ad",
            ],
            "coverage_targets": {
                "opening_focus_points": ["e", "f", "j"],
                "bridge_focus_points": ["e", "f", "j", "g"],
                "goal_points": ["a", "e", "f", "c", "j"],
                "non_anchor_points": ["e", "f", "j", "g"],
                "coordinate_focus_points": ["e", "f", "g"],
                "coordinate_focus_relations": [
                    "point f looks like the midpoint of ac",
                    "point g looks like the midpoint of cd",
                ],
                "coordinate_reuse_min": 1,
                "early_coordinate_reuse_min": 1,
            },
            "bridge_steps": [
                {
                    "relation": "c, g, k are collinear",
                    "required_supports": [
                        "c, d, g are collinear",
                        "c, d, k are collinear",
                    ],
                    "min_support_mentions": 2,
                    "focus_points": ["g", "d", "c"],
                }
            ],
            "goal_finish": "ratio ae to af equals ratio ce to cj",
        }
        body = (
            "The target ratio involving ae, af, ce, cj lacks a direct link through the configuration around e, f, and j. "
            "Since point f looks like the midpoint of ac, a helper is needed to place a new point on an existing line and a useful circle to connect the segments near e, f, j, and g. "
            "Construct point k on line cd such that b, f, g, k are concyclic. "
            "Because c, d, k are collinear and b, f, g, k are concyclic, c, g, k are collinear, and this fixes the angle alignment needed in the next step. "
            "Therefore ratio ae to af equals ratio ce to cj."
        )

        ok, message = validate_writer_body(
            body,
            visible_goal="eqratio a e a f c e c j",
            injected_prefix="prefix",
            plan=plan,
        )

        self.assertFalse(ok)
        self.assertIn("at least 2 approved supporting relations", message)

    def test_find_skipped_prerequisite_route_checkpoint_flags_similarity_jump(self):
        hidden_route_relations = [
            "c, g, k are collinear",
            "angle bf/bg equals angle fk/gk",
            "angle af/ag equals angle fk/gi",
            "angle bd/bg equals angle fk/dk",
            "angle bg/df equals angle dg/fk",
            "triangles bdg and kdf are similar",
        ]
        step = {
            "relation": "triangles bdg and kdf are similar",
            "approved_route_relation": "triangles bdg and kdf are similar",
            "approved_route_position": 6,
            "depends_on": [
                "angle bf/bg equals angle fk/gk",
                "b, f, g, k are concyclic",
            ],
        }

        skipped = find_skipped_prerequisite_route_checkpoint(
            step,
            previous_route_position=2,
            hidden_route_relations=hidden_route_relations,
            point_names=["a", "b", "c", "d", "e", "f", "g", "i", "k"],
            previous_bridge_relation="angle bf/bg equals angle fk/gk",
        )

        self.assertEqual(skipped, "angle bg/df equals angle dg/fk")

    def test_find_skipped_prerequisite_route_checkpoint_ignores_well_supported_similarity_step(self):
        hidden_route_relations = [
            "c, g, k are collinear",
            "angle bf/bg equals angle fk/gk",
            "angle bd/bg equals angle fk/dk",
            "triangles bdg and kdf are similar",
        ]
        step = {
            "relation": "triangles bdg and kdf are similar",
            "approved_route_relation": "triangles bdg and kdf are similar",
            "approved_route_position": 4,
            "depends_on": [
                "angle bd/bg equals angle fk/dk",
                "b, f, g, k are concyclic",
            ],
        }

        skipped = find_skipped_prerequisite_route_checkpoint(
            step,
            previous_route_position=2,
            hidden_route_relations=hidden_route_relations,
            point_names=["a", "b", "c", "d", "e", "f", "g", "k"],
            previous_bridge_relation="angle bf/bg equals angle fk/gk",
        )

        self.assertEqual(skipped, "")

    def test_find_unsupported_bridge_relation_segments_flags_angle_jump_with_new_segments(self):
        step = {
            "relation": "angle bg/df equals angle dg/fk",
            "required_supports": [
                "angle bf/bg equals angle fk/gk",
                "b, f, g, k are concyclic",
            ],
        }

        unsupported = find_unsupported_bridge_relation_segments(
            step,
            step["required_supports"],
        )

        self.assertEqual(unsupported, ["df", "dg"])

    def test_find_unsupported_bridge_relation_segments_accepts_well_grounded_similarity(self):
        step = {
            "relation": "triangles bdg and kdf are similar",
            "required_supports": [
                "angle bd/bg equals angle fk/dk",
                "angle bg/df equals angle dg/fk",
            ],
        }

        unsupported = find_unsupported_bridge_relation_segments(
            step,
            step["required_supports"],
        )

        self.assertEqual(unsupported, [])

    def test_find_unsupported_bridge_relation_segments_accepts_angle_step_once_three_supports_ground_objects(self):
        step = {
            "relation": "angle bd/bg equals angle fk/dk",
            "required_supports": [
                "b, d, f are collinear",
                "b, f, g, k are concyclic",
                "c, d, k are collinear",
            ],
        }

        unsupported = find_unsupported_bridge_relation_segments(
            step,
            step["required_supports"],
        )

        self.assertEqual(unsupported, [])

    def test_build_hidden_proof_guidance_backfills_segment_grounding_checkpoint(self):
        sanitized_rest = (
            "<proof>"
            "coll c g k; "
            "eqangle b f b g f k g k; "
            "eqratio a f c f d g c g; "
            "coll b d f; "
            "eqangle b d b g f k d k; "
            "eqangle b g d f d g f k; "
            "simtrir b d g k d f; "
            "eqratio a e a f c e c j; "
            "</proof>"
        )
        aux_part = "<aux> x00 k : cyclic b f g k [016] coll c d k [017] ; </aux>"

        guidance = build_hidden_proof_guidance(
            sanitized_rest,
            aux_part,
            "eqratio a e a f c e c j",
        )

        ordered_route = guidance["ordered_route_relations"]
        self.assertIn("b, d, f are collinear", ordered_route)
        self.assertLess(
            ordered_route.index("b, d, f are collinear"),
            ordered_route.index("angle bd/bg equals angle fk/dk"),
        )

    def test_rebalance_anchor_points_for_coordinate_coverage_drops_coordinate_heavy_extra_anchor(self):
        rebalanced = rebalance_anchor_points_for_coordinate_coverage(
            anchor_points=["a", "b", "c", "d"],
            coordinate_relations=[
                "point f looks like the midpoint of ac",
                "point g looks like the midpoint of cd",
                "points b, d, and f look nearly collinear",
            ],
            visible_points=["a", "b", "c", "d", "e", "f", "g", "j"],
            min_anchor_count=3,
            required_non_anchor_coverage=3,
        )

        self.assertEqual(rebalanced, ["a", "b", "c"])

    def test_should_extend_plan_retry_budget_only_for_recoverable_plan_failures(self):
        self.assertTrue(
            should_extend_plan_retry_budget(
                "coordinate_relations should cover at least 3 visible non-anchor points so the route does not stay trapped on the anchor frame",
                used_bonus_retries=0,
            )
        )
        self.assertFalse(
            should_extend_plan_retry_budget(
                "goal_finish contains forbidden pattern: midpoint properties",
                used_bonus_retries=0,
            )
        )
        self.assertFalse(
            should_extend_plan_retry_budget(
                "coordinate_relations should cover at least 3 visible non-anchor points so the route does not stay trapped on the anchor frame",
                used_bonus_retries=2,
            )
        )

    def test_run_plan_stage_grants_bonus_retry_for_recoverable_plan_failures(self):
        failing_messages = [
            "coordinate_relations should cover at least 3 visible non-anchor points so the route does not stay trapped on the anchor frame",
            "bridge_steps should not skip prerequisite hidden-route checkpoints before higher-order similarity or ratio steps; missing prerequisite: angle bg/df equals angle dg/fk",
            "bridge_steps[2].relation still introduces unsupported angle/ratio/similar segments before they are grounded by required_supports: ['bd', 'df', 'dk']",
        ]
        validate_side_effect = [
            (False, failing_messages[0], None),
            (False, failing_messages[1], None),
            (False, failing_messages[2], None),
            (True, "Valid plan", {"anchor_points": ["a", "b", "c"]}),
        ]

        with patch(
            "experiments.cot_sft_generation.generate_cot_sft.call_model",
            side_effect=["plan1", "plan2", "plan3", "plan4"],
        ), patch(
            "experiments.cot_sft_generation.generate_cot_sft.validate_plan_response",
            side_effect=validate_side_effect,
        ):
            result = run_plan_stage(
                stage_name="plan",
                messages=[{"role": "user", "content": "prompt"}],
                model_name="fixture-model",
                point_coords={"a": (0, 0), "b": (1, 0), "c": (0, 1)},
                visible_goal="eqratio a b c d",
                aux_part="<aux>x00 k : coll k a b</aux>",
                coordinate_candidates=[],
                sanitized_rest="",
                visible_premise_summaries=[],
                max_retries=3,
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["attempts_used"], 4)
        self.assertEqual(result["parsed"], {"anchor_points": ["a", "b", "c"]})


if __name__ == "__main__":
    unittest.main()
