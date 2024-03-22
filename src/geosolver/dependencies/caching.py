from typing import TYPE_CHECKING, Optional


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

    if name in ["const", "aconst", "rconst"]:
        a, b, c, d, y = args
        a, b = sorted([a, b])
        c, d = sorted([c, d])
        return name, a, b, c, d, y

    if name in ["npara", "nperp", "para", "cong", "perp", "collx"]:
        a, b, c, d = args

        a, b = sorted([a, b])
        c, d = sorted([c, d])
        (a, b), (c, d) = sorted([(a, b), (c, d)])

        return (name, a, b, c, d)

    if name in ["midp", "midpoint"]:
        a, b, c = args
        b, c = sorted([b, c])
        return (name, a, b, c)

    if name in ["coll", "cyclic", "ncoll", "diff", "triangle"]:
        return (name,) + tuple(sorted(list(set(args))))

    if name == "circle":
        x, a, b, c = args
        return (name, x) + tuple(sorted([a, b, c]))

    if name in ["eqangle", "eqratio", "eqangle6", "eqratio6"]:
        a, b, c, d, e, f, g, h = args
        a, b = sorted([a, b])
        c, d = sorted([c, d])
        e, f = sorted([e, f])
        g, h = sorted([g, h])
        if tuple(sorted([a, b, e, f])) > tuple(sorted([c, d, g, h])):
            a, b, e, f, c, d, g, h = c, d, g, h, a, b, e, f
        if (a, b, c, d) > (e, f, g, h):
            a, b, c, d, e, f, g, h = e, f, g, h, a, b, c, d

        if name == "eqangle6":
            name = "eqangle"
        if name == "eqratio6":
            name = "eqratio"
        return (name,) + (a, b, c, d, e, f, g, h)

    if name in ["contri", "simtri", "simtri2", "contri2", "contri*", "simtri*"]:
        a, b, c, x, y, z = args
        (a, x), (b, y), (c, z) = sorted([(a, x), (b, y), (c, z)], key=sorted)
        (a, b, c), (x, y, z) = sorted([(a, b, c), (x, y, z)], key=sorted)
        return (name, a, b, c, x, y, z)

    if name in ["eqratio3"]:
        a, b, c, d, o, o = args
        (a, c), (b, d) = sorted([(a, c), (b, d)], key=sorted)
        (a, b), (c, d) = sorted([(a, b), (c, d)], key=sorted)
        return (name, a, b, c, d, o, o)

    if name in ["sameside", "s_angle"]:
        return (name,) + tuple(args)

    raise ValueError(f"Not recognize {name} to hash.")


def hashed(name: str, args: list["Point"], rename: bool = False) -> tuple[str, ...]:
    if name == "s_angle":
        args = [p.name if not rename else p.new_name for p in args[:-1]] + [
            str(args[-1])
        ]
    else:
        args = [p.name if not rename else p.new_name for p in args]
    return hashed_txt(name, args)
