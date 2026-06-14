import unittest

from experiments.cot_sft_generation.core.backtrace_extractor import (
    build_backtrace_writer_handoff,
    extract_backtrace_slots,
)
from experiments.cot_sft_generation.core.proof_dag import parse_proof_dag


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
        self.assertEqual(slots["backtrace_chain_step_ids"], ["015", "014"])
        self.assertEqual(slots["frontier_node_ids"], ["014"])
        self.assertEqual(slots["supporting_c1_by_frontier"], {"014": ["011"]})

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

    def test_build_backtrace_writer_handoff_keeps_minimum_fields(self):
        handoff = build_backtrace_writer_handoff(
            {
                "goal_nl": "ratio ab to bc equals ratio be to ce",
                "backtrace_chain_nl": ["ratio ab to bc equals ratio be to ce"],
                "frontier_nodes_nl": ["angle ab/bc equals angle be/ce"],
                "supporting_c1_facts_nl": {"angle ab/bc equals angle be/ce": ["angle ab/ac equals angle bc/bd"]},
                "aux_construction_nl": "construct point f such that f is the midpoint of ad",
            }
        )

        self.assertEqual(
            handoff,
            {
                "goal_nl": "ratio ab to bc equals ratio be to ce",
                "backtrace_chain_nl": ["ratio ab to bc equals ratio be to ce"],
                "frontier_nodes_nl": ["angle ab/bc equals angle be/ce"],
                "supporting_c1_facts_nl": {
                    "angle ab/bc equals angle be/ce": ["angle ab/ac equals angle bc/bd"]
                },
                "aux_construction_nl": "construct point f such that f is the midpoint of ad",
            },
        )


if __name__ == "__main__":
    unittest.main()
