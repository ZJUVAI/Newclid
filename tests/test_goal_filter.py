"""Tests for GoalFilter."""

from unittest.mock import MagicMock
import pytest
from newclid.generation.filter import GoalFilter


@pytest.fixture
def goal_filter():
    return GoalFilter()


@pytest.fixture
def mock_dep_graph():
    """A dep_graph where all Statement.check() calls return False."""
    return MagicMock()


class TestNaiveCongFilter:
    def test_reject_same_segment(self, goal_filter, mock_dep_graph):
        assert (
            goal_filter.naive_goal_filter("cong", ["a", "b", "a", "b"], mock_dep_graph)
            is False
        )

    def test_reject_reversed_segment(self, goal_filter, mock_dep_graph):
        assert (
            goal_filter.naive_goal_filter("cong", ["a", "b", "b", "a"], mock_dep_graph)
            is False
        )

    def test_accept_different_segments(self, goal_filter, mock_dep_graph):
        assert (
            goal_filter.naive_goal_filter("cong", ["a", "b", "c", "d"], mock_dep_graph)
            is True
        )


class TestNaiveParaFilter:
    def test_reject_shared_point(self, goal_filter, mock_dep_graph):
        # para AB AC implies collinearity
        assert (
            goal_filter.naive_goal_filter("para", ["a", "b", "a", "c"], mock_dep_graph)
            is False
        )

    def test_accept_distinct_lines(self, goal_filter, mock_dep_graph):
        assert (
            goal_filter.naive_goal_filter("para", ["a", "b", "c", "d"], mock_dep_graph)
            is True
        )


class TestNaiveContriFilter:
    def test_reject_same_triangle(self, goal_filter, mock_dep_graph):
        assert (
            goal_filter.naive_goal_filter(
                "contri", ["a", "b", "c", "a", "b", "c"], mock_dep_graph
            )
            is False
        )

    def test_accept_different_triangles(self, goal_filter, mock_dep_graph):
        assert (
            goal_filter.naive_goal_filter(
                "contri", ["a", "b", "c", "d", "e", "f"], mock_dep_graph
            )
            is True
        )


class TestNaiveRconstFilter:
    def test_reject_ratio_one(self, goal_filter, mock_dep_graph):
        assert (
            goal_filter.naive_goal_filter(
                "rconst", ["a", "b", "c", "d", "1/1"], mock_dep_graph
            )
            is False
        )

    def test_accept_other_ratio(self, goal_filter, mock_dep_graph):
        assert (
            goal_filter.naive_goal_filter(
                "rconst", ["a", "b", "c", "d", "3/4"], mock_dep_graph
            )
            is True
        )


class TestNaiveAconstFilter:
    def test_reject_common_angles(self, goal_filter, mock_dep_graph):
        for angle in ("0pi/1", "1pi/2", "1pi/1", "1pi/3", "2pi/3", "1pi/4", "3pi/4"):
            assert (
                goal_filter.naive_goal_filter(
                    "aconst", ["a", "b", "c", angle], mock_dep_graph
                )
                is False
            )

    def test_accept_uncommon_angle(self, goal_filter, mock_dep_graph):
        assert (
            goal_filter.naive_goal_filter(
                "aconst", ["a", "b", "c", "7pi/20"], mock_dep_graph
            )
            is True
        )


class TestPassthroughPredicates:
    def test_coll_passes(self, goal_filter, mock_dep_graph):
        assert (
            goal_filter.naive_goal_filter("coll", ["a", "b", "c"], mock_dep_graph)
            is True
        )

    def test_perp_passes(self, goal_filter, mock_dep_graph):
        assert (
            goal_filter.naive_goal_filter("perp", ["a", "b", "c", "d"], mock_dep_graph)
            is True
        )

    def test_cyclic_passes(self, goal_filter, mock_dep_graph):
        assert (
            goal_filter.naive_goal_filter(
                "cyclic", ["a", "b", "c", "d"], mock_dep_graph
            )
            is True
        )

    def test_unknown_predicate_rejected(self, goal_filter, mock_dep_graph):
        assert goal_filter.naive_goal_filter("unknown", [], mock_dep_graph) is False


class TestAuxPredicatesValidCheck:
    def test_valid_predicates(self, goal_filter):
        llm_output = (
            "<aux> x00 e : perp a b c d [002] ; x00 f : para c d e f [003] </aux>"
        )
        assert goal_filter.aux_predicates_valid_check(llm_output) is True

    def test_invalid_predicate(self, goal_filter):
        llm_output = "<aux> x00 e : unknown_predicate a b c d [002] </aux>"
        assert goal_filter.aux_predicates_valid_check(llm_output) is False

    def test_no_aux_tag(self, goal_filter):
        assert goal_filter.aux_predicates_valid_check("no aux here") is True

    def test_empty_aux(self, goal_filter):
        assert goal_filter.aux_predicates_valid_check("<aux></aux>") is True

    def test_multiple_predicates(self, goal_filter):
        llm_output = (
            "<aux> x00 e : perp a b c d [002] ; x00 f : cong a b c d [003] </aux>"
        )
        assert goal_filter.aux_predicates_valid_check(llm_output) is True
