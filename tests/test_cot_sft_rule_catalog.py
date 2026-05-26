"""Tests for core/rule_catalog.py — rule name translation."""

import unittest
from pathlib import Path

from experiments.cot_sft_generation.core.rule_catalog import (
    load_rule_catalog,
    humanize_rule,
    expected_numerical_predicates,
    RuleEntry,
    _HUMAN_NAME_OVERRIDES,
)

RULES_FILE = Path("src/newclid/default_configs/rules.txt")


class TestLoadRuleCatalog(unittest.TestCase):
    def test_parses_rules_file(self):
        catalog = load_rule_catalog(RULES_FILE)
        self.assertGreater(len(catalog), 20)
        self.assertIn("r03", catalog)
        entry = catalog["r03"]
        self.assertIsInstance(entry, RuleEntry)
        self.assertEqual(entry.rule_id, "r03")
        self.assertIn("cyclic", entry.lhs_predicates)
        self.assertIn("eqangle", entry.rhs_predicates)

    def test_parses_similarity_rules(self):
        catalog = load_rule_catalog(RULES_FILE)
        self.assertIn("r34", catalog)
        entry = catalog["r34"]
        self.assertIn("eqangle", entry.lhs_predicates)
        self.assertIn("sameclock", entry.lhs_predicates)
        self.assertIn("simtri", entry.rhs_predicates)

    def test_missing_file_returns_empty(self):
        catalog = load_rule_catalog("/nonexistent/path.txt")
        self.assertEqual(catalog, {})


class TestHumanizeRule(unittest.TestCase):
    def test_overrides_applied(self):
        self.assertEqual(humanize_rule("r03"), "by the inscribed angle theorem")
        self.assertEqual(humanize_rule("r34"), "by AA similarity")
        self.assertEqual(humanize_rule("r07"), "by Thales' theorem")
        self.assertEqual(humanize_rule("r62"), "by SAS similarity")
        self.assertEqual(humanize_rule("r57"), "by the Pythagorean theorem")

    def test_ar_returns_algebraic_combination(self):
        self.assertEqual(humanize_rule("AR"), "by algebraic combination")
        self.assertEqual(humanize_rule("ar"), "by algebraic combination")

    def test_unknown_id_returns_fallback(self):
        self.assertEqual(humanize_rule("r999"), "by a standard geometric identity")
        self.assertEqual(humanize_rule(""), "by a standard geometric identity")
        self.assertEqual(humanize_rule(None), "by a standard geometric identity")

    def test_non_overridden_rule_uses_raw_name(self):
        catalog = load_rule_catalog(RULES_FILE)
        for rule_id, entry in catalog.items():
            result = humanize_rule(rule_id)
            self.assertTrue(result.startswith("by "), f"{rule_id}: {result}")


class TestExpectedNumericalPredicates(unittest.TestCase):
    def test_similarity_rules_need_sameclock(self):
        self.assertIn("sameclock", expected_numerical_predicates("r34"))
        self.assertIn("sameclock", expected_numerical_predicates("r35"))
        self.assertIn("sameclock", expected_numerical_predicates("r60"))
        self.assertIn("sameclock", expected_numerical_predicates("r62"))
        self.assertIn("sameclock", expected_numerical_predicates("r63"))

    def test_inscribed_angle_no_numerical(self):
        self.assertEqual(expected_numerical_predicates("r03"), set())

    def test_same_chord_needs_sameclock_and_sameside(self):
        preds = expected_numerical_predicates("r58")
        self.assertIn("sameclock", preds)
        self.assertIn("sameside", preds)

    def test_unknown_rule_returns_empty(self):
        self.assertEqual(expected_numerical_predicates("r999"), set())
        self.assertEqual(expected_numerical_predicates("AR"), set())

    def test_converse_inscribed_angle_needs_ncoll(self):
        preds = expected_numerical_predicates("r04")
        self.assertIn("ncoll", preds)


if __name__ == "__main__":
    unittest.main()
