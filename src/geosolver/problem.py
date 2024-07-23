"""Implements objects to represent problems, theorems, proofs, traceback."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from geosolver.definition.clause import Clause, translate_sentence
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
            " ? " + "; ".join(" ".join(goal) for goal in self.goals)
        )

    @classmethod
    def parse_txt_file(cls, fname: Path) -> dict[str, Problem]:
        with open(fname, "r") as f:
            lines = f.read().split("\n")

        lines = [line for line in lines if line]
        data = [
            cls.from_text(url + "\n" + problem) for (url, problem) in reshape(lines, 2)
        ]
        return {p.name: p for p in data}

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
            constructions=Clause.parse_line(constructions_str),
            goals=tuple(atomize(g) for g in atomize(goals_str, ";"))
            if len(goals_str) > 0
            else (),
        )
        return problem

    @classmethod
    def from_file(cls, problems_path: Path, problem_name: str) -> Problem:
        """
        `tranlate = True` by default for better LLM training
        """
        problems = Problem.parse_txt_file(problems_path)
        if problem_name not in problems:
            print(problem_name, "!!", problems.keys())
            raise ValueError(f"{problem_name} not found in {list(problems.keys())}")
        return problems[problem_name]

    def with_more_construction(self, constructions: str) -> Problem:
        return Problem(
            name=self.name,
            constructions=self.constructions + Clause.parse_line(constructions),
            goals=self.goals,
        )

    def renamed(self) -> Problem:
        mp: dict[str, str] = {}
        for construction in self.constructions:
            for point in construction.points:
                if point not in mp:
                    mp[point] = chr(ord("a") + len(mp))
        return Problem(
            self.name,
            tuple(construction.renamed(mp) for construction in self.constructions),
            tuple(translate_sentence(mp, s) for s in self.goals),
        )

    def points(self) -> tuple[str, ...]:
        s: set[str] = set()
        for construction in self.constructions:
            for p in construction.points:
                s.add(p)
        return tuple(s)
