"""Tests for PointNaming utility."""

import pytest
from newclid.generation.point_naming import PointNaming


class TestGetPointName:
    def test_single_letter_names(self):
        pn = PointNaming()
        assert pn.get_point_name(0) == "a"
        assert pn.get_point_name(1) == "b"
        assert pn.get_point_name(25) == "z"

    def test_numbered_names(self):
        pn = PointNaming()
        assert pn.get_point_name(26) == "a0"
        assert pn.get_point_name(27) == "b0"
        assert pn.get_point_name(51) == "z0"
        assert pn.get_point_name(52) == "a1"

    def test_sequential_names(self):
        pn = PointNaming()
        names = [pn.get_point_name(i) for i in range(30)]
        assert names[:3] == ["a", "b", "c"]
        assert names[26] == "a0"
        assert names[29] == "d0"


class TestPrefetchPoints:
    def test_prefetch_basic(self):
        pn = PointNaming()
        result = pn.prefetch_points(3)
        assert result == ["a", "b", "c"]
        # Points not yet defined
        assert pn.defined_points == []

    def test_prefetch_after_define(self):
        pn = PointNaming()
        first = pn.prefetch_points(2)
        pn.define_points(first)
        second = pn.prefetch_points(2)
        assert first == ["a", "b"]
        assert second == ["c", "d"]

    def test_prefetch_exceeds_max(self):
        pn = PointNaming(max_points=5)
        pn.define_points(pn.prefetch_points(3))
        with pytest.raises(ValueError, match="exhausted"):
            pn.prefetch_points(3)  # only 2 slots left


class TestDefinePoints:
    def test_define_increments_count(self):
        pn = PointNaming()
        pn.define_points(["a", "b"])
        assert pn.defined_points == ["a", "b"]
        pn.define_points(["c"])
        assert pn.defined_points == ["a", "b", "c"]

    def test_define_exceeds_max(self):
        pn = PointNaming(max_points=2)
        pn.define_points(["a", "b"])
        with pytest.raises(ValueError, match="exhausted"):
            pn.define_points(["c"])
