"""Utilities for string manipulation in the DSL."""

import geosolver.predicates as preds
from geosolver.predicate_name import PredicateName
from geosolver.pretty_angle import pretty_angle


MAP_SYMBOL = {
    "C": preds.Coll.NAME,
    "X": preds.Collx.NAME,
    "P": preds.Para.NAME,
    "T": preds.Perp.NAME,
    "M": preds.MidPoint.NAME,
    "D": preds.Cong.NAME,
    "I": preds.Circumcenter.NAME,
    "O": preds.Cyclic.NAME,
    "^": preds.EqAngle.NAME,
    "/": preds.EqRatio.NAME,
    "%": preds.EqRatio.NAME,
    "S": PredicateName.SIMILAR_TRIANGLE.value,
    "=": PredicateName.CONTRI_TRIANGLE.value,
    "A": PredicateName.COMPUTE_ANGLE.value,
    "R": PredicateName.COMPUTE_RATIO.value,
    "Q": PredicateName.FIX_C.value,
    "E": PredicateName.FIX_L.value,
    "V": PredicateName.FIX_B.value,
    "H": PredicateName.FIX_T.value,
    "Z": PredicateName.FIX_P.value,
    "Y": PredicateName.IND.value,
}


def map_symbol(c: str) -> str:
    return MAP_SYMBOL[c]


def map_symbol_inv(c: str) -> str:
    return {v: k for k, v in MAP_SYMBOL.items()}[c]


def pretty2r(a: str, b: str, c: str, d: str) -> str:
    if b in (c, d):
        a, b = b, a

    if a == d:
        c, d = d, c

    return f"{a} {b} {c} {d}"


def pretty2a(a: str, b: str, c: str, d: str) -> str:
    if b in (c, d):
        a, b = b, a

    if a == d:
        c, d = d, c

    return f"{a} {b} {c} {d}"


def pretty_nl(name: str, args: list[str]) -> str:
    """Natural lang formatting a predicate."""

    if name == PredicateName.COMPUTE_ANGLE.value:
        a, b, c, d = args
        return f"{pretty_angle(a, b, c, d)}"
    if name in [
        PredicateName.SIMILAR_TRIANGLE_REFLECTED.value,
        PredicateName.SIMILAR_TRIANGLE.value,
        PredicateName.SIMILAR_TRIANGLE_BOTH.value,
    ]:
        a, b, c, x, y, z = args
        return f"\u0394{a}{b}{c} is similar to \u0394{x}{y}{z}"
    if name in [
        PredicateName.CONTRI_TRIANGLE_REFLECTED.value,
        PredicateName.CONTRI_TRIANGLE.value,
        PredicateName.CONTRI_TRIANGLE_BOTH.value,
    ]:
        a, b, c, x, y, z = args
        return f"\u0394{a}{b}{c} is congruent to \u0394{x}{y}{z}"

    if name == "foot":
        a, b, c, d = args
        return f"{a} is the foot of {b} on {c}{d}"
    raise NotImplementedError(f"Cannot write pretty name for {name}")


def pretty(txt: tuple[str, ...]) -> str:
    """Pretty formating a predicate string."""
    if isinstance(txt, str):
        txt = txt.split(" ")
    name, *args = txt
    if name == PredicateName.IND.value:
        return "Y " + " ".join(args)
    if name in [
        PredicateName.FIX_C.value,
        PredicateName.FIX_L.value,
        PredicateName.FIX_B.value,
        PredicateName.FIX_T.value,
        PredicateName.FIX_P.value,
    ]:
        return map_symbol_inv(name) + " " + " ".join(args)
    if name == PredicateName.COMPUTE_ANGLE.value:
        a, b, c, d = args
        return "A " + " ".join(args)
    if name == PredicateName.COMPUTE_RATIO.value:
        a, b, c, d = args
        return "R " + " ".join(args)
    if name == preds.ConstantAngle.NAME:
        a, b, c, d, y = args
        return f"^ {pretty2a(a, b, c, d)} {y}"
    if name == preds.ConstantRatio.NAME:
        a, b, c, d, y = args
        return f"/ {pretty2r(a, b, c, d)} {y}"
    if name == preds.Coll.NAME:
        return "C " + " ".join(args)
    if name == preds.Collx.NAME:
        return "X " + " ".join(args)
    if name == preds.Cyclic.NAME:
        return "O " + " ".join(args)
    if name in [preds.MidPoint.NAME, "midpoint"]:
        x, a, b = args
        return f"M {x} {a} {b}"
    if name == preds.EqAngle.NAME:
        a, b, c, d, e, f, g, h = args
        return f"^ {pretty2a(a, b, c, d)} {pretty2a(e, f, g, h)}"
    if name == preds.EqRatio.NAME:
        a, b, c, d, e, f, g, h = args
        return f"/ {pretty2r(a, b, c, d)} {pretty2r(e, f, g, h)}"
    if name == preds.EqRatio3.NAME:
        a, b, c, d, o, o = args
        return f"S {o} {a} {b} {o} {c} {d}"
    if name == preds.Cong.NAME:
        a, b, c, d = args
        return f"D {a} {b} {c} {d}"
    if name == preds.Perp.NAME:
        if len(args) == 2:  # this is algebraic derivation.
            ab, cd = args  # ab = 'd( ... )'
            return f"T {ab} {cd}"
        a, b, c, d = args
        return f"T {a} {b} {c} {d}"
    if name == preds.Para.NAME:
        if len(args) == 2:  # this is algebraic derivation.
            ab, cd = args  # ab = 'd( ... )'
            return f"P {ab} {cd}"
        a, b, c, d = args
        return f"P {a} {b} {c} {d}"
    if name in [
        PredicateName.SIMILAR_TRIANGLE_REFLECTED.value,
        PredicateName.SIMILAR_TRIANGLE.value,
        PredicateName.SIMILAR_TRIANGLE_BOTH.value,
    ]:
        a, b, c, x, y, z = args
        return f"S {a} {b} {c} {x} {y} {z}"
    if name in [
        PredicateName.CONTRI_TRIANGLE_REFLECTED.value,
        PredicateName.CONTRI_TRIANGLE.value,
        PredicateName.CONTRI_TRIANGLE_BOTH.value,
    ]:
        a, b, c, x, y, z = args
        return f"= {a} {b} {c} {x} {y} {z}"
    if name == preds.Circumcenter.NAME:
        o, a, b, c = args
        return f"I {o} {a} {b} {c}"
    if name == "foot":
        a, b, c, d = args
        return f"F {a} {b} {c} {d}"
    return " ".join(txt)
