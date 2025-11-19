from copy import deepcopy
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, Collection, Optional, Union
from adjustText import adjust_text

import numpy as np

from newclid.numerical.geometries import (
    PointNum,
    intersect,
)
from newclid.dependencies.symbols import Point, Circle, Line
import matplotlib.patches as patches
from numpy.random import Generator
from matplotlib.axes import Axes
from matplotlib.figure import Figure

if TYPE_CHECKING:
    from newclid.proof import ProofState
    from newclid.statement import Statement

PALETTE = [
    "#e6194b",
    "#3cb44b",
    "#ffe119",
    "#4363d8",
    "#f58231",
    "#911eb4",
    "#46f0f0",
    "#f032e6",
    "#bcf60c",
    "#fabebe",
    "#008080",
    "#e6beff",
    "#9a6324",
    "#fffac8",
    "#800000",
    "#aaffc3",
    "#808000",
    "#ffd8b1",
    "#0000cd",
    "#808080",
    "#ffffff",
]


def init_figure() -> "Figure":
    imsize = 512 / 100
    fig = Figure(figsize=(imsize, imsize))
    ax = fig.add_subplot(111)  # type: ignore
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0, wspace=0, hspace=0)
    ax.set_facecolor((0.0, 0.0, 0.0))
    ax.set_aspect("equal", adjustable="datalim")
    return fig


def draw_figure(
    proof: "ProofState",
    *,
    save_to: Optional[Union[Path, BytesIO]] = None,
    rng: Generator,
    format: str = "svg",
) -> None:
    """Draw everything on the same canvas."""
    symbols_graph = proof.symbols_graph
    points: list[Point] = list(symbols_graph.nodes_of_type(Point))
    fig = deepcopy(proof.fig)
    (ax,) = fig.axes

    if proof.check_goals():
        _draw(
            ax,
            points,
            [dep.statement for dep in proof.dep_graph.proof_deps(proof.goals)],
            rng,
        )
    else:
        _draw(ax, points, proof.dep_graph.checked(), rng)

    if save_to is not None:
        fig.savefig(save_to, format=format)  # type: ignore


def _draw(
    ax: "Axes", points: list[Point], statements: Collection["Statement"], rng: Generator
):
    """Draw everything."""
    for statement in statements:
        statement.draw(ax, rng)
    point_names = []
    for p in points:
        point_names.append(draw_point(ax, p))
    adjust_text(point_names, ax=ax)


def fill_missing(d0: dict[Any, Any], d1: dict[Any, Any]):
    for k in d1.keys():
        if k not in d0:
            d0[k] = d1[k]


def draw_circle(ax: "Axes", c: Circle, **args: Any) -> None:
    fill_missing(
        args,
        {
            "color": "cyan",
            "fill": False,
            "lw": 0.8,
        },
    )
    ax.add_patch(
        patches.Circle(  # type: ignore
            (c.num.center.x, c.num.center.y), c.num.radius, **args
        )
    )


def draw_line(ax: "Axes", line: Line, **args: Any):
    """Draw a line. Return the two extremities"""
    fill_missing(args, {"color": "white", "lw": 0.4, "alpha": 0.9})

    points: list[PointNum] = [p.num for p in line.points]
    p0, p1 = points[:2]
    ax.axline((p0.x, p0.y), (p1.x, p1.y), **args)  # type: ignore


def draw_segment(ax: "Axes", p0: Point, p1: Point, **args: Any):
    fill_missing(args, {"color": "white", "lw": 0.4, "alpha": 0.9})
    ax.plot((p0.num.x, p1.num.x), (p0.num.y, p1.num.y), **args)  # type: ignore


def draw_segment_num(ax: "Axes", p0: PointNum, p1: PointNum, **args: Any):
    fill_missing(args, {"color": "white", "lw": 0.4, "alpha": 0.9})
    ax.plot((p0.x, p1.x), (p0.y, p1.y), **args)  # type: ignore


def draw_angle(ax: "Axes", point0: Point, point1: Point, point2: Point, **args: Any):
    draw_segment(ax, point0, point1)
    draw_segment(ax, point0, point2)
    dir1, dir2 = point1.num - point0.num, point2.num - point0.num
    if dir1.x * dir2.y - dir1.y * dir2.x < 0:
        dir1, dir2 = dir2, dir1
    if dir1.x * dir2.x + dir1.y * dir2.y >= 0:
        ang1 = np.arctan2(dir1.y, dir1.x)
        ang2 = np.arctan2(dir2.y, dir2.x)
    else:
        len2 = np.sqrt(dir2.x**2 + dir2.y**2)
        o = point0.num - dir2 / len2 * 0.2
        draw_segment_num(ax, point0.num, o, ls="dashed")
        ang1 = np.arctan2(-dir2.y, -dir2.x)
        ang2 = np.arctan2(dir1.y, dir1.x)
    wedge = patches.Wedge(
        (point0.num.x, point0.num.y), theta1=ang1 / np.pi * 180, theta2=ang2 / np.pi * 180, **args
    )
    ax.add_patch(wedge)


def draw_rectangle(ax: "Axes", line0: Line, line1: Line, **args: Any):
    (o,) = intersect(line0.num, line1.num)
    ang0 = min(line0.num.angle(), line1.num.angle())
    rectangle = patches.Rectangle((o.x, o.y), angle=ang0 / np.pi * 180, **args)
    ax.add_patch(rectangle)


def draw_point(
    ax: "Axes",
    p: Point,
    args_point: Optional[dict[Any, Any]] = None,
    args_name: Optional[dict[Any, Any]] = None,
):
    """draw a point."""
    args_point = args_point or {}
    args_name = args_name or {}
    fill_missing(args_point, {"color": "white", "s": 5.0})
    ax.scatter(p.num.x, p.num.y, **args_point)  # type: ignore
    fill_missing(args_name, {"color": "lime", "fontsize": 10})
    return ax.annotate(  # type: ignore
        p.pretty_name, (p.num.x, p.num.y), **args_name
    )
