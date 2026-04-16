"""Tests for construction config loading and resolution."""

import pytest
from newclid.generation.constructions import (
    BASIC,
    BASIC_FREE,
    INTERSECT,
    OTHER,
    STEP_KEYS,
    load_default_construction_config,
    resolve_construction_config,
)


class TestDefaultConfig:
    def test_load_default_config(self):
        config = load_default_construction_config()
        assert isinstance(config, dict)
        assert "construction_sets" in config
        for key in STEP_KEYS:
            assert key in config

    def test_default_sets_are_lists(self):
        assert isinstance(BASIC, list)
        assert isinstance(BASIC_FREE, list)
        assert isinstance(INTERSECT, list)
        assert isinstance(OTHER, list)
        assert len(BASIC) > 0

    def test_basic_free_and_basic_are_disjoint(self):
        """BASIC_FREE and BASIC should be separate categories."""
        assert len(set(BASIC_FREE)) > 0
        assert len(set(BASIC)) > 0


class TestResolveConfig:
    def test_resolve_default_config(self):
        result = resolve_construction_config(None)
        assert "step1_pool" in result
        assert "step2_pool" in result
        assert "step3_pool" in result
        assert len(result["step1_pool"]) > 0

    def test_resolve_custom_config(self):
        custom = {
            "construction_sets": {
                "S1": ["triangle", "free"],
                "S2": ["on_line"],
            },
            "step1_sets": ["S1"],
            "step2_intersect_sets": ["S2"],
            "step3_single_sets": ["S1"],
        }
        result = resolve_construction_config(custom)
        assert "triangle" in result["step1_pool"]
        assert "free" in result["step1_pool"]
        assert "on_line" in result["step2_pool"]

    def test_resolve_with_unknown_set_name(self):
        custom = {
            "construction_sets": {"S1": ["triangle"]},
            "step1_sets": ["UNKNOWN"],
            "step2_intersect_sets": ["S1"],
            "step3_single_sets": ["S1"],
        }
        with pytest.raises(ValueError, match="unknown construction set"):
            resolve_construction_config(custom)

    def test_resolve_with_empty_pool(self):
        custom = {
            "construction_sets": {"S1": []},
            "step1_sets": ["S1"],
            "step2_intersect_sets": ["S1"],
            "step3_single_sets": ["S1"],
        }
        with pytest.raises(ValueError, match="empty pool"):
            resolve_construction_config(custom)

    def test_resolve_missing_step_key(self):
        custom = {
            "construction_sets": {"S1": ["triangle"]},
            "step1_sets": ["S1"],
            # missing step2_intersect_sets and step3_single_sets
        }
        with pytest.raises(ValueError, match="missing required keys"):
            resolve_construction_config(custom)
