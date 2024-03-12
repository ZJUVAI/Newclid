"""Helper functions for manipulating points when matching theorems for DD."""

import geosolver.geometry as gm


from typing import Any, Generator


def rotate_simtri(
    a: gm.Point, b: gm.Point, c: gm.Point, x: gm.Point, y: gm.Point, z: gm.Point
) -> Generator[tuple[gm.Point, ...], None, None]:
    """Rotate points around for similar triangle predicates."""
    yield (z, y, x, c, b, a)
    for p in [
        (b, c, a, y, z, x),
        (c, a, b, z, x, y),
        (x, y, z, a, b, c),
        (y, z, x, b, c, a),
        (z, x, y, c, a, b),
    ]:
        yield p
        yield p[::-1]


def rotate_contri(
    a: gm.Point, b: gm.Point, c: gm.Point, x: gm.Point, y: gm.Point, z: gm.Point
) -> Generator[tuple[gm.Point, ...], None, None]:
    for p in [(b, a, c, y, x, z), (x, y, z, a, b, c), (y, x, z, b, a, c)]:
        yield p


def diff_point(line: gm.Line, a: gm.Point) -> gm.Point:
    for x in line.neighbors(gm.Point):
        if x != a:
            return x
    return None


def intersect1(set1: set[Any], set2: set[Any]) -> Any:
    for x in set1:
        if x in set2:
            return x
    return None
