"""
Proof Scout - Knowledge Discovery and Theorem Extraction Module

This module provides tools for analyzing proof graphs and extracting geometric theorems.

Submodules:
- core: Core graph structures and utilities (no ML dependencies)
- extraction: Rule extraction utilities (no ML dependencies)
- ml: Machine learning components (requires torch, etc.)
- docs: Documentation

Quick Start:
    from newclid.proof_scout import ProofGraph, GraphPruner
    from newclid.proof_scout.core import FilterAndPruneEngine
    from newclid.proof_scout.extraction import RuleExtractor
"""

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
    # Core
    "ProofGraph",
    "SingleProofGraph",
    "GraphPruner",
    "ProofGraphVisualizer",
    "FilterAndPruneEngine",
    "AuxExtractor",
    # Extraction
    "RuleExtractor",
]
