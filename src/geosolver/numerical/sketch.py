from __future__ import annotations
from fractions import Fraction
from typing import TYPE_CHECKING, Optional, Union
from numpy.random import Generator

import geosolver.geometry as gm
from geosolver._lazy_loading import lazy_import
from geosolver.numerical import close_enough
from geosolver.numerical.angles import ang_between, ang_of
from geosolver.numerical.distances import (
    check_too_close_numerical,
    check_too_far_numerical,
)
from geosolver.numerical.geometries import (
    Circle,
    HalfLine,
    HoleCircle,
    Line,
    Point,
    circle_circle_intersection,
    line_circle_intersection,
    line_line_intersection,
)
from geosolver.statements.statement import angle_to_num_den

if TYPE_CHECKING:
    import numpy
    import numpy.random

np: "numpy" = lazy_import("numpy")
np_random: "numpy.random" = lazy_import("numpy.random")


def sketch(
    name: str,
    args: list[Union[Point, gm.Point]],
    rnd_generator: Generator = None,
) -> list[Union[Point, Line, Circle, HalfLine, HoleCircle]]:
    fun = globals()["sketch_" + name]
    args = [p.num if isinstance(p, gm.Point) else p for p in args]
    out = fun(args, rnd_gen=rnd_generator)

    # out can be one or multiple {Point/Line/HalfLine}
    if isinstance(out, (tuple, list)):
        return list(out)
    return [out]


def try_to_sketch_intersect(
    name1: str,
    args1: list[Union[gm.Point, Point]],
    name2: str,
    args2: list[Union[gm.Point, Point]],
    existing_points: list[Point],
    rnd_generator: Generator = None,
) -> Optional[Point]:
    """Try to sketch an intersection between two objects."""
    obj1 = sketch(name1, args1, rnd_generator)[0]
    obj2 = sketch(name2, args2, rnd_generator)[0]

    if isinstance(obj1, Line) and isinstance(obj2, Line):
        fn = line_line_intersection
    elif isinstance(obj1, Circle) and isinstance(obj2, Circle):
        fn = circle_circle_intersection
    else:
        fn = line_circle_intersection
        if isinstance(obj2, Line) and isinstance(obj1, Circle):
            obj1, obj2 = obj2, obj1

    x = fn(obj1, obj2)

    if isinstance(x, Point):
        return x

    x1, x2 = x

    close1 = check_too_close_numerical([x1], existing_points)
    far1 = check_too_far_numerical([x1], existing_points)
    if not close1 and not far1:
        return x1
    close2 = check_too_close_numerical([x2], existing_points)
    far2 = check_too_far_numerical([x2], existing_points)
    if not close2 and not far2:
        return x2

    return None


def sketch_aline(args: tuple[gm.Point, ...], **kwargs) -> HalfLine:
    """Sketch the construction aline."""
    A, B, C, D, E = args
    ab = A - B
    cb = C - B
    de = D - E

    dab = A.distance(B)
    ang_ab = np.arctan2(ab.y / dab, ab.x / dab)

    dcb = C.distance(B)
    ang_bc = np.arctan2(cb.y / dcb, cb.x / dcb)

    dde = D.distance(E)
    ang_de = np.arctan2(de.y / dde, de.x / dde)

    ang_ex = ang_de + ang_bc - ang_ab
    X = E + Point(np.cos(ang_ex), np.sin(ang_ex))
    return HalfLine(E, X)


def sketch_acircle(args: tuple[gm.Point, ...], **kwargs) -> Circle:
    a, b, c, d, f = args
    de = sketch_aline([c, a, b, f, d])
    fe = sketch_aline([a, c, b, d, f])
    e = line_line_intersection(de, fe)
    return Circle(p1=d, p2=e, p3=f)


def sketch_amirror(args: tuple[gm.Point, ...], **kwargs) -> HalfLine:
    """Sketch the angle mirror."""
    A, B, C = args
    ab = A - B
    cb = C - B

    dab = A.distance(B)
    ang_ab = np.arctan2(ab.y / dab, ab.x / dab)
    dcb = C.distance(B)
    ang_bc = np.arctan2(cb.y / dcb, cb.x / dcb)

    ang_bx = 2 * ang_bc - ang_ab
    X = B + Point(np.cos(ang_bx), np.sin(ang_bx))
    return HalfLine(B, X)


def sketch_bisect(args: tuple[gm.Point, ...], **kwargs) -> Line:
    a, b, c = args
    ab = a.distance(b)
    bc = b.distance(c)
    x = b + (c - b) * (ab / bc)
    m = (a + x) * 0.5
    return Line(b, m)


def sketch_exbisect(args: tuple[gm.Point, ...], **kwargs) -> Line:
    a, b, c = args
    return sketch_bisect(args).perpendicular_line(b)


def sketch_bline(args: tuple[gm.Point, ...], **kwargs) -> Line:
    a, b = args
    m = (a + b) * 0.5
    return m.perpendicular_line(Line(a, b))


def sketch_dia(args: tuple[gm.Point, ...], **kwargs) -> Circle:
    a, b = args
    return Circle((a + b) * 0.5, p1=a)


def sketch_tangent(args: tuple[gm.Point, ...], **kwargs) -> tuple[Point, Point]:
    a, o, b = args
    dia = sketch_dia([a, o])
    return circle_circle_intersection(Circle(o, p1=b), dia)


def sketch_circle(args: tuple[gm.Point, ...], **kwargs) -> Circle:
    a, b, c = args
    return Circle(center=a, radius=b.distance(c))


def sketch_cc_tangent(args: tuple[gm.Point, ...], **kwargs) -> tuple[Point, ...]:
    """Sketch tangents to two circles."""
    o, a, w, b = args
    ra, rb = o.distance(a), w.distance(b)

    ow = Line(o, w)
    if close_enough(ra, rb):
        oo = ow.perpendicular_line(o)
        oa = Circle(o, ra)
        x, z = line_circle_intersection(oo, oa)
        y = x + w - o
        t = z + w - o
        return x, y, z, t

    swap = rb > ra
    if swap:
        o, a, w, b = w, b, o, a
        ra, rb = rb, ra

    oa = Circle(o, ra)
    q = o + (w - o) * ra / (ra - rb)

    x, z = circle_circle_intersection(sketch_dia([o, q]), oa)
    y = w.foot(Line(x, q))
    t = w.foot(Line(z, q))

    if swap:
        x, y, z, t = y, x, t, z

    return x, y, z, t


def sketch_hcircle(args: tuple[gm.Point, ...], **kwargs) -> HoleCircle:
    a, b = args
    return HoleCircle(center=a, radius=a.distance(b), hole=b)


def sketch_e5128(args: tuple[gm.Point, ...], **kwargs) -> tuple[Point, Point]:
    a, b, c, d = args

    g = (a + b) * 0.5
    de = Line(d, g)

    e, f = line_circle_intersection(de, Circle(c, p1=b))

    if e.distance(d) < f.distance(d):
        e = f
    return e, g


def random_rfss(*points: Point, rnd_gen: Generator) -> list[Point]:
    """Random rotate-flip-scale-shift a point cloud."""
    # center point cloud.
    average = sum(points, Point(0.0, 0.0)) * (1.0 / len(points))
    points = [p - average for p in points]

    # rotate
    ang = rnd_gen.uniform(0.0, 2 * np.pi)
    sin, cos = np.sin(ang), np.cos(ang)
    # scale and shift
    scale = rnd_gen.uniform(0.5, 2.0)
    shift = Point(rnd_gen.uniform(-1, 1), rnd_gen.uniform(-1, 1))
    points = [p.rotate(sin, cos) * scale + shift for p in points]

    # randomly flip
    if rnd_gen.random() < 0.5:
        points = [p.flip() for p in points]

    return points


def head_from(tail: Point, ang: float, length: float = 1) -> Point:
    vector = Point(np.cos(ang) * length, np.sin(ang) * length)
    return tail + vector


def sketch_eq_quadrangle(
    args: tuple[gm.Point, ...], rnd_gen: Generator
) -> tuple[Point, ...]:
    """Sketch quadrangle with two equal opposite sides."""
    a = Point(0.0, 0.0)
    b = Point(1.0, 0.0)

    length = rnd_gen.uniform(0.5, 2.0)
    ang = rnd_gen.uniform(np.pi / 3, np.pi * 2 / 3)
    d = head_from(a, ang, length)

    ang = ang_of(b, d)
    ang = rnd_gen.uniform(ang / 10, ang / 9)
    c = head_from(b, ang, length)
    a, b, c, d = random_rfss(a, b, c, d, rnd_gen=rnd_gen)
    return a, b, c, d


def sketch_iso_trapezoid(
    args: tuple[gm.Point, ...], rnd_gen: Generator
) -> tuple[Point, ...]:
    a = Point(0.0, 0.0)
    b = Point(1.0, 0.0)
    lenght = rnd_gen.uniform(0.5, 2.0)
    height = rnd_gen.uniform(0.5, 2.0)
    c = Point(0.5 + lenght / 2.0, height)
    d = Point(0.5 - lenght / 2.0, height)

    a, b, c, d = random_rfss(a, b, c, d, rnd_gen=rnd_gen)
    return a, b, c, d


def sketch_eqangle2(args: tuple[gm.Point, ...], rnd_gen: Generator) -> Point:
    """Sketch the def eqangle2."""
    a, b, c = args

    ba = b.distance(a)
    bc = b.distance(c)
    lenght = ba * ba / bc

    if rnd_gen.uniform(0.0, 1.0) < 0.5:
        be = min(lenght, bc)
        be = rnd_gen.uniform(be * 0.1, be * 0.9)
    else:
        be = max(lenght, bc)
        be = rnd_gen.uniform(be * 1.1, be * 1.5)

    e = b + (c - b) * (be / bc)
    y = b + (a - b) * (be / lenght)
    return line_line_intersection(Line(c, y), Line(a, e))


def sketch_eqangle3(args: tuple[gm.Point, ...], **kwargs) -> Circle:
    a, b, d, e, f = args
    de = d.distance(e)
    ef = e.distance(f)
    ab = b.distance(a)
    ang_ax = ang_of(a, b) + ang_between(e, d, f)
    x = head_from(a, ang_ax, length=de / ef * ab)
    return Circle(p1=a, p2=b, p3=x)


def sketch_eqdia_quadrangle(
    args: tuple[gm.Point, ...], rnd_gen: Generator
) -> tuple[Point, ...]:
    """Sketch quadrangle with two equal diagonals."""
    m = rnd_gen.uniform(0.3, 0.7)
    n = rnd_gen.uniform(0.3, 0.7)
    a = Point(-m, 0.0)
    c = Point(1 - m, 0.0)
    b = Point(0.0, -n)
    d = Point(0.0, 1 - n)

    ang = rnd_gen.uniform(-0.25 * np.pi, 0.25 * np.pi)
    sin, cos = np.sin(ang), np.cos(ang)
    b = b.rotate(sin, cos)
    d = d.rotate(sin, cos)
    a, b, c, d = random_rfss(a, b, c, d, rnd_gen=rnd_gen)
    return a, b, c, d


def random_points(n: int = 3, rnd_gen: Generator = None) -> list[Point]:
    rnd_gen = np_random if rnd_gen is None else rnd_gen
    return [Point(rnd_gen.uniform(-1, 1), rnd_gen.uniform(-1, 1)) for _ in range(n)]


def sketch_free(args: tuple[gm.Point, ...], rnd_gen: Generator) -> Point:
    return random_points(1, rnd_gen)[0]


def sketch_isos(args: tuple[gm.Point, ...], rnd_gen: Generator) -> tuple[Point, ...]:
    base = rnd_gen.uniform(0.5, 1.5)
    height = rnd_gen.uniform(0.5, 1.5)

    b = Point(-base / 2, 0.0)
    c = Point(base / 2, 0.0)
    a = Point(0.0, height)
    a, b, c = random_rfss(a, b, c, rnd_gen=rnd_gen)
    return a, b, c


def sketch_line(args: tuple[gm.Point, ...], **kwargs) -> Line:
    a, b = args
    return Line(a, b)


def sketch_cyclic(args: tuple[gm.Point, ...], **kwargs) -> Circle:
    a, b, c = args
    return Circle(p1=a, p2=b, p3=c)


def sketch_hline(args: tuple[gm.Point, ...], **kwargs) -> HalfLine:
    a, b = args
    return HalfLine(a, b)


def sketch_midp(args: tuple[gm.Point, ...], **kwargs) -> Point:
    a, b = args
    return (a + b) * 0.5


def sketch_pentagon(
    args: tuple[gm.Point, ...], rnd_gen: Generator
) -> tuple[Point, ...]:
    points = [Point(1.0, 0.0)]
    ang = 0.0

    for i in range(4):
        ang += (2 * np.pi - ang) / (5 - i) * rnd_gen.uniform(0.5, 1.5)
        point = Point(np.cos(ang), np.sin(ang))
        points.append(point)

    a, b, c, d, e = points
    a, b, c, d, e = random_rfss(a, b, c, d, e, rnd_gen=rnd_gen)
    return a, b, c, d, e


def sketch_pline(args: tuple[gm.Point, ...], **kwargs) -> Line:
    a, b, c = args
    return a.parallel_line(Line(b, c))


def sketch_pmirror(args: tuple[gm.Point, ...], **kwargs) -> Point:
    a, b = args
    return b * 2 - a


def sketch_quadrangle(
    args: tuple[gm.Point, ...], rnd_gen: Generator
) -> tuple[Point, ...]:
    """Sketch a random quadrangle."""
    m = rnd_gen.uniform(0.3, 0.7)

    a = Point(-m, 0.0)
    c = Point(1 - m, 0.0)
    b = Point(0.0, -rnd_gen.uniform(0.25, 0.75))
    d = Point(0.0, rnd_gen.uniform(0.25, 0.75))

    ang = rnd_gen.uniform(-0.25 * np.pi, 0.25 * np.pi)
    sin, cos = np.sin(ang), np.cos(ang)
    b = b.rotate(sin, cos)
    d = d.rotate(sin, cos)
    a, b, c, d = random_rfss(a, b, c, d, rnd_gen=rnd_gen)
    return a, b, c, d


def sketch_r_trapezoid(
    args: tuple[gm.Point, ...], rnd_gen: Generator
) -> tuple[Point, ...]:
    a = Point(0.0, 1.0)
    d = Point(0.0, 0.0)
    b = Point(rnd_gen.uniform(0.5, 1.5), 1.0)
    c = Point(rnd_gen.uniform(0.5, 1.5), 0.0)
    a, b, c, d = random_rfss(a, b, c, d, rnd_gen=rnd_gen)
    return a, b, c, d


def sketch_r_triangle(
    args: tuple[gm.Point, ...], rnd_gen: Generator
) -> tuple[Point, ...]:
    a = Point(0.0, 0.0)
    b = Point(0.0, rnd_gen.uniform(0.5, 2.0))
    c = Point(rnd_gen.uniform(0.5, 2.0), 0.0)
    a, b, c = random_rfss(a, b, c, rnd_gen=rnd_gen)
    return a, b, c


def sketch_rectangle(
    args: tuple[gm.Point, ...], rnd_gen: Generator
) -> tuple[Point, ...]:
    a = Point(0.0, 0.0)
    b = Point(0.0, 1.0)
    lenght = rnd_gen.uniform(0.5, 2.0)
    c = Point(lenght, 1.0)
    d = Point(lenght, 0.0)
    a, b, c, d = random_rfss(a, b, c, d, rnd_gen=rnd_gen)
    return a, b, c, d


def sketch_reflect(args: tuple[gm.Point, ...], **kwargs) -> Point:
    a, b, c = args
    m = a.foot(Line(b, c))
    return m * 2 - a


def sketch_risos(args: tuple[gm.Point, ...], rnd_gen: Generator) -> tuple[Point, ...]:
    a = Point(0.0, 0.0)
    b = Point(0.0, 1.0)
    c = Point(1.0, 0.0)
    a, b, c = random_rfss(a, b, c, rnd_gen=rnd_gen)
    return a, b, c


def sketch_rotaten90(args: tuple[gm.Point, ...], **kwargs) -> Point:
    a, b = args
    ang = -np.pi / 2
    return a + (b - a).rotate(np.sin(ang), np.cos(ang))


def sketch_rotatep90(args: tuple[gm.Point, ...], **kwargs) -> Point:
    a, b = args
    ang = np.pi / 2
    return a + (b - a).rotate(np.sin(ang), np.cos(ang))


def sketch_s_angle(args: tuple[gm.Point, ...], **kwargs) -> HalfLine:
    a, b, angle = args
    num, den = angle_to_num_den(angle)
    ang = num * np.pi / den
    x = b + (a - b).rotatea(ang)
    return HalfLine(b, x)


def sketch_aconst(args: tuple[gm.Point, ...], **kwargs) -> HalfLine:
    a, b, c, angle = args
    num, den = angle_to_num_den(angle)
    ang = num * np.pi / den
    x = c + (a - b).rotatea(ang)
    return HalfLine(c, x)


def sketch_segment(
    args: tuple[gm.Point, ...], rnd_gen: Generator
) -> tuple[Point, Point]:
    a, b = random_points(2, rnd_gen)
    return a, b


def sketch_shift(args: tuple[gm.Point, ...], **kwargs) -> Point:
    a, b, c = args
    return c + (b - a)


def sketch_square(args: tuple[gm.Point, ...], **kwargs) -> tuple[Point, Point]:
    a, b = args
    c = b + (a - b).rotatea(-np.pi / 2)
    d = a + (b - a).rotatea(np.pi / 2)
    return c, d


def sketch_isquare(args: tuple[gm.Point, ...], rnd_gen: Generator) -> tuple[Point, ...]:
    a = Point(0.0, 0.0)
    b = Point(1.0, 0.0)
    c = Point(1.0, 1.0)
    d = Point(0.0, 1.0)
    a, b, c, d = random_rfss(a, b, c, d, rnd_gen=rnd_gen)
    return a, b, c, d


def sketch_tline(args: tuple[gm.Point, ...], **kwargs) -> Line:
    a, b, c = args
    return a.perpendicular_line(Line(b, c))


def sketch_trapezoid(
    args: tuple[gm.Point, ...], rnd_gen: Generator
) -> tuple[Point, ...]:
    d = Point(0.0, 0.0)
    c = Point(1.0, 0.0)

    base = rnd_gen.uniform(0.5, 2.0)
    height = rnd_gen.uniform(0.5, 2.0)
    a = Point(rnd_gen.uniform(-0.5, 1.5), height)
    b = Point(a.x + base, height)
    a, b, c, d = random_rfss(a, b, c, d, rnd_gen=rnd_gen)
    return a, b, c, d


def sketch_triangle(
    args: tuple[gm.Point, ...], rnd_gen: Generator
) -> tuple[Point, ...]:
    a = Point(0.0, 0.0)
    b = Point(1.0, 0.0)
    ac = rnd_gen.uniform(0.5, 2.0)
    ang = rnd_gen.uniform(0.2, 0.8) * np.pi
    c = head_from(a, ang, ac)
    a, b, c = random_rfss(a, b, c, rnd_gen=rnd_gen)
    return a, b, c


def sketch_triangle12(
    args: tuple[gm.Point, ...], rnd_gen: Generator
) -> tuple[Point, ...]:
    b = Point(0.0, 0.0)
    c = Point(rnd_gen.uniform(1.5, 2.5), 0.0)
    a, _ = circle_circle_intersection(Circle(b, 1.0), Circle(c, 2.0))
    a, b, c = random_rfss(a, b, c, rnd_gen=rnd_gen)
    return a, b, c


def sketch_trisect(args: tuple[gm.Point, ...], **kwargs) -> tuple[Point, Point]:
    """Sketch two trisectors of an angle."""
    a, b, c = args
    ang1 = ang_of(b, a)
    ang2 = ang_of(b, c)

    swap = 0
    if ang1 > ang2:
        ang1, ang2 = ang2, ang1
        swap += 1

    if ang2 - ang1 > np.pi:
        ang1, ang2 = ang2, ang1 + 2 * np.pi
        swap += 1

    angx = ang1 + (ang2 - ang1) / 3
    angy = ang2 - (ang2 - ang1) / 3

    x = b + Point(np.cos(angx), np.sin(angx))
    y = b + Point(np.cos(angy), np.sin(angy))

    ac = Line(a, c)
    x = line_line_intersection(Line(b, x), ac)
    y = line_line_intersection(Line(b, y), ac)

    if swap == 1:
        return y, x
    return x, y


def sketch_trisegment(args: tuple[gm.Point, ...], **kwargs) -> tuple[Point, Point]:
    a, b = args
    x, y = a + (b - a) * (1.0 / 3), a + (b - a) * (2.0 / 3)
    return x, y


def sketch_on_opline(args: tuple[gm.Point, ...], **kwargs) -> HalfLine:
    a, b = args
    return HalfLine(a, a + a - b)


def sketch_on_hline(args: tuple[gm.Point, ...], **kwargs) -> HalfLine:
    a, b = args
    return HalfLine(a, b)


def sketch_ieq_triangle(
    args: tuple[gm.Point, ...], rnd_gen: Generator
) -> tuple[Point, ...]:
    a = Point(0.0, 0.0)
    b = Point(1.0, 0.0)

    c, _ = Circle(a, p1=b).intersect(Circle(b, p1=a))
    a, b, c = random_rfss(a, b, c, rnd_gen=rnd_gen)
    return a, b, c


def sketch_incenter2(args: tuple[gm.Point, ...], **kwargs) -> tuple[Point, ...]:
    a, b, c = args
    l1 = sketch_bisect([b, a, c])
    l2 = sketch_bisect([a, b, c])
    i = line_line_intersection(l1, l2)
    x = i.foot(Line(b, c))
    y = i.foot(Line(c, a))
    z = i.foot(Line(a, b))
    return x, y, z, i


def sketch_excenter2(args: tuple[gm.Point, ...], **kwargs) -> tuple[Point, ...]:
    a, b, c = args
    l1 = sketch_bisect([b, a, c])
    l2 = sketch_exbisect([a, b, c])
    i = line_line_intersection(l1, l2)
    x = i.foot(Line(b, c))
    y = i.foot(Line(c, a))
    z = i.foot(Line(a, b))
    return x, y, z, i


def sketch_centroid(args: tuple[gm.Point, ...], **kwargs) -> tuple[Point, ...]:
    a, b, c = args
    x = (b + c) * 0.5
    y = (c + a) * 0.5
    z = (a + b) * 0.5
    i = line_line_intersection(Line(a, x), Line(b, y))
    return x, y, z, i


def sketch_ninepoints(args: tuple[gm.Point, ...], **kwargs) -> tuple[Point, ...]:
    a, b, c = args
    x = (b + c) * 0.5
    y = (c + a) * 0.5
    z = (a + b) * 0.5
    c = Circle(p1=x, p2=y, p3=z)
    return x, y, z, c.center


def sketch_2l1c(args: tuple[gm.Point, ...], **kwargs) -> tuple[Point, ...]:
    """Sketch a circle touching two lines and another circle."""
    a, b, c, p = args
    bc, ac = Line(b, c), Line(a, c)
    circle = Circle(p, p1=a)

    d, d_ = line_circle_intersection(p.perpendicular_line(bc), circle)
    if bc.diff_side(d_, a):
        d = d_

    e, e_ = line_circle_intersection(p.perpendicular_line(ac), circle)
    if ac.diff_side(e_, b):
        e = e_

    df = d.perpendicular_line(Line(p, d))
    ef = e.perpendicular_line(Line(p, e))
    f = line_line_intersection(df, ef)

    g, g_ = line_circle_intersection(Line(c, f), circle)
    if bc.same_side(g_, a):
        g = g_

    b_ = c + (b - c) / b.distance(c)
    a_ = c + (a - c) / a.distance(c)
    m = (a_ + b_) * 0.5
    x = line_line_intersection(Line(c, m), Line(p, g))
    return x.foot(ac), x.foot(bc), g, x


def sketch_3peq(args: tuple[gm.Point, ...], rnd_gen: Generator) -> tuple[Point, ...]:
    a, b, c = args
    ab, _, ca = Line(a, b), Line(b, c), Line(c, a)

    z = b + (c - b) * rnd_gen.uniform(-0.5, 1.5)

    z_ = z * 2 - c
    ca_parallel_line = z_.parallel_line(ca)
    x = line_line_intersection(ca_parallel_line, ab)
    y = z * 2 - x
    return x, y, z


###### NEW FUNCTIONS FOR NEW DEFINITIONS ---- V. S.


def sketch_isosvertex(args: tuple[gm.Point, ...], **kwargs) -> Line:
    b, c = args
    m = (b + c) / 2.0

    return m.perpendicular_line(Line(b, c))


def sketch_aline0(args: tuple[gm.Point, ...], **kwargs) -> Line:
    """Sketch the construction aline."""
    A, B, C, D, E, F, G = args
    ab = A - B
    cd = C - D
    ef = E - F

    dab = A.distance(B)
    ang_ab = np.arctan2(ab.y / dab, ab.x / dab)

    dcd = C.distance(D)
    ang_cd = np.arctan2(cd.y / dcd, cd.x / dcd)

    d_ef = E.distance(F)
    ang_ef = np.arctan2(ef.y / d_ef, ef.x / d_ef)

    ang_gx = ang_ef + ang_cd - ang_ab
    X = G + Point(np.cos(ang_gx), np.sin(ang_gx))
    return Line(G, X)


def sketch_eqratio(args: tuple[gm.Point, ...], **kwargs) -> Circle:
    A, B, C, D, E, F, G = args

    dab = A.distance(B)
    dcd = C.distance(D)
    d_ef = E.distance(F)

    dgx = d_ef * dcd / dab
    return Circle(center=G, radius=dgx)


def sketch_rconst(args: tuple[gm.Point, ...], **kwargs) -> Circle:
    """Sketches point x such that ab/cx=r"""
    A, B, C, r = args
    dab = A.distance(B)
    length = float(dab / Fraction(r.name))
    return Circle(center=C, radius=length)


def sketch_eqratio6(args: tuple[gm.Point, ...], **kwargs) -> Circle | Line:
    """Sketches a point x such that ax/cx=ef/gh"""
    A, C, E, F, G, H = args
    d_ef = E.distance(F)
    dgh = G.distance(H)

    if dgh == d_ef:
        M = (A + C) * 0.5
        return M.perpendicular_line(Line(A, C))

    else:
        ratio = d_ef / dgh
        extremum_1 = (1 / (1 - ratio)) * (A - ratio * C)
        extremum_2 = (1 / (1 + ratio)) * (ratio * C + A)
        center = (extremum_1 + extremum_2) * 0.5
        radius = 0.5 * extremum_1.distance(extremum_2)
        return Circle(center=center, radius=radius)


def sketch_radiuscircle(args: tuple[gm.Point, ...], **kwargs) -> Circle:
    a, y = args
    return Circle(center=a, radius=y)


def sketch_rconst2(args: tuple[gm.Point, ...], **kwargs) -> Circle | Line:
    """Sketches point x such that ax/bx=r"""

    A, B, r = args
    ratio = Fraction(r.name)

    if ratio == 1 / 1:
        M = (A + B) * 0.5
        return M.perpendicular_line(Line(A, B))

    else:
        extremum_1 = (1 / (1 - ratio)) * (A - ratio * B)
        extremum_2 = (1 / (1 + ratio)) * (ratio * B + A)
        center = (extremum_1 + extremum_2) * 0.5
        radius = 0.5 * extremum_1.distance(extremum_2)
        return Circle(center=center, radius=radius)
