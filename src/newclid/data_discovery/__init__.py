"""
DEPRECATED: This module has been reorganized into newclid.proof_scout

Please update your imports:
  - newclid.data_discovery.proof_graph -> newclid.proof_scout.core.proof_graph
  - newclid.data_discovery.filter_and_prune_engine -> newclid.proof_scout.core.filter_and_prune_engine
  - newclid.data_discovery.rule_extractor -> newclid.proof_scout.extraction.rule_extractor

This compatibility layer will be removed in a future version.
"""

import warnings

warnings.warn(
    "newclid.data_discovery is deprecated and will be removed in a future version. "
    "Please use newclid.proof_scout instead.",
    DeprecationWarning,
    stacklevel=2
)

# Re-export from new locations for backward compatibility
from newclid.proof_scout.core import (
    ProofGraph,
    SingleProofGraph,
    GraphPruner,
    FilterAndPruneEngine,
    AuxExtractor,
)
from newclid.proof_scout.extraction import RuleExtractor

# Lazy import for ProofGraphVisualizer to avoid visualization dependencies
def __getattr__(name):
    if name == "ProofGraphVisualizer":
        from newclid.proof_scout.core import ProofGraphVisualizer
        return ProofGraphVisualizer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "ProofGraph",
    "SingleProofGraph",
    "GraphPruner",
    "ProofGraphVisualizer",
    "FilterAndPruneEngine",
    "AuxExtractor",
    "RuleExtractor",
]
