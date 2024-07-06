from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from geosolver.numerical.angles import ang_of
from geosolver.numerical.geometries import (
    CircleNum,
    InvalidQuadSolveError,
    PointNum,
    circle_circle_intersection,
    circle_segment_intersect,
)
from geosolver.dependency.symbols import Point, Circle, Line
import numpy as np
import matplotlib.pyplot as plt

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure
    from geosolver.dependency.symbols_graph import SymbolsGraph


HCOLORS = None
THEME = "dark"


def draw_figure(
    symbols_graph: "SymbolsGraph",
    block: bool = True,
    save_to: Optional[Path] = None,
    theme: str = "dark",
) -> None:
    """Draw everything on the same canvas."""
    points: list[Point] = symbols_graph.nodes_of_type(Point)
    lines: list[Line] = symbols_graph.nodes_of_type(Line)
    circles: list[Circle] = symbols_graph.nodes_of_type(Circle)
    plt.close()
    imsize = 512 / 100
    fig, ax = plt.subplots(figsize=(imsize, imsize), dpi=100)  # type: ignore
    fig: Figure
    ax: Axes

    set_theme(theme)

    if get_theme() == "dark":
        ax.set_facecolor((0.0, 0.0, 0.0))
    else:
        ax.set_facecolor((1.0, 1.0, 1.0))

    _draw(ax, points, lines, circles)

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


def _draw(
    ax: "Axes",
    points: list[Point],
    lines: list[Line],
    circles: list[Circle],
):
    """Draw everything."""
    pcolor = "black"
    lcolor = "black"
    ccolor = "grey"
    if get_theme() == "dark":
        pcolor, lcolor, ccolor = "white", "white", "cyan"
    elif get_theme() == "light":
        pcolor, lcolor, ccolor = "black", "black", "blue"
    elif get_theme() == "grey":
        pcolor, lcolor, ccolor = "black", "black", "grey"

    line_boundaries: list[tuple[PointNum, PointNum]] = []
    for line in lines:
        p1, p2 = draw_line(ax, line, color=lcolor)
        line_boundaries.append((p1, p2))
    for c in circles:
        draw_circle(ax, c, color=ccolor)
    for p in points:
        draw_point(ax, p, line_boundaries, circles, color=pcolor)


def get_theme() -> str:
    return THEME


def set_theme(theme: str) -> None:
    global THEME
    THEME = theme  # type: ignore


def draw_circle(ax: "Axes", c: Circle, color: Any = "cyan", lw: float = 1.2) -> None:
    ls = "-"
    if color == "--":
        color = "black"
        ls = "--"

    ax.add_patch(
        plt.Circle(  # type: ignore
            (c.num.center.x, c.num.center.y),
            c.num.radius,
            color=color,
            alpha=0.8,
            fill=False,
            lw=lw,
            ls=ls,
        )
    )


def draw_line(
    ax: "Axes", line: Line, color: Any = "white"
) -> tuple[PointNum, PointNum]:
    """Draw a line. Return the two extremities"""
    points: list[PointNum] = [p.num for p in line.points]
    p1, p2 = points[:2]

    ax.axline((p1.x, p1.y), (p2.x, p2.y), color=color, alpha=0.8, lw=0.2)  # type: ignore

    pmin, pmax = (p1, 0.0), (p2, (p2 - p1).dot(p2 - p1))

    for p in points[2:]:
        v = (p - p1).dot(p2 - p1)
        if v < pmin[1]:
            pmin = p, v
        if v > pmax[1]:
            pmax = p, v

    p1, p2 = pmin[0], pmax[0]
    return p1, p2


def draw_point(
    ax: "Axes",
    p: Point,
    line_boundaries: list[tuple[PointNum, PointNum]],
    circles: list[Circle],
    color: Any = "white",
    size: float = 15,
) -> None:
    """draw a point."""
    ax.scatter(p.num.x, p.num.y, color=color, s=size)  # type: ignore

    if color == "white":
        color = "lightgreen"
    else:
        color = "grey"

    ax.annotate(  # type: ignore
        p.name,
        naming_position(ax, p, line_boundaries, circles),
        color=color,
        fontsize=15,
    )


def naming_position(
    ax: "Axes",
    p: Point,
    line_boundaries: list[tuple[PointNum, PointNum]],
    circles: list[Circle],
) -> tuple[float, float]:
    """Figure out a good naming position on the drawing."""
    _ = ax
    r = 0.08
    c = CircleNum(center=p.num, radius=r)
    avoid: list[PointNum] = []
    for p1, p2 in line_boundaries:
        try:
            avoid.extend(circle_segment_intersect(c, p1, p2))
        except InvalidQuadSolveError:
            continue
    for x in circles:
        try:
            avoid.extend(circle_circle_intersection(c, x.num))
        except InvalidQuadSolveError:
            continue

    if not avoid:
        return p.num.x + 0.01, p.num.y + 0.01

    angs = sorted([ang_of(p.num, a) for a in avoid])
    angs += [angs[0] + 2 * np.pi]
    angs = [(angs[i + 1] - a, a) for i, a in enumerate(angs[:-1])]

    d, a = max(angs)
    ang = a + d / 2

    name_pos = p.num + PointNum(np.cos(ang), np.sin(ang)) * r

    x, y = (name_pos.x - r / 1.5, name_pos.y - r / 1.5)
    return x, y
