import unittest
from pathlib import Path

from experiments.cot_sft_generation.audits import (
    audit_source_record,
    bridge_step_relation_realized,
    build_visible_premise_summaries,
    extract_visible_formal_facts,
    get_point_coords,
)


class CotSftAuditsTest(unittest.TestCase):
    def test_get_point_coords_normalizes_grid_coord(self):
        coords = get_point_coords({"grid_coord": {"A": [1, 2], "b": (3, 4)}})

        self.assertEqual(coords, {"A": (1, 2), "b": (3, 4)})

    def test_extract_visible_formal_facts_ignores_goal_clause(self):
        record = {
            "llm_input_renamed": (
                "<problem>g1: para a b c d [000] ; g2: cong a b a c [001] ? "
                "eqangle a b c d</problem>"
            )
        }

        facts = extract_visible_formal_facts(record)

        self.assertEqual(len(facts), 2)
        self.assertEqual(facts[0]["predicate"], "para")
        self.assertEqual(facts[1]["predicate"], "cong")

    def test_build_visible_premise_summaries_deduplicates_visible_facts(self):
        record = {
            "llm_input_renamed": (
                "<problem>g1: para a b c d [000] ; g2: para a b c d [001] ; "
                "g3: cong a b a c [002] ? eqangle a b c d</problem>"
            )
        }

        summaries = build_visible_premise_summaries(record)

        self.assertEqual(
            summaries,
            ["line ab is parallel to line cd", "ab equals ac"],
        )

    def test_audit_source_record_flags_missing_goal_finish_guidance(self):
        record = {
            "llm_input_renamed": "<problem>g1: cong a b a c [000] ? eqangle a b a c</problem>",
            "point_coords_grid": {"a": [0, 0], "b": [1, 0], "c": [0, 1]},
        }

        audit = audit_source_record(
            record,
            image_path=Path("/tmp/nonexistent.png"),
            aux_part="<aux>x00 d : coll d a b [001] ; </aux>",
            visible_goal="eqangle a b a c",
            proof_guidance={},
        )

        self.assertTrue(audit["has_issue"])
        self.assertIn("missing_image", audit["issues"])
        self.assertIn("proof_guidance_missing_goal_finish_relations", audit["issues"])

    def test_bridge_step_relation_realized_requires_explicit_relation(self):
        step = {
            "relation": "de equals ce",
            "approved_route_relation": "de equals ce",
        }

        self.assertTrue(
            bridge_step_relation_realized(
                "Because de equals ce, this supplies the equality needed next.",
                step,
            )
        )
        self.assertFalse(
            bridge_step_relation_realized(
                "This prepares the next equality without naming the relation.",
                step,
            )
        )


if __name__ == "__main__":
    unittest.main()
