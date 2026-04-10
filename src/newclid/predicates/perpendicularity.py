from __future__ import annotations
from typing import TYPE_CHECKING, Any, Optional

from matplotlib.axes import Axes
import matplotlib.patches as patches
import numpy as np
from numpy.random import Generator

from newclid.dependencies.symbols import Point
from newclid.numerical import nearly_zero
from newclid.numerical.draw_figure import draw_segment_num
from newclid.predicates.equal_angles import EqAngle
from newclid.predicates.predicate import Predicate
from newclid.numerical.geometries import intersect
from newclid.numerical.geometries import LineNum

if TYPE_CHECKING:
    from newclid.algebraic_reasoning.tables import Table
    from newclid.algebraic_reasoning.tables import SumCV
    from newclid.dependencies.dependency import Dependency
    from newclid.dependencies.dependency_graph import DependencyGraph
    from newclid.statement import Statement


class Perp(Predicate):
    """perp A B C D -
    Represent that the line AB is perpendicular to the line CD.
    """

    NAME = "perp"

    @classmethod
    def preparse(cls, args: tuple[str, ...]) -> Optional[tuple[str, ...]]:
        a, b, c, d = args
        if a == b or c == d:
            return None
        a, b = sorted((a, b), key=cls.custom_key)
        c, d = sorted((c, d), key=cls.custom_key)
        if cls.compare((a, b), (c, d)) > 0:
            a, b, c, d = c, d, a, b
        return (a, b, c, d)

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> Optional[tuple[Any, ...]]:
        preparse = cls.preparse(args)
        return (
            tuple(dep_graph.symbols_graph.names2points(preparse)) if preparse else None
        )

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        args: tuple[Point, ...] = statement.args
        a, b, c, d = args
        return nearly_zero((a.num - b.num).dot(c.num - d.num))

    @classmethod
    def _prep_ar(cls, statement: Statement) -> tuple[list[SumCV], Table]:
        points: tuple[Point, ...] = statement.args
        table = statement.dep_graph.ar.atable
        symbols_graph = statement.dep_graph.symbols_graph
        return [
            table.get_equal_elements_up_to(
                symbols_graph.line_thru_pair(points[2], points[3], table).name,
                symbols_graph.line_thru_pair(points[0], points[1], table).name,
            )
        ], table

    @classmethod
    def add(cls, dep: Dependency) -> None:
        eqs, table = cls._prep_ar(dep.statement)
        for eq in eqs:
            table.add_expr(eq, dep)

    @classmethod
    def check(cls, statement: Statement) -> bool:
        try:
            eqs, table = cls._prep_ar(statement)
        except Exception:
            return False
        return all(table.expr_delta(eq) for eq in eqs)

    @classmethod
    def why(cls, statement: Statement) -> Dependency:
        args: tuple[Point, ...] = statement.args
        a, b, c, d = args
        return EqAngle.why(
            statement.with_new(EqAngle, (a, b, c, d, c, d, a, b))
        ).with_new(statement)

    @classmethod
    def to_constructive(cls, point: str, args: tuple[str, ...]) -> str:
        a, b, c, d = args
        if point in [c, d]:
            a, b, c, d = c, d, a, b
        if point == b:
            a, b = b, a
        if point == d:
            c, d = d, c
        if a == c and a == point:
            return f"on_dia {a} {b} {d}"
        return f"on_tline {a} {b} {c} {d}"

    @classmethod
    def pretty(cls, statement: Statement) -> str:
        args: tuple[Point, ...] = statement.args
        a, b, c, d = args
        return f"{a.pretty_name}{b.pretty_name} ⟂ {c.pretty_name}{d.pretty_name}"

    @classmethod
    def to_tokens(cls, args: tuple[Any, ...]) -> tuple[str, ...]:
        return tuple(p.name for p in args)

    @classmethod
    def draw(
        cls,
        ax: Axes,
        args: tuple[Any, ...],
        dep_graph: DependencyGraph,
        rng: Generator,
        draw_annotations: bool = True,
    ):
        line0_num = LineNum(p1=args[0].num, p2=args[1].num)
        line1_num = LineNum(p1=args[2].num, p2=args[3].num)
        (o,) = intersect(line0_num, line1_num)
        dir1 = args[0].num - o if not o.close_enough(args[0].num) else args[1].num - o
        dir2 = args[2].num - o if not o.close_enough(args[2].num) else args[3].num - o
        if dir1.x * dir2.y - dir1.y * dir2.x < 0:
            dir1, dir2 = dir2, dir1
        # Get current axis limits to determine figure size
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        figure_width = xlim[1] - xlim[0]
        figure_height = ylim[1] - ylim[0]
        figure_size = max(figure_width, figure_height)

        if draw_annotations:
            # Set rectangle size proportional to figure size
            rectangle_size = figure_size * 0.03  # 3% of figure size

            ang = np.arctan2(dir1.y, dir1.x)
            rectangle = patches.Rectangle(
                (o.x, o.y),
                angle=ang / np.pi * 180,
                fill=False,
                color="yellow",
                width=rectangle_size,
                height=rectangle_size,
            )
            ax.add_patch(rectangle)

        draw_segment_num(ax, o, args[0].num)
        draw_segment_num(ax, o, args[1].num)
        draw_segment_num(ax, o, args[2].num)
        draw_segment_num(ax, o, args[3].num)


class NPerp(Predicate):
    """nperp A B C D -
    Represent that lines AB and CD are NOT perpendicular.

    Numerical only.
    """

    NAME = "nperp"

    @classmethod
    def preparse(cls, args: tuple[str, ...]) -> Optional[tuple[str, ...]]:
        return Perp.preparse(args)

    @classmethod
    def parse(
        cls, args: tuple[str, ...], dep_graph: DependencyGraph
    ) -> Optional[tuple[Any, ...]]:
        return Perp.parse(args, dep_graph)

    @classmethod
    def check_numerical(cls, statement: Statement) -> bool:
        return not Perp.check_numerical(statement)

    @classmethod
    def check(cls, statement: Statement) -> bool:
        return True

    @classmethod
    def pretty(cls, statement: Statement) -> str:
        args: tuple[Point, ...] = statement.args
        a, b, c, d = args
        return f"{a.pretty_name}{b.pretty_name} ⟂̸ {c.pretty_name}{d.pretty_name}"
