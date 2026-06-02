from __future__ import annotations

import re

from newclid.predicates.collinearity import Coll
from newclid.predicates.congruence import Cong
from newclid.predicates.cyclic import Cyclic
from newclid.predicates.equal_angles import EqAngle
from newclid.predicates.equal_ratios import EqRatio
from newclid.predicates.midpoint import MidPoint
from newclid.predicates.parallelism import Para
from newclid.predicates.perpendicularity import Perp


AUX_PREFIX_RE = re.compile(r"^x\d+\s+")
ALLOWED_AUX_PREDICATES = frozenset(
    {"perp", "para", "cong", "coll", "cyclic", "midp", "eqangle", "eqratio"}
)


def extract_tag_content(text: str, tag: str) -> str:
    match = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL)
    return match.group(1).strip() if match else ""


def split_segments(text: str) -> list[str]:
    return [segment.strip() for segment in text.split(";") if segment.strip()]


def extract_tag_segments(
    text: str, tag: str, *, strip_aux_prefix: bool = False
) -> list[str]:
    content = extract_tag_content(text, tag)
    if not content:
        return []
    segments = split_segments(content)
    if not strip_aux_prefix:
        return segments
    return [AUX_PREFIX_RE.sub("", segment).strip() for segment in segments if segment]


def arrange_angle_points(a: str, b: str, c: str, d: str) -> tuple[str, str, str] | None:
    if a == c:
        return b, a, d
    if a == d:
        return b, a, c
    if b == c:
        return a, b, d
    if b == d:
        return a, b, c
    return None


def translate_eqangle(point: str, args: list[str]) -> str | None:
    if len(args) != 8:
        return None

    a, b, c, d, e, f, g, h = args
    if len({a, b, c, d, e, f, g, h}) == 8:
        if point == h:
            return f"on_aline0 {h} {a} {b} {c} {d} {e} {f} {g}"
        if point == g:
            return f"on_aline0 {g} {a} {b} {c} {d} {e} {f} {h}"
        if point == f:
            return f"on_aline0 {f} {c} {d} {a} {b} {g} {h} {e}"
        if point == e:
            return f"on_aline0 {e} {c} {d} {a} {b} {g} {h} {f}"
        if point == d:
            return f"on_aline0 {d} {e} {f} {g} {h} {a} {b} {c}"
        if point == c:
            return f"on_aline0 {c} {e} {f} {g} {h} {a} {b} {d}"
        if point == b:
            return f"on_aline0 {b} {g} {h} {e} {f} {c} {d} {a}"
        if point == a:
            return f"on_aline0 {a} {g} {h} {e} {f} {c} {d} {b}"
        return None

    if len({a, b, c, d}) == 4 and len({a, b, e, f}) == 3:
        a, b, c, d, e, f, g, h = a, b, e, f, c, d, g, h
    left = arrange_angle_points(a, b, c, d)
    right = arrange_angle_points(e, f, g, h)
    if left is None or right is None:
        return None
    return EqAngle.to_constructive(point, left + right)


def translate_dsl_to_construction(
    point: str, predicate: str, args: list[str]
) -> str | None:
    translators = {
        "perp": Perp,
        "para": Para,
        "cong": Cong,
        "midp": MidPoint,
        "coll": Coll,
        "cyclic": Cyclic,
        "eqratio": EqRatio,
    }
    if predicate in translators:
        return translators[predicate].to_constructive(point, tuple(args))
    if predicate == "eqangle":
        return translate_eqangle(point, args)
    return None


def translate_aux_segment(segment: str) -> str | None:
    if ":" not in segment:
        return None

    points_part, premises_part = re.split(r"\s*:\s*", segment, maxsplit=1)
    points = points_part.strip().split()
    if len(points) != 1:
        return None

    point = points[0]
    premises = [
        part.strip() for part in re.split(r"\s*\[\d+\]", premises_part) if part.strip()
    ]
    if len(premises) > 2:
        return None
    if not premises:
        return f"{point} = free {point}"

    constructions: list[str] = []
    for premise in premises:
        parts = premise.split()
        if not parts or parts[0] not in ALLOWED_AUX_PREDICATES:
            return None
        construction = translate_dsl_to_construction(point, parts[0], parts[1:])
        if construction is None:
            return None
        constructions.append(construction)
    return f"{point} = {', '.join(constructions)}"


def aux_segments_are_translatable(aux_segments: list[str]) -> bool:
    return all(translate_aux_segment(segment) is not None for segment in aux_segments)


def aux_text_is_translatable(llm_output: str) -> bool:
    aux_segments = extract_tag_segments(llm_output, "aux", strip_aux_prefix=True)
    return aux_segments_are_translatable(aux_segments)
