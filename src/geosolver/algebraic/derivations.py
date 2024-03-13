from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from geosolver.proof_graph import ProofGraph
    from geosolver.geometry import Point
    from geosolver.problem import Dependency


def apply_derivations(
    g: "ProofGraph", derives: dict[str, list[tuple["Point", ...]]]
) -> list["Dependency"]:
    applied = []
    all_derives = list(derives.items())
    for name, args in all_derives:
        for arg in args:
            applied += g.do_algebra(name, arg)
    return applied
