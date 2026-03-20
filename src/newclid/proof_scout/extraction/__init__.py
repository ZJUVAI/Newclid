"""
Proof Scout Extraction Module - Rule extraction utilities (no ML dependencies)

This module provides rule extraction functionality:
- RuleExtractor: Base class for rule extraction
- RuleConverter: Convert Proof Scout rules to DDAR format
- RuleTester: Validate rules using DDAR solver
- extract_rules: Multi-stage rule extraction
- get_minimal_rules: Minimal rule computation
- fold_rules: Rule folding utilities
"""

from newclid.proof_scout.extraction.rule_extractor import (
    RuleExtractor,
    BasicRuleExtractor,
    AdvancedRuleExtractor,
    MLBasedRuleExtractor,
    create_rule_extractor,
)
from newclid.proof_scout.extraction.rule_converter import (
    RuleConverter,
    VALID_PREDICATES,
    PREDICATE_ALIASES,
)
from newclid.proof_scout.extraction.rule_tester import RuleTester

__all__ = [
    "RuleExtractor",
    "BasicRuleExtractor",
    "AdvancedRuleExtractor",
    "MLBasedRuleExtractor",
    "create_rule_extractor",
    "RuleConverter",
    "VALID_PREDICATES",
    "PREDICATE_ALIASES",
    "RuleTester",
]
