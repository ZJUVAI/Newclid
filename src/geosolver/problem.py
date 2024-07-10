"""Implements objects to represent problems, theorems, proofs, traceback."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from geosolver.definition.clause import Clause
from geosolver.tools import atomize, reshape

if TYPE_CHECKING:
    pass


class Problem(NamedTuple):
    """Describe one problem to solve."""

    name: str
    constructions: tuple[Clause, ...]
    goals: tuple[tuple[str, ...], ...]

    def __str__(self) -> str:
        return "; ".join([str(c) for c in self.constructions]) + (
            " ? " + "; ".join(str(goal) for goal in self.goals) if self.goals else ""
        )

    @classmethod
    def parse_txt_file(cls, fname: str | Path):
        with open(fname, "r") as f:
            lines = f.read().split("\n")

        lines = [line for line in lines if line]
        data = [
            cls.from_text(url + "\n" + problem) for (url, problem) in reshape(lines, 2)
        ]
        return data

    @classmethod
    def from_text(cls, s: str) -> Problem:
        """Load a problem from a str object."""
        name = ""
        if "\n" in s:
            name, s = s.split("\n")

        if "?" in s:
            constructions_str, goals_str = atomize(s, "?")
        else:
            constructions_str, goals_str = s, ""

        problem = Problem(
            name=name,
            constructions=tuple(Clause.parse_line(constructions_str)),
            goals=tuple(atomize(g) for g in atomize(goals_str, ";"))
            if len(goals_str) > 0
            else (),
        )
        return problem

    @classmethod
    def to_dict(cls, data: list[Problem]) -> dict[str, Problem]:
        return {p.name: p for p in data}
