from copy import deepcopy
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, Collection, Optional, Union
from adjustText import adjust_text
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from numpy.random import Generator

import numpy as np
import matplotlib.patches as patches

from newclid.numerical.geometries import (
    PointNum,
    intersect,
)
from newclid.dependencies.symbols import Point, Circle, Line
from newclid.numerical.geometries import CircleNum

if TYPE_CHECKING:
    from newclid.proof import ProofState
    from newclid.statement import Statement

LIGHT_THEME = {
    "background": "#ffffff",
    "circle": "#ff0000",
    "line": "#000000",
    "point": "#000000",
    "point_name": "#ff00ff",
    "perpendicular": "#0000ff",
    "angle_default": "#ffffff",
    "palette": [
        "#19e6b4",
        "#c34bb4",
        "#001ee6",
        "#bc9c27",
        "#0a7dce",
        "#6ee14b",
        "#b90f0f",
        "#0fcd19",
        "#4309f3",
        "#054141",
        "#ff7f7f",
        "#194100",
        "#659cdb",
        "#000537",
        "#7fffff",
        "#55003c",
        "#7f7fff",
        "#00274e",
        "#ffff32",
        "#7f7f7f",
        "#000000",
    ],
}

PALETTE = LIGHT_THEME["palette"]


def get_figure_theme(ax: "Axes") -> dict[str, Any]:
    return getattr(ax, "_newclid_theme", LIGHT_THEME)


def init_figure(theme: Optional[dict[str, Any]] = None) -> "Figure":
    imsize = 512 / 100
    fig = Figure(figsize=(imsize, imsize))
    ax = fig.add_subplot(111)  # type: ignore
    figure_theme = theme or LIGHT_THEME
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0, wspace=0, hspace=0)
    fig.patch.set_facecolor(figure_theme["background"])
    ax._newclid_theme = figure_theme  # type: ignore[attr-defined]
    ax.set_facecolor(figure_theme["background"])
    ax.tick_params(colors=figure_theme["background"])
    for spine in ax.spines.values():
        spine.set_color(figure_theme["background"])
    ax.set_aspect("equal", adjustable="datalim")
    return fig


def draw_figure(
    proof: "ProofState",
    *,
    save_to: Optional[Union[Path, BytesIO]] = None,
    rng: Generator,
    format: str = "svg",
    draw_annotations: bool = True,
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
            draw_annotations,
        )
    else:
        _draw(ax, points, proof.dep_graph.checked(), rng, draw_annotations)

    if save_to is not None:
        fig.savefig(
            save_to,
            format=format,
            facecolor=fig.get_facecolor(),
            edgecolor="none",
        )  # type: ignore


def _draw(
    ax: "Axes",
    points: list[Point],
    statements: Collection["Statement"],
    rng: Generator,
    draw_annotations: bool = True,
):
    """Draw everything."""
    for statement in statements:
        statement.draw(ax, rng, draw_annotations)
    point_names = []
    for p in points:
        point_names.append(draw_point(ax, p))
    adjust_text(point_names, ax=ax)


def draw_with_mapping(
    ax: "Axes",
    points: list[Point],
    statements: Collection["Statement"],
    goal: "Statement",
    rng: Generator,
    mapping: dict[str, str],
    draw_annotations: bool = True,
):
    """Draw everything with point mapping."""
    point_names = []
    for p in points:
        mapped_p = Point(name=mapping[p.name], symbols_graph=None, dep=None)
        mapped_p.num = p.num
        point_names.append(draw_point(ax, mapped_p))

    segment_parent: dict[tuple[str, str], tuple[str, str]] = {}
    segment_colors: dict[tuple[str, str], int] = {}
    figure_sizes: list = []
    for statement in statements:
        if statement.predicate.NAME == "cong":
            statement.predicate.draw(
                ax,
                statement.args,
                statement.dep_graph,
                rng,
                segment_parent,
                segment_colors,
                figure_sizes,
                draw_annotations,
            )
        else:
            statement.draw(ax, rng, draw_annotations)

    if goal.predicate.NAME == "cong":
        draw_segment(ax, goal.args[0], goal.args[1])
        draw_segment(ax, goal.args[2], goal.args[3])
    else:
        goal.draw(ax, rng, draw_annotations)

    adjust_text(point_names, ax=ax)


def fill_missing(d0: dict[Any, Any], d1: dict[Any, Any]):
    for k in d1.keys():
        if k not in d0:
            d0[k] = d1[k]


def draw_circle(ax: "Axes", c: Circle, **args: Any) -> None:
    fill_missing(
        args,
        {
            "color": get_figure_theme(ax)["circle"],
            "fill": False,
            "lw": 0.8,
        },
    )
    ax.add_patch(
        patches.Circle(  # type: ignore
            (c.num.center.x, c.num.center.y), c.num.radius, **args
        )
    )


def draw_circle_num(ax: "Axes", c: CircleNum, **args: Any) -> None:
    fill_missing(
        args,
        {
            "color": get_figure_theme(ax)["circle"],
            "fill": False,
            "lw": 0.8,
        },
    )
    ax.add_patch(
        patches.Circle(  # type: ignore
            (c.center.x, c.center.y), c.radius, **args
        )
    )


def draw_line(ax: "Axes", line: Line, **args: Any):
    """Draw a line. Return the two extremities"""
    fill_missing(
        args,
        {"color": get_figure_theme(ax)["line"], "lw": 0.4, "alpha": 0.9},
    )

    points: list[PointNum] = [p.num for p in line.points]
    p0, p1 = points[:2]
    ax.axline((p0.x, p0.y), (p1.x, p1.y), **args)  # type: ignore


def draw_segment(ax: "Axes", p0: Point, p1: Point, **args: Any):
    fill_missing(
        args,
        {"color": get_figure_theme(ax)["line"], "lw": 0.4, "alpha": 0.9},
    )
    ax.plot((p0.num.x, p1.num.x), (p0.num.y, p1.num.y), **args)  # type: ignore


def draw_segment_num(ax: "Axes", p0: PointNum, p1: PointNum, **args: Any):
    fill_missing(
        args,
        {"color": get_figure_theme(ax)["line"], "lw": 0.4, "alpha": 0.9},
    )
    ax.plot((p0.x, p1.x), (p0.y, p1.y), **args)  # type: ignore


def draw_angle(
    ax: "Axes",
    point0: Point,
    point1: Point,
    point2: Point,
    rng: Generator,
    color: Optional[str] = None,
    alpha: float = 0.5,
):
    color = color or get_figure_theme(ax)["angle_default"]
    # 1. Dynamic sizing based on figure bounds
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    figure_size = max(xlim[1] - xlim[0], ylim[1] - ylim[0])

    # Random base radius
    base_r = figure_size * rng.random() * 0.1 + 0.1

    # Fixed styling ratios
    wedge_radius = base_r * 0.8
    wedge_width = wedge_radius * 0.15

    # 2. Vector calculation
    dir1 = point1.num - point0.num
    dir2 = point2.num - point0.num

    # 3. Direction check (Cross Product)
    cross_product = dir1.x * dir2.y - dir1.y * dir2.x

    if cross_product >= 0:
        # Case A: CCW - Standard angle
        ang1 = np.arctan2(dir1.y, dir1.x)
        ang2 = np.arctan2(dir2.y, dir2.x)
    else:
        # Case B: CW - Supplementary angle logic
        # Calculate extension length (slightly longer than wedge)
        len2 = np.sqrt(dir2.x**2 + dir2.y**2)
        ext_len = wedge_radius * 1.3

        # Draw dashed extension line for dir2
        if len2 > 0:
            vec_ext = (dir2 / len2) * ext_len
            o_pos = point0.num - vec_ext
            draw_segment_num(ax, point0.num, o_pos, ls="dashed", alpha=0.5)

        # Adjust angles (dir1 to -dir2)
        ang1 = np.arctan2(dir1.y, dir1.x)
        ang2 = np.arctan2(-dir2.y, -dir2.x)

    # 4. Draw Wedge with explicit parameters
    wedge = patches.Wedge(
        (point0.num.x, point0.num.y),
        r=wedge_radius,
        theta1=np.degrees(ang1),
        theta2=np.degrees(ang2),
        width=wedge_width,
        color=color,
        alpha=alpha,
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
    theme = get_figure_theme(ax)
    fill_missing(args_point, {"color": theme["point"], "s": 5.0})
    ax.scatter(p.num.x, p.num.y, **args_point)  # type: ignore
    fill_missing(args_name, {"color": theme["point_name"], "fontsize": 10})
    return ax.annotate(  # type: ignore
        p.pretty_name, (p.num.x, p.num.y), **args_name
    )
