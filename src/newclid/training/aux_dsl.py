"""Helpers for parsing and translating auxiliary-point DSL completions."""

from __future__ import annotations

import re
from typing import Optional

from newclid.predicates.collinearity import Coll
from newclid.predicates.congruence import Cong
from newclid.predicates.cyclic import Cyclic
from newclid.predicates.equal_angles import EqAngle
from newclid.predicates.equal_ratios import EqRatio
from newclid.predicates.midpoint import MidPoint
from newclid.predicates.parallelism import Para
from newclid.predicates.perpendicularity import Perp


_AUX_BLOCK_RE = re.compile(r"<aux>\s*(.*?)\s*</aux>", re.DOTALL | re.IGNORECASE)
_AUX_PREFIX_RE = re.compile(r"^x\d+\s+")
_AUX_WS_RE = re.compile(r"\s+")


def extract_aux_body(completion: str) -> Optional[str]:
    """Return the first aux block body or fall back to the raw completion text."""
    if completion is None:
        return None

    text = str(completion).strip()
    if not text:
        return None

    match = _AUX_BLOCK_RE.search(text)
    body = match.group(1) if match else text
    body = body.strip()
    if not body:
        return None

    body = _AUX_PREFIX_RE.sub("", body, count=1)
    body = body.strip()
    return body or None


def normalize_aux_text(aux_body: str) -> str:
    """Canonicalize aux text for caching and dataset conversion."""
    return _AUX_WS_RE.sub(" ", aux_body).strip()


def extract_first_aux_block(completion: str) -> Optional[str]:
    """Return a normalized first aux block suitable as a training target."""
    aux_body = extract_aux_body(completion)
    if aux_body is None:
        return None
    return f"<aux> {normalize_aux_text(aux_body)} </aux>"


def extract_first_tagged_aux_block(completion: str) -> Optional[str]:
    """Return a normalized aux block only when the source contains <aux> tags."""
    if completion is None:
        return None
    match = _AUX_BLOCK_RE.search(str(completion))
    if match is None:
        return None
    return extract_first_aux_block(match.group(0))


def try_dsl_to_constructions(content: str) -> Optional[str]:
    """Translate generated aux DSL into internal construction syntax."""
    if content is None:
        return None

    content = content.strip()
    if not content:
        return None

    try:
        points, premises = content.split(";", 1)[0].split(" : ", 1)
    except ValueError:
        return None

    points = points.strip().split()
    if len(points) == 0 or len(points) > 1:
        return None
    point = points[0]

    premises = re.split(r"\s*\[\d+\]", premises)
    premises = [segment.strip() for segment in premises if segment.strip()]
    if len(premises) > 2:
        return None
    if len(premises) == 0:
        return f"{point} = free {point}"

    result_constructions = []
    for premise in premises:
        parts = premise.split()
        if not parts or not parts[0].isalpha():
            return None
        construction = translate_dsl_to_construction(point, parts[0], parts[1:])
        result_constructions.append(construction)
    return point + " = " + ", ".join(result_constructions)


def translate_dsl_to_construction(point: str, predicate: str, args: list[str]) -> str:
    """Translate a single DSL predicate into constructive syntax."""
    if predicate == "perp":
        return Perp.to_constructive(point, tuple(args))
    if predicate == "para":
        return Para.to_constructive(point, tuple(args))
    if predicate == "cong":
        return Cong.to_constructive(point, tuple(args))
    if predicate == "midp":
        return MidPoint.to_constructive(point, tuple(args))
    if predicate == "coll":
        return Coll.to_constructive(point, tuple(args))
    if predicate == "eqangle":

        def arrange_angle_points(a, b, c, d):
            if a == c:
                return (b, a, d)
            if a == d:
                return (b, a, c)
            if b == c:
                return (a, b, d)
            if b == d:
                return (a, b, c)
            return None

        a, b, c, d, e, f, g, h = args
        if len(set([a, b, c, d, e, f, g, h])) == 8:
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

        if len(set([a, b, c, d])) == 4 and len(set([a, b, e, f])) == 3:
            a, b, c, d, e, f, g, h = a, b, e, f, c, d, g, h
        left = arrange_angle_points(a, b, c, d)
        right = arrange_angle_points(e, f, g, h)
        if left is None or right is None:
            return None
        return EqAngle.to_constructive(point, left + right)

    if predicate == "cyclic":
        return Cyclic.to_constructive(point, tuple(args))
    if predicate == "eqratio":
        return EqRatio.to_constructive(point, tuple(args))
    return f"{predicate} {' '.join(args)}"
