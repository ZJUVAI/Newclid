"""
Auxiliary points module for geometric constructions.

This module provides utilities for finding and adding meaningful auxiliary points
to constructions, including intersections, midpoints, reflections, and feet.
"""

from .primitives import TOLERANCE, ROUND_DECIMALS, round_coord, normalize_direction
from .distance import is_point_too_close, is_point_too_far
from .line_utils import extract_points, lines, check_on_line
from .circle_utils import circles, check_on_circle
from .intersection import (
    intersection_between_lines,
    intersection_between_circles,
    intersection_between_line_and_circle,
)
from .finder import midpoint, reflection, foot, add_potential_points

__all__ = [
    # primitives
    "TOLERANCE",
    "ROUND_DECIMALS",
    "round_coord",
    "normalize_direction",
    # distance
    "is_point_too_close",
    "is_point_too_far",
    # line_utils
    "extract_points",
    "lines",
    "check_on_line",
    # circle_utils
    "circles",
    "check_on_circle",
    # intersection
    "intersection_between_lines",
    "intersection_between_circles",
    "intersection_between_line_and_circle",
    # finder
    "midpoint",
    "reflection",
    "foot",
    "add_potential_points",
]
