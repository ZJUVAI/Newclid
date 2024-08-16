from typing import Sequence
from geosolver.numerical.geometries import PointNum


class PointTooCloseError(Exception):
    pass


class PointTooFarError(Exception):
    pass


def check_too_close_numerical(
    newpoints: Sequence[PointNum], points: Sequence[PointNum], tol: float = 0.1
) -> bool:
    if len(points) < 2:
        return False
    mindist = (
        sum([sum([p.distance(p1) for p1 in points if p1 != p]) for p in points])
        / len(points)
        / (len(points) - 1)
    )
    for p0 in newpoints:
        for p1 in points:
            if p0.distance(p1) < tol * mindist:
                return True
    return False


def check_too_far_numerical(
    newpoints: Sequence[PointNum], points: Sequence[PointNum], tol: float = 10.0
) -> bool:
    if len(points) < 2:
        return False
    maxdist = (
        sum([sum([p.distance(p1) for p1 in points if p1 != p]) for p in points])
        / len(points)
        / (len(points) - 1)
    )
    for p0 in newpoints:
        for p1 in points:
            if p0.distance(p1) > tol * maxdist:
                return True
    return False
