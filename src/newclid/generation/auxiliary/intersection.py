"""
Geometric point construction utilities.

Provides functions for constructing auxiliary points including:
- Intersections between lines and circles
- Midpoints
- Reflections (over points and lines)
- Feet (perpendicular projections)
"""

from collections import defaultdict
from itertools import combinations

import numpy as np

from .utils import TOLERANCE, round_coord
from .line_utils import lines, check_on_line
from .circle_utils import circles, check_on_circle


def intersection_between_lines(
    point_names: list[str],
    coords: dict[str, tuple[float, float]],
    lines_result: list[tuple[str, ...]] | None = None,
    rounded_coords: dict[str, tuple[float, float]] | None = None,
) -> list[tuple[tuple[float, float], list[tuple[str, list[str]]]]]:
    """
    Find intersection points where at least 3 lines meet.

    Args:
        point_names: List of point names.
        coords: Dict mapping point names to (x, y) coordinates.
        lines_result: Optional pre-computed lines result to avoid recomputation.
        rounded_coords: Optional pre-computed rounded coordinates to avoid recomputation.

    Returns:
        List of (coord, constructions) tuples where:
        - coord: (x, y) intersection point
        - constructions: List of (construction_type, args) tuples,
          e.g., [("on_line", ["a", "b"]), ("on_line", ["c", "d"])]
    """
    result = []
    ls = lines_result if lines_result is not None else lines(point_names, coords)

    # Compute rounded_coords if not provided
    if rounded_coords is None:
        rounded_coords = {name: round_coord(coords[name]) for name in point_names}

    point_to_lines = defaultdict(set)

    for l1, l2 in combinations(ls, 2):
        A = coords[l1[0]]
        B = coords[l1[1]]
        C = coords[l2[0]]
        D = coords[l2[1]]
        AB = (B[0] - A[0], B[1] - A[1])
        CD = (D[0] - C[0], D[1] - C[1])
        denom = AB[0] * CD[1] - AB[1] * CD[0]

        if abs(denom) < TOLERANCE:
            continue

        CA = (A[0] - C[0], A[1] - C[1])
        t = (CA[0] * CD[1] - CA[1] * CD[0]) / denom
        inter = (A[0] - t * AB[0], A[1] - t * AB[1])
        inter = round_coord(inter)

        # Remove points that coincide with intersection
        cleaned_l1 = [name for name in l1 if rounded_coords[name] != inter]
        cleaned_l2 = [name for name in l2 if rounded_coords[name] != inter]

        if len(cleaned_l1) <= 1 and len(cleaned_l2) <= 1:
            continue

        use_l1 = cleaned_l1 if len(cleaned_l1) > 1 else list(l1)
        use_l2 = cleaned_l2 if len(cleaned_l2) > 1 else list(l2)

        point_to_lines[inter].add(tuple(sorted(use_l1)))
        point_to_lines[inter].add(tuple(sorted(use_l2)))

    # Only keep points where at least 3 lines meet
    for coord, line_set in point_to_lines.items():
        if len(line_set) < 3:
            continue
        line_list = sorted([list(t) for t in line_set], key=lambda ln: ln[0])
        line1 = line_list[0]
        line2 = line_list[1]
        constructions = [
            ("on_line", [line1[0], line1[1]]),
            ("on_line", [line2[0], line2[1]]),
        ]
        result.append((coord, constructions))

    return result


def intersection_between_circles(
    point_names: list[str],
    coords: dict[str, tuple[float, float]],
    circles_result: list[dict] | None = None,
    rounded_coords: dict[str, tuple[float, float]] | None = None,
) -> list[tuple[tuple[float, float], list[tuple[str, list[str]]]]]:
    """
    Find intersection points where at least 3 circles meet.

    Args:
        point_names: List of point names.
        coords: Dict mapping point names to (x, y) coordinates.
        circles_result: Optional pre-computed circles result to avoid recomputation.
        rounded_coords: Optional pre-computed rounded coordinates to avoid recomputation.

    Returns:
        List of (coord, constructions) tuples where:
        - coord: (x, y) intersection point
        - constructions: List of (construction_type, args) tuples,
          e.g., [("on_circum", ["a", "b", "c"]), ("on_circum", ["d", "e", "f"])]
    """
    result = []
    cs = circles_result if circles_result is not None else circles(point_names, coords)

    if len(cs) < 2:
        return result

    # Compute rounded_coords if not provided
    if rounded_coords is None:
        rounded_coords = {name: round_coord(coords[name]) for name in point_names}

    point_to_circles = defaultdict(set)

    # Vectorized precomputation
    centers = np.array([c["center"] for c in cs])
    radii = np.array([c["radius"] for c in cs])

    # Batch compute pairwise distance matrix
    diff = centers[:, np.newaxis, :] - centers[np.newaxis, :, :]
    distances = np.linalg.norm(diff, axis=2)

    # Vectorized intersection condition filtering
    r_sum = radii[:, np.newaxis] + radii[np.newaxis, :]
    r_min = np.minimum(radii[:, np.newaxis], radii[np.newaxis, :])
    r_max = np.maximum(radii[:, np.newaxis], radii[np.newaxis, :])

    can_intersect = (
        (distances > TOLERANCE) &
        (distances <= r_sum + TOLERANCE) &
        (distances + r_min >= r_max - TOLERANCE)
    )

    # Only process circle pairs that can intersect
    pairs = np.argwhere(np.triu(can_intersect, k=1))

    for idx in range(len(pairs)):
        i, j = int(pairs[idx, 0]), int(pairs[idx, 1])
        cir1, cir2 = cs[i], cs[j]
        d = distances[i, j]

        # Compute intersection points (preserve original logic)
        c1, c2 = cir1["center"], cir2["center"]
        r1, r2 = cir1["radius"], cir2["radius"]
        dx, dy = c2[0] - c1[0], c2[1] - c1[1]

        a = (r1*r1 - r2*r2 + d*d) / (2 * d)
        h_squared = r1*r1 - a*a
        h = max(0.0, h_squared) ** 0.5
        px = c1[0] + a * (dx / d)
        py = c1[1] + a * (dy / d)

        candidates = []
        if h < TOLERANCE:
            candidates.append((px, py))
        else:
            ux, uy = -dy / d, dx / d
            candidates.append((px + h * ux, py + h * uy))
            candidates.append((px - h * ux, py - h * uy))

        # Deduplicate candidates (preserve original logic)
        unique = []
        for pt in candidates:
            if not any(
                ((pt[0] - u[0])**2 + (pt[1] - u[1])**2) ** 0.5 < TOLERANCE*2
                for u in unique
            ):
                unique.append(round_coord(pt))

        for pt in unique:
            # Remove points that coincide with intersection
            cleaned_l1 = [name for name in cir1["points"]
                          if rounded_coords[name] != pt]
            cleaned_l2 = [name for name in cir2["points"]
                          if rounded_coords[name] != pt]

            if len(cleaned_l1) <= 2 and len(cleaned_l2) <= 2:
                continue

            use1 = cleaned_l1 if len(cleaned_l1) > 2 else cir1["points"][:]
            use2 = cleaned_l2 if len(cleaned_l2) > 2 else cir2["points"][:]

            point_to_circles[pt].add(tuple(use1))
            point_to_circles[pt].add(tuple(use2))

    # Only keep points where at least 3 circles meet
    for coord, circle_set in point_to_circles.items():
        if len(circle_set) < 3:
            continue
        circle_list = sorted([list(t) for t in circle_set], key=lambda ln: ln[0])
        c1 = circle_list[0]
        c2 = circle_list[1]
        constructions = [
            ("on_circum", [c1[0], c1[1], c1[2]]),
            ("on_circum", [c2[0], c2[1], c2[2]]),
        ]
        result.append((coord, constructions))

    return result


def intersection_between_line_and_circle(
    point_names: list[str],
    coords: dict[str, tuple[float, float]],
    lines_result: list[tuple[str, ...]] | None = None,
    circles_result: list[dict] | None = None,
    rounded_coords: dict[str, tuple[float, float]] | None = None,
) -> list[tuple[tuple[float, float], list[tuple[str, list[str]]]]]:
    """
    Find intersection points where lines and circles meet (at least 3 objects).

    Args:
        point_names: List of point names.
        coords: Dict mapping point names to (x, y) coordinates.
        lines_result: Optional pre-computed lines result to avoid recomputation.
        circles_result: Optional pre-computed circles result to avoid recomputation.
        rounded_coords: Optional pre-computed rounded coordinates to avoid recomputation.

    Returns:
        List of (coord, constructions) tuples where:
        - coord: (x, y) intersection point
        - constructions: List of (construction_type, args) tuples,
          e.g., [("on_circum", ["a", "b", "c"]), ("on_line", ["d", "e"])]
    """
    result = []
    ls = lines_result if lines_result is not None else lines(point_names, coords)
    cs = circles_result if circles_result is not None else circles(point_names, coords)

    # Compute rounded_coords if not provided
    if rounded_coords is None:
        rounded_coords = {name: round_coord(coords[name]) for name in point_names}

    point_to_objects = defaultdict(set)

    for cir in cs:
        for l in ls:
            center = cir["center"]
            radius = cir["radius"]
            A = coords[l[0]]
            B = coords[l[1]]
            dx = B[0] - A[0]
            dy = B[1] - A[1]
            fx = A[0] - center[0]
            fy = A[1] - center[1]
            a = dx*dx + dy*dy
            b = 2 * (fx*dx + fy*dy)
            c = fx*fx + fy*fy - radius*radius
            disc = b*b - 4*a*c

            if disc < -TOLERANCE:
                continue

            disc = max(0.0, disc)
            sqrt_disc = disc ** 0.5
            candidates = []

            if abs(a) < TOLERANCE:
                dist_sq = fx*fx + fy*fy
                if abs(dist_sq - radius*radius) < TOLERANCE:
                    candidates.append(A)
            else:
                for sign in [1, -1]:
                    t = (-b + sign * sqrt_disc) / (2 * a)
                    inter_x = A[0] + t * dx
                    inter_y = A[1] + t * dy
                    candidates.append((inter_x, inter_y))

            # Deduplicate candidates
            unique = []
            for pt in candidates:
                if not any(
                    abs(pt[0] - u[0]) < TOLERANCE and abs(pt[1] - u[1]) < TOLERANCE
                    for u in unique
                ):
                    unique.append(round_coord(pt))

            for pt in unique:
                # Remove points that coincide with intersection
                cleaned_line = [name for name in l
                                if rounded_coords[name] != pt]
                cleaned_circle = [name for name in cir["points"]
                                  if rounded_coords[name] != pt]

                if len(cleaned_line) <= 2 and len(cleaned_circle) <= 3:
                    continue

                use_line = cleaned_line if len(cleaned_line) >= 2 else list(l)
                use_circle = cleaned_circle if len(cleaned_circle) >= 3 else cir["points"][:]

                point_to_objects[pt].add(("line", tuple(sorted(use_line))))
                point_to_objects[pt].add(("circle", tuple(sorted(use_circle))))

    # Only keep points where at least 3 objects meet
    for coord, obj_set in point_to_objects.items():
        line_objs = [obj for obj in obj_set if obj[0] == "line"]
        circle_objs = [obj for obj in obj_set if obj[0] == "circle"]

        if len(line_objs) + len(circle_objs) < 3:
            continue
        if len(line_objs) <= 0 or len(circle_objs) <= 0:
            continue

        line_objs.sort(key=lambda x: x[1][0])
        smallest_line = line_objs[0][1]

        circle_objs.sort(key=lambda x: x[1][0])
        smallest_circle = circle_objs[0][1]

        constructions = [
            ("on_circum", [smallest_circle[0], smallest_circle[1], smallest_circle[2]]),
            ("on_line", [smallest_line[0], smallest_line[1]]),
        ]
        result.append((coord, constructions))

    return result


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
