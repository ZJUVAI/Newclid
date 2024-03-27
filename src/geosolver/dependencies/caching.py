from typing import TYPE_CHECKING, Optional

from geosolver.concepts import ConceptName


if TYPE_CHECKING:
    from geosolver.geometry import Point
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

    if name in [
        ConceptName.CONSTANT_ANGLE.value,
        ConceptName.CONSTANT_RATIO.value,
    ]:
        a, b, c, d, y = args
        a, b = sorted([a, b])
        c, d = sorted([c, d])
        return name, a, b, c, d, y

    if name in [
        ConceptName.NON_PARALLEL.value,
        ConceptName.NON_PERPENDICULAR.value,
        ConceptName.PARALLEL.value,
        ConceptName.CONGRUENT.value,
        ConceptName.PERPENDICULAR.value,
        ConceptName.COLLINEAR_X.value,
    ]:
        a, b, c, d = args

        a, b = sorted([a, b])
        c, d = sorted([c, d])
        (a, b), (c, d) = sorted([(a, b), (c, d)])

        return (name, a, b, c, d)

    if name in [ConceptName.MIDPOINT.value, "midpoint"]:
        a, b, c = args
        b, c = sorted([b, c])
        return (name, a, b, c)

    if name in [
        ConceptName.COLLINEAR.value,
        ConceptName.CYCLIC.value,
        ConceptName.NON_COLLINEAR.value,
        ConceptName.DIFFERENT.value,
        "triangle",
    ]:
        return (name,) + tuple(sorted(list(set(args))))

    if name == ConceptName.CIRCLE.value:
        x, a, b, c = args
        return (name, x) + tuple(sorted([a, b, c]))

    if name in [
        ConceptName.EQANGLE.value,
        ConceptName.EQRATIO.value,
        ConceptName.EQANGLE6.value,
        ConceptName.EQRATIO6.value,
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

        if name == ConceptName.EQANGLE6.value:
            name = ConceptName.EQANGLE.value
        if name == ConceptName.EQRATIO6.value:
            name = ConceptName.EQRATIO.value
        return (name,) + (a, b, c, d, e, f, g, h)

    if name in [
        ConceptName.SIMILAR_TRIANGLE.value,
        ConceptName.SIMILAR_TRIANGLE_REFLECTED.value,
        ConceptName.SIMILAR_TRIANGLE_BOTH.value,
        ConceptName.CONTRI_TRIANGLE.value,
        ConceptName.CONTRI_TRIANGLE_REFLECTED.value,
        ConceptName.CONTRI_TRIANGLE_BOTH.value,
    ]:
        a, b, c, x, y, z = args
        (a, x), (b, y), (c, z) = sorted([(a, x), (b, y), (c, z)], key=sorted)
        (a, b, c), (x, y, z) = sorted([(a, b, c), (x, y, z)], key=sorted)
        return (name, a, b, c, x, y, z)

    if name in [ConceptName.EQRATIO3.value]:
        a, b, c, d, o, o = args
        (a, c), (b, d) = sorted([(a, c), (b, d)], key=sorted)
        (a, b), (c, d) = sorted([(a, b), (c, d)], key=sorted)
        return (name, a, b, c, d, o, o)

    if name in [ConceptName.SAMESIDE.value, ConceptName.S_ANGLE.value]:
        return (name,) + tuple(args)

    raise ValueError(f"Not recognize {name} to hash.")


def hashed(name: str, args: list["Point"], rename: bool = False) -> tuple[str, ...]:
    if name == ConceptName.S_ANGLE.value:
        args = [p.name if not rename else p.new_name for p in args[:-1]] + [
            str(args[-1])
        ]
    else:
        args = [p.name if not rename else p.new_name for p in args]
    return hashed_txt(name, args)
