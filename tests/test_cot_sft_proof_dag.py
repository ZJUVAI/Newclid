"""Tests for core/proof_dag.py — DAG parsing and milestone selection."""

import json
import unittest
from pathlib import Path

from experiments.cot_sft_generation.core.proof_dag import (
    ProofDAG,
    ProofStep,
    Milestone,
    NumericalFact,
    parse_proof_dag,
    parse_numerical_check,
    walk_milestones,
    build_step_natural_language,
    _parse_step_clause,
)

BENCHMARK_FILE = Path("experiments/cot_sft_generation/benchmarks/quality_review_v1/quality_review_v1_input.jsonl")


def _load_benchmark_record(index=0):
    with open(BENCHMARK_FILE) as f:
        for i, line in enumerate(f):
            if i == index:
                return json.loads(line)
    return None


class TestParseStepClause(unittest.TestCase):
    def test_rule_step(self):
        clause = "eqangle a c a d c f d f [012] r03 [006]"
        step = _parse_step_clause(clause)
        self.assertIsNotNone(step)
        self.assertEqual(step.step_id, "012")
        self.assertEqual(step.predicate, "eqangle")
        self.assertEqual(step.args, ["a", "c", "a", "d", "c", "f", "d", "f"])
        self.assertEqual(step.rule_id, "r03")
        self.assertEqual(step.deps, ["006"])

    def test_ar_step_with_multiple_deps(self):
        clause = "eqangle a b a c a d a e [020] AR [007] [010] [011] [019] [000] [003] [012]"
        step = _parse_step_clause(clause)
        self.assertIsNotNone(step)
        self.assertEqual(step.step_id, "020")
        self.assertEqual(step.rule_id, "AR")
        self.assertEqual(step.deps, ["007", "010", "011", "019", "000", "003", "012"])

    def test_simtrir_step(self):
        clause = "simtrir a d f c f d [016] r35 [014] [015] [008]"
        step = _parse_step_clause(clause)
        self.assertIsNotNone(step)
        self.assertEqual(step.predicate, "simtrir")
        self.assertEqual(step.rule_id, "r35")
        self.assertEqual(step.deps, ["014", "015", "008"])

    def test_empty_clause_returns_none(self):
        self.assertIsNone(_parse_step_clause(""))
        self.assertIsNone(_parse_step_clause("   "))

    def test_no_step_id_returns_none(self):
        self.assertIsNone(_parse_step_clause("cong a b c d"))


class TestParseProofDag(unittest.TestCase):
    def test_real_benchmark_record(self):
        record = _load_benchmark_record(1)
        if record is None:
            self.skipTest("Benchmark file not available")
        dag = parse_proof_dag(record["llm_output_renamed"])
        self.assertIsInstance(dag, ProofDAG)
        self.assertEqual(len(dag.steps_by_id), 12)
        self.assertEqual(dag.goal_step_id, "020")

        step_012 = dag.get("012")
        self.assertIsNotNone(step_012)
        self.assertEqual(step_012.rule_id, "r03")
        self.assertEqual(step_012.deps, ["006"])

    def test_numerical_check_parsed(self):
        record = _load_benchmark_record(0)
        if record is None:
            self.skipTest("Benchmark file not available")
        dag = parse_proof_dag(record["llm_output_renamed"])
        self.assertIn("sameclock", dag.numerical_facts)
        self.assertIn("ncoll", dag.numerical_facts)
        self.assertTrue(len(dag.numerical_facts["sameclock"]) >= 5)

    def test_empty_input(self):
        dag = parse_proof_dag("")
        self.assertEqual(len(dag.steps_by_id), 0)
        self.assertEqual(dag.goal_step_id, "")

    def test_no_proof_block(self):
        dag = parse_proof_dag("<aux>x00 h : midp h a d [008] ;</aux>")
        self.assertEqual(len(dag.steps_by_id), 0)


class TestWalkMilestones(unittest.TestCase):
    def test_skips_ar_and_recurses_into_deps(self):
        record = _load_benchmark_record(1)
        if record is None:
            self.skipTest("Benchmark file not available")
        dag = parse_proof_dag(record["llm_output_renamed"])
        milestones = walk_milestones(dag, max_steps=6)
        kinds = [m.kind for m in milestones]
        step_ids = [m.step.step_id for m in milestones]
        self.assertIn("020", step_ids)
        goal_m = [m for m in milestones if m.step.step_id == "020"][0]
        self.assertEqual(goal_m.kind, "ar")
        rule_milestones = [m for m in milestones if m.kind == "rule"]
        self.assertTrue(len(rule_milestones) >= 2)
        self.assertTrue(any(m.step.rule_id == "r03" for m in rule_milestones))

    def test_caps_at_max_steps(self):
        record = _load_benchmark_record(0)
        if record is None:
            self.skipTest("Benchmark file not available")
        dag = parse_proof_dag(record["llm_output_renamed"])
        milestones = walk_milestones(dag, max_steps=4)
        rule_milestones = [m for m in milestones if m.kind == "rule"]
        self.assertTrue(len(rule_milestones) <= 3)

    def test_forward_order(self):
        record = _load_benchmark_record(1)
        if record is None:
            self.skipTest("Benchmark file not available")
        dag = parse_proof_dag(record["llm_output_renamed"])
        milestones = walk_milestones(dag, max_steps=6)
        step_ids = [m.step.step_id for m in milestones]
        self.assertEqual(step_ids, sorted(step_ids))

    def test_empty_dag(self):
        dag = ProofDAG()
        milestones = walk_milestones(dag)
        self.assertEqual(milestones, [])

    def test_ar_only_proof_emits_goal_as_ar(self):
        dag = ProofDAG(
            steps_by_id={
                "001": ProofStep("001", "cong", ["a", "b", "c", "d"], "AR", ["000"], "cong a b c d [001] AR [000]"),
            },
            ordered_step_ids=["001"],
            goal_step_id="001",
        )
        milestones = walk_milestones(dag)
        self.assertEqual(len(milestones), 1)
        self.assertEqual(milestones[0].kind, "ar")
        self.assertEqual(milestones[0].step.step_id, "001")


class TestBuildStepNaturalLanguage(unittest.TestCase):
    def test_cong(self):
        nl = build_step_natural_language("cong", ["a", "b", "c", "d"])
        self.assertIn("equals", nl.lower())

    def test_eqangle(self):
        nl = build_step_natural_language("eqangle", ["a", "b", "c", "d", "e", "f", "g", "h"])
        self.assertIn("angle", nl.lower())

    def test_simtri(self):
        nl = build_step_natural_language("simtri", ["a", "b", "c", "d", "e", "f"])
        self.assertIn("similar", nl.lower())

    def test_cyclic(self):
        nl = build_step_natural_language("cyclic", ["a", "b", "c", "d"])
        self.assertIn("concyclic", nl.lower())


class TestParseNumericalCheck(unittest.TestCase):
    def test_groups_by_predicate(self):
        record = _load_benchmark_record(0)
        if record is None:
            self.skipTest("Benchmark file not available")
        facts = parse_numerical_check(record["llm_output_renamed"])
        self.assertIn("sameclock", facts)
        self.assertIn("ncoll", facts)
        for fact in facts["sameclock"]:
            self.assertIsInstance(fact, NumericalFact)
            self.assertEqual(fact.predicate, "sameclock")


if __name__ == "__main__":
    unittest.main()
