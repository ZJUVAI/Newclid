#!/usr/bin/env python3
"""
Small helpers for the model_evidence writer contract.
"""

from __future__ import annotations

import json


def build_instruction_text():
    return (
        "Given the geometry image and the formal problem text, write a forward-thinking "
        "trace that explains the visible gap, motivates the auxiliary construction, "
        "and briefly carries the route to the goal."
    )


def join_natural_list(items):
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def render_coordinate_derivation_snippet(derivation, point_coords):
    witness = (derivation or {}).get("witness", {}) if isinstance(derivation, dict) else {}
    relation = (derivation or {}).get("relation", "") if isinstance(derivation, dict) else ""
    calc_type = (derivation or {}).get("calc_type", "") if isinstance(derivation, dict) else ""
    points = [
        point for point in ((derivation or {}).get("points") or [])
        if isinstance(point, str) and point in point_coords
    ]
    coords_text = ", ".join(
        f"{point}=({point_coords[point][0]},{point_coords[point][1]})"
        for point in points
    )
    if calc_type == "parallel":
        return (
            f"{coords_text}; vec({points[0]}{points[1]})={tuple(witness.get('vector_1', []))} and "
            f"vec({points[2]}{points[3]})={tuple(witness.get('vector_2', []))}, so the cross product is "
            f"{witness.get('cross', 0)} and {relation}."
        )
    if calc_type == "perpendicular":
        return (
            f"{coords_text}; vec({points[0]}{points[1]})={tuple(witness.get('vector_1', []))} and "
            f"vec({points[2]}{points[3]})={tuple(witness.get('vector_2', []))}, so the dot product is "
            f"{witness.get('dot', 0)} and {relation}."
        )
    if calc_type == "equal_length":
        return (
            f"{coords_text}; |{points[0]}{points[1]}|^2={witness.get('length_sq_1')} and "
            f"|{points[2]}{points[3]}|^2={witness.get('length_sq_2')}, so {relation}."
        )
    if calc_type == "midpoint":
        midpoint = tuple(witness.get("midpoint_of_endpoints", []))
        return (
            f"{coords_text}; the midpoint of {points[1]}{points[2]} is {midpoint}, which matches {points[0]} "
            f"up to residual {witness.get('midpoint_gap')}, and the collinearity residual is {witness.get('line_residual')}, so {relation}."
        )
    if calc_type == "collinear":
        return (
            f"{coords_text}; the signed area test gives residual {witness.get('area_residual')}, so {relation}."
        )
    return f"{coords_text}; {relation}."


def build_coordinate_derivation_block(plan, point_coords):
    lines = []
    for derivation in (plan.get("coordinate_derivations") or []) if isinstance(plan, dict) else []:
        if not isinstance(derivation, dict):
            continue
        rendered = derivation.get("rendered_text") or render_coordinate_derivation_snippet(derivation, point_coords)
        if rendered:
            lines.append(f"- {rendered}")
    return "\n".join(lines) if lines else "- No explicit coordinate computation is required."


def build_writer_handoff(plan):
    if not isinstance(plan, dict):
        return {}
    return {
        "selected_text_fact_ids": list(plan.get("selected_text_fact_ids") or []),
        "selected_coordinate_candidate_ids": list(plan.get("selected_coordinate_candidate_ids") or []),
        "visible_relations": list(plan.get("visible_relations") or []),
        "coordinate_relations": list(plan.get("coordinate_relations") or []),
        "bridge_steps": list(plan.get("bridge_steps") or []),
        "goal_finish": plan.get("goal_finish", ""),
    }


def dump_writer_handoff(plan):
    return json.dumps(build_writer_handoff(plan), ensure_ascii=False, indent=2)


__all__ = [
    "build_coordinate_derivation_block",
    "build_instruction_text",
    "build_writer_handoff",
    "dump_writer_handoff",
    "join_natural_list",
    "render_coordinate_derivation_snippet",
]
