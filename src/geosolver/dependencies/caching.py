from __future__ import annotations
from typing import TYPE_CHECKING, Optional, Tuple, TypeVar, Union

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


def hashed_txt(name: Union[str, Predicate], args: list[str]) -> tuple[str, ...]:
    """Return a tuple unique to name and args upto arg permutation equivariant."""
    predicate = Predicate(name)
    if isinstance(name, Predicate):
        name = predicate.value
    if predicate is Predicate.EQANGLE6:
        name = Predicate.EQANGLE.value
    if predicate is Predicate.EQRATIO6:
        name = Predicate.EQRATIO.value
    return PREDICATE_TO_HASH[predicate](name, args)


P = TypeVar("P")


def _hash_unordered_set_of_points(name: str, args: list[P]) -> list[str | P]:
    return (name,) + tuple(sorted(list(set(args))))


def _hash_ordered_list_of_points(name: str, args: list[P]) -> list[str | P]:
    return (name,) + tuple(args)


def _hash_point_then_set_of_points(name: str, args: list[P]):
    return (name, args[0]) + tuple(sorted(args[1:]))


def _hashed_unordered_two_lines_points(
    name: str, args: tuple[P, P, P, P]
) -> Tuple[str, P, P, P, P]:
    a, b, c, d = args

    a, b = sorted([a, b])
    c, d = sorted([c, d])
    (a, b), (c, d) = sorted([(a, b), (c, d)])

    return (name, a, b, c, d)


def _hash_ordered_two_lines_with_value(
    name: str, args: tuple[P, P, P, P, P]
) -> Tuple[str, P, P, P, P, P]:
    a, b, c, d, y = args
    a, b = sorted([a, b])
    c, d = sorted([c, d])
    return name, a, b, c, d, y


def _hash_point_and_line(name: str, args: tuple[P, P, P]) -> Tuple[str, P, P, P]:
    a, b, c = args
    b, c = sorted([b, c])
    return (name, a, b, c)


def _hash_two_times_two_unorded_lines(
    name: str, args: tuple[P, P, P, P, P, P, P, P]
) -> Tuple[str, P, P, P, P, P, P, P, P]:
    a, b, c, d, e, f, g, h = args
    a, b = sorted([a, b])
    c, d = sorted([c, d])
    e, f = sorted([e, f])
    g, h = sorted([g, h])
    if tuple(sorted([a, b, e, f])) > tuple(sorted([c, d, g, h])):
        a, b, e, f, c, d, g, h = c, d, g, h, a, b, e, f
    if (a, b, c, d) > (e, f, g, h):
        a, b, c, d, e, f, g, h = e, f, g, h, a, b, c, d

    return (name,) + (a, b, c, d, e, f, g, h)


def _hash_triangle(
    name: str, args: tuple[P, P, P, P, P, P]
) -> Tuple[str, P, P, P, P, P, P]:
    a, b, c, x, y, z = args
    (a, x), (b, y), (c, z) = sorted([(a, x), (b, y), (c, z)], key=sorted)
    (a, b, c), (x, y, z) = sorted([(a, b, c), (x, y, z)], key=sorted)
    return (name, a, b, c, x, y, z)


def _hash_eqratio_3(
    name: str, args: tuple[P, P, P, P, P, P]
) -> Tuple[str, P, P, P, P, P, P]:
    a, b, c, d, o, o = args
    (a, c), (b, d) = sorted([(a, c), (b, d)], key=sorted)
    (a, b), (c, d) = sorted([(a, b), (c, d)], key=sorted)
    return (name, a, b, c, d, o, o)


PREDICATE_TO_HASH = {
    Predicate.PARALLEL: _hashed_unordered_two_lines_points,
    Predicate.CONGRUENT: _hashed_unordered_two_lines_points,
    Predicate.PERPENDICULAR: _hashed_unordered_two_lines_points,
    Predicate.COLLINEAR_X: _hashed_unordered_two_lines_points,
    Predicate.NON_PARALLEL: _hashed_unordered_two_lines_points,
    Predicate.NON_PERPENDICULAR: _hashed_unordered_two_lines_points,
    Predicate.COLLINEAR: _hash_unordered_set_of_points,
    Predicate.CYCLIC: _hash_unordered_set_of_points,
    Predicate.NON_COLLINEAR: _hash_unordered_set_of_points,
    Predicate.DIFFERENT: _hash_unordered_set_of_points,
    Predicate.CIRCLE: _hash_point_then_set_of_points,
    Predicate.MIDPOINT: _hash_point_and_line,
    Predicate.CONSTANT_ANGLE: _hash_ordered_two_lines_with_value,
    Predicate.CONSTANT_RATIO: _hash_ordered_two_lines_with_value,
    Predicate.EQANGLE: _hash_two_times_two_unorded_lines,
    Predicate.EQRATIO: _hash_two_times_two_unorded_lines,
    Predicate.EQANGLE6: _hash_two_times_two_unorded_lines,
    Predicate.EQRATIO6: _hash_two_times_two_unorded_lines,
    Predicate.SAMESIDE: _hash_ordered_list_of_points,
    Predicate.S_ANGLE: _hash_ordered_list_of_points,
    Predicate.SIMILAR_TRIANGLE: _hash_triangle,
    Predicate.SIMILAR_TRIANGLE_REFLECTED: _hash_triangle,
    Predicate.SIMILAR_TRIANGLE_BOTH: _hash_triangle,
    Predicate.CONTRI_TRIANGLE: _hash_triangle,
    Predicate.CONTRI_TRIANGLE_REFLECTED: _hash_triangle,
    Predicate.CONTRI_TRIANGLE_BOTH: _hash_triangle,
    Predicate.EQRATIO3: _hash_eqratio_3,
}


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
