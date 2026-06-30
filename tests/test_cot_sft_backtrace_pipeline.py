import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments.cot_sft_generation.core.backtrace_extractor import (
    build_backtrace_writer_handoff,
    extract_backtrace_slots,
)
from experiments.cot_sft_generation.core.backtrace_pipeline import (
    build_backtrace_write_prompt,
    collect_backtrace_writer_issues,
    validate_backtrace_writer_body,
)
from experiments.cot_sft_generation.core.backtrace_schema import BACKTRACE_TEXT_V1, BACKTRACE_TEXT_V2
from experiments.cot_sft_generation.core.proof_dag import parse_proof_dag
from experiments.cot_sft_generation.generate_cot_sft import parse_args, process_and_generate_sft
from experiments.cot_sft_generation.replay_artifact_checks import recheck_item_record


def _build_backtrace_record():
    problem = (
        "<problem>"
        "g1: cong a b a c [000] ; "
        "g2: coll b c d [001] ; "
        "g3: para a d b e [002] ? "
        "eqratio a b b c b e c e"
        "</problem>"
    )
    aux = "<aux>x00 f : midp f a d [100] ; </aux>"
    proof = (
        "<proof>"
        "cong a b a c [010] AR [000] ; "
        "eqangle a b a c b c b d [011] AR [010] [001] ; "
        "midp f a d [012] AR [100] ; "
        "cong b f c f [013] AR [012] [010] ; "
        "eqangle a b b c b e c e [014] AR [013] [011] [002] ; "
        "eqratio a b b c b e c e [015] AR [014] [010] ; "
        "</proof>"
    )
    return {
        "llm_input_renamed": problem,
        "llm_output_renamed": f"{problem}\n{aux}\n{proof}",
    }


def _build_branching_backtrace_record():
    problem = (
        "<problem>"
        "g1: cong a b a c [000] ; "
        "g2: coll b c d [001] ; "
        "g3: para a d b e [002] ; "
        "g4: coll a d e [003] ? "
        "eqratio a b b c b e c e"
        "</problem>"
    )
    aux = "<aux>x00 f : midp f a d [100] ; </aux>"
    proof = (
        "<proof>"
        "cong a b a c [010] AR [000] ; "
        "eqangle a b a c b c b d [011] AR [010] [001] ; "
        "coll a d e [012] AR [003] ; "
        "midp f a d [013] AR [100] ; "
        "cong b f c f [014] AR [013] [010] ; "
        "eqangle a b b c b e c e [015] AR [014] [011] [002] ; "
        "eqangle a d d e b e c e [016] AR [012] [002] ; "
        "eqratio a d d e b e c e [017] AR [013] [016] ; "
        "eqratio a b b c b e c e [018] AR [015] [017] [010] ; "
        "</proof>"
    )
    return {
        "llm_input_renamed": problem,
        "llm_output_renamed": f"{problem}\n{aux}\n{proof}",
    }


def _build_mixed_boundary_backtrace_record():
    problem = (
        "<problem>"
        "g1: cong a b a c [000] ; "
        "g2: coll b c d [001] ; "
        "g3: para a d b e [002] ? "
        "eqratio a b b c b e c e"
        "</problem>"
    )
    aux = "<aux>x00 f : midp f a d [100] ; </aux>"
    proof = (
        "<proof>"
        "cong a b a c [010] AR [000] ; "
        "eqangle a b a c b c b d [011] AR [010] [001] ; "
        "midp f a d [012] AR [100] ; "
        "cong b f c f [013] AR [012] [010] ; "
        "eqangle a b b c b e c e [014] AR [013] [011] [002] ; "
        "eqratio a b b c b e c e [015] AR [014] [013] [010] ; "
        "</proof>"
    )
    return {
        "llm_input_renamed": problem,
        "llm_output_renamed": f"{problem}\n{aux}\n{proof}",
    }


class CotSftBacktraceExtractorTest(unittest.TestCase):
    def test_extract_backtrace_slots_classifies_C1_C2_C3_V_H(self):
        record = _build_backtrace_record()
        dag = parse_proof_dag(record["llm_output_renamed"])

        slots = extract_backtrace_slots(
            dag,
            visible_goal="eqratio a b b c b e c e",
            aux_part="<aux>x00 f : midp f a d [100] ; </aux>",
        )

        self.assertEqual(slots["C1_step_ids"], ["010", "011"])
        self.assertEqual(slots["C2_step_ids"], ["010", "011", "014", "015"])
        self.assertEqual(slots["C3_step_ids"], ["012", "013", "014", "015"])
        self.assertEqual(slots["V_step_ids"], ["014", "015"])
        self.assertEqual(slots["H_step_ids"], ["012", "013"])

    def test_extract_backtrace_slots_builds_V_core_frontier_and_supporting_c1(self):
        record = _build_backtrace_record()
        dag = parse_proof_dag(record["llm_output_renamed"])

        slots = extract_backtrace_slots(
            dag,
            visible_goal="eqratio a b b c b e c e",
            aux_part="<aux>x00 f : midp f a d [100] ; </aux>",
        )

        self.assertEqual(slots["V_core_step_ids"], ["014", "015"])
        self.assertEqual(slots["backtrace_root_step_id"], "015")
        self.assertEqual(slots["backtrace_stage_order_step_ids"], ["015", "014"])
        self.assertEqual(slots["terminal_stage_ids"], ["014"])
        self.assertEqual(slots["backtrace_chain_step_ids"], ["015", "014"])
        self.assertEqual(slots["frontier_node_ids"], ["014"])
        self.assertEqual(slots["supporting_c1_by_frontier"], {"014": ["011"]})
        self.assertEqual(
            slots["backtrace_stages"],
            [
                {
                    "step_id": "015",
                    "claim_nl": "ratio ab to bc equals ratio be to ce",
                    "parent_stage_ids": [],
                    "depth": 0,
                    "visible_support_step_ids": ["010"],
                    "visible_support_nl": ["ab equals ac"],
                    "next_v_step_ids": ["014"],
                    "next_v_nl": ["angle ab/bc equals angle be/ce"],
                    "blocking_h_step_ids": [],
                    "blocking_h_nl": [],
                    "is_terminal": False,
                    "stop_reason": "",
                },
                {
                    "step_id": "014",
                    "claim_nl": "angle ab/bc equals angle be/ce",
                    "parent_stage_ids": ["015"],
                    "depth": 1,
                    "visible_support_step_ids": ["011"],
                    "visible_support_nl": ["angle ab/ac equals angle bc/bd"],
                    "next_v_step_ids": [],
                    "next_v_nl": [],
                    "blocking_h_step_ids": ["013"],
                    "blocking_h_nl": ["bf equals cf"],
                    "is_terminal": True,
                    "stop_reason": "has_direct_h_dependency",
                },
            ],
        )

    def test_extract_backtrace_slots_builds_aux_and_canonical_nl_fields(self):
        record = _build_backtrace_record()
        dag = parse_proof_dag(record["llm_output_renamed"])

        slots = extract_backtrace_slots(
            dag,
            visible_goal="eqratio a b b c b e c e",
            aux_part="<aux>x00 f : midp f a d [100] ; </aux>",
        )

        self.assertEqual(slots["aux_construction_formal"], "x00 f : midp f a d")
        self.assertEqual(slots["aux_construction_nl"], "construct point f such that f is the midpoint of ad")
        self.assertEqual(slots["goal_nl"], "ratio ab to bc equals ratio be to ce")
        self.assertEqual(
            slots["backtrace_chain_nl"],
            [
                "ratio ab to bc equals ratio be to ce",
                "angle ab/bc equals angle be/ce",
            ],
        )
        self.assertEqual(slots["frontier_nodes_nl"], ["angle ab/bc equals angle be/ce"])
        self.assertEqual(
            slots["supporting_c1_facts_nl"],
            {"angle ab/bc equals angle be/ce": ["angle ab/ac equals angle bc/bd"]},
        )

    def test_extract_backtrace_slots_expands_multiple_v_children_in_stage_order(self):
        record = _build_branching_backtrace_record()
        dag = parse_proof_dag(record["llm_output_renamed"])

        slots = extract_backtrace_slots(
            dag,
            visible_goal="eqratio a b b c b e c e",
            aux_part="<aux>x00 f : midp f a d [100] ; </aux>",
        )

        self.assertEqual(slots["backtrace_stage_order_step_ids"], ["018", "015", "017"])
        self.assertEqual(slots["terminal_stage_ids"], ["015", "017"])
        self.assertEqual(slots["frontier_node_ids"], ["015", "017"])
        self.assertEqual(slots["backtrace_stages"][0]["next_v_step_ids"], ["015", "017"])
        self.assertEqual(
            slots["backtrace_stages"][0]["next_v_nl"],
            [
                "angle ab/bc equals angle be/ce",
                "ratio ad to de equals ratio be to ce",
            ],
        )

    def test_extract_backtrace_slots_stops_expansion_when_direct_h_dependency_exists(self):
        record = _build_mixed_boundary_backtrace_record()
        dag = parse_proof_dag(record["llm_output_renamed"])

        slots = extract_backtrace_slots(
            dag,
            visible_goal="eqratio a b b c b e c e",
            aux_part="<aux>x00 f : midp f a d [100] ; </aux>",
        )

        self.assertEqual(slots["V_core_step_ids"], ["014", "015"])
        self.assertEqual(slots["backtrace_stage_order_step_ids"], ["015"])
        self.assertEqual(slots["terminal_stage_ids"], ["015"])
        self.assertEqual(slots["backtrace_stages"][0]["next_v_step_ids"], ["014"])
        self.assertEqual(slots["backtrace_stages"][0]["blocking_h_step_ids"], ["013"])

    def test_build_backtrace_writer_handoff_keeps_stage_fields(self):
        handoff = build_backtrace_writer_handoff(
            {
                "goal_nl": "ratio ab to bc equals ratio be to ce",
                "backtrace_stages": [
                    {
                        "claim_nl": "ratio ab to bc equals ratio be to ce",
                        "depth": 0,
                        "visible_support_nl": ["ab equals ac"],
                        "next_v_nl": ["angle ab/bc equals angle be/ce"],
                        "is_terminal": False,
                    },
                    {
                        "claim_nl": "angle ab/bc equals angle be/ce",
                        "depth": 1,
                        "visible_support_nl": ["angle ab/ac equals angle bc/bd"],
                        "next_v_nl": [],
                        "blocking_h_nl": ["bf equals cf"],
                        "is_terminal": True,
                    },
                ],
                "aux_construction_nl": "construct point f such that f is the midpoint of ad",
            }
        )

        self.assertEqual(
            handoff,
            {
                "goal_nl": "ratio ab to bc equals ratio be to ce",
                "backtrace_stages": [
                    {
                        "claim_nl": "ratio ab to bc equals ratio be to ce",
                        "depth": 0,
                        "stage_type": "visible_backtrace",
                        "visible_support_nl": ["ab equals ac"],
                        "subgoal_claims_nl": ["angle ab/bc equals angle be/ce"],
                    },
                    {
                        "claim_nl": "angle ab/bc equals angle be/ce",
                        "depth": 1,
                        "stage_type": "aux_boundary",
                        "aux_boundary_h_nl": ["bf equals cf"],
                        "aux_boundary_non_h_nl": ["angle ab/ac equals angle bc/bd"],
                    },
                ],
                "terminal_claims_nl": ["angle ab/bc equals angle be/ce"],
                "aux_construction_nl": "construct point f such that f is the midpoint of ad",
            },
        )

    def test_build_backtrace_write_prompt_includes_fixed_contract(self):
        handoff = build_backtrace_writer_handoff(
            {
                "goal_nl": "ratio ab to bc equals ratio be to ce",
                "backtrace_stages": [
                    {
                        "claim_nl": "ratio ab to bc equals ratio be to ce",
                        "depth": 0,
                        "visible_support_nl": ["ab equals ac"],
                        "next_v_nl": ["angle ab/bc equals angle be/ce"],
                        "is_terminal": False,
                    },
                    {
                        "claim_nl": "angle ab/bc equals angle be/ce",
                        "depth": 1,
                        "visible_support_nl": ["angle ab/ac equals angle bc/bd"],
                        "next_v_nl": [],
                        "is_terminal": True,
                    },
                ],
                "aux_construction_nl": "construct point f such that f is the midpoint of ad",
            }
        )

        prompt = build_backtrace_write_prompt(_build_backtrace_record(), handoff)

        self.assertIn("current claim", prompt)
        self.assertIn("subgoal_claims_nl", prompt)
        self.assertIn("aux_boundary_non_h_nl", prompt)
        self.assertIn("[Writer Handoff]", prompt)
        self.assertNotIn("[Visible Point Coordinates]", prompt)
        self.assertNotIn("planner", prompt.lower())

    def test_validate_backtrace_writer_body_accepts_ordered_text_only_body(self):
        record = _build_backtrace_record()
        dag = parse_proof_dag(record["llm_output_renamed"])
        slots = extract_backtrace_slots(
            dag,
            visible_goal="eqratio a b b c b e c e",
            aux_part="<aux>x00 f : midp f a d [100] ; </aux>",
        )
        handoff = build_backtrace_writer_handoff(slots)
        body = (
            "The target is ratio ab to bc equals ratio be to ce. "
            "For this claim, the visible support already includes ab equals ac, but we still need angle ab/bc equals angle be/ce. "
            "For angle ab/bc equals angle be/ce, the visible support already includes angle ab/ac equals angle bc/bd, but that is still not enough by itself to finish the visible route. "
            "So we need a new helper: construct point f such that f is the midpoint of ad. "
            "After introducing f, we can get bf equals cf; together with angle ab/ac equals angle bc/bd, this reaches angle ab/bc equals angle be/ce."
        )

        ok, message = validate_backtrace_writer_body(
            body,
            writer_handoff=handoff,
            backtrace_slots=slots,
            aux_part="<aux>x00 f : midp f a d [100] ; </aux>",
        )

        self.assertTrue(ok, msg=message)

    def test_validate_backtrace_writer_body_allows_theorem_phrasing_without_proof_ids(self):
        record = _build_backtrace_record()
        dag = parse_proof_dag(record["llm_output_renamed"])
        slots = extract_backtrace_slots(
            dag,
            visible_goal="eqratio a b b c b e c e",
            aux_part="<aux>x00 f : midp f a d [100] ; </aux>",
        )
        handoff = build_backtrace_writer_handoff(slots)
        body = (
            "The target is ratio ab to bc equals ratio be to ce. "
            "For this claim, the visible support already includes ab equals ac, but we still need angle ab/bc equals angle be/ce. "
            "For angle ab/bc equals angle be/ce, the visible support already includes angle ab/ac equals angle bc/bd, but that is still not enough by itself to finish the visible route. "
            "So we need a new helper: construct point f such that f is the midpoint of ad. "
            "Then the midpoint theorem gives bf equals cf, and with angle ab/ac equals angle bc/bd this reaches angle ab/bc equals angle be/ce."
        )

        issues = collect_backtrace_writer_issues(
            body,
            writer_handoff=handoff,
            backtrace_slots=slots,
            aux_part="<aux>x00 f : midp f a d [100] ; </aux>",
        )

        self.assertNotIn("proof_marker_leak", issues)

    def test_validate_backtrace_writer_body_accepts_embedded_relation_phrases(self):
        record = _build_backtrace_record()
        dag = parse_proof_dag(record["llm_output_renamed"])
        slots = extract_backtrace_slots(
            dag,
            visible_goal="eqratio a b b c b e c e",
            aux_part="<aux>x00 f : midp f a d [100] ; </aux>",
        )
        handoff = build_backtrace_writer_handoff(slots)
        body = (
            "The goal is to prove that the ratio of segment ab to bc equals the ratio of segment be to ce. "
            "At this stage, the visible support includes the equality of ab and ac, so we reduce the task to the subgoal that angle ab/bc equals angle be/ce. "
            "For angle ab/bc equals angle be/ce, the visible support includes angle ab/ac equals angle bc/bd, but the visible route is still not enough by itself. "
            "So we construct point f such that f is the midpoint of ad. "
            "This auxiliary point can provide bf equals cf, which combines with angle ab/ac equals angle bc/bd to reach angle ab/bc equals angle be/ce."
        )

        ok, message = validate_backtrace_writer_body(
            body,
            writer_handoff=handoff,
            backtrace_slots=slots,
            aux_part="<aux>x00 f : midp f a d [100] ; </aux>",
        )

        self.assertTrue(ok, msg=message)

    def test_collect_backtrace_writer_issues_does_not_flag_visible_ratio_summary_as_hidden_relation(self):
        writer_handoff = {
            "goal_nl": "triangles acg and fag are similar",
            "backtrace_stages": [
                {
                    "claim_nl": "triangles acg and fag are similar",
                    "depth": 0,
                    "visible_support_nl": ["angle ac/af equals angle cg/ag"],
                    "subgoal_claims_nl": ["ratio ac to af equals ratio cg to ag"],
                    "stage_type": "visible_backtrace",
                },
                {
                    "claim_nl": "ratio ac to af equals ratio cg to ag",
                    "depth": 1,
                    "stage_type": "aux_boundary",
                    "aux_boundary_h_nl": [],
                    "aux_boundary_non_h_nl": [
                        "ad equals cd",
                        "be equals dg",
                        "ratio ab to ac equals ratio be to ag",
                        "ratio ab to ac equals ratio cd to ce",
                        "ratio ac to ae equals ratio cd to ce",
                        "ratio ae to cg equals ratio de to eg",
                    ],
                },
            ],
            "terminal_claims_nl": ["ratio ac to af equals ratio cg to ag"],
            "aux_construction_nl": "construct point h such that a, b, e, h are concyclic and a, c, g, h are concyclic",
        }
        backtrace_slots = {
            "H_relations_nl": [
                "ratio ad to bc equals ratio de to ch",
                "triangles afg and bfh are similar",
            ]
        }
        body = (
            "To prove that triangles acg and fag are similar, we begin by identifying the visible angular conditions. "
            "We see that angle ac/af equals angle cg/ag, which satisfies one requirement for similarity. "
            "The remaining subgoal is to demonstrate that the ratio ac to af equals the ratio cg to ag. "
            "Turning to this ratio claim, we examine the available visible support regarding segment lengths and proportions. "
            "We know that ad equals cd and be equals dg. Additionally, the ratio ab to ac equals the ratio be to ag, and the ratio ab to ac equals the ratio cd to ce. "
            "We also have that the ratio ac to ae equals the ratio cd to ce, and the ratio ae to cg equals the ratio de to eg. "
            "Although these relations establish connections between segments ad, cd, be, dg, ab, ac, ce, ae, de, and eg, they do not directly yield the equality between the ratio ac to af and the ratio cg to ag. "
            "The visible route is not enough to conclude this proportionality using only the stated constraints. "
            "Since the visible path reaches its limit, we introduce an auxiliary construction to bridge the gap. "
            "We construct point h such that a, b, e, h are concyclic and a, c, g, h are concyclic."
        )

        issues = collect_backtrace_writer_issues(
            body,
            writer_handoff=writer_handoff,
            backtrace_slots=backtrace_slots,
            aux_part="<aux>x00 h : cyclic a b e h [010] cyclic a c g h [011] ; </aux>",
        )

        self.assertNotIn("early_hidden_relation", issues)

    def test_collect_backtrace_writer_issues_allows_reused_terminal_subgoal_after_later_parent_stage(self):
        writer_handoff = {
            "goal_nl": "triangles agi and igh are similar",
            "backtrace_stages": [
                {
                    "claim_nl": "triangles agi and igh are similar",
                    "depth": 0,
                    "visible_support_nl": [],
                    "subgoal_claims_nl": [
                        "angle ag/ai equals angle hi/gi",
                        "ratio ag to ai equals ratio gi to hi",
                    ],
                    "stage_type": "visible_backtrace",
                },
                {
                    "claim_nl": "angle ag/ai equals angle hi/gi",
                    "depth": 1,
                    "visible_support_nl": [
                        "a, g, h are collinear",
                        "ad equals ae",
                    ],
                    "subgoal_claims_nl": ["dg equals gi"],
                    "stage_type": "visible_backtrace",
                },
                {
                    "claim_nl": "dg equals gi",
                    "depth": 2,
                    "stage_type": "aux_boundary",
                    "aux_boundary_h_nl": [],
                    "aux_boundary_non_h_nl": [],
                },
                {
                    "claim_nl": "ratio ag to ai equals ratio gi to hi",
                    "depth": 1,
                    "visible_support_nl": [
                        "de equals dg",
                        "de equals dh",
                    ],
                    "subgoal_claims_nl": ["dg equals gi"],
                    "stage_type": "visible_backtrace",
                },
            ],
            "terminal_claims_nl": ["dg equals gi"],
            "aux_construction_nl": (
                "construct point j such that line cf is perpendicular to line fj and cf equals fj. "
                "then construct point k such that line cf is parallel to line jk and line ck is parallel to line fj"
            ),
        }
        body = (
            "We start with the goal that triangles agi and igh are similar. "
            "At this stage, there is no immediate visible support, so we break the claim down into two subgoal claims: "
            "first, that the angle ag/ai equals angle hi/gi, and second, that the ratio ag to ai equals ratio gi to hi. "
            "Moving to the first subgoal, we examine the claim that angle ag/ai equals angle hi/gi. "
            "The visible support for this includes the collinearity of points a, g, and h, and we also have ad equals ae. "
            "Despite this support, the claim reduces to a remaining subgoal: we must show that dg equals gi. "
            "Next, we focus on the claim that dg equals gi. "
            "At this depth, there is no visible support available to confirm this equality directly. "
            "We have reached the visible boundary, indicating that the current visible route is not enough to derive this result from the existing configuration. "
            "To proceed past this limit, we introduce an auxiliary construction. "
            "We construct point j such that line cf is perpendicular to line fj and cf equals fj. "
            "Then we construct point k such that line cf is parallel to line jk and line ck is parallel to line fj. "
            "Finally, we consider the second subgoal from the initial stage, that the ratio ag to ai equals ratio gi to hi. "
            "The visible support here includes equalities like de equals dg and de equals dh. "
            "This claim also reduces to the subgoal that dg equals gi."
        )

        issues = collect_backtrace_writer_issues(
            body,
            writer_handoff=writer_handoff,
            backtrace_slots={"H_relations_nl": []},
            aux_part="<aux>x00 j : perp c f f j [016] cong c f f j [017] ; x00 k : para c f j k [018] para c k f j [019] ; </aux>",
        )

        self.assertNotIn("narrative_order_violation", issues)
        self.assertEqual(issues, [])

    def test_collect_backtrace_writer_issues_accepts_does_not_provide_enough_boundary_phrase(self):
        writer_handoff = {
            "goal_nl": "triangles ach and dbh are congruent",
            "backtrace_stages": [
                {
                    "claim_nl": "triangles ach and dbh are congruent",
                    "depth": 0,
                    "visible_support_nl": [],
                    "subgoal_claims_nl": ["bh equals ch"],
                    "stage_type": "visible_backtrace",
                },
                {
                    "claim_nl": "bh equals ch",
                    "depth": 1,
                    "stage_type": "aux_boundary",
                    "aux_boundary_h_nl": [],
                    "aux_boundary_non_h_nl": [],
                },
            ],
            "terminal_claims_nl": ["bh equals ch"],
            "aux_construction_nl": "construct point i such that i is the midpoint of ac",
        }
        body = (
            "The main objective is to prove that triangles ach and dbh are congruent. "
            "To establish this congruence, we reduce the task to the subgoal that bh equals ch. "
            "Next, we address the subgoal that bh equals ch. "
            "The visible support involves collinearity with point h and congruences related to point g. "
            "Despite these constraints, the visible route does not provide enough information to confirm that bh equals ch. "
            "We must introduce an auxiliary construction to proceed. "
            "Construct point i such that i is the midpoint of ac."
        )

        issues = collect_backtrace_writer_issues(
            body,
            writer_handoff=writer_handoff,
            backtrace_slots={"H_relations_nl": []},
            aux_part="<aux>x00 i : midp i a c [010] ; </aux>",
        )

        self.assertEqual(issues, [])

    def test_collect_backtrace_writer_issues_allows_root_subgoal_list_before_sibling_expansion(self):
        writer_handoff = {
            "goal_nl": "triangles abe and dca are similar",
            "backtrace_stages": [
                {
                    "claim_nl": "triangles abe and dca are similar",
                    "depth": 0,
                    "visible_support_nl": [],
                    "subgoal_claims_nl": [
                        "angle ab/be equals angle cd/ac",
                        "ratio ab to be equals ratio cd to ac",
                    ],
                    "stage_type": "visible_backtrace",
                },
                {
                    "claim_nl": "angle ab/be equals angle cd/ac",
                    "depth": 1,
                    "stage_type": "aux_boundary",
                    "aux_boundary_h_nl": [],
                    "aux_boundary_non_h_nl": [],
                },
                {
                    "claim_nl": "ratio ab to be equals ratio cd to ac",
                    "depth": 1,
                    "stage_type": "aux_boundary",
                    "aux_boundary_h_nl": [],
                    "aux_boundary_non_h_nl": [],
                },
            ],
            "terminal_claims_nl": [
                "angle ab/be equals angle cd/ac",
                "ratio ab to be equals ratio cd to ac",
            ],
            "aux_construction_nl": (
                "construct point f such that bf equals cf and b, c, d, f are concyclic. "
                "then construct point g such that c, d, g are collinear and a, f, g are collinear"
            ),
        }
        body = (
            "To prove that triangles abe and dca are similar, the main claim breaks down into two immediate subgoals. "
            "The first subgoal is to show that the angle formed by sides ab and be equals the angle formed by sides cd and ac. "
            "The second subgoal is to show that the ratio of the length ab to be equals the ratio of the length cd to ac. "
            "For the first subgoal, I examine the angle condition where the angle formed by ab and be must equal the angle formed by cd and ac. "
            "The visible route for this subgoal reaches its limit without proving the claim. "
            "For the second subgoal, I examine the ratio condition where the ratio of ab to be must equal the ratio of cd to ac. "
            "The visible support does not extend far enough to establish this proportionality without additional geometric connections. "
            "Since both subgoals reach a boundary, I will construct a point f such that the length bf equals cf and the points b, c, d, f are concyclic. "
            "Then, I will construct a point g such that points c, d, g are collinear and points a, f, g are collinear."
        )

        issues = collect_backtrace_writer_issues(
            body,
            writer_handoff=writer_handoff,
            backtrace_slots={"H_relations_nl": []},
            aux_part="<aux>x00 f : cong b f c f [010] cyclic b c d f [011] ; x00 g : coll c d g [012] coll a f g [013] ; </aux>",
        )

        self.assertEqual(issues, [])

    def test_collect_backtrace_writer_issues_allows_aux_after_all_sibling_boundaries(self):
        writer_handoff = {
            "goal_nl": "triangles abe and dca are similar",
            "backtrace_stages": [
                {
                    "claim_nl": "triangles abe and dca are similar",
                    "depth": 0,
                    "visible_support_nl": [],
                    "subgoal_claims_nl": [
                        "angle ab/be equals angle cd/ac",
                        "ratio ab to be equals ratio cd to ac",
                    ],
                    "stage_type": "visible_backtrace",
                },
                {
                    "claim_nl": "angle ab/be equals angle cd/ac",
                    "depth": 1,
                    "stage_type": "aux_boundary",
                    "aux_boundary_h_nl": [
                        "b, e, g are collinear",
                        "angle ab/bg equals angle cg/ac",
                    ],
                    "aux_boundary_non_h_nl": [],
                },
                {
                    "claim_nl": "ratio ab to be equals ratio cd to ac",
                    "depth": 1,
                    "stage_type": "aux_boundary",
                    "aux_boundary_h_nl": [
                        "ratio ab to be equals ratio dg to eg",
                        "ratio ac to cd equals ratio eg to dg",
                    ],
                    "aux_boundary_non_h_nl": [],
                },
            ],
            "terminal_claims_nl": [
                "angle ab/be equals angle cd/ac",
                "ratio ab to be equals ratio cd to ac",
            ],
            "aux_construction_nl": (
                "construct point f such that bf equals cf and b, c, d, f are concyclic. "
                "then construct point g such that c, d, g are collinear and a, f, g are collinear"
            ),
        }
        body = (
            "To prove that triangles abe and dca are similar, we begin with the claim that triangles abe and dca are similar. "
            "This requires establishing two subgoals: angle ab/be equals angle cd/ac and ratio ab to be equals ratio cd to ac. "
            "Focusing on the claim that angle ab/be equals angle cd/ac, the visible route is not enough. "
            "Next, for the claim that ratio ab to be equals ratio cd to ac, the visible route is also not enough. "
            "We introduce the auxiliary construction: construct point f such that bf equals cf and b, c, d, f are concyclic. "
            "Then construct point g such that c, d, g are collinear and a, f, g are collinear. "
            "With this construction, b, e, g are collinear and angle ab/bg equals angle cg/ac, reaching the first boundary claim. "
            "The relations ratio ab to be equals ratio dg to eg and ratio ac to cd equals ratio eg to dg reach the second boundary claim."
        )

        issues = collect_backtrace_writer_issues(
            body,
            writer_handoff=writer_handoff,
            backtrace_slots={"H_relations_nl": []},
            aux_part="<aux>x00 f : cong b f c f [010] cyclic b c d f [011] ; x00 g : coll c d g [012] coll a f g [013] ; </aux>",
        )

        self.assertEqual(issues, [])

    def test_collect_backtrace_writer_issues_allows_visible_sibling_after_terminal_boundary(self):
        writer_handoff = {
            "goal_nl": "ratio af to ag equals ratio cf to eg",
            "backtrace_stages": [
                {
                    "claim_nl": "ratio af to ag equals ratio cf to eg",
                    "depth": 0,
                    "visible_support_nl": [],
                    "subgoal_claims_nl": [
                        "ratio ac to ae equals ratio af to ag",
                        "ratio ac to ae equals ratio cf to eg",
                    ],
                    "stage_type": "visible_backtrace",
                },
                {
                    "claim_nl": "ratio ac to ae equals ratio af to ag",
                    "depth": 1,
                    "visible_support_nl": ["line cf is parallel to line eg"],
                    "subgoal_claims_nl": ["a, f, g are collinear"],
                    "stage_type": "visible_backtrace",
                },
                {
                    "claim_nl": "a, f, g are collinear",
                    "depth": 2,
                    "stage_type": "aux_boundary",
                    "aux_boundary_h_nl": ["a, d, h are collinear", "bh equals ch"],
                    "aux_boundary_non_h_nl": ["b, e, g are collinear"],
                },
                {
                    "claim_nl": "ratio ac to ae equals ratio cf to eg",
                    "depth": 1,
                    "visible_support_nl": ["line cf is parallel to line eg"],
                    "subgoal_claims_nl": ["a, f, g are collinear"],
                    "stage_type": "visible_backtrace",
                },
            ],
            "terminal_claims_nl": ["a, f, g are collinear"],
            "aux_construction_nl": "construct point h such that h is the midpoint of ad",
        }
        body = (
            "To show that ratio af to ag equals ratio cf to eg, we first need ratio ac to ae equals ratio af to ag "
            "and ratio ac to ae equals ratio cf to eg. "
            "For ratio ac to ae equals ratio af to ag, line cf is parallel to line eg, reducing this to a, f, g are collinear. "
            "The visible route is not enough for a, f, g are collinear. "
            "For ratio ac to ae equals ratio cf to eg, line cf is parallel to line eg, and it also reduces to a, f, g are collinear. "
            "We construct point h such that h is the midpoint of ad. "
            "The new auxiliary relations a, d, h are collinear and bh equals ch, together with the already-visible relation b, e, g are collinear, reach a, f, g are collinear."
        )

        issues = collect_backtrace_writer_issues(
            body,
            writer_handoff=writer_handoff,
            backtrace_slots={"H_relations_nl": []},
            aux_part="<aux>x00 h : midp h a d [010] ; </aux>",
        )

        self.assertEqual(issues, [])

    def test_collect_backtrace_writer_issues_allows_sibling_expansion_before_shared_boundary(self):
        writer_handoff = {
            "goal_nl": "triangles agi and igh are similar",
            "backtrace_stages": [
                {
                    "claim_nl": "triangles agi and igh are similar",
                    "depth": 0,
                    "visible_support_nl": [],
                    "subgoal_claims_nl": [
                        "angle ag/ai equals angle hi/gi",
                        "ratio ag to ai equals ratio gi to hi",
                    ],
                    "stage_type": "visible_backtrace",
                },
                {
                    "claim_nl": "angle ag/ai equals angle hi/gi",
                    "depth": 1,
                    "visible_support_nl": ["a, g, h are collinear"],
                    "subgoal_claims_nl": ["dg equals gi"],
                    "stage_type": "visible_backtrace",
                },
                {
                    "claim_nl": "dg equals gi",
                    "depth": 2,
                    "stage_type": "aux_boundary",
                    "aux_boundary_h_nl": ["d, e, k, i are concyclic"],
                    "aux_boundary_non_h_nl": [],
                },
                {
                    "claim_nl": "ratio ag to ai equals ratio gi to hi",
                    "depth": 1,
                    "visible_support_nl": ["de equals dg"],
                    "subgoal_claims_nl": ["dg equals gi"],
                    "stage_type": "visible_backtrace",
                },
            ],
            "terminal_claims_nl": ["dg equals gi"],
            "aux_construction_nl": "construct point k such that line cf is parallel to line jk",
        }
        body = (
            "To prove that triangles agi and igh are similar, we need two conditions. "
            "First, angle ag/ai equals angle hi/gi. "
            "Second, ratio ag to ai equals ratio gi to hi. "
            "For the angle condition, a, g, h are collinear and the path reduces to dg equals gi. "
            "For the ratio condition, de equals dg and this path also reduces to dg equals gi. "
            "The claim dg equals gi is the boundary where the visible route is not enough. "
            "Construct point k such that line cf is parallel to line jk. "
            "The new relation d, e, k, i are concyclic reaches dg equals gi."
        )

        issues = collect_backtrace_writer_issues(
            body,
            writer_handoff=writer_handoff,
            backtrace_slots={"H_relations_nl": []},
            aux_part="<aux>x00 k : para c f j k [010] ; </aux>",
        )

        self.assertEqual(issues, [])

    def test_collect_backtrace_writer_issues_prefers_pre_aux_sibling_expansion_over_summary(self):
        writer_handoff = {
            "goal_nl": "ratio af to ag equals ratio cf to eg",
            "backtrace_stages": [
                {
                    "claim_nl": "ratio af to ag equals ratio cf to eg",
                    "depth": 0,
                    "visible_support_nl": [],
                    "subgoal_claims_nl": [
                        "ratio ac to ae equals ratio af to ag",
                        "ratio ac to ae equals ratio cf to eg",
                    ],
                    "stage_type": "visible_backtrace",
                },
                {
                    "claim_nl": "ratio ac to ae equals ratio af to ag",
                    "depth": 1,
                    "visible_support_nl": ["line cf is parallel to line eg"],
                    "subgoal_claims_nl": ["a, f, g are collinear"],
                    "stage_type": "visible_backtrace",
                },
                {
                    "claim_nl": "a, f, g are collinear",
                    "depth": 2,
                    "stage_type": "aux_boundary",
                    "aux_boundary_h_nl": ["a, d, h are collinear", "bh equals ch"],
                    "aux_boundary_non_h_nl": [],
                },
                {
                    "claim_nl": "ratio ac to ae equals ratio cf to eg",
                    "depth": 1,
                    "visible_support_nl": ["line cf is parallel to line eg"],
                    "subgoal_claims_nl": ["a, f, g are collinear"],
                    "stage_type": "visible_backtrace",
                },
            ],
            "terminal_claims_nl": ["a, f, g are collinear"],
            "aux_construction_nl": "construct point h such that h is the midpoint of ad",
        }
        body = (
            "To prove ratio af to ag equals ratio cf to eg, we use two intermediate claims. "
            "First, ratio ac to ae equals ratio af to ag. "
            "Second, ratio ac to ae equals ratio cf to eg. "
            "For ratio ac to ae equals ratio af to ag, line cf is parallel to line eg, provided a, f, g are collinear. "
            "For ratio ac to ae equals ratio cf to eg, line cf is parallel to line eg, and it also reduces to a, f, g are collinear. "
            "The boundary claim a, f, g are collinear is not visible enough. "
            "Construct point h such that h is the midpoint of ad. "
            "The new auxiliary relations a, d, h are collinear and bh equals ch reach a, f, g are collinear. "
            "Thus ratio ac to ae equals ratio af to ag and ratio ac to ae equals ratio cf to eg."
        )

        issues = collect_backtrace_writer_issues(
            body,
            writer_handoff=writer_handoff,
            backtrace_slots={"H_relations_nl": []},
            aux_part="<aux>x00 h : midp h a d [010] ; </aux>",
        )

        self.assertEqual(issues, [])

    def test_collect_backtrace_writer_issues_prefers_pre_aux_terminal_boundary_claim(self):
        writer_handoff = {
            "goal_nl": "ratio ac to ad equals ratio bc to de",
            "backtrace_stages": [
                {
                    "claim_nl": "ratio ac to ad equals ratio bc to de",
                    "depth": 0,
                    "visible_support_nl": [],
                    "subgoal_claims_nl": ["triangles abc and aed are similar"],
                    "stage_type": "visible_backtrace",
                },
                {
                    "claim_nl": "triangles abc and aed are similar",
                    "depth": 1,
                    "visible_support_nl": ["ratio ab to ac equals ratio ae to ad"],
                    "subgoal_claims_nl": ["angle ab/ac equals angle ad/ae"],
                    "stage_type": "visible_backtrace",
                },
                {
                    "claim_nl": "angle ab/ac equals angle ad/ae",
                    "depth": 2,
                    "stage_type": "aux_boundary",
                    "aux_boundary_h_nl": ["d, e, f are collinear", "bc equals cf"],
                    "aux_boundary_non_h_nl": ["ad equals ae"],
                },
            ],
            "terminal_claims_nl": ["angle ab/ac equals angle ad/ae"],
            "aux_construction_nl": "construct point f such that a, c, d, f are concyclic",
        }
        body = (
            "To show ratio ac to ad equals ratio bc to de, we aim to show that triangles abc and aed are similar. "
            "For these triangles, ratio ab to ac equals ratio ae to ad. "
            "This reduces to showing that angle formed by ab and ac equals angle formed by ad and ae. "
            "However, the visible route is not enough to prove this angle equality directly. "
            "Construct point f such that a, c, d, f are concyclic. "
            "With this auxiliary point, d, e, f are collinear and bc equals cf. "
            "Using the already-visible relation ad equals ae, these relations reach angle formed by ab and ac equals angle formed by ad and ae."
        )

        issues = collect_backtrace_writer_issues(
            body,
            writer_handoff=writer_handoff,
            backtrace_slots={"H_relations_nl": []},
            aux_part="<aux>x00 f : cyclic a c d f [010] ; </aux>",
        )

        self.assertEqual(issues, [])

    def test_collect_backtrace_writer_issues_tolerates_angle_involving_wording(self):
        writer_handoff = {
            "goal_nl": "triangles abh and gde are similar",
            "backtrace_stages": [
                {
                    "claim_nl": "triangles abh and gde are similar",
                    "depth": 0,
                    "visible_support_nl": ["angle ab/bh equals angle de/dg"],
                    "subgoal_claims_nl": ["angle ah/bh equals angle de/eg"],
                    "stage_type": "visible_backtrace",
                },
                {
                    "claim_nl": "angle ah/bh equals angle de/eg",
                    "depth": 1,
                    "stage_type": "aux_boundary",
                    "aux_boundary_h_nl": ["cf equals ci"],
                    "aux_boundary_non_h_nl": [],
                },
            ],
            "terminal_claims_nl": ["angle ah/bh equals angle de/eg"],
            "aux_construction_nl": "construct point i such that a, c, i are collinear",
        }
        body = (
            "To prove that triangles abh and gde are similar, angle ab/bh equals angle de/dg. "
            "Thus the subgoal becomes showing that the angle involving ah and bh equals the angle involving de and eg. "
            "The visible route is not enough. "
            "Construct point i such that a, c, i are collinear. "
            "The new auxiliary relation cf equals ci reaches the angle involving ah and bh equals the angle involving de and eg."
        )

        issues = collect_backtrace_writer_issues(
            body,
            writer_handoff=writer_handoff,
            backtrace_slots={"H_relations_nl": []},
            aux_part="<aux>x00 i : coll a c i [010] ; </aux>",
        )

        self.assertEqual(issues, [])

    def test_collect_backtrace_writer_issues_accepts_do_not_provide_sufficient_boundary_phrase(self):
        writer_handoff = {
            "goal_nl": "angle ab/ac equals angle ad/ae",
            "backtrace_stages": [
                {
                    "claim_nl": "angle ab/ac equals angle ad/ae",
                    "depth": 0,
                    "stage_type": "aux_boundary",
                    "aux_boundary_h_nl": [],
                    "aux_boundary_non_h_nl": ["ad equals ae"],
                }
            ],
            "terminal_claims_nl": ["angle ab/ac equals angle ad/ae"],
            "aux_construction_nl": "construct point f such that a, c, d, f are concyclic and b, d, f are collinear",
        }
        body = (
            "The goal is to prove that angle bac equals angle dae. "
            "We are given that ad equals ae. "
            "However, the direct length and angle equalities among the given points do not provide a sufficient geometric bridge to equate the two angles. "
            "To proceed beyond this boundary, we introduce an auxiliary construction. "
            "Construct point f such that points a, c, d, f are concyclic and points b, d, f are collinear."
        )

        issues = collect_backtrace_writer_issues(
            body,
            writer_handoff=writer_handoff,
            backtrace_slots={"H_relations_nl": []},
            aux_part="<aux>x00 f : cyclic a c d f [010] coll b d f [011] ; </aux>",
        )

        self.assertEqual(issues, [])

    def test_collect_backtrace_writer_issues_tolerates_loose_equal_wording(self):
        writer_handoff = {
            "goal_nl": "triangles bde and ceg are similar",
            "backtrace_stages": [
                {
                    "claim_nl": "triangles bde and ceg are similar",
                    "depth": 0,
                    "stage_type": "visible_backtrace",
                    "visible_support_nl": ["angle bd/be equals angle cg/ce"],
                    "subgoal_claims_nl": ["ratio bd to be equals ratio ce to cg"],
                },
                {
                    "claim_nl": "ratio bd to be equals ratio ce to cg",
                    "depth": 1,
                    "stage_type": "aux_boundary",
                    "aux_boundary_h_nl": ["ratio be to bh equals ratio ce to ch"],
                    "aux_boundary_non_h_nl": ["af equals ef", "be equals ef", "cg equals fg"],
                },
            ],
            "terminal_claims_nl": ["ratio bd to be equals ratio ce to cg"],
            "aux_construction_nl": (
                "construct point h such that line bd is parallel to line fh "
                "and line bd is perpendicular to line bh"
            ),
        }
        body = (
            "The goal is to prove that triangles bde and ceg are similar. "
            "The angle formed by sides bd and be is equal to the angle formed by sides cg and ce. "
            "The remaining subgoal is that the ratio of side bd to side be is equal to the ratio of side ce to side cg. "
            "For this ratio bd to be equals ratio ce to cg, the visible route is not enough. "
            "We construct point h such that line bd is parallel to line fh and line bd is perpendicular to line bh. "
            "This can lead to the ratio be to bh equalling the ratio ce to ch. "
            "Combining that with af equalling ef, be equalling ef, and cg equalling fg reaches the boundary claim."
        )

        issues = collect_backtrace_writer_issues(
            body,
            writer_handoff=writer_handoff,
            backtrace_slots={"H_relations_nl": []},
            aux_part="<aux>x00 h : para b d f h [010] perp b d b h [011] ; </aux>",
        )

        self.assertEqual(issues, [])

    def test_collect_backtrace_writer_issues_allows_non_hidden_wording(self):
        writer_handoff = {
            "goal_nl": "be equals ef",
            "backtrace_stages": [
                {
                    "claim_nl": "be equals ef",
                    "depth": 0,
                    "stage_type": "aux_boundary",
                    "aux_boundary_h_nl": ["ae equals ag"],
                    "aux_boundary_non_h_nl": ["b, c, e are collinear"],
                }
            ],
            "terminal_claims_nl": ["be equals ef"],
            "aux_construction_nl": (
                "construct point g such that line be is perpendicular to line cg "
                "and line bg is parallel to line de"
            ),
        }
        body = (
            "The goal is be equals ef, but the visible route is not enough. "
            "We construct point g such that line be is perpendicular to line cg and line bg is parallel to line de. "
            "The new auxiliary relation ae equals ag combines with the non-hidden relation b, c, e are collinear to reach be equals ef."
        )

        issues = collect_backtrace_writer_issues(
            body,
            writer_handoff=writer_handoff,
            backtrace_slots={"H_relations_nl": []},
            aux_part="<aux>x00 g : perp b e c g [010] para b g d e [011] ; </aux>",
        )

        self.assertEqual(issues, [])

    def test_collect_backtrace_writer_issues_does_not_treat_pronoun_i_as_aux_leak(self):
        writer_handoff = {
            "goal_nl": "triangles ach and dbh are congruent",
            "backtrace_stages": [
                {
                    "claim_nl": "triangles ach and dbh are congruent",
                    "depth": 0,
                    "stage_type": "aux_boundary",
                    "aux_boundary_h_nl": ["triangles bih and cih are congruent"],
                    "aux_boundary_non_h_nl": [],
                }
            ],
            "terminal_claims_nl": ["triangles ach and dbh are congruent"],
            "aux_construction_nl": "construct point i such that i is the midpoint of ac",
        }
        body = (
            "To prove that triangles ach and dbh are congruent, I need to verify the sides. "
            "The visible route is not enough. "
            "I construct point i such that i is the midpoint of ac. "
            "After the construction, triangles bih and cih are congruent, reaching the claim."
        )

        issues = collect_backtrace_writer_issues(
            body,
            writer_handoff=writer_handoff,
            backtrace_slots={"H_relations_nl": ["triangles bih and cih are congruent"]},
            aux_part="<aux>x00 i : midp i a c [010] ; </aux>",
        )

        self.assertEqual(issues, [])

    def test_collect_backtrace_writer_issues_still_flags_pre_aux_h_relation(self):
        writer_handoff = {
            "goal_nl": "angle ab/ac equals angle bd/cd",
            "backtrace_stages": [
                {
                    "claim_nl": "angle ab/ac equals angle bd/cd",
                    "depth": 0,
                    "stage_type": "aux_boundary",
                    "aux_boundary_h_nl": ["a, e, d are collinear"],
                    "aux_boundary_non_h_nl": [],
                }
            ],
            "terminal_claims_nl": ["angle ab/ac equals angle bd/cd"],
            "aux_construction_nl": "construct point e such that line ab is perpendicular to line ce",
        }
        body = (
            "We aim to prove that angle ab/ac equals angle bd/cd. "
            "The visible route is not enough, so we need a, e, d are collinear. "
            "Construct point e such that line ab is perpendicular to line ce. "
            "After construction, a, e, d are collinear and reaches the boundary."
        )

        issues = collect_backtrace_writer_issues(
            body,
            writer_handoff=writer_handoff,
            backtrace_slots={"H_relations_nl": ["a, e, d are collinear"]},
            aux_part="<aux>x00 e : perp a b c e [010] ; </aux>",
        )

        self.assertEqual(issues, ["early_hidden_relation"])

    def test_collect_backtrace_writer_issues_does_not_treat_non_aux_constructed_point_as_aux_start(self):
        writer_handoff = {
            "goal_nl": "triangles ach and dbh are congruent",
            "backtrace_stages": [
                {
                    "claim_nl": "triangles ach and dbh are congruent",
                    "depth": 0,
                    "visible_support_nl": [],
                    "subgoal_claims_nl": ["bh equals ch"],
                    "stage_type": "visible_backtrace",
                },
                {
                    "claim_nl": "bh equals ch",
                    "depth": 1,
                    "stage_type": "aux_boundary",
                    "aux_boundary_h_nl": [],
                    "aux_boundary_non_h_nl": [],
                },
            ],
            "terminal_claims_nl": ["bh equals ch"],
            "aux_construction_nl": (
                "construct point i such that i is the midpoint of ac. "
                "then construct point j such that a, c, j are collinear and e, f, j are collinear"
            ),
        }
        body = (
            "To establish that triangles ach and dbh are congruent, we reduce the task to the subgoal that bh equals ch. "
            "Next, we examine the claim that bh equals ch. "
            "Point h is constructed based on points d and g, while b and c are foundational points. "
            "Consequently, the visible route reaches its limit here, as the existing geometry does not enforce this equality without further intervention. "
            "We construct point i such that i is the midpoint of ac. "
            "Then we construct point j such that a, c, j are collinear and e, f, j are collinear."
        )

        issues = collect_backtrace_writer_issues(
            body,
            writer_handoff=writer_handoff,
            backtrace_slots={"H_relations_nl": []},
            aux_part="<aux>x00 i : midp i a c [010] ; x00 j : coll a c j [011] coll e f j [012] ; </aux>",
        )

        self.assertEqual(issues, [])

    def test_process_and_generate_sft_runs_backtrace_text_v2_without_image_inputs(self):
        record = _build_backtrace_record()

        body = (
            "The target is ratio ab to bc equals ratio be to ce. "
            "For this claim, the visible support already includes ab equals ac, but we still need angle ab/bc equals angle be/ce. "
            "For angle ab/bc equals angle be/ce, the visible support already includes angle ab/ac equals angle bc/bd, but that is still not enough by itself to finish the visible route. "
            "So we need a new helper: construct point f such that f is the midpoint of ad. "
            "After introducing f, we can get bf equals cf; together with angle ab/ac equals angle bc/bd, this reaches angle ab/bc equals angle be/ce."
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            input_path = temp_dir_path / "input.jsonl"
            output_path = temp_dir_path / "out.jsonl"
            run_dir = temp_dir_path / "artifacts"
            input_path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")

            with patch(
                "experiments.cot_sft_generation.generate_cot_sft.call_model",
                side_effect=[body],
            ), patch(
                "experiments.cot_sft_generation.generate_cot_sft._encode_image_base64",
                side_effect=AssertionError("backtrace_text_v2 must not encode images"),
            ):
                result = process_and_generate_sft(
                    input_jsonl=str(input_path),
                    output_jsonl=str(output_path),
                    sample_size=1,
                    num_workers=1,
                    model_name="fixture-model",
                    verbose=True,
                    random_sample=False,
                    process_all=False,
                    max_retries=1,
                    generation_style=BACKTRACE_TEXT_V2,
                    run_dir=run_dir,
                )

            output_records = [
                json.loads(line)
                for line in output_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            item_records = [
                json.loads(line)
                for line in (run_dir / "item_records.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(result["summary"]["generation_style"], BACKTRACE_TEXT_V2)
        self.assertEqual(len(output_records), 1)
        self.assertNotIn("image_path", output_records[0])
        self.assertEqual(item_records[0]["plan_prompt"], None)
        self.assertEqual(item_records[0]["plan_output"], None)
        self.assertEqual(item_records[0]["plan_parsed"], None)
        self.assertEqual(item_records[0]["insight_plan_parsed"], None)
        self.assertIsInstance(item_records[0]["backtrace_slots"], dict)
        self.assertIsInstance(item_records[0]["writer_handoff"], dict)
        self.assertEqual(item_records[0]["writer_validation_issues"], [])
        self.assertTrue(item_records[0]["thinking"].startswith("<thinking>"))
        self.assertNotIn("missing_image", item_records[0]["source_audit"]["issues"])
        self.assertNotIn("missing_point_coords", item_records[0]["source_audit"]["issues"])

    def test_parse_args_defaults_generation_style_to_backtrace_text_v2(self):
        with patch("sys.argv", ["generate_cot_sft.py"]):
            args = parse_args()

        self.assertEqual(args.generation_style, BACKTRACE_TEXT_V2)

    def test_collect_backtrace_writer_issues_rejects_proof_leak_wrong_order_and_aux_drift(self):
        record = _build_backtrace_record()
        dag = parse_proof_dag(record["llm_output_renamed"])
        slots = extract_backtrace_slots(
            dag,
            visible_goal="eqratio a b b c b e c e",
            aux_part="<aux>x00 f : midp f a d [100] ; </aux>",
        )
        handoff = build_backtrace_writer_handoff(slots)

        leak_issues = collect_backtrace_writer_issues(
            (
                "The target is ratio ab to bc equals ratio be to ce. "
                "For this claim, the visible support already includes ab equals ac, but proof [015] with r33 says angle ab/bc equals angle be/ce is the key hidden step. "
                "So we need a new helper: construct point f such that f is the midpoint of ad."
            ),
            writer_handoff=handoff,
            backtrace_slots=slots,
            aux_part="<aux>x00 f : midp f a d [100] ; </aux>",
        )
        self.assertIn("proof_marker_leak", leak_issues)

        wrong_order_issues = collect_backtrace_writer_issues(
            (
                "Construct point f such that f is the midpoint of ad. "
                "The target is ratio ab to bc equals ratio be to ce. "
                "Working backward, that would be available once angle ab/bc equals angle be/ce is secured."
            ),
            writer_handoff=handoff,
            backtrace_slots=slots,
            aux_part="<aux>x00 f : midp f a d [100] ; </aux>",
        )
        self.assertIn("narrative_order_violation", wrong_order_issues)

        aux_drift_issues = collect_backtrace_writer_issues(
            (
                "The target is ratio ab to bc equals ratio be to ce. "
                "For this claim, the visible support already includes ab equals ac, but we still need angle ab/bc equals angle be/ce. "
                "For angle ab/bc equals angle be/ce, the visible support already includes angle ab/ac equals angle bc/bd, but that is still not enough by itself to finish the visible route. "
                "So we need a new helper: construct point g such that g lies on ad."
            ),
            writer_handoff=handoff,
            backtrace_slots=slots,
            aux_part="<aux>x00 f : midp f a d [100] ; </aux>",
        )
        self.assertIn("aux_construction_misaligned", aux_drift_issues)

    def test_process_and_generate_sft_persists_writer_validation_issues_on_bad_sample(self):
        record = _build_backtrace_record()
        bad_body = (
            "Construct point f such that f is the midpoint of ad. "
            "The target is ratio ab to bc equals ratio be to ce. "
            "For this claim, the visible support already includes ab equals ac, but we still need angle ab/bc equals angle be/ce."
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            input_path = temp_dir_path / "input.jsonl"
            output_path = temp_dir_path / "out.jsonl"
            run_dir = temp_dir_path / "artifacts"
            input_path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")

            with patch(
                "experiments.cot_sft_generation.generate_cot_sft.call_model",
                side_effect=[bad_body],
            ):
                result = process_and_generate_sft(
                    input_jsonl=str(input_path),
                    output_jsonl=str(output_path),
                    sample_size=1,
                    num_workers=1,
                    model_name="fixture-model",
                    verbose=True,
                    random_sample=False,
                    process_all=False,
                    max_retries=1,
                    generation_style=BACKTRACE_TEXT_V2,
                    run_dir=run_dir,
                )

            output_records = [
                json.loads(line)
                for line in output_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            item_records = [
                json.loads(line)
                for line in (run_dir / "item_records.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(result["summary"]["surface_fail_items"], 1)
        self.assertEqual(output_records, [])
        self.assertIn("narrative_order_violation", item_records[0]["writer_validation_issues"])

    def test_replay_artifact_checks_revalidates_backtrace_item_record(self):
        record = _build_backtrace_record()
        body = (
            "The target is ratio ab to bc equals ratio be to ce. "
            "For this claim, the visible support already includes ab equals ac, but we still need angle ab/bc equals angle be/ce. "
            "For angle ab/bc equals angle be/ce, the visible support already includes angle ab/ac equals angle bc/bd, but that is still not enough by itself to finish the visible route. "
            "So we need a new helper: construct point f such that f is the midpoint of ad. "
            "After introducing f, we can get bf equals cf; together with angle ab/ac equals angle bc/bd, this reaches angle ab/bc equals angle be/ce."
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            input_path = temp_dir_path / "input.jsonl"
            output_path = temp_dir_path / "out.jsonl"
            run_dir = temp_dir_path / "artifacts"
            input_path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")

            with patch(
                "experiments.cot_sft_generation.generate_cot_sft.call_model",
                side_effect=[body],
            ):
                process_and_generate_sft(
                    input_jsonl=str(input_path),
                    output_jsonl=str(output_path),
                    sample_size=1,
                    num_workers=1,
                    model_name="fixture-model",
                    verbose=True,
                    random_sample=False,
                    process_all=False,
                    max_retries=1,
                    generation_style=BACKTRACE_TEXT_V1,
                    run_dir=run_dir,
                )

            item_record = json.loads((run_dir / "item_records.jsonl").read_text(encoding="utf-8").splitlines()[0])

        rechecked = recheck_item_record(item_record)
        self.assertTrue(rechecked["revalidated_plan_ok"])
        self.assertTrue(rechecked["writer_valid"])
        self.assertTrue(rechecked["thinking_valid"])
        self.assertTrue(rechecked["current_all_checks_pass"])


if __name__ == "__main__":
    unittest.main()
