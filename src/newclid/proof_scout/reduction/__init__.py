#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rule Reduction Module - Eliminate redundant rules via subsumption testing.

This module implements a rule reduction algorithm that:
1. Scores rules by generality (fewer premises = more general)
2. Tests subsumption relationships using formal reasoning
3. Eliminates redundant rules to produce a minimal basis set

Key classes:
- RuleReducer: Main reduction orchestrator
- GeneralityScorer: Compute rule generality scores
- SubsumptionTester: Test if one rule subsumes another
- DAGRetriever: (Phase 2+) Accelerate subsumption testing with DAG-based retrieval
"""

from newclid.proof_scout.reduction.rule_reducer import (
    RuleReducer,
    RuleWithSource,
    IncrementalReducer,
    ChunkedIterativeReducer,
    load_rules_from_discovery_output,
    load_rules_by_ids,
    stream_chunked_reduce_from_files,
)
from newclid.proof_scout.reduction.generality_scorer import GeneralityScorer
from newclid.proof_scout.reduction.subsumption_tester import SubsumptionTester

__all__ = [
    "RuleReducer",
    "RuleWithSource",
    "IncrementalReducer",
    "ChunkedIterativeReducer",
    "GeneralityScorer",
    "SubsumptionTester",
    "load_rules_from_discovery_output",
    "load_rules_by_ids",
    "stream_chunked_reduce_from_files",
]
