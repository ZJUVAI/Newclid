from typing import Union
import numpy as np
import geosolver.geometry as gm

from geosolver.numerical import ATOM, close_enough
from geosolver.numerical.angles import ang_between
from geosolver.numerical.geometries import Circle, Line, Point, bring_together


def check_circle_numerical(points: list[Point]) -> bool:
    if len(points) != 4:
        return False
    o, a, b, c = points
    oa, ob, oc = o.distance(a), o.distance(b), o.distance(c)
    return close_enough(oa, ob) and close_enough(ob, oc)


def check_coll_numerical(points: list[Point]) -> bool:
    a, b = points[:2]
    line = Line(a, b)
    for p in points[2:]:
        if abs(line(p.x, p.y)) > ATOM:
            return False
    return True


def check_ncoll_numerical(points: list[Point]) -> bool:
    return not check_coll_numerical(points)


def check_aconst_numerical(args: list[Point]) -> bool:
    a, b, c, d, num, den = args
    d = d + a - c
    ang = ang_between(a, b, d)
    if ang < 0:
        ang += np.pi
    return close_enough(ang, num * np.pi / den)


def check_sameside_numerical(points: list[Point]) -> bool:
    b, a, c, y, x, z = points
    # whether b is to the same side of a & c as y is to x & z
    ba = b - a
    bc = b - c
    yx = y - x
    yz = y - z
    return ba.dot(bc) * yx.dot(yz) > 0


def check_para_numerical(points: list[Point]) -> bool:
    a, b, c, d = points
    ab = Line(a, b)
    cd = Line(c, d)
    if ab.same(cd):
        return False
    return ab.is_parallel(cd)


def check_para_or_coll_numerical(points: list[Point]) -> bool:
    return check_para_numerical(points) or check_coll_numerical(points)


def check_perp_numerical(points: list[Point]) -> bool:
    a, b, c, d = points
    ab = Line(a, b)
    cd = Line(c, d)
    return ab.is_perp(cd)


def check_cyclic_numerical(points: list[Point]) -> bool:
    points = list(set(points))
    a, b, c, *ps = points
    circle = Circle(p1=a, p2=b, p3=c)
    for d in ps:
        if not close_enough(d.distance(circle.center), circle.radius):
            return False
    return True


def check_const_angle_numerical(points: list[Point]) -> bool:
    """Check if the angle is equal to the given constant."""
    a, b, c, d, m, n = points
    a, b, c, d = bring_together(a, b, c, d)
    ba = b - a
    dc = d - c

    a3 = np.arctan2(ba.y, ba.x)
    a4 = np.arctan2(dc.y, dc.x)
    y = a3 - a4

    return close_enough(m / n % 1, y / np.pi % 1)


def check_eqangle_numerical(points: list[Point]) -> bool:
    """Check if 8 points make 2 equal angles."""
    a, b, c, d, e, f, g, h = points

    ab = Line(a, b)
    cd = Line(c, d)
    ef = Line(e, f)
    gh = Line(g, h)

    if ab.is_parallel(cd):
        return ef.is_parallel(gh)
    if ef.is_parallel(gh):
        return ab.is_parallel(cd)

    a, b, c, d = bring_together(a, b, c, d)
    e, f, g, h = bring_together(e, f, g, h)

    ba = b - a
    dc = d - c
    fe = f - e
    hg = h - g

    sameclock = (ba.x * dc.y - ba.y * dc.x) * (fe.x * hg.y - fe.y * hg.x) > 0
    if not sameclock:
        ba = ba * -1.0

    a1 = np.arctan2(fe.y, fe.x)
    a2 = np.arctan2(hg.y, hg.x)
    x = a1 - a2

    a3 = np.arctan2(ba.y, ba.x)
    a4 = np.arctan2(dc.y, dc.x)
    y = a3 - a4

    xy = (x - y) % (2 * np.pi)
    return close_enough(xy, 0, tol=1e-11) or close_enough(xy, 2 * np.pi, tol=1e-11)


def check_eqratio_numerical(points: list[Point]) -> bool:
    a, b, c, d, e, f, g, h = points
    ab = a.distance(b)
    cd = c.distance(d)
    ef = e.distance(f)
    gh = g.distance(h)
    return close_enough(ab * gh, cd * ef)


def check_cong_numerical(points: list[Point]) -> bool:
    a, b, c, d = points
    return close_enough(a.distance(b), c.distance(d))


def check_midp_numerical(points: list[Point]) -> bool:
    a, b, c = points
    return check_coll_numerical(points) and close_enough(a.distance(b), a.distance(c))


def check_simtri_numerical(points: list[Point]) -> bool:
    """Check if 6 points make a pair of similar triangles."""
    a, b, c, x, y, z = points
    ab = a.distance(b)
    bc = b.distance(c)
    ca = c.distance(a)
    xy = x.distance(y)
    yz = y.distance(z)
    zx = z.distance(x)
    tol = 1e-9
    return close_enough(ab * yz, bc * xy, tol) and close_enough(bc * zx, ca * yz, tol)


def check_contri_numerical(points: list[Point]) -> bool:
    a, b, c, x, y, z = points
    ab = a.distance(b)
    bc = b.distance(c)
    ca = c.distance(a)
    xy = x.distance(y)
    yz = y.distance(z)
    zx = z.distance(x)
    tol = 1e-9
    return (
        close_enough(ab, xy, tol)
        and close_enough(bc, yz, tol)
        and close_enough(ca, zx, tol)
    )


def check_ratio_numerical(points: list[Point]) -> bool:
    a, b, c, d, m, n = points
    ab = a.distance(b)
    cd = c.distance(d)
    return close_enough(ab * n, cd * m)


NUMERICAL_CHECK_FUNCTIONS = {
    "eqangle": check_eqangle_numerical,
    "eqratio": check_eqratio_numerical,
    "simtri": check_simtri_numerical,
    "contri": check_contri_numerical,
    "para_or_coll": check_para_or_coll_numerical,
    "cyclic": check_cyclic_numerical,
    "ratio": check_ratio_numerical,
    "coll": check_coll_numerical,
    "ncoll": check_ncoll_numerical,
    "perp": check_perp_numerical,
    "cong": check_cong_numerical,
    "aconst": check_aconst_numerical,
    "circle": check_circle_numerical,
    "const_angle": check_const_angle_numerical,
    "midp": check_midp_numerical,
    "sameside": check_sameside_numerical,
}


def check_numerical(name: str, args: list[Union[gm.Point, Point]]) -> bool:
    """Numerical check."""
    if name == "eqangle6":
        name = "eqangle"
    elif name == "eqratio6":
        name = "eqratio"
    elif name in ["simtri2", "simtri*"]:
        name = "simtri"
    elif name in ["contri2", "contri*"]:
        name = "contri"
    elif name == "para":
        name = "para_or_coll"
    elif name == "on_line":
        name = "coll"
    elif name in ["rcompute", "acompute"]:
        return True
    elif name in ["fixl", "fixc", "fixb", "fixt", "fixp"]:
        return True

    args = [p.num if isinstance(p, gm.Point) else p for p in args]
    return NUMERICAL_CHECK_FUNCTIONS[name](args)


def same_clock(a: Point, b: Point, c: Point, d: Point, e: Point, f: Point) -> bool:
    ba = b - a
    cb = c - b
    ed = e - d
    fe = f - e
    return (ba.x * cb.y - ba.y * cb.x) * (ed.x * fe.y - ed.y * fe.x) > 0


def same_sign(a: Point, b: Point, c: Point, d: Point, e: Point, f: Point) -> bool:
    a, b, c, d, e, f = map(lambda p: p.sym, [a, b, c, d, e, f])
    ab, cb = a - b, c - b
    de, fe = d - e, f - e
    return (ab.x * cb.y - ab.y * cb.x) * (de.x * fe.y - de.y * fe.x) > 0
