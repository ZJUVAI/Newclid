from pathlib import Path
from typing import TYPE_CHECKING, Any, Collection, Optional

from geosolver.numerical.geometries import (
    PointNum,
)
from geosolver.dependency.symbols import Point, Circle, Line
import matplotlib.pyplot as plt

if TYPE_CHECKING:
    from geosolver.statement import Statement
    from geosolver.dependency.dependency_graph import DependencyGraph
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure


HCOLORS = None


def draw_figure(
    dep_graph: "DependencyGraph",
    block: bool = True,
    save_to: Optional[Path] = None,
) -> None:
    """Draw everything on the same canvas."""
    symbols_graph = dep_graph.symbols_graph
    points: list[Point] = symbols_graph.nodes_of_type(Point)
    plt.close()
    imsize = 512 / 100
    fig, ax = plt.subplots(figsize=(imsize, imsize))  # type: ignore
    fig: Figure
    ax: Axes

    ax.set_facecolor((0.0, 0.0, 0.0))

    _draw(ax, points, dep_graph.hyper_graph.keys())

    plt.axis("equal")  # type: ignore
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0, wspace=0, hspace=0)
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
    fill_missing(args, {"color": "white", "lw": 0.2, "alpha": 0.8})

    points: list[PointNum] = [p.num for p in line.points]
    p1, p2 = points[:2]

    ax.axline((p1.x, p1.y), (p2.x, p2.y), **args)  # type: ignore


def draw_point(
    ax: "Axes",
    p: Point,
    args_point: Optional[dict[Any, Any]] = None,
    args_name: Optional[dict[Any, Any]] = None,
) -> None:
    """draw a point."""
    args_point = args_point or {}
    args_name = args_name or {}
    fill_missing(args_point, {"color": "white", "s": 15.0})
    ax.scatter(p.num.x, p.num.y, **args_point)  # type: ignore
    fill_missing(args_name, {"color": "green", "fontsize": 15.0})
    ax.annotate(  # type: ignore
        p.name, (p.num.x, p.num.y), **args_name
    )
