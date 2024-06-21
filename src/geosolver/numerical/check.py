from __future__ import annotations
from typing import TYPE_CHECKING
from geosolver.predicates.coll import Coll
from geosolver.predicates.predicate_name import PredicateName
import geosolver.geometry as gm


from geosolver.numerical import close_enough
from geosolver.numerical.angles import ang_between
from geosolver.numerical.geometries import CircleNum, PointNum, bring_together
from geosolver.listing import list_eqratio3
from geosolver.statements.statement import Statement, angle_to_num_den, ratio_to_num_den

from geosolver._lazy_loading import lazy_import

if TYPE_CHECKING:
    import numpy

np: "numpy" = lazy_import("numpy")


def check_circle_numerical(points: list[PointNum]) -> bool:
    if len(points) != 4:
        return False
    o, a, b, c = points
    oa, ob, oc = o.distance(a), o.distance(b), o.distance(c)
    return close_enough(oa, ob) and close_enough(ob, oc)


def check_ncoll_numerical(points: list[PointNum]) -> bool:
    return not Coll.check_numerical(points)


def check_sangle_numerical(args: list[PointNum | gm.Angle]) -> bool:
    a, b, c, angle = args
    num, den = angle_to_num_den(angle)
    ang = ang_between(b, c, a)
    # if ang < -ATOM:
    if ang < 0:
        ang += np.pi
    return close_enough(ang, num * np.pi / den)


def check_aconst_numerical(args: list[PointNum | gm.Angle]) -> bool:
    a, b, c, d, angle = args
    num, den = angle_to_num_den(angle)
    d = d + a - c
    ang = ang_between(a, b, d)
    # if ang < -ATOM:
    if ang < 0:
        ang += np.pi
    return close_enough(ang, num * np.pi / den)


def check_sameside_numerical(points: list[PointNum]) -> bool:
    b, a, c, y, x, z = points
    # whether b is to the same side of a & c as y is to x & z
    ba = b - a
    bc = b - c
    yx = y - x
    yz = y - z
    # return ba.dot(bc) * yx.dot(yz) > ATOM
    return ba.dot(bc) * yx.dot(yz) > 0


def check_cyclic_numerical(points: list[PointNum]) -> bool:
    points = list(set(points))
    a, b, c, *ps = points
    circle = CircleNum(p1=a, p2=b, p3=c)
    for d in ps:
        if not close_enough(d.distance(circle.center), circle.radius):
            return False
    return True


def check_const_angle_numerical(points: list[PointNum]) -> bool:
    """Check if the angle is equal to the given constant."""
    a, b, c, d, m, n = points
    a, b, c, d = bring_together(a, b, c, d)
    ba = b - a
    dc = d - c

    a3 = np.arctan2(ba.y, ba.x)
    a4 = np.arctan2(dc.y, dc.x)
    y = a3 - a4

    return close_enough(m / n % 1, y / np.pi % 1)


def check_eqratio_numerical(points: list[PointNum]) -> bool:
    a, b, c, d, e, f, g, h = points
    ab = a.distance(b)
    cd = c.distance(d)
    ef = e.distance(f)
    gh = g.distance(h)
    return close_enough(ab * gh, cd * ef)


def check_eqratio3_numerical(points: list[PointNum]) -> bool:
    for ratio in list_eqratio3(points):
        if not check_eqratio_numerical(ratio):
            return False
    return True


def check_cong_numerical(points: list[PointNum]) -> bool:
    a, b, c, d = points
    return close_enough(a.distance(b), c.distance(d))


def check_midp_numerical(points: list[PointNum]) -> bool:
    a, b, c = points
    return Coll.check_numerical(points) and close_enough(a.distance(b), a.distance(c))


def check_simtri_numerical(points: list[PointNum]) -> bool:
    """Check if 6 points make a pair of similar triangles."""
    a, b, c, x, y, z = points
    ab = a.distance(b)
    bc = b.distance(c)
    ca = c.distance(a)
    xy = x.distance(y)
    yz = y.distance(z)
    zx = z.distance(x)
    return close_enough(ab * yz, bc * xy) and close_enough(bc * zx, ca * yz)


def check_contri_numerical(points: list[PointNum]) -> bool:
    a, b, c, x, y, z = points
    ab = a.distance(b)
    bc = b.distance(c)
    ca = c.distance(a)
    xy = x.distance(y)
    yz = y.distance(z)
    zx = z.distance(x)
    return close_enough(ab, xy) and close_enough(bc, yz) and close_enough(ca, zx)


def check_ratio_numerical(points: list[PointNum | gm.Ratio]) -> bool:
    a, b, c, d, ratio = points
    m, n = ratio_to_num_den(ratio)
    ab = a.distance(b)
    cd = c.distance(d)
    return close_enough(ab * n, cd * m)


def check_length_numerical(points: list[PointNum | gm.Length]) -> bool:
    a, b, length = points
    ab = a.distance(b)
    return close_enough(ab, float(length.name))


PREDICATE_TO_NUMERICAL_CHECK = {
    PredicateName.MIDPOINT: check_midp_numerical,
    PredicateName.CONGRUENT: check_cong_numerical,
    PredicateName.CIRCLE: check_circle_numerical,
    PredicateName.CYCLIC: check_cyclic_numerical,
    PredicateName.EQANGLE6: "check_eqangle_numerical",
    PredicateName.EQRATIO: check_eqratio_numerical,
    PredicateName.EQRATIO3: check_eqratio3_numerical,
    PredicateName.EQRATIO6: check_eqratio_numerical,
    PredicateName.SIMILAR_TRIANGLE: check_simtri_numerical,
    PredicateName.SIMILAR_TRIANGLE_REFLECTED: check_simtri_numerical,
    PredicateName.SIMILAR_TRIANGLE_BOTH: check_simtri_numerical,
    PredicateName.CONTRI_TRIANGLE: check_contri_numerical,
    PredicateName.CONTRI_TRIANGLE_REFLECTED: check_contri_numerical,
    PredicateName.CONTRI_TRIANGLE_BOTH: check_contri_numerical,
    PredicateName.CONSTANT_ANGLE: check_aconst_numerical,
    PredicateName.S_ANGLE: check_sangle_numerical,
    PredicateName.SAMESIDE: check_sameside_numerical,
    PredicateName.NON_COLLINEAR: check_ncoll_numerical,
    PredicateName.CONSTANT_RATIO: check_ratio_numerical,
    PredicateName.CONSTANT_LENGTH: check_length_numerical,
}


def check_numerical(statement: Statement) -> bool:
    """Numerical check."""

    if statement.predicate in [
        PredicateName.COMPUTE_RATIO,
        PredicateName.COMPUTE_ANGLE,
        PredicateName.FIX_L,
        PredicateName.FIX_C,
        PredicateName.FIX_B,
        PredicateName.FIX_T,
        PredicateName.FIX_P,
    ]:
        return True

    num_args = [p.num if isinstance(p, gm.Point) else p for p in statement.args]
    return PREDICATE_TO_NUMERICAL_CHECK[statement.predicate](num_args)


def same_clock(
    a: PointNum, b: PointNum, c: PointNum, d: PointNum, e: PointNum, f: PointNum
) -> bool:
    return clock(a, b, c) * clock(d, e, f) > 0
    # return clock(a, b, c) * clock(d, e, f) > ATOM


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
    # return (ab.x * cb.y - ab.y * cb.x) * (de.x * fe.y - de.y * fe.x) > ATOM
