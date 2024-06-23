from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING, Type, TypeVar

from geosolver.dependencies.dependency import Reason, Dependency
from geosolver.geometry import Symbol, Point, Angle, Ratio, Length

if TYPE_CHECKING:
    from geosolver.predicates.predicate import Predicate
    from geosolver.dependencies.dependency_building import DependencyBody
    from geosolver.dependencies.why_graph import DependencyGraph
    from geosolver.symbols_graph import SymbolsGraph
    from geosolver.intrinsic_rules import IntrinsicRules


@dataclass
class Statement:
    """One predicate applied to a set of points and values."""

    predicate: Type["Predicate"]
    args: tuple["Point" | "Ratio" | "Angle" | "Length", ...]

    def __post_init__(self):
        assert not isinstance(self.predicate, str)
        self.hash_tuple = self.predicate.hash([_symbol_to_txt(p) for p in self.args])

    def translate(self, mapping: dict[str, str]) -> Statement:
        args = [mapping[a] if a in mapping else a for a in self.args]
        return Statement(self.name, tuple(args))

    def add(
        self,
        dep_body: "DependencyBody",
        dep_graph: "DependencyGraph",
        symbols_graph: "SymbolsGraph",
        disabled_intrinsic_rules: list[IntrinsicRules],
    ) -> tuple[list["Dependency"], list[tuple[Statement, "Dependency"]]]:
        """Add the statement as an admitted fact."""
        return self.predicate.add(
            self.args,
            dep_body=dep_body,
            dep_graph=dep_graph,
            symbols_graph=symbols_graph,
            disabled_intrinsic_rules=disabled_intrinsic_rules,
        )

    def check(self, symbols_graph: "SymbolsGraph"):
        """Symbolically check if the statement is currently considered True."""
        return self.predicate.check(self.args, symbols_graph)

    def check_numerical(self):
        """Check if the statement is numerically sound."""
        num_args = [p.num if isinstance(p, Point) else p for p in self.args]
        return self.predicate.check_numerical(num_args)

    def why(
        self,
        dep_graph: "DependencyGraph",
        use_cache: bool = True,
    ) -> tuple["Reason", list["Dependency"]]:
        if use_cache:
            cached_me = dep_graph.dependency_cache.get(self)
            if cached_me is not None:
                return cached_me.reason, cached_me.why

        reason = Reason(f"why_{self.predicate.NAME}_resolution")
        _reason, why = self.predicate.why(dep_graph, self)
        if _reason is not None:
            reason = _reason
        return reason, why

    @property
    def name(self):
        return self.predicate.NAME

    def __str__(self) -> str:
        return name_and_arguments_to_str(self.name, self.args, " ")

    def __hash__(self) -> tuple[str, ...]:
        return hash(self.hash_tuple)


def name_and_arguments_to_str(
    name: str, args: list[str | int | "Symbol"], join: str
) -> list[str]:
    return join.join([name] + _arguments_to_str(args))


def _symbol_to_txt(symbol: "Point" | "Ratio" | int | str):
    if isinstance(symbol, str):
        return symbol
    if isinstance(symbol, int):
        return str(symbol)
    return symbol.name


def _arguments_to_str(args: list[str | int | "Symbol"]) -> list[str]:
    args_str = []
    for arg in args:
        if isinstance(arg, (int, str, float)):
            args_str.append(str(arg))
        else:
            args_str.append(arg.name)
    return args_str


P = TypeVar("P")


def hash_unordered_set_of_points(name: str, args: list[P]) -> tuple[str | P]:
    return (name,) + tuple(sorted(list(set(args))))


def hash_unordered_set_of_points_with_value(name: str, args: list[P]) -> tuple[str | P]:
    return hash_unordered_set_of_points(name, args[:-1]) + (args[-1],)


def hash_ordered_list_of_points(name: str, args: list[P]) -> tuple[str | P]:
    return (name,) + tuple(args)


def hash_point_then_set_of_points(name: str, args: list[P]) -> tuple[str | P]:
    return (name, args[0]) + tuple(sorted(args[1:]))


def hashed_unordered_two_lines_points(
    name: str, args: tuple[P, P, P, P]
) -> tuple[str, P, P, P, P]:
    a, b, c, d = args

    a, b = sorted([a, b])
    c, d = sorted([c, d])
    (a, b), (c, d) = sorted([(a, b), (c, d)])

    return (name, a, b, c, d)


def hash_ordered_two_lines_with_value(
    name: str, args: tuple[P, P, P, P, P]
) -> tuple[str, P, P, P, P, P]:
    a, b, c, d, y = args
    a, b = sorted([a, b])
    c, d = sorted([c, d])
    return name, a, b, c, d, y


def hash_point_and_line(name: str, args: tuple[P, P, P]) -> tuple[str, P, P, P]:
    a, b, c = args
    b, c = sorted([b, c])
    return (name, a, b, c)


def hash_two_times_two_unorded_lines(
    name: str, args: tuple[P, P, P, P, P, P, P, P]
) -> tuple[str, P, P, P, P, P, P, P, P]:
    a, b, c, d, e, f, g, h = args
    a, b = sorted([a, b])
    c, d = sorted([c, d])
    e, f = sorted([e, f])
    g, h = sorted([g, h])
    if tuple(sorted([a, b, e, f])) > tuple(sorted([c, d, g, h])):
        a, b, e, f, c, d, g, h = c, d, g, h, a, b, e, f
    if (a, b, c, d) > (e, f, g, h):
        a, b, c, d, e, f, g, h = e, f, g, h, a, b, c, d

    return (name,) + (a, b, c, d, e, f, g, h)


def hash_triangle(
    name: str, args: tuple[P, P, P, P, P, P]
) -> tuple[str, P, P, P, P, P, P]:
    a, b, c, x, y, z = args
    (a, x), (b, y), (c, z) = sorted([(a, x), (b, y), (c, z)], key=sorted)
    (a, b, c), (x, y, z) = sorted([(a, b, c), (x, y, z)], key=sorted)
    return (name, a, b, c, x, y, z)


def angle_to_num_den(angle: "Angle" | str) -> tuple[int, int]:
    name = angle
    if not isinstance(angle, str):
        name = angle.name
    num, den = name.split("pi/")
    return int(num), int(den)


def ratio_to_num_den(ratio: "Ratio" | str) -> tuple[int, int]:
    name = ratio
    if not isinstance(ratio, str):
        name = ratio.name
    num, den = name.split("/")
    return int(num), int(den)
