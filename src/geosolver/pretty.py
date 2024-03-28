# Copyright 2023 DeepMind Technologies Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

"""Utilities for string manipulation in the DSL."""

from geosolver.concepts import ConceptName


MAP_SYMBOL = {
    "C": ConceptName.COLLINEAR.value,
    "X": ConceptName.COLLINEAR_X.value,
    "P": ConceptName.PARALLEL.value,
    "T": ConceptName.PERPENDICULAR.value,
    "M": ConceptName.MIDPOINT.value,
    "D": ConceptName.CONGRUENT.value,
    "I": ConceptName.CIRCLE.value,
    "O": ConceptName.CYCLIC.value,
    "^": ConceptName.EQANGLE.value,
    "/": ConceptName.EQRATIO.value,
    "%": ConceptName.EQRATIO.value,
    "S": ConceptName.SIMILAR_TRIANGLE.value,
    "=": ConceptName.CONTRI_TRIANGLE.value,
    "A": ConceptName.COMPUTE_ANGLE.value,
    "R": ConceptName.COMPUTE_RATIO.value,
    "Q": ConceptName.FIX_C.value,
    "E": ConceptName.FIX_L.value,
    "V": ConceptName.FIX_B.value,
    "H": ConceptName.FIX_T.value,
    "Z": ConceptName.FIX_P.value,
    "Y": ConceptName.IND.value,
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


def pretty_angle(a: str, b: str, c: str, d: str) -> str:
    if b in (c, d):
        a, b = b, a
    if a == d:
        c, d = d, c

    if a == c:
        return f"\u2220{b}{a}{d}"
    return f"\u2220({a}{b}-{c}{d})"


def pretty_nl(name: str, args: list[str]) -> str:
    """Natural lang formatting a predicate."""
    if name == ConceptName.CONSTANT_ANGLE.value:
        a, b, c, d, y = args
        return f"{pretty_angle(a, b, c, d)} = {y}"
    if name == ConceptName.CONSTANT_RATIO.value:
        a, b, c, d, y = args
        return f"{a}{b}:{c}{d} = {y}"
    if name == ConceptName.COMPUTE_ANGLE.value:
        a, b, c, d = args
        return f"{pretty_angle(a, b, c, d)}"
    if name in [ConceptName.COLLINEAR.value, "C"]:
        return "" + ",".join(args) + " are collinear"
    if name == ConceptName.COLLINEAR_X.value:
        return "" + ",".join(list(set(args))) + " are collinear"
    if name in [ConceptName.CYCLIC.value, "O"]:
        return "" + ",".join(args) + " are concyclic"
    if name in [ConceptName.MIDPOINT.value, "midpoint", "M"]:
        x, a, b = args
        return f"{x} is midpoint of {a}{b}"
    if name in [ConceptName.EQANGLE.value, ConceptName.EQANGLE6.value, "^"]:
        a, b, c, d, e, f, g, h = args
        return f"{pretty_angle(a, b, c, d)} = {pretty_angle(e, f, g, h)}"
    if name in [ConceptName.EQRATIO.value, ConceptName.EQRATIO6.value, "/"]:
        return "{}{}:{}{} = {}{}:{}{}".format(*args)
    if name == ConceptName.EQRATIO3.value:
        a, b, c, d, o, o = args
        return f"S {o} {a} {b} {o} {c} {d}"
    if name in [ConceptName.CONGRUENT.value, "D"]:
        a, b, c, d = args
        return f"{a}{b} = {c}{d}"
    if name in [ConceptName.PERPENDICULAR.value, "T"]:
        if len(args) == 2:  # this is algebraic derivation.
            ab, cd = args  # ab = 'd( ... )'
            return f"{ab} \u27c2 {cd}"
        a, b, c, d = args
        return f"{a}{b} \u27c2 {c}{d}"
    if name in [ConceptName.PARALLEL.value, "P"]:
        if len(args) == 2:  # this is algebraic derivation.
            ab, cd = args  # ab = 'd( ... )'
            return f"{ab} \u2225 {cd}"
        a, b, c, d = args
        return f"{a}{b} \u2225 {c}{d}"
    if name in [
        ConceptName.SIMILAR_TRIANGLE_REFLECTED.value,
        ConceptName.SIMILAR_TRIANGLE.value,
        ConceptName.SIMILAR_TRIANGLE_BOTH.value,
    ]:
        a, b, c, x, y, z = args
        return f"\u0394{a}{b}{c} is similar to \u0394{x}{y}{z}"
    if name in [
        ConceptName.CONTRI_TRIANGLE_REFLECTED.value,
        ConceptName.CONTRI_TRIANGLE.value,
        ConceptName.CONTRI_TRIANGLE_BOTH.value,
    ]:
        a, b, c, x, y, z = args
        return f"\u0394{a}{b}{c} is congruent to \u0394{x}{y}{z}"
    if name in [ConceptName.CIRCLE.value, "I"]:
        o, a, b, c = args
        return f"{o} is the circumcenter of \\Delta {a}{b}{c}"
    if name == "foot":
        a, b, c, d = args
        return f"{a} is the foot of {b} on {c}{d}"


def pretty(txt: str) -> str:
    """Pretty formating a predicate string."""
    if isinstance(txt, str):
        txt = txt.split(" ")
    name, *args = txt
    if name == ConceptName.IND.value:
        return "Y " + " ".join(args)
    if name in [
        ConceptName.FIX_C.value,
        ConceptName.FIX_L.value,
        ConceptName.FIX_B.value,
        ConceptName.FIX_T.value,
        ConceptName.FIX_P.value,
    ]:
        return map_symbol_inv(name) + " " + " ".join(args)
    if name == ConceptName.COMPUTE_ANGLE.value:
        a, b, c, d = args
        return "A " + " ".join(args)
    if name == ConceptName.COMPUTE_RATIO.value:
        a, b, c, d = args
        return "R " + " ".join(args)
    if name == ConceptName.CONSTANT_ANGLE.value:
        a, b, c, d, y = args
        return f"^ {pretty2a(a, b, c, d)} {y}"
    if name == ConceptName.CONSTANT_RATIO.value:
        a, b, c, d, y = args
        return f"/ {pretty2r(a, b, c, d)} {y}"
    if name == ConceptName.COLLINEAR.value:
        return "C " + " ".join(args)
    if name == ConceptName.COLLINEAR_X.value:
        return "X " + " ".join(args)
    if name == ConceptName.CYCLIC.value:
        return "O " + " ".join(args)
    if name in [ConceptName.MIDPOINT.value, "midpoint"]:
        x, a, b = args
        return f"M {x} {a} {b}"
    if name == ConceptName.EQANGLE.value:
        a, b, c, d, e, f, g, h = args
        return f"^ {pretty2a(a, b, c, d)} {pretty2a(e, f, g, h)}"
    if name == ConceptName.EQRATIO.value:
        a, b, c, d, e, f, g, h = args
        return f"/ {pretty2r(a, b, c, d)} {pretty2r(e, f, g, h)}"
    if name == ConceptName.EQRATIO3.value:
        a, b, c, d, o, o = args
        return f"S {o} {a} {b} {o} {c} {d}"
    if name == ConceptName.CONGRUENT.value:
        a, b, c, d = args
        return f"D {a} {b} {c} {d}"
    if name == ConceptName.PERPENDICULAR.value:
        if len(args) == 2:  # this is algebraic derivation.
            ab, cd = args  # ab = 'd( ... )'
            return f"T {ab} {cd}"
        a, b, c, d = args
        return f"T {a} {b} {c} {d}"
    if name == ConceptName.PARALLEL.value:
        if len(args) == 2:  # this is algebraic derivation.
            ab, cd = args  # ab = 'd( ... )'
            return f"P {ab} {cd}"
        a, b, c, d = args
        return f"P {a} {b} {c} {d}"
    if name in [
        ConceptName.SIMILAR_TRIANGLE_REFLECTED.value,
        ConceptName.SIMILAR_TRIANGLE.value,
        ConceptName.SIMILAR_TRIANGLE_BOTH.value,
    ]:
        a, b, c, x, y, z = args
        return f"S {a} {b} {c} {x} {y} {z}"
    if name in [
        ConceptName.CONTRI_TRIANGLE_REFLECTED.value,
        ConceptName.CONTRI_TRIANGLE.value,
        ConceptName.CONTRI_TRIANGLE_BOTH.value,
    ]:
        a, b, c, x, y, z = args
        return f"= {a} {b} {c} {x} {y} {z}"
    if name == ConceptName.CIRCLE.value:
        o, a, b, c = args
        return f"I {o} {a} {b} {c}"
    if name == "foot":
        a, b, c, d = args
        return f"F {a} {b} {c} {d}"
    return " ".join(txt)
