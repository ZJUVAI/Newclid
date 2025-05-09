from __future__ import annotations
from pathlib import Path
from typing import NamedTuple

from newclid.tools import atomize


class Rule(NamedTuple):
    """Deduction rule."""

    descrption: str
    premises: tuple[tuple[str, ...], ...]
    conclusions: tuple[tuple[str, ...], ...]

    def __str__(self) -> str:
        premises_txt = ", ".join([str(premise) for premise in self.premises])
        conclusions_txt = ", ".join(
            [str(conclusion) for conclusion in self.conclusions]
        )
        return f"{premises_txt} => {conclusions_txt}"

    @classmethod
    def parse_txt_file(cls, fname: Path) -> list[Rule]:
        with open(fname, "r") as f:
            return cls.parse_text(f.read())

    @classmethod
    def parse_text(cls, text: str) -> list[Rule]:
        """Load deduction rule from a str object."""
        description = ""
        res: list[Rule] = []
        for i, s in enumerate(atomize(text, "\n")):
            if "=>" in s:
                res.append(cls.from_string(s, description or f"rule of line {i}"))
                description = ""
            else:
                description = s
        return res

    @classmethod
    def from_string(cls, s: str, name: str = "") -> Rule:
        premises, conclusions = atomize(s, "=>")
        premises = atomize(premises, ",")
        conclusions = atomize(conclusions, ",")
        return Rule(
            descrption=name,
            premises=tuple(atomize(p) for p in premises),
            conclusions=tuple(atomize(c) for c in conclusions),
        )

    def variables(self) -> list[str]:
        s: set[str] = set()
        for p in self.premises + self.conclusions:
            for x in p[1:]:
                if str.isalpha(x[0]):
                    s.add(x)
        return list(s)
