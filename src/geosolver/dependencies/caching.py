from __future__ import annotations
from typing import TYPE_CHECKING, Optional

from geosolver.predicates import Predicate
from geosolver.geometry import Point, Ratio

if TYPE_CHECKING:
    from geosolver.dependencies.dependency import Dependency


class DependencyCache:
    def __init__(self, *args, **kwargs):
        self.cache = {}

    def add_dependency(
        self, name: str, args: list["Point"], dep: "Dependency", rename: bool = False
    ):
        dep_hash = hashed(name, args, rename)
        if dep_hash in self.cache:
            return
        self.cache[dep_hash] = dep

    def get(
        self, name: str, args: list["Point"], rename: bool = False
    ) -> Optional["Dependency"]:
        return self.cache.get(hashed(name, args, rename))

    def get_cached(self, dep: "Dependency") -> Optional["Dependency"]:
        return self.cache.get(dep.hashed())

    def contains(
        self, name: str, args: list["Point"], rename: bool = False
    ) -> Optional["Dependency"]:
        return hashed(name, args, rename) in self.cache

    def __contains__(self, obj: object):
        if not isinstance(obj, "Dependency"):
            return False
        return obj.hashed() in self.cache


def hashed_txt(name: str, args: list[str]) -> tuple[str, ...]:
    """Return a tuple unique to name and args upto arg permutation equivariant."""

    if name in [Predicate.CONSTANT_ANGLE.value, Predicate.CONSTANT_RATIO.value]:
        a, b, c, d, y = args
        a, b = sorted([a, b])
        c, d = sorted([c, d])
        return name, a, b, c, d, y

    if name in [
        Predicate.NON_PARALLEL.value,
        Predicate.NON_PERPENDICULAR.value,
        Predicate.PARALLEL.value,
        Predicate.CONGRUENT.value,
        Predicate.PERPENDICULAR.value,
        Predicate.COLLINEAR_X.value,
    ]:
        a, b, c, d = args

        a, b = sorted([a, b])
        c, d = sorted([c, d])
        (a, b), (c, d) = sorted([(a, b), (c, d)])

        return (name, a, b, c, d)

    if name in [Predicate.MIDPOINT.value, "midpoint"]:
        a, b, c = args
        b, c = sorted([b, c])
        return (name, a, b, c)

    if name in [
        Predicate.COLLINEAR.value,
        Predicate.CYCLIC.value,
        Predicate.NON_COLLINEAR.value,
        Predicate.DIFFERENT.value,
        "triangle",
    ]:
        return (name,) + tuple(sorted(list(set(args))))

    if name == Predicate.CIRCLE.value:
        x, a, b, c = args
        return (name, x) + tuple(sorted([a, b, c]))

    if name in [
        Predicate.EQANGLE.value,
        Predicate.EQRATIO.value,
        Predicate.EQANGLE6.value,
        Predicate.EQRATIO6.value,
    ]:
        a, b, c, d, e, f, g, h = args
        a, b = sorted([a, b])
        c, d = sorted([c, d])
        e, f = sorted([e, f])
        g, h = sorted([g, h])
        if tuple(sorted([a, b, e, f])) > tuple(sorted([c, d, g, h])):
            a, b, e, f, c, d, g, h = c, d, g, h, a, b, e, f
        if (a, b, c, d) > (e, f, g, h):
            a, b, c, d, e, f, g, h = e, f, g, h, a, b, c, d

        if name == Predicate.EQANGLE6.value:
            name = Predicate.EQANGLE.value
        if name == Predicate.EQRATIO6.value:
            name = Predicate.EQRATIO.value
        return (name,) + (a, b, c, d, e, f, g, h)

    if name in [
        Predicate.SIMILAR_TRIANGLE.value,
        Predicate.SIMILAR_TRIANGLE_REFLECTED.value,
        Predicate.SIMILAR_TRIANGLE_BOTH.value,
        Predicate.CONTRI_TRIANGLE.value,
        Predicate.CONTRI_TRIANGLE_REFLECTED.value,
        Predicate.CONTRI_TRIANGLE_BOTH.value,
    ]:
        a, b, c, x, y, z = args
        (a, x), (b, y), (c, z) = sorted([(a, x), (b, y), (c, z)], key=sorted)
        (a, b, c), (x, y, z) = sorted([(a, b, c), (x, y, z)], key=sorted)
        return (name, a, b, c, x, y, z)

    if name in [Predicate.EQRATIO3.value]:
        a, b, c, d, o, o = args
        (a, c), (b, d) = sorted([(a, c), (b, d)], key=sorted)
        (a, b), (c, d) = sorted([(a, b), (c, d)], key=sorted)
        return (name, a, b, c, d, o, o)

    if name in [Predicate.SAMESIDE.value, Predicate.S_ANGLE.value]:
        return (name,) + tuple(args)

    raise ValueError(f"Not recognize {name} to hash.")


def hashed(
    name: str, args: list["Point" | "Ratio" | int], rename: bool = False
) -> tuple[str, ...]:
    return hashed_txt(name, [symbol_to_txt(p, rename=rename) for p in args])


def symbol_to_txt(symbol: "Point" | "Ratio" | int, rename):
    if isinstance(symbol, int):
        return str(symbol)

    if rename and isinstance(symbol, Point):
        return symbol.new_name

    return symbol.name
