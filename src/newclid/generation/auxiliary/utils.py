"""
Core utility functions for auxiliary point generation.

Provides:
- Geometric constants (TOLERANCE, ROUND_DECIMALS)
- Coordinate rounding and direction normalization
- Distance validation (too close/too far checks)
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


def is_point_too_close(
    new_coords: list[tuple[float, float]],
    existing_coords: list[tuple[float, float]],
    tol: float = 0.05,
    round_eps: float = 1e-10
) -> bool:
    """
    Check if new points are too close to existing points.

    A point is considered "too close" if its distance to any existing point
    is between round_eps and tol * average_distance.

    Args:
        new_coords: List of (x, y) coordinates for new points.
        existing_coords: List of (x, y) coordinates for existing points.
        tol: Tolerance factor for minimum distance.
        round_eps: Minimum distance threshold to avoid rounding issues.

    Returns:
        True if any new point is too close to an existing point.
    """
    if len(existing_coords) < 2:
        return False

    # Calculate average pairwise distance
    total_dist = 0.0
    count = 0
    n = len(existing_coords)
    for i in range(n):
        for j in range(i + 1, n):
            x1, y1 = existing_coords[i]
            x2, y2 = existing_coords[j]
            dist = ((x1 - x2)**2 + (y1 - y2)**2) ** 0.5
            total_dist += dist
            count += 1
    avg_dist = total_dist / count

    # Check each new point
    for nx, ny in new_coords:
        for px, py in existing_coords:
            dx = nx - px
            dy = ny - py
            dist = (dx*dx + dy*dy) ** 0.5
            if round_eps < dist < tol * avg_dist:
                return True
    return False


def is_point_too_far(
    new_coords: list[tuple[float, float]],
    existing_coords: list[tuple[float, float]],
    factor: float = 5.0
) -> bool:
    """
    Check if new points are too far from existing points.

    A point is considered "too far" if its distance to any existing point
    exceeds factor * max_distance_from_centroid.

    Args:
        new_coords: List of (x, y) coordinates for new points.
        existing_coords: List of (x, y) coordinates for existing points.
        factor: Factor for maximum allowed distance.

    Returns:
        True if any new point is too far from existing points.
    """
    if len(existing_coords) < 2:
        return False

    # Calculate centroid
    n = len(existing_coords)
    sum_x = sum(x for x, y in existing_coords)
    sum_y = sum(y for x, y in existing_coords)
    avg_x = sum_x / n
    avg_y = sum_y / n

    # Calculate max distance from centroid (scale of point cloud)
    maxdist = 0.0
    for px, py in existing_coords:
        dx = px - avg_x
        dy = py - avg_y
        dist = (dx*dx + dy*dy) ** 0.5
        if dist > maxdist:
            maxdist = dist

    # Check if any new point is too far
    for nx, ny in new_coords:
        for px, py in existing_coords:
            dx = nx - px
            dy = ny - py
            dist = (dx*dx + dy*dy) ** 0.5
            if dist > factor * maxdist:
                return True
    return False
