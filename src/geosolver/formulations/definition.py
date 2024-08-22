from __future__ import annotations
from pathlib import Path
from typing import NamedTuple

from geosolver.formulations.clause import Clause
from geosolver.formulations.problem import reshape
from geosolver.tools import atomize


class DefinitionJGEX(NamedTuple):
    """Definitions of construction statements."""

    declare: tuple[str, ...]
    rely: dict[str, tuple[str, ...]]
    require: Clause
    basics: tuple[Clause, ...]
    numerics: tuple[tuple[str, ...], ...]

    @classmethod
    def parse_txt_file(cls, fname: Path) -> list[DefinitionJGEX]:
        with open(fname, "r") as f:
            lines = f.read()
            return cls.parse_text(lines)

    @classmethod
    def parse_text(cls, text: str) -> list[DefinitionJGEX]:
        lines = text.split("\n")
        data = [cls.from_str("\n".join(group)) for group in reshape(lines, 6)]
        return data

    @classmethod
    def from_str(cls, s: str) -> DefinitionJGEX:
        """Load the definition from a str object."""
        declare, rely, require, basics, numerics = s.split("\n")[:5]
        return cls(
            declare=atomize(declare),
            rely=_parse_rely(rely),
            require=Clause.parse_line(require)[0],
            basics=Clause.parse_line(basics),
            numerics=tuple(atomize(c) for c in numerics.split(",")),
        )

    @classmethod
    def to_dict(cls, defs: list[DefinitionJGEX]) -> dict[str, DefinitionJGEX]:
        return {d.declare[0]: d for d in defs}


def _parse_rely(s: str) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    if not s:
        return result
    for x in s.split(","):
        a, b = atomize(x, ":")
        a, b = atomize(a), atomize(b)
        result.update({m: b for m in a})
    return result
