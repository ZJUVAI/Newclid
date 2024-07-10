from __future__ import annotations


from geosolver.numerical import ATOM
from geosolver.numerical.geometries import PointNum


def same_clock(
    a: PointNum, b: PointNum, c: PointNum, d: PointNum, e: PointNum, f: PointNum
) -> bool:
    """
    a, b, c; d, e, f are of the same clock and they are not colinear
    """
    return clock(a, b, c) * clock(d, e, f) > ATOM


def clock(a: PointNum, b: PointNum, c: PointNum):
    ab = b - a
    ac = c - a
    return ab.x * ac.y - ab.y * ac.x
