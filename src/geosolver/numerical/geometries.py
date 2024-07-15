# Some variables are there for better code reading.


# Naming in geometry is a little different
# we stick to geometry naming to better read the code.


from typing import TYPE_CHECKING, Any, Iterable, Optional, Union, overload

from numpy.random import Generator
from geosolver.numerical import ATOM, close_enough
import numpy as np

if TYPE_CHECKING:
    pass

ObjNum = Union["PointNum", "LineNum", "CircleNum"]


class PointNum:
    """Numerical point."""

    def __init__(self, x: Any, y: Any):
        self.x: float = float(x)
        self.y: float = float(y)

    def __lt__(self, other: "PointNum") -> bool:
        return (self.x, self.y) < (other.x, other.y)

    def __gt__(self, other: "PointNum") -> bool:
        return (self.x, self.y) > (other.x, other.y)

    def __add__(self, p: "PointNum") -> "PointNum":
        return PointNum(self.x + p.x, self.y + p.y)

    def __sub__(self, p: "PointNum") -> "PointNum":
        return PointNum(self.x - p.x, self.y - p.y)

    def __mul__(self, f: Any) -> "PointNum":
        f = float(f)
        return PointNum(self.x * f, self.y * f)

    def __rmul__(self, f: Any) -> "PointNum":
        return self * float(f)

    def __truediv__(self, f: Any) -> "PointNum":
        f = float(f)
        return PointNum(self.x / f, self.y / f)

    def __floordiv__(self, f: Any) -> "PointNum":
        f = float(f)
        div = self / f
        return PointNum(int(div.x), int(div.y))

    def __str__(self) -> str:
        return "P({},{})".format(self.x, self.y)

    def __abs__(self) -> str:
        return np.sqrt(self.dot(self))

    def __iter__(self):
        return iter((self.x, self.y))

    def angle(self) -> float:
        return np.arctan2(self.y, self.x)

    def close_enough(self, point: "PointNum") -> bool:
        return close_enough(self.x, point.x) and close_enough(self.y, point.y)

    def midpoint(self, p: "PointNum") -> "PointNum":
        return PointNum(0.5 * (self.x + p.x), 0.5 * (self.y + p.y))

    def distance(self, p: Union["PointNum", "LineNum", "CircleNum"]) -> float:
        return np.sqrt(self.distance2(p))

    def distance2(self, p: Union["PointNum", "LineNum", "CircleNum"]) -> float:
        if isinstance(p, LineNum):
            return p.distance(self)
        if isinstance(p, CircleNum):
            return (p.radius - self.distance(p.center)) ** 2
        dx = self.x - p.x
        dy = self.y - p.y
        dx2 = dx * dx
        dy2 = dy * dy
        dx2 = dx2 if abs(dx2) > ATOM else 0.0
        dy2 = dy2 if abs(dy2) > ATOM else 0.0
        return dx * dx + dy * dy

    def rotatea(self, ang: Any) -> "PointNum":
        ang = float(ang)
        sinb, cosb = np.sin(ang), np.cos(ang)
        return self.rotate(sinb, cosb)

    def rotate(self, sinb: float, cosb: float) -> "PointNum":
        sinb = float(sinb)
        cosb = float(cosb)
        x, y = self.x, self.y
        return PointNum(x * cosb - y * sinb, x * sinb + y * cosb)

    def flip(self) -> "PointNum":
        return PointNum(-self.x, self.y)

    def perpendicular_line(self, line: "LineNum") -> "LineNum":
        return line.perpendicular_line(self)

    def foot(self, line: Union["LineNum", "CircleNum"]) -> "PointNum":
        if isinstance(line, LineNum):
            perpendicular_line = line.perpendicular_line(self)
            return line_line_intersection(perpendicular_line, line)
        else:
            c, r = line.center, line.radius
            return c + (self - c) * r / self.distance(c)

    def parallel_line(self, line: "LineNum") -> "LineNum":
        return line.parallel_line(self)

    def norm(self) -> float:
        return np.sqrt(self.x**2 + self.y**2)

    def cos(self, other: "PointNum") -> float:
        x, y = self.x, self.y
        a, b = other.x, other.y
        return (x * a + y * b) / self.norm() / other.norm()

    def dot(self, other: "PointNum") -> float:
        return self.x * other.x + self.y * other.y

    def sign(self, line: "LineNum") -> int:
        return line.sign(self)

    @classmethod
    def deduplicate(cls, points: Iterable["PointNum"]) -> list["PointNum"]:
        res: list["PointNum"] = []
        for p in points:
            if all(not r.close_enough(p) for r in res):
                res.append(p)
        return res

    def intersect(self, obj: ObjNum) -> list["PointNum"]:
        raise NotImplementedError()


class LineNum:
    """Numerical line."""

    def __init__(
        self,
        p1: Optional["PointNum"] = None,
        p2: Optional["PointNum"] = None,
        coefficients: Optional[tuple[float, float, float]] = None,
    ):
        a, b, c = None, None, None
        if coefficients:
            a, b, c = coefficients
        elif p1 and p2:
            a, b, c = (
                p1.y - p2.y,
                p2.x - p1.x,
                p1.x * p2.y - p2.x * p1.y,
            )
        assert a is not None and b is not None and c is not None

        # Make sure a is always positive (or always negative for that matter)
        # With a == 0, Assuming a = +epsilon > 0
        # Then b such that ax + by = 0 with y>0 should be negative.
        if a < -ATOM or abs(a) < ATOM and b > ATOM:
            a, b, c = -a, -b, -c

        self.coefficients = a, b, c

    def parallel_line(self, p: "PointNum") -> "LineNum":
        a, b, _ = self.coefficients
        return LineNum(coefficients=(a, b, -a * p.x - b * p.y))

    def perpendicular_line(self, p: "PointNum") -> "LineNum":
        a, b, _ = self.coefficients
        return LineNum(p, p + PointNum(a, b))

    def same(self, other: "LineNum") -> bool:
        a, b, c = self.coefficients
        x, y, z = other.coefficients
        return close_enough(a * y, b * x) and close_enough(b * z, c * y)

    def intersect(self, obj: ObjNum) -> list[PointNum]:
        if isinstance(obj, LineNum):
            return [line_line_intersection(self, obj)]
        elif isinstance(obj, CircleNum):
            res = PointNum.deduplicate(line_circle_intersection(self, obj))
            if len(res) == 0:
                raise InvalidIntersectError()
            return res
        else:
            raise NotImplementedError()

    def distance(self, p: "PointNum") -> float:
        a, b, _ = self.coefficients
        return abs(self(p.x, p.y)) / np.sqrt(a * a + b * b)

    @overload
    def __call__(self, x: PointNum) -> float:
        ...

    @overload
    def __call__(self, x: float, y: float) -> float:
        ...

    def __call__(self, x: Any, y: Any = None) -> float:
        if isinstance(x, PointNum) and y is None:
            return self(x.x, x.y)
        a, b, c = self.coefficients
        return x * a + y * b + c

    def is_parallel(self, other: "LineNum") -> bool:
        a, b, _ = self.coefficients
        x, y, _ = other.coefficients
        return abs(a * y - b * x) < ATOM

    def is_perp(self, other: "LineNum") -> bool:
        a, b, _ = self.coefficients
        x, y, _ = other.coefficients
        return abs(a * x + b * y) < 5 * ATOM

    def cross(self, other: "LineNum") -> float:
        a, b, _ = self.coefficients
        x, y, _ = other.coefficients
        return a * y - b * x

    def dot(self, other: "LineNum") -> float:
        a, b, _ = self.coefficients
        x, y, _ = other.coefficients
        return a * x + b * y

    def point_at(
        self, x: Optional[float] = None, y: Optional[float] = None
    ) -> Optional[PointNum]:
        """Infer the point on the line by its x and/or y coordinate(s)"""
        a, b, c = self.coefficients
        # ax + by + c = 0
        if x is None and y is not None:
            if not close_enough(a, 0):
                return PointNum((-c - b * y) / a, y)
            else:
                return None
        elif x is not None and y is None:
            if not close_enough(b, 0):
                return PointNum(x, (-c - a * x) / b)
            else:
                return None
        elif x is not None and y is not None:
            if close_enough(a * x + b * y, -c):
                return PointNum(x, y)
        return None

    def diff_side(self, p1: "PointNum", p2: "PointNum") -> Optional[bool]:
        d1 = self(p1.x, p1.y)
        d2 = self(p2.x, p2.y)
        if close_enough(d1, 0) or close_enough(d2, 0):
            return None
        return d1 * d2 < 0

    def same_side(self, p1: "PointNum", p2: "PointNum") -> Optional[bool]:
        d1 = self(p1.x, p1.y)
        d2 = self(p2.x, p2.y)
        if close_enough(d1, 0) or close_enough(d2, 0):
            return None
        return d1 * d2 > 0

    def sign(self, point: "PointNum") -> int:
        s = self(point.x, point.y)
        if s > 0:
            return 1
        elif s < 0:
            return -1
        return 0

    def is_same(self, other: "LineNum") -> bool:
        a, b, c = self.coefficients
        x, y, z = other.coefficients
        return close_enough(a * y, b * x) and close_enough(b * z, c * y)

    def sample_within(
        self, points: list[PointNum], n: int = 5, *, rng: Generator
    ) -> PointNum:
        """Sample a point within the boundary of points."""
        center = sum(points, PointNum(0.0, 0.0)) / len(points)
        radius = max([p.distance(center) for p in points])

        if close_enough(center.distance(self), radius):
            center = center.foot(self)
        a, b = line_circle_intersection(self, CircleNum(center.foot(self), radius))

        result = None
        best = -1.0
        for _ in range(n):
            rand = rng.uniform(0.0, 1.0)
            x = a + (b - a) * rand
            mind = min([x.distance(p) for p in points])
            if mind > best:
                best = mind
                result = x
        assert result
        return result


class CircleNum:
    """Numerical circle."""

    def __init__(
        self,
        center: Optional[PointNum] = None,
        radius: Optional[float] = None,
        p1: Optional[PointNum] = None,
        p2: Optional[PointNum] = None,
        p3: Optional[PointNum] = None,
    ):
        if not center:
            if not (p1 and p2 and p3):
                raise ValueError("Circle without center need p1 p2 p3")

            l12 = perpendicular_bisector(p1, p2)
            l23 = perpendicular_bisector(p2, p3)
            self.center = line_line_intersection(l12, l23)
        else:
            self.center = center

        self.a, self.b = self.center.x, self.center.y

        if not radius:
            p = p1 or p2 or p3
            if p is None:
                raise ValueError("Circle needs radius or p1 or p2 or p3")
            self.r2 = (self.a - p.x) ** 2 + (self.b - p.y) ** 2
            self.radius = np.sqrt(self.r2)
        else:
            self.radius = radius
            self.r2 = radius * radius

    def intersect(self, obj: ObjNum) -> list[PointNum]:
        if isinstance(obj, LineNum):
            return obj.intersect(self)
        elif isinstance(obj, CircleNum):
            return PointNum.deduplicate(
                c for c in circle_circle_intersection(self, obj)
            )
        raise NotImplementedError()

    def sample_within(
        self, points: list[PointNum], n: int = 5, *, rng: Generator
    ) -> PointNum:
        """Sample a point within the boundary of points."""
        result = None
        best = -1.0

        for _ in range(n):
            ang = rng.uniform(0.0, 2.0) * np.pi
            x = self.center + PointNum(np.cos(ang), np.sin(ang)) * self.radius
            mind = min([x.distance(p) for p in points])
            if mind > best:
                best = mind
                result = x

        assert result
        return result


def perpendicular_bisector(p1: "PointNum", p2: "PointNum") -> "LineNum":
    midpoint = (p1 + p2) * 0.5
    return LineNum(midpoint, midpoint + PointNum(p2.y - p1.y, p1.x - p2.x))


class InvalidIntersectError(Exception):
    pass


class InvalidReduceError(Exception):
    pass


class InvalidQuadSolveError(Exception):
    pass


def solve_quad(a: float, b: float, c: float) -> Optional[tuple[float, float]]:
    """Solve a x^2 + bx + c = 0."""
    a = 2 * a
    d = b * b - 2 * a * c
    if d < -ATOM:
        return None  # the caller should expect this result.
    if abs(d) < ATOM:
        d = 0.0
    y = np.sqrt(d)
    return (-b - y) / (a + ATOM), (-b + y) / (a + ATOM)


def circle_circle_intersection(
    c1: CircleNum, c2: CircleNum
) -> tuple[PointNum, PointNum]:
    """Returns a pair of Points as intersections of c1 and c2."""
    # circle 1: (x0, y0), radius r0
    # circle 2: (x1, y1), radius r1
    x0, y0, r0 = c1.a, c1.b, c1.radius
    x1, y1, r1 = c2.a, c2.b, c2.radius

    d = np.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2)
    if abs(d) < ATOM:
        raise InvalidQuadSolveError()

    a = (r0**2 - r1**2 + d**2) / (2 * d)
    h = r0**2 - a**2
    if h < -ATOM:
        raise InvalidQuadSolveError()
    if abs(h) < ATOM:
        h = 0.0
    h = np.sqrt(h)
    d += ATOM
    x2 = x0 + a * (x1 - x0) / d
    y2 = y0 + a * (y1 - y0) / d
    x3 = x2 + h * (y1 - y0) / d
    y3 = y2 - h * (x1 - x0) / d
    x4 = x2 - h * (y1 - y0) / d
    y4 = y2 + h * (x1 - x0) / d

    return PointNum(x3, y3), PointNum(x4, y4)


def line_circle_intersection(
    line: LineNum, circle: CircleNum
) -> tuple[PointNum, PointNum]:
    """Returns a pair of points as intersections of line and circle."""
    a, b, c = line.coefficients
    r = float(circle.radius)
    center = circle.center
    p, q = center.x, center.y

    if abs(b) < ATOM:
        x = -c / a
        x_p = x - p
        x_p2 = x_p * x_p
        y = solve_quad(1, -2 * q, q * q + x_p2 - r * r)
        if y is None:
            raise InvalidQuadSolveError()
        y1, y2 = y
        return (PointNum(x, y1), PointNum(x, y2))

    if abs(a) < ATOM:
        y = -c / b
        y_q = y - q
        y_q2 = y_q * y_q
        x = solve_quad(1, -2 * p, p * p + y_q2 - r * r)
        if x is None:
            raise InvalidQuadSolveError()
        x1, x2 = x
        return (PointNum(x1, y), PointNum(x2, y))

    c_ap = c + a * p
    a2 = a * a
    y = solve_quad(
        a2 + b * b, 2 * (b * c_ap - a2 * q), c_ap * c_ap + a2 * (q * q - r * r)
    )
    if y is None:
        raise InvalidQuadSolveError()
    y1, y2 = y

    return PointNum(-(b * y1 + c) / a, y1), PointNum(-(b * y2 + c) / a, y2)


def _check_between(a: PointNum, b: PointNum, c: PointNum) -> bool:
    """Whether a is between b & c."""
    # return (a - b).dot(c - b) > 0 and (a - c).dot(b - c) > 0
    return (a - b).dot(c - b) > ATOM and (a - c).dot(b - c) > ATOM


def circle_segment_intersect(
    circle: CircleNum, p1: PointNum, p2: PointNum
) -> list[PointNum]:
    line = LineNum(p1, p2)
    px, py = line_circle_intersection(line, circle)

    result: list[PointNum] = []
    if _check_between(px, p1, p2):
        result.append(px)
    if _check_between(py, p1, p2):
        result.append(py)
    return result


def line_segment_intersection(line: LineNum, A: PointNum, B: PointNum) -> PointNum:
    a, b, c = line.coefficients
    x1, y1, x2, y2 = A.x, A.y, B.x, B.y
    dx, dy = x2 - x1, y2 - y1
    alpha = (-c - a * x1 - b * y1) / (a * dx + b * dy)
    return PointNum(x1 + alpha * dx, y1 + alpha * dy)


def line_line_intersection(line_1: LineNum, line_2: LineNum) -> PointNum:
    a1, b1, c1 = line_1.coefficients
    a2, b2, c2 = line_2.coefficients
    # a1x + b1y + c1 = 0
    # a2x + b2y + c2 = 0
    d = a1 * b2 - a2 * b1
    if abs(d) < ATOM:
        raise InvalidIntersectError
    return PointNum((c2 * b1 - c1 * b2) / d, (c1 * a2 - c2 * a1) / d)


def reduce(
    objs: list[ObjNum],
    existing_points: list[PointNum],
    rng: Generator,
) -> list[PointNum]:
    """
    If all PointNum, then no touch.
    Else reduce intersecting objects into one point of intersections other than the existing points.
    """
    if all(isinstance(o, PointNum) for o in objs):
        return objs  # type: ignore
    elif len(objs) == 1:
        obj = objs[0]
        assert not isinstance(obj, PointNum)
        return [obj.sample_within(existing_points, rng=rng)]

    elif len(objs) == 2:
        u, v = objs
        result: list[PointNum] = u.intersect(v)
        if len(result) == 1:
            return result
        a, b = result
        a_close = any([a.close_enough(x) for x in existing_points])
        if a_close:
            return [b]
        b_close = any([b.close_enough(x) for x in existing_points])
        if b_close:
            return [a]
        return [rng.choice([a, b])]  # type: ignore

    else:
        raise NotImplementedError()
