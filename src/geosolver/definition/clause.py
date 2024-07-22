from __future__ import annotations
from typing import NamedTuple

from geosolver.tools import atomize


class Clause(NamedTuple):
    points: tuple[str, ...]
    sentences: tuple[tuple[str, ...], ...]

    @classmethod
    def parse_line(cls, s: str) -> tuple[Clause, ...]:
        levels = atomize(s, ";")

        basics: list[Clause] = []
        for level in levels:
            points: tuple[str, ...] = tuple()
            points_str, bs_str = (
                level.split(":")
                if ":" in level
                else level.split("=")
                if "=" in level
                else ("", level)
            )
            points = tuple(points_str.strip().split())
            bs_str = bs_str.strip()
            bs = tuple(atomize(b) for b in bs_str.split(",") if b.strip() != "")
            basics.append(Clause(points, bs))

        return tuple(basics)
