"""
Primitive geometry utilities.

Provides basic geometric constants and utility functions for coordinate
rounding and direction normalization.
"""

import numpy as np

# Floating point comparison tolerance
TOLERANCE = 1e-8

# Number of decimal places for coordinate rounding
ROUND_DECIMALS = 9


def round_coord(coord: tuple[float, float]) -> tuple[float, float]:
    """
    Round coordinates to avoid floating point errors.

    Args:
        coord: A tuple of (x, y) coordinates.

    Returns:
        A tuple of rounded (x, y) coordinates.
    """
    return (round(coord[0], ROUND_DECIMALS), round(coord[1], ROUND_DECIMALS))


def normalize_direction(dx: float, dy: float) -> tuple[float, float]:
    """
    Normalize a direction vector to unit length.

    Args:
        dx: The x component of the direction vector.
        dy: The y component of the direction vector.

    Returns:
        A tuple of (dx, dy) normalized to unit length.
        Returns (0.0, 0.0) if the input vector has zero length.
    """
    norm = np.sqrt(dx**2 + dy**2)
    if norm < TOLERANCE:
        return (0.0, 0.0)
    return (dx / norm, dy / norm)
