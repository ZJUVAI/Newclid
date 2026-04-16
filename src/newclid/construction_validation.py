from __future__ import annotations

from collections.abc import Collection

from newclid.formulations.clause import Clause
from newclid.formulations.definition import DefinitionJGEX
from newclid.tools import atomize


def build_construction_mapping(
    construction: Clause,
    constr_sentence: tuple[str, ...],
    cdef: DefinitionJGEX,
) -> dict[str, str]:
    if len(constr_sentence) == len(cdef.declare):
        return dict(zip(cdef.declare[1:], constr_sentence[1:]))

    assert len(constr_sentence) + len(construction.points) == len(cdef.declare)
    return dict(zip(cdef.declare[1:], construction.points + constr_sentence[1:]))


def clause_point_names(construction: Clause) -> tuple[str, ...]:
    point_names: list[str] = []
    for point in construction.points:
        if "@" in point:
            point, _ = atomize(point, "@")
        point_names.append(point)
    return tuple(point_names)


def validate_construction_new_points(
    construction: Clause,
    defs: dict[str, DefinitionJGEX],
    existing_point_names: Collection[str],
) -> tuple[str, ...]:
    existing_names = set(existing_point_names)

    for constr_sentence in construction.sentences:
        cdef = defs[constr_sentence[0]]
        mapping = build_construction_mapping(construction, constr_sentence, cdef)
        for point in cdef.points:
            if mapping[point] in existing_names:
                raise Exception(
                    "The new point "
                    f"{mapping[point]} is already used. existing points: {sorted(existing_names)}. "
                    f"construction: {construction}"
                )

    point_names = clause_point_names(construction)
    for point_name in point_names:
        if point_name in existing_names:
            raise Exception(
                "The new point "
                f"{point_name} is already used. existing points: {sorted(existing_names)}. "
                f"construction: {construction}"
            )
    return point_names
