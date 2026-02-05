"""
Auxiliary point finder utilities.

Provides functions for finding potential auxiliary points including
midpoints, reflections, feet, and intersections.
"""

import random
from itertools import combinations

from .primitives import TOLERANCE, round_coord
from .distance import is_point_too_close, is_point_too_far
from .line_utils import lines, check_on_line
from .circle_utils import circles, check_on_circle
from .intersection import (
    intersection_between_lines,
    intersection_between_circles,
    intersection_between_line_and_circle,
)


def midpoint(
    point_names: list[str],
    coords: dict[str, tuple[float, float]],
    lines_result: list[tuple[str, ...]] | None = None,
    circles_result: list[dict] | None = None,
) -> list[tuple[tuple[float, float], list[tuple[str, list[str]]]]]:
    """
    Find midpoints that lie on non-trivial lines or circles.

    Args:
        point_names: List of point names.
        coords: Dict mapping point names to (x, y) coordinates.
        lines_result: Optional pre-computed lines result to avoid recomputation.
        circles_result: Optional pre-computed circles result to avoid recomputation.

    Returns:
        List of (coord, constructions) tuples where:
        - coord: (x, y) midpoint coordinate
        - constructions: List of (construction_type, args) tuples,
          e.g., [("midpoint", ["a", "b"])]
    """
    result = []
    ls = lines_result if lines_result is not None else lines(point_names, coords)
    cs = circles_result if circles_result is not None else circles(point_names, coords)

    for p1, p2 in combinations(point_names, 2):
        x1, y1 = coords[p1]
        x2, y2 = coords[p2]
        mid_coord = ((x1 + x2) / 2, (y1 + y2) / 2)

        # Require midpoint to be on a non-trivial line or circle
        if check_on_line(mid_coord, ls, coords, [[p1, p2]]) or check_on_circle(mid_coord, cs, coords):
            constructions = [("midpoint", [p1, p2])]
            result.append((mid_coord, constructions))

    return result


def reflection(
    point_names: list[str],
    coords: dict[str, tuple[float, float]],
    lines_result: list[tuple[str, ...]] | None = None,
    circles_result: list[dict] | None = None,
) -> list[tuple[tuple[float, float], list[tuple[str, list[str]]]]]:
    """
    Find reflection points (over points and lines) that lie on non-trivial lines or circles.

    Args:
        point_names: List of point names.
        coords: Dict mapping point names to (x, y) coordinates.
        lines_result: Optional pre-computed lines result to avoid recomputation.
        circles_result: Optional pre-computed circles result to avoid recomputation.

    Returns:
        List of (coord, constructions) tuples where:
        - coord: (x, y) reflection point coordinate
        - constructions: List of (construction_type, args) tuples,
          e.g., [("mirror", ["p", "c"])] for point reflection
          or [("reflect", ["p", "a", "b"])] for line reflection
    """
    result = []
    ls = lines_result if lines_result is not None else lines(point_names, coords)
    cs = circles_result if circles_result is not None else circles(point_names, coords)

    # Reflection over points
    for center_name in point_names:
        for pt_name in point_names:
            if pt_name == center_name:
                continue
            center_coord = coords[center_name]
            pt_coord = coords[pt_name]
            refl_coord = (
                2 * center_coord[0] - pt_coord[0],
                2 * center_coord[1] - pt_coord[1]
            )

            if check_on_line(refl_coord, ls, coords, [[center_name, pt_name]]) or check_on_circle(refl_coord, cs, coords):
                constructions = [("mirror", [pt_name, center_name])]
                result.append((refl_coord, constructions))

    # Reflection over lines
    for l in ls:
        line_sorted = sorted(l)
        for pt_name in point_names:
            if pt_name in line_sorted:
                continue
            px, py = coords[pt_name]
            x1, y1 = coords[line_sorted[0]]
            x2, y2 = coords[line_sorted[1]]
            abx = x2 - x1
            aby = y2 - y1
            denom = abx * abx + aby * aby

            if abs(denom) < TOLERANCE:
                continue

            apx = px - x1
            apy = py - y1
            t = (apx * abx + apy * aby) / denom
            foot_coord = (x1 + t * abx, y1 + t * aby)
            refl_coord = (2 * foot_coord[0] - px, 2 * foot_coord[1] - py)

            if check_on_line(refl_coord, ls, coords) or check_on_circle(refl_coord, cs, coords):
                constructions = [("reflect", [pt_name, line_sorted[0], line_sorted[1]])]
                result.append((refl_coord, constructions))

    return result


def foot(
    point_names: list[str],
    coords: dict[str, tuple[float, float]],
    lines_result: list[tuple[str, ...]] | None = None,
) -> list[tuple[tuple[float, float], list[tuple[str, list[str]]]]]:
    """
    Find foot points (perpendicular projections) that lie on non-trivial lines.

    Args:
        point_names: List of point names.
        coords: Dict mapping point names to (x, y) coordinates.
        lines_result: Optional pre-computed lines result to avoid recomputation.

    Returns:
        List of (coord, constructions) tuples where:
        - coord: (x, y) foot point coordinate
        - constructions: List of (construction_type, args) tuples,
          e.g., [("foot", ["p", "a", "b"])]
    """
    ls = lines_result if lines_result is not None else lines(point_names, coords)
    result = []

    for l in ls:
        line_sorted = sorted(l)
        for pt_name in point_names:
            if pt_name in line_sorted:
                continue
            px, py = coords[pt_name]
            x1, y1 = coords[line_sorted[0]]
            x2, y2 = coords[line_sorted[1]]
            abx = x2 - x1
            aby = y2 - y1
            denom = abx * abx + aby * aby

            if abs(denom) < TOLERANCE:
                continue

            apx = px - x1
            apy = py - y1
            t = (apx * abx + apy * aby) / denom
            foot_coord = (x1 + t * abx, y1 + t * aby)

            # Require foot to be on a non-trivial line
            if check_on_line(foot_coord, ls, coords, [[pt_name], line_sorted]):
                constructions = [("foot", [pt_name, line_sorted[0], line_sorted[1]])]
                result.append((foot_coord, constructions))

    return result


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
