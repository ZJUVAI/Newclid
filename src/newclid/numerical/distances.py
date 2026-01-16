from typing import Sequence
from newclid.numerical.geometries import PointNum


class PointTooCloseError(Exception):
    pass


class PointTooFarError(Exception):
    pass


def check_too_close_numerical(
    newpoints: Sequence[PointNum], points: Sequence[PointNum], tol: float = 0.05, round: float = 1e-10
) -> bool:
    if len(points) < 2:
        return False
    mindist = (
        sum([sum([p.distance(p1) for p1 in points if p1 != p])
            for p in points])
        / len(points)
        / (len(points) - 1)
    )
    for p0 in newpoints:
        for p1 in points:
            dist = p0.distance(p1)
            if dist > round and dist < tol * mindist:
                return True
    return False


def check_too_far_numerical(
    newpoints: Sequence[PointNum], points: Sequence[PointNum], tol: float = 5.0
) -> bool:
    if len(points) < 2:
        return False
    avg = sum(points, PointNum(0.0, 0.0)) * 1.0 / len(points)
    maxdist = max([p.distance(avg) for p in points])
    for p0 in newpoints:
        for p1 in points:
            if p0.distance(p1) > tol * maxdist:
                return True
    return False
