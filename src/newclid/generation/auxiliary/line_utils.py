"""
Line utilities for geometric calculations.

Provides functions for extracting points, finding lines, and checking
if points lie on lines.
"""

import re
from collections import OrderedDict, defaultdict
from itertools import combinations

import numpy as np

from .utils import TOLERANCE, normalize_direction


def extract_points(text: str) -> tuple[list[str], dict[str, tuple[float, float]]]:
    """
    Extract point names and coordinates from a geometric description string.

    Args:
        text: String containing point definitions in format "name@x_y".

    Returns:
        A tuple of (point_names, coords_dict) where:
        - point_names: List of point names in order of appearance.
        - coords_dict: OrderedDict mapping point names to (x, y) coordinates.
    """
    pattern = r'([a-zA-Z][a-zA0-9]*)@([-+]?\d*\.?\d+)_([-+]?\d*\.?\d+)'
    matches = re.findall(pattern, text)
    original_points = OrderedDict()
    for name, x_str, y_str in matches:
        original_points[name] = (float(x_str), float(y_str))
    point_names = list(original_points.keys())
    return point_names, original_points


def lines(
    point_names: list[str],
    coords: dict[str, tuple[float, float]]
) -> list[tuple[str, ...]]:
    """
    Find all lines defined by collinear points.

    Args:
        point_names: List of point names.
        coords: Dict mapping point names to (x, y) coordinates.

    Returns:
        List of tuples, each containing names of collinear points.
        Sorted by number of points (descending) then alphabetically.
    """
    line_to_points = defaultdict(set)

    # Find all basic lines from point pairs
    for a, b in combinations(point_names, 2):
        if a >= b:
            continue
        p1, p2 = coords[a], coords[b]
        dir_norm = normalize_direction(p2[0] - p1[0], p2[1] - p1[1])
        if dir_norm == (0.0, 0.0):
            continue
        key = (p1[0], p1[1], dir_norm[0], dir_norm[1])
        line_to_points[key].update([a, b])

    # Merge lines and find all collinear points
    final_lines = []
    for key, pts_set in line_to_points.items():
        current_pts = sorted(list(pts_set))
        while True:
            added = False
            max_dist = -1
            base_a, base_b = current_pts[0], current_pts[1]

            # Find the two most distant points as base
            for i in range(len(current_pts)):
                for j in range(i + 1, len(current_pts)):
                    pa = np.array(coords[current_pts[i]])
                    pb = np.array(coords[current_pts[j]])
                    dist_sq = np.sum((pa - pb)**2)
                    if dist_sq > max_dist:
                        max_dist = dist_sq
                        base_a, base_b = current_pts[i], current_pts[j]

            direction = np.subtract(coords[base_b], coords[base_a])
            dir_norm = np.linalg.norm(direction)

            # Check if other points are collinear
            for name in point_names:
                if name in pts_set:
                    continue
                pt = np.array(coords[name])
                vec = pt - np.array(coords[base_a])
                # Distance from point to line (cross product / direction length)
                dist = abs(np.cross(direction, vec)) / dir_norm

                if dist < TOLERANCE:
                    pts_set.add(name)
                    current_pts.append(name)
                    added = True
            if not added:
                break

        if len(pts_set) >= 2:
            final_lines.append(sorted(list(pts_set)))

    # Remove duplicates and sort
    result = sorted(
        {tuple(sorted(line)) for line in final_lines},
        key=lambda x: (-len(x), x)
    )
    return result


def check_on_line(
    coord: tuple[float, float],
    all_lines: list[tuple[str, ...]],
    coords: dict[str, tuple[float, float]],
    current_line: list[list[str]] = None
) -> bool:
    """
    Check if a point lies on any line (excluding specified lines).

    Args:
        coord: The (x, y) coordinate to check.
        all_lines: List of lines (each line is a tuple of point names).
        coords: Dict mapping point names to coordinates.
        current_line: Lines to exclude from checking (optional).

    Returns:
        True if the point lies on any non-excluded line.
    """
    if current_line is None:
        current_line = []
    current_sets = [set(cand) for cand in current_line]

    for line_points in all_lines:
        known_set = set(line_points)
        # Skip if this line is a subset of any excluded line
        if any(curr_set.issubset(known_set) for curr_set in current_sets):
            continue

        x1, y1 = coords[line_points[0]]
        x2, y2 = coords[line_points[1]]
        dx = x2 - x1
        dy = y2 - y1
        line_len = (dx**2 + dy**2)**0.5
        vec_x = coord[0] - x1
        vec_y = coord[1] - y1
        cross = vec_x * dy - vec_y * dx
        dist = abs(cross) / line_len

        if dist <= TOLERANCE:
            return True
    return False
