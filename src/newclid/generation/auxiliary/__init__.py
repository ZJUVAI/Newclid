"""
Auxiliary points module for geometric constructions.

This module provides utilities for finding and adding meaningful auxiliary points
to constructions, including intersections, midpoints, reflections, and feet.

Public API:
    add_potential_points: Main entry point for finding auxiliary points
"""

from .find_points import add_potential_points

__all__ = [
    "add_potential_points",
]
