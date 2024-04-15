from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from geosolver.proof import Proof
    from geosolver.geometry import Point
    from geosolver.dependencies.dependency import Dependency


def apply_derivations(
    proof: "Proof", derives: dict[str, list[tuple["Point", ...]]]
) -> list["Dependency"]:
    applied = []
    for name, args in derives.items():
        for arg in args:
            applied += proof.do_algebra(name, arg)
    return applied
