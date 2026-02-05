"""
Generation module for geometry problem generation.

This module provides tools for:
- Sampling geometric problems and constructions
- Finding and adding auxiliary points
- Filtering goals
- Processing geometry problems
- Generating statistics reports
"""

from newclid.generation_new.auxiliary import (
    TOLERANCE,
    ROUND_DECIMALS,
    round_coord,
    normalize_direction,
    is_point_too_close,
    is_point_too_far,
    extract_points,
    lines,
    check_on_line,
    circles,
    check_on_circle,
    intersection_between_lines,
    intersection_between_circles,
    intersection_between_line_and_circle,
    midpoint,
    reflection,
    foot,
    add_potential_points,
)
from newclid.generation_new.point_naming import PointNaming
from newclid.generation_new.constructions import (
    BASIC,
    BASIC_FREE,
    INTERSECT,
    OTHER,
)
from newclid.generation_new.sampler import ProblemSampler
from newclid.generation_new.filter import GoalFilter
from newclid.generation_new.statistics import Statistics, get_first_predicate
from newclid.generation_new.worker import ProblemWorker
from newclid.generation_new.pipeline import ProblemPipeline

__all__ = [
    # Primitives
    "TOLERANCE",
    "ROUND_DECIMALS",
    "round_coord",
    "normalize_direction",
    # Distance
    "is_point_too_close",
    "is_point_too_far",
    # Line utilities
    "extract_points",
    "lines",
    "check_on_line",
    # Circle utilities
    "circles",
    "check_on_circle",
    # Intersection
    "intersection_between_lines",
    "intersection_between_circles",
    "intersection_between_line_and_circle",
    # Point naming
    "PointNaming",
    # Construction types
    "BASIC",
    "BASIC_FREE",
    "INTERSECT",
    "OTHER",
    # Problem sampler
    "ProblemSampler",
    # Auxiliary points
    "midpoint",
    "reflection",
    "foot",
    "add_potential_points",
    # Goal filter
    "GoalFilter",
    # Statistics
    "Statistics",
    "get_first_predicate",
    # Problem worker
    "ProblemWorker",
    # Problem pipeline
    "ProblemPipeline",
]
