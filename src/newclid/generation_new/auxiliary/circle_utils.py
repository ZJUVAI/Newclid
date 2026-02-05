"""
Circle utilities for geometric calculations.

Provides functions for finding circles through points and checking
if points lie on circles.
"""

from collections import defaultdict
from itertools import combinations

import numpy as np

from .primitives import TOLERANCE


def circles(
    point_names: list[str],
    coords: dict[str, tuple[float, float]]
) -> list[dict]:
    """
    Find all circles defined by three or more concyclic points.

    Args:
        point_names: List of point names.
        coords: Dict mapping point names to (x, y) coordinates.

    Returns:
        List of circle dicts, each containing:
        - "center": (x, y) tuple of circle center
        - "radius": Circle radius
        - "points": Sorted list of point names on the circle
        Sorted by number of points (descending) then radius.
    """
    def get_circle_from_three(p1: str, p2: str, p3: str):
        """Calculate circle through three points. Returns None if collinear."""
        A = coords[p1]
        B = coords[p2]
        C = coords[p3]

        ba = (B[0] - A[0], B[1] - A[1])
        ca = (C[0] - A[0], C[1] - A[1])

        # Check for collinearity
        cross = ba[0] * ca[1] - ba[1] * ca[0]
        if abs(cross) < TOLERANCE:
            return None

        # Determinant D
        D = 2 * (
            A[0] * (B[1] - C[1]) +
            B[0] * (C[1] - A[1]) +
            C[0] * (A[1] - B[1])
        )
        if abs(D) < TOLERANCE:
            return None

        # Circle center coordinates
        ux = (
            (A[0]**2 + A[1]**2) * (B[1] - C[1]) +
            (B[0]**2 + B[1]**2) * (C[1] - A[1]) +
            (C[0]**2 + C[1]**2) * (A[1] - B[1])
        ) / D

        uy = (
            (A[0]**2 + A[1]**2) * (C[0] - B[0]) +
            (B[0]**2 + B[1]**2) * (A[0] - C[0]) +
            (C[0]**2 + C[1]**2) * (B[0] - A[0])
        ) / D

        center = (ux, uy)
        radius = np.hypot(ux - A[0], uy - A[1])
        return center, radius

    def point_on_circle(pt_name: str, center: tuple, radius: float) -> bool:
        """Check if a point lies on a circle."""
        px, py = coords[pt_name]
        cx, cy = center
        dist = np.hypot(cx - px, cy - py)
        return abs(dist - radius) < 1e-8

    # Collect all circles from point triplets
    raw_circles = defaultdict(set)
    for comb in combinations(point_names, 3):
        cir = get_circle_from_three(*comb)
        if cir is not None:
            raw_circles[cir].update(comb)

    # Extend circles with all points that lie on them
    circle_list = []
    for (center, radius), pts_set in raw_circles.items():
        all_pts = set(pts_set)
        for pt in point_names:
            if pt not in all_pts:
                if point_on_circle(pt, center, radius):
                    all_pts.add(pt)
        if len(all_pts) >= 3:
            circle_list.append({
                "center": center,
                "radius": radius,
                "points": sorted(all_pts)
            })

    # Deduplicate circles with same point set
    circles_by_points = defaultdict(list)
    for cir in circle_list:
        key = frozenset(cir["points"])
        circles_by_points[key].append(cir)

    # Take representative circle for each point set
    dedup_circles = []
    for points_key, group in circles_by_points.items():
        if len(group) == 1:
            dedup_circles.append(group[0])
        else:
            # Sort by radius and take middle one
            group.sort(key=lambda x: x["radius"])
            rep = group[len(group) // 2]
            dedup_circles.append({
                "center": rep["center"],
                "radius": rep["radius"],
                "points": sorted(points_key)
            })

    # Sort by number of points (descending) then radius
    dedup_circles.sort(key=lambda x: (-len(x["points"]), x["radius"]))
    return dedup_circles


def check_on_circle(
    coord: tuple[float, float],
    all_circles: list[dict],
    coords: dict[str, tuple[float, float]]
) -> bool:
    """
    Check if a point lies on any circle.

    Args:
        coord: The (x, y) coordinate to check.
        all_circles: List of circle dicts with "center" and "radius" keys.
        coords: Dict mapping point names to coordinates (unused but kept for API consistency).

    Returns:
        True if the point lies on any circle.
    """
    for cir in all_circles:
        cx, cy = cir["center"]
        r = cir["radius"]
        dist = np.hypot(coord[0] - cx, coord[1] - cy)
        if abs(dist - r) < TOLERANCE:
            return True
    return False
