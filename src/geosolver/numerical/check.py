from __future__ import annotations
from typing import TYPE_CHECKING, Union
from geosolver.predicates import Predicate
import geosolver.geometry as gm

from geosolver._lazy_loading import lazy_import
from geosolver.numerical import ATOM, close_enough
from geosolver.numerical.angles import ang_between
from geosolver.numerical.geometries import Circle, Line, Point, bring_together
from geosolver.listing import list_eqratio3

if TYPE_CHECKING:
    import numpy

np: "numpy" = lazy_import("numpy")


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


def check_sangle_numerical(args: list[Point | gm.Angle]) -> bool:
    a, b, c, angle = args
    num, den = map(int, angle.name.split("pi/"))
    ang = ang_between(b, c, a)
    if ang < 0:
        ang += np.pi
    return close_enough(ang, num * np.pi / den)


def check_aconst_numerical(args: list[Point | gm.Angle]) -> bool:
    a, b, c, d, angle = args
    num, den = map(int, angle.name.split("pi/"))
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


def check_eqratio3_numerical(points: list[Point]) -> bool:
    for ratio in list_eqratio3(points):
        if not check_eqratio_numerical(ratio):
            return False
    return True


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


def check_ratio_numerical(points: list[Point | gm.Ratio]) -> bool:
    a, b, c, d, ratio = points
    m, n = map(int, ratio.name.split("/"))
    ab = a.distance(b)
    cd = c.distance(d)
    return close_enough(ab * n, cd * m)


NUMERICAL_CHECK_FUNCTIONS = {
    Predicate.COLLINEAR.value: check_coll_numerical,
    Predicate.PERPENDICULAR.value: check_perp_numerical,
    Predicate.MIDPOINT.value: check_midp_numerical,
    Predicate.CONGRUENT.value: check_cong_numerical,
    Predicate.CIRCLE.value: check_circle_numerical,
    Predicate.CYCLIC.value: check_cyclic_numerical,
    Predicate.EQANGLE.value: check_eqangle_numerical,
    Predicate.EQANGLE6.value: check_eqangle_numerical,
    Predicate.EQRATIO.value: check_eqratio_numerical,
    Predicate.EQRATIO3.value: check_eqratio3_numerical,
    Predicate.EQRATIO6.value: check_eqratio_numerical,
    Predicate.SIMILAR_TRIANGLE.value: check_simtri_numerical,
    Predicate.SIMILAR_TRIANGLE_REFLECTED.value: check_simtri_numerical,
    Predicate.SIMILAR_TRIANGLE_BOTH.value: check_simtri_numerical,
    Predicate.CONTRI_TRIANGLE.value: check_contri_numerical,
    Predicate.CONTRI_TRIANGLE_REFLECTED.value: check_contri_numerical,
    Predicate.CONTRI_TRIANGLE_BOTH.value: check_contri_numerical,
    Predicate.CONSTANT_ANGLE.value: check_aconst_numerical,
    Predicate.S_ANGLE.value: check_sangle_numerical,
    Predicate.SAMESIDE.value: check_sameside_numerical,
    Predicate.NON_COLLINEAR.value: check_ncoll_numerical,
    Predicate.CONSTANT_RATIO.value: check_ratio_numerical,
    "para_or_coll": check_para_or_coll_numerical,
    "const_angle": check_const_angle_numerical,
}


def check_numerical(name: str, args: list[Union[gm.Point, Point]]) -> bool:
    """Numerical check."""
    if name == "on_line":
        name = Predicate.COLLINEAR.value
    elif name == Predicate.PARALLEL.value:
        name = "para_or_coll"
    elif name in [
        Predicate.COMPUTE_RATIO.value,
        Predicate.COMPUTE_ANGLE.value,
        Predicate.FIX_L.value,
        Predicate.FIX_C.value,
        Predicate.FIX_B.value,
        Predicate.FIX_T.value,
        Predicate.FIX_P.value,
    ]:
        return True

    args = [p.num if isinstance(p, gm.Point) else p for p in args]
    return NUMERICAL_CHECK_FUNCTIONS[name](args)


def same_clock(a: Point, b: Point, c: Point, d: Point, e: Point, f: Point) -> bool:
    return clock(a, b, c) * clock(d, e, f) > 0


def clock(a: Point, b: Point, c: Point):
    ba = b - a
    cb = c - b
    return ba.x * cb.y - ba.y * cb.x


def same_sign(a: Point, b: Point, c: Point, d: Point, e: Point, f: Point) -> bool:
    a, b, c, d, e, f = map(lambda p: p.sym, [a, b, c, d, e, f])
    ab, cb = a - b, c - b
    de, fe = d - e, f - e
    return (ab.x * cb.y - ab.y * cb.x) * (de.x * fe.y - de.y * fe.x) > 0
