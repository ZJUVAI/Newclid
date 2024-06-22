from __future__ import annotations


from geosolver.numerical.geometries import PointNum


def same_clock(
    a: PointNum, b: PointNum, c: PointNum, d: PointNum, e: PointNum, f: PointNum
) -> bool:
    return clock(a, b, c) * clock(d, e, f) > 0


def clock(a: PointNum, b: PointNum, c: PointNum):
    ba = b - a
    cb = c - b
    return ba.x * cb.y - ba.y * cb.x


def same_sign(
    a: PointNum, b: PointNum, c: PointNum, d: PointNum, e: PointNum, f: PointNum
) -> bool:
    a, b, c, d, e, f = map(lambda p: p.sym, [a, b, c, d, e, f])
    ab, cb = a - b, c - b
    de, fe = d - e, f - e
    return (ab.x * cb.y - ab.y * cb.x) * (de.x * fe.y - de.y * fe.x) > 0
