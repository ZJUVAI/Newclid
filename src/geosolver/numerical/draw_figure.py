from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING, Any, Collection, Optional

import numpy as np


from geosolver.numerical.geometries import (
    PointNum,
    intersect,
)
from geosolver.dependency.symbols import Point, Circle, Line
import matplotlib.pyplot as plt
import matplotlib
import matplotlib.patches as patches

matplotlib.use("svg")

if TYPE_CHECKING:
    from geosolver.proof import ProofState
    from geosolver.statement import Statement
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure


def init_figure() -> "Figure":
    imsize = 512 / 100
    fig, ax = plt.subplots(figsize=(imsize, imsize))  # type: ignore
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0, wspace=0, hspace=0)
    ax.set_facecolor((0.0, 0.0, 0.0))
    ax.set_aspect("equal", adjustable="datalim")
    return fig


def draw_figure(
    proof: "ProofState",
    block: bool = True,
    save_to: Optional[Path] = None,
) -> None:
    """Draw everything on the same canvas."""
    symbols_graph = proof.symbols_graph
    points: list[Point] = symbols_graph.nodes_of_type(Point)
    plt.close()
    fig = deepcopy(proof.fig)
    # fig = init_figure()
    (ax,) = fig.axes

    if proof.check_goals():
        _draw(
            ax,
            points,
            [dep.statement for dep in proof.dep_graph.proof_deps(proof.goals)],
        )
    else:
        _draw(ax, points, proof.dep_graph.hyper_graph.keys())

    if points:
        xmin = min([p.num.x for p in points])
        xmax = max([p.num.x for p in points])
        ymin = min([p.num.y for p in points])
        ymax = max([p.num.y for p in points])
        plt.margins((xmax - xmin) * 0.1, (ymax - ymin) * 0.1)

    if save_to is not None:
        fig.savefig(save_to)  # type: ignore

    plt.show(block=block)  # type: ignore
    if block or save_to is not None:
        plt.close(fig)


def _draw(ax: "Axes", points: list[Point], statements: Collection["Statement"]):
    """Draw everything."""
    for statement in statements:
        statement.draw(ax)
    for p in points:
        draw_point(ax, p)


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
        plt.Circle(  # type: ignore
            (c.num.center.x, c.num.center.y), c.num.radius, **args
        )
    )


def draw_line(ax: "Axes", line: Line, **args: Any):
    """Draw a line. Return the two extremities"""
    fill_missing(args, {"color": "white", "lw": 0.4, "alpha": 0.8})

    points: list[PointNum] = [p.num for p in line.points]
    p1, p2 = points[:2]

    ax.axline((p1.x, p1.y), (p2.x, p2.y), **args)  # type: ignore


def draw_angle(ax: "Axes", line0: Line, line1: Line, **args: Any):
    (o,) = intersect(line0.num, line1.num)
    ang0, ang1 = line0.num.angle(), line1.num.angle()
    if ang0 > ang1:
        ang0, ang1 = ang1, ang0
    if ang0 - ang1 + np.pi < ang1 - ang0:
        ang0, ang1 = ang1 - np.pi, ang0
    wedge = patches.Wedge(
        (o.x, o.y), theta1=ang0 / np.pi * 180, theta2=ang1 / np.pi * 180, **args
    )
    ax.add_artist(wedge)


def draw_rectangle(ax: "Axes", line0: Line, line1: Line, **args: Any):
    (o,) = intersect(line0.num, line1.num)
    ang0 = min(line0.num.angle(), line1.num.angle())
    rectangle = patches.Rectangle((o.x, o.y), angle=ang0 / np.pi * 180, **args)
    ax.add_artist(rectangle)


def draw_point(
    ax: "Axes",
    p: Point,
    args_point: Optional[dict[Any, Any]] = None,
    args_name: Optional[dict[Any, Any]] = None,
) -> None:
    """draw a point."""
    args_point = args_point or {}
    args_name = args_name or {}
    fill_missing(args_point, {"color": "white", "s": 5.0})
    ax.scatter(p.num.x, p.num.y, **args_point)  # type: ignore
    fill_missing(args_name, {"color": "green", "fontsize": 10})
    ax.annotate(  # type: ignore
        p.name, (p.num.x, p.num.y), **args_name
    )
