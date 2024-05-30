from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from geosolver.geometry import Node, Point


class Construction:
    """One predicate."""

    def __init__(self, name: str, args: list[str | "Point"]):
        self.name = name
        self.args = args

    def translate(self, mapping: dict[str, str]) -> Construction:
        args = [mapping[a] if a in mapping else a for a in self.args]
        return Construction(self.name, args)

    def txt(self) -> str:
        return

    def __str__(self) -> str:
        return name_and_arguments_to_str(self.name, self.args, " ")

    @classmethod
    def from_txt(cls, data: str) -> Construction:
        data = data.split(" ")
        return Construction(data[0], data[1:])


def name_and_arguments_to_str(
    name: str, args: list[str | int | "Node"], join: str
) -> list[str]:
    return join.join([name] + arguments_to_str(args))


def arguments_to_str(args: list[str | int | "Node"]) -> list[str]:
    args_str = []
    for arg in args:
        if isinstance(arg, (int, str, float)):
            args_str.append(str(arg))
        else:
            args_str.append(arg.name)
    return args_str


class Clause:
    """One construction (>= 1 predicate)."""

    def __init__(self, points: list[str], constructions: list[Construction]):
        self.points = []
        self.nums = []

        for p in points:
            num = None
            if isinstance(p, str) and "@" in p:
                p, num = p.split("@")
                x, y = num.split("_")
                num = float(x), float(y)
            self.points.append(p)
            self.nums.append(num)

        self.constructions = constructions

    def translate(self, mapping: dict[str, str]) -> Clause:
        points0 = []
        for p in self.points:
            pcount = len(mapping) + 1
            name = chr(96 + pcount)
            if name > "z":  # pcount = 26 -> name = 'z'
                name = chr(97 + (pcount - 1) % 26) + str((pcount - 1) // 26)

            p0 = mapping.get(p, name)
            mapping[p] = p0
            points0.append(p0)
        return Clause(points0, [c.translate(mapping) for c in self.constructions])

    def add(self, name: str, args: list[str]) -> None:
        self.constructions.append(Construction(name, args))

    def __str__(self) -> str:
        return (
            " ".join(self.points)
            + " = "
            + ", ".join(str(c) for c in self.constructions)
        )

    @classmethod
    def from_txt(cls, data: str) -> Clause:
        if data == " =":
            return Clause([], [])
        points, constructions = data.split(" = ")
        return Clause(
            points.split(" "),
            [Construction.from_txt(c) for c in constructions.split(", ")],
        )
