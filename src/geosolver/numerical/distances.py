from geosolver.numerical.geometries import Point


class PointTooCloseError(Exception):
    pass


class PointTooFarError(Exception):
    pass


def check_too_close_numerical(
    newpoints: list[Point], points: list[Point], tol: int = 0.1
) -> bool:
    if not points:
        return False
    avg = sum(points, Point(0.0, 0.0)) * 1.0 / len(points)
    mindist = min([p.distance(avg) for p in points])
    for p0 in newpoints:
        for p1 in points:
            if p0.distance(p1) < tol * mindist:
                return True
    return False


def check_too_far_numerical(
    newpoints: list[Point], points: list[Point], tol: int = 4
) -> bool:
    if len(points) < 2:
        return False
    avg = sum(points, Point(0.0, 0.0)) * 1.0 / len(points)
    maxdist = max([p.distance(avg) for p in points])
    for p in newpoints:
        if p.distance(avg) > maxdist * tol:
            return True
    return False
