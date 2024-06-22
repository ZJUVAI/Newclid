from __future__ import annotations
from typing import TYPE_CHECKING

from geosolver.predicate_name import PredicateName
import geosolver.geometry as gm


from geosolver.numerical import close_enough
from geosolver.numerical.geometries import PointNum, bring_together
from geosolver.statements.statement import Statement

from geosolver._lazy_loading import lazy_import

if TYPE_CHECKING:
    import numpy

np: "numpy" = lazy_import("numpy")


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


PREDICATE_TO_NUMERICAL_CHECK = {
    PredicateName.SIMILAR_TRIANGLE: check_simtri_numerical,
    PredicateName.SIMILAR_TRIANGLE_REFLECTED: check_simtri_numerical,
    PredicateName.SIMILAR_TRIANGLE_BOTH: check_simtri_numerical,
    PredicateName.CONTRI_TRIANGLE: check_contri_numerical,
    PredicateName.CONTRI_TRIANGLE_REFLECTED: check_contri_numerical,
    PredicateName.CONTRI_TRIANGLE_BOTH: check_contri_numerical,
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
