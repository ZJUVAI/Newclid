from typing import Any


import numpy as np
from numpy.random import uniform as unif

from matplotlib import pyplot as plt
import matplotlib.colors as mcolors

import geosolver.geometry as gm
from geosolver.numerical.angles import ang_of
from geosolver.numerical.geometries import (
    Circle,
    InvalidLineIntersectError,
    InvalidQuadSolveError,
    Line,
    Point,
    bring_together,
    circle_circle_intersection,
    circle_segment_intersect,
    line_line_intersection,
)


HCOLORS = None
THEME = "dark"


def draw_figure(
    points: list[gm.Point],
    lines: list[gm.Line],
    circles: list[gm.Circle],
    segments: list[gm.Segment],
    goal: Any = None,
    highlights: list[tuple[str, list[gm.Point]]] = None,
    equals: list[tuple[Any, Any]] = None,
    block: bool = True,
    save_to: str = None,
    theme: str = "dark",
) -> None:
    """Draw everything on the same canvas."""
    plt.close()
    imsize = 512 / 100
    fig, ax = plt.subplots(figsize=(imsize, imsize), dpi=100)

    set_theme(theme)

    if get_theme() == "dark":
        ax.set_facecolor((0.0, 0.0, 0.0))
    else:
        ax.set_facecolor((1.0, 1.0, 1.0))

    _draw(ax, points, lines, circles, goal, equals, highlights)

    plt.axis("equal")
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0, wspace=0, hspace=0)
    if points:
        xmin = min([p.num.x for p in points])
        xmax = max([p.num.x for p in points])
        ymin = min([p.num.y for p in points])
        ymax = max([p.num.y for p in points])
        plt.margins((xmax - xmin) * 0.1, (ymax - ymin) * 0.1)

    if save_to is not None:
        fig.savefig(save_to)

    plt.show(block=block)


def _draw(
    ax: plt.Axes,
    points: list[gm.Point],
    lines: list[gm.Line],
    circles: list[gm.Circle],
    goal: Any,
    equals: list[tuple[Any, Any]],
    highlights: list[tuple[str, list[gm.Point]]],
):
    """Draw everything."""
    colors = ["red", "green", "blue", "orange", "magenta", "purple"]
    pcolor = "black"
    lcolor = "black"
    ccolor = "grey"
    if get_theme() == "dark":
        pcolor, lcolor, ccolor = "white", "white", "cyan"
    elif get_theme() == "light":
        pcolor, lcolor, ccolor = "black", "black", "blue"
    elif get_theme() == "grey":
        pcolor, lcolor, ccolor = "black", "black", "grey"
        colors = ["grey"]

    line_boundaries = []
    for line in lines:
        p1, p2 = draw_line(ax, line, color=lcolor)
        line_boundaries.append((p1, p2))
    circles = [draw_circle(ax, c, color=ccolor) for c in circles]

    for p in points:
        draw_point(ax, p.num, p.name, line_boundaries, circles, color=pcolor)

    if equals:
        for i, segs in enumerate(equals["segments"]):
            color = colors[i % len(colors)]
            for a, b in segs:
                mark_segment(ax, a, b, color, 0.5)

        for i, angs in enumerate(equals["angles"]):
            color = colors[i % len(colors)]
            for a, b, c, d in angs:
                highlight_angle(ax, a, b, c, d, color, 0.5)

    if highlights:
        global HCOLORS
        if HCOLORS is None:
            HCOLORS = [k for k in mcolors.TABLEAU_COLORS.keys() if "red" not in k]

        for i, (name, args) in enumerate(highlights):
            color_i = HCOLORS[i % len(HCOLORS)]
            highlight(ax, name, args, "black", color_i, color_i)

    if goal:
        name, args = goal
        lcolor = color1 = color2 = "red"
        highlight(ax, name, args, lcolor, color1, color2)


def get_theme() -> str:
    return THEME


def set_theme(theme) -> None:
    global THEME
    THEME = theme


def draw_angle(
    ax: plt.Axes,
    head: Point,
    p1: Point,
    p2: Point,
    color: Any = "red",
    alpha: float = 0.5,
    frac: float = 1.0,
) -> None:
    """Draw an angle on plt ax."""
    d1 = p1 - head
    d2 = p2 - head

    a1 = np.arctan2(float(d1.y), float(d1.x))
    a2 = np.arctan2(float(d2.y), float(d2.x))
    a1, a2 = a1 * 180 / np.pi, a2 * 180 / np.pi
    a1, a2 = a1 % 360, a2 % 360

    if a1 > a2:
        a1, a2 = a2, a1

    if a2 - a1 > 180:
        a1, a2 = a2, a1

    b1, b2 = a1, a2
    if b1 > b2:
        b2 += 360
    d = b2 - b1
    # if d >= 90:
    #   return

    scale = min(2.0, 90 / d)
    scale = max(scale, 0.4)
    fov = plt.patches.Wedge(
        (float(head.x), float(head.y)),
        unif(0.075, 0.125) * scale * frac,
        a1,
        a2,
        color=color,
        alpha=alpha,
    )
    ax.add_artist(fov)


def draw_circle(ax: plt.Axes, circle: Circle, color: Any = "cyan") -> Circle:
    """Draw a circle."""
    if circle.num is not None:
        circle = circle.num
    else:
        points = circle.neighbors(gm.Point)
        if len(points) <= 2:
            return
        points = [p.num for p in points]
        p1, p2, p3 = points[:3]
        circle = Circle(p1=p1, p2=p2, p3=p3)

    _draw_circle(ax, circle, color)
    return circle


def _draw_circle(ax: plt.Axes, c: Circle, color: Any = "cyan", lw: float = 1.2) -> None:
    ls = "-"
    if color == "--":
        color = "black"
        ls = "--"

    ax.add_patch(
        plt.Circle(
            (c.center.x, c.center.y),
            c.radius,
            color=color,
            alpha=0.8,
            fill=False,
            lw=lw,
            ls=ls,
        )
    )


def draw_line(ax: plt.Axes, line: Line, color: Any = "white") -> tuple[Point, Point]:
    """Draw a line."""
    points = line.neighbors(gm.Point)
    if len(points) <= 1:
        return

    points = [p.num for p in points]
    p1, p2 = points[:2]

    pmin, pmax = (p1, 0.0), (p2, (p2 - p1).dot(p2 - p1))

    for p in points[2:]:
        v = (p - p1).dot(p2 - p1)
        if v < pmin[1]:
            pmin = p, v
        if v > pmax[1]:
            pmax = p, v

    p1, p2 = pmin[0], pmax[0]
    _draw_line(ax, p1, p2, color=color)
    return p1, p2


def _draw_line(
    ax: plt.Axes,
    p1: Point,
    p2: Point,
    color: Any = "white",
    lw: float = 1.2,
    alpha: float = 0.8,
) -> None:
    """Draw a line in plt."""
    ls = "-"
    if color == "--":
        color = "black"
        ls = "--"

    lx, ly = (p1.x, p2.x), (p1.y, p2.y)
    ax.plot(lx, ly, color=color, lw=lw, alpha=alpha, ls=ls)


def draw_point(
    ax: plt.Axes,
    p: Point,
    name: str,
    lines: list[Line],
    circles: list[Circle],
    color: Any = "white",
    size: float = 15,
) -> None:
    """draw a point."""
    ax.scatter(p.x, p.y, color=color, s=size)

    if color == "white":
        color = "lightgreen"
    else:
        color = "grey"

    name = name.upper()
    if len(name) > 1:
        name = name[0] + "_" + name[1:]

    ax.annotate(name, naming_position(ax, p, lines, circles), color=color, fontsize=15)


def mark_segment(ax: plt.Axes, p1: Point, p2: Point, color: Any, alpha: float) -> None:
    _ = alpha
    x, y = (p1.x + p2.x) / 2, (p1.y + p2.y) / 2
    ax.scatter(x, y, color=color, alpha=1.0, marker="o", s=50)


def highlight_angle(
    ax: plt.Axes,
    a: Point,
    b: Point,
    c: Point,
    d: Point,
    color: Any,
    alpha: float,
) -> None:
    """Highlight an angle between ab and cd with (color, alpha)."""
    try:
        a, b, c, d = bring_together(a, b, c, d)
    except (InvalidLineIntersectError, InvalidQuadSolveError):
        return
    draw_angle(ax, a, b, d, color=color, alpha=alpha, frac=1.0)


def highlight(
    ax: plt.Axes,
    name: str,
    args: list[gm.Point],
    lcolor: Any,
    color1: Any,
    color2: Any,
) -> None:
    """Draw highlights."""
    args = list(map(lambda x: x.num if isinstance(x, gm.Point) else x, args))

    if name == "cyclic":
        a, b, c, d = args
        _draw_circle(ax, Circle(p1=a, p2=b, p3=c), color=color1, lw=2.0)
    if name == "coll":
        a, b, c = args
        a, b = max(a, b, c), min(a, b, c)
        _draw_line(ax, a, b, color=color1, lw=2.0)
    if name == "para":
        a, b, c, d = args
        _draw_line(ax, a, b, color=color1, lw=2.0)
        _draw_line(ax, c, d, color=color2, lw=2.0)
    if name == "eqangle":
        a, b, c, d, e, f, g, h = args

        x = line_line_intersection(Line(a, b), Line(c, d))
        if b.distance(x) > a.distance(x):
            a, b = b, a
        if d.distance(x) > c.distance(x):
            c, d = d, c
        a, b, d = x, a, c

        y = line_line_intersection(Line(e, f), Line(g, h))
        if f.distance(y) > e.distance(y):
            e, f = f, e
        if h.distance(y) > g.distance(y):
            g, h = h, g
        e, f, h = y, e, g

        _draw_line(ax, a, b, color=lcolor, lw=2.0)
        _draw_line(ax, a, d, color=lcolor, lw=2.0)
        _draw_line(ax, e, f, color=lcolor, lw=2.0)
        _draw_line(ax, e, h, color=lcolor, lw=2.0)
        if color1 == "--":
            color1 = "red"
        draw_angle(ax, a, b, d, color=color1, alpha=0.5)
        if color2 == "--":
            color2 = "red"
        draw_angle(ax, e, f, h, color=color2, alpha=0.5)
    if name == "perp":
        a, b, c, d = args
        _draw_line(ax, a, b, color=color1, lw=2.0)
        _draw_line(ax, c, d, color=color1, lw=2.0)
    if name == "ratio":
        a, b, c, d, m, n = args
        _draw_line(ax, a, b, color=color1, lw=2.0)
        _draw_line(ax, c, d, color=color2, lw=2.0)
    if name == "cong":
        a, b, c, d = args
        _draw_line(ax, a, b, color=color1, lw=2.0)
        _draw_line(ax, c, d, color=color2, lw=2.0)
    if name == "midp":
        m, a, b = args
        _draw_line(ax, a, m, color=color1, lw=2.0, alpha=0.5)
        _draw_line(ax, b, m, color=color2, lw=2.0, alpha=0.5)
    if name == "eqratio":
        a, b, c, d, m, n, p, q = args
        _draw_line(ax, a, b, color=color1, lw=2.0, alpha=0.5)
        _draw_line(ax, c, d, color=color2, lw=2.0, alpha=0.5)
        _draw_line(ax, m, n, color=color1, lw=2.0, alpha=0.5)
        _draw_line(ax, p, q, color=color2, lw=2.0, alpha=0.5)


def naming_position(
    ax: plt.Axes, p: Point, lines: list[Line], circles: list[Circle]
) -> tuple[float, float]:
    """Figure out a good naming position on the drawing."""
    _ = ax
    r = 0.08
    c = Circle(center=p, radius=r)
    avoid = []
    for p1, p2 in lines:
        try:
            avoid.extend(circle_segment_intersect(c, p1, p2))
        except InvalidQuadSolveError:
            continue
    for x in circles:
        try:
            avoid.extend(circle_circle_intersection(c, x))
        except InvalidQuadSolveError:
            continue

    if not avoid:
        return [p.x + 0.01, p.y + 0.01]

    angs = sorted([ang_of(p, a) for a in avoid])
    angs += [angs[0] + 2 * np.pi]
    angs = [(angs[i + 1] - a, a) for i, a in enumerate(angs[:-1])]

    d, a = max(angs)
    ang = a + d / 2

    name_pos = p + Point(np.cos(ang), np.sin(ang)) * r

    x, y = (name_pos.x - r / 1.5, name_pos.y - r / 1.5)
    return x, y
