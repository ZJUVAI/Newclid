"""Tests for ProblemJGEX and Rule parsing."""

import pytest
from newclid.formulations.problem import ProblemJGEX
from newclid.formulations.rule import Rule


class TestProblemJGEX:
    def test_from_text_with_goal(self):
        p = ProblemJGEX.from_text("test_problem\na b c = triangle a b c ? perp a b c d")
        assert p.name == "test_problem"
        assert len(p.constructions) > 0
        assert len(p.goals) > 0
        assert p.goals[0][0] == "perp"

    def test_from_text_without_goal(self):
        p = ProblemJGEX.from_text("a b c = triangle a b c")
        assert p.name == ""
        assert len(p.constructions) > 0
        assert len(p.goals) == 0

    def test_from_text_multiple_clauses(self):
        p = ProblemJGEX.from_text(
            "a b c = triangle a b c; h = on_tline h b a c ? perp a h b c"
        )
        assert len(p.constructions) == 2

    def test_str_roundtrip(self):
        text = "a b c = triangle a b c ? perp a b c d"
        p = ProblemJGEX.from_text(text)
        assert "triangle" in str(p)
        assert "perp" in str(p)

    def test_with_more_construction(self):
        p = ProblemJGEX.from_text("a b = segment a b ? cong a b a b")
        p2 = p.with_more_construction("c = midpoint c a b")
        assert len(p2.constructions) == len(p.constructions) + 1

    def test_parse_txt_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text(
            "prob1\na b = segment a b ? coll a b c\nprob2\na = free a ? coll a b c\n"
        )
        problems = ProblemJGEX.parse_txt_file(f)
        assert "prob1" in problems
        assert "prob2" in problems

    def test_from_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("my_problem\na b = segment a b ? coll a b c\n")
        p = ProblemJGEX.from_file(f, "my_problem")
        assert p.name == "my_problem"

    def test_from_file_not_found(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("my_problem\na b = segment a b ? coll a b c\n")
        with pytest.raises(ValueError, match="not found"):
            ProblemJGEX.from_file(f, "nonexistent")


class TestRule:
    def test_parse_single_rule(self):
        rules = Rule.parse_text("perp A B C D, perp C D E F => para A B E F")
        assert len(rules) == 1
        assert len(rules[0].premises) == 2
        assert len(rules[0].conclusions) == 1

    def test_parse_multiple_rules(self):
        text = (
            "r00\nperp A B C D, perp C D E F => para A B E F\n"
            "r01\ncyclic A B P Q => eqangle P A P B Q A Q B\n"
        )
        rules = Rule.parse_text(text)
        assert len(rules) == 2

    def test_rule_str(self):
        rules = Rule.parse_text("perp A B C D => para A B E F")
        assert "=>" in str(rules[0])

    def test_parse_txt_file(self, tmp_path):
        f = tmp_path / "rules.txt"
        f.write_text("perp A B C D, perp C D E F => para A B E F\n")
        rules = Rule.parse_txt_file(f)
        assert len(rules) == 1
