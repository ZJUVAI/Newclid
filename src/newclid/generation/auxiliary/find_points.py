"""
Auxiliary point discovery utilities.

Provides the main entry point for finding potential auxiliary points
by randomly selecting and filtering geometric constructions.
"""

import random

from .utils import round_coord, is_point_too_close, is_point_too_far
from .line_utils import lines
from .circle_utils import circles
from .intersection import (
    intersection_between_lines,
    intersection_between_circles,
    intersection_between_line_and_circle,
    midpoint,
    reflection,
    foot,
)


def add_potential_points(
    point_names: list[str],
    coords: dict[str, tuple[float, float]],
    max_points: int = 2
) -> list[tuple[tuple[float, float], list[tuple[str, list[str]]]]]:
    """
    Find potential auxiliary points.

    Args:
        point_names: List of existing point names.
        coords: Dict mapping point names to (x, y) coordinates.
        max_points: Maximum number of points to return.

    Returns:
        List of (coord, constructions) tuples where:
        - coord: (x, y) coordinate of the auxiliary point
        - constructions: List of (construction_type, args) tuples,
          e.g., [("midpoint", ["a", "b"])] or
          [("on_line", ["a", "b"]), ("on_line", ["c", "d"])]
    """
    # Randomly select point types to consider
    all_types = list(range(6))  # 0..5 for six types
    random.shuffle(all_types)
    max_type_count = max(1, min(max_points, len(all_types)))
    type_count = random.randint(1, max_type_count)
    selected_types = all_types[:type_count]

    # Pre-compute lines and circles for types that need them
    # Type 0 (line-line), 2 (line-circle), 3 (midpoint), 4 (reflection), 5 (foot) need lines
    # Type 1 (circle-circle), 2 (line-circle), 3 (midpoint), 4 (reflection) need circles
    needs_lines = any(t in selected_types for t in [0, 2, 3, 4, 5])
    needs_circles = any(t in selected_types for t in [1, 2, 3, 4])

    lines_result = lines(point_names, coords) if needs_lines else None
    circles_result = circles(point_names, coords) if needs_circles else None

    # Pre-compute rounded_coords for intersection functions (computed once, used by all)
    needs_rounded = any(t in selected_types for t in [0, 1, 2])
    rounded_coords = {name: round_coord(coords[name]) for name in point_names} if needs_rounded else None

    # Compute potential points only for selected types
    type_to_points: dict[int, list[tuple[tuple[float, float], list[tuple[str, list[str]]]]]] = {}
    for t in selected_types:
        if t == 0:
            type_to_points[t] = intersection_between_lines(point_names, coords, lines_result, rounded_coords)
        elif t == 1:
            type_to_points[t] = intersection_between_circles(point_names, coords, circles_result, rounded_coords)
        elif t == 2:
            type_to_points[t] = intersection_between_line_and_circle(point_names, coords, lines_result, circles_result, rounded_coords)
        elif t == 3:
            type_to_points[t] = midpoint(point_names, coords, lines_result, circles_result)
        elif t == 4:
            type_to_points[t] = reflection(point_names, coords, lines_result, circles_result)
        elif t == 5:
            type_to_points[t] = foot(point_names, coords, lines_result)

    # Return empty if no potential points found
    if all(len(v) == 0 for v in type_to_points.values()):
        return []

    result = []
    existing_coords = list(coords.values())

    # Limit attempts to avoid infinite loop
    max_trials = max_points * 20
    trials = 0

    while len(result) < max_points and trials < max_trials:
        trials += 1

        # Select a random type from selected types
        t = random.choice(selected_types)
        candidates = type_to_points.get(t, [])
        if not candidates:
            continue

        # Select a random candidate
        coord, constructions = random.choice(candidates)

        # Distance filtering
        if is_point_too_close([coord], existing_coords) or is_point_too_far([coord], existing_coords):
            # Remove unsuitable point from candidates
            type_to_points[t] = [item for item in candidates if item[0] != coord]
            continue

        # Add the point
        existing_coords.append(coord)
        result.append((coord, constructions))

        # Remove used point from candidates
        type_to_points[t] = [item for item in candidates if item[0] != coord]

    return result
