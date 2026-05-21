from pathlib import Path

import numpy as np
from PIL import Image

from newclid.algebraic_reasoning.algebraic_manipulator import AlgebraicManipulator
from newclid.dependencies.dependency_graph import DependencyGraph
from newclid.dependencies.symbols import Point
from newclid.generation.writer import build_point_coords_grid, save_figure_as_png
from newclid.numerical.draw_figure import LIGHT_THEME, draw_circle_num, draw_point
from newclid.numerical.draw_figure import draw_segment, init_figure
from newclid.numerical.geometries import CircleNum, PointNum
from newclid.predicates.congruence import Cong
from newclid.predicates.equal_angles import EqAngle
from newclid.predicates.parallelism import Para
from newclid.predicates.perpendicularity import Perp


def _make_point(dep_graph: DependencyGraph, name: str, x: float, y: float) -> Point:
    point = Point(name=name, symbols_graph=dep_graph.symbols_graph, dep=None)
    point.num = PointNum(x, y)
    dep_graph.symbols_graph.name2node[name] = point
    return point


def _draw_reference_scene(fig) -> None:
    dep_graph = DependencyGraph(AlgebraicManipulator())
    rng = np.random.default_rng(20260513)
    ax = fig.axes[0]

    a = _make_point(dep_graph, "a", 0.0, 0.0)
    b = _make_point(dep_graph, "b", 2.0, 0.0)
    c = _make_point(dep_graph, "c", 0.0, 2.0)
    d = _make_point(dep_graph, "d", 2.0, 2.0)
    e = _make_point(dep_graph, "e", 1.0, 1.0)
    f = _make_point(dep_graph, "f", 3.0, 1.0)

    draw_segment(ax, a, d)
    draw_circle_num(ax, CircleNum(center=e.num, p1=a.num))
    for point in (a, b, c, d, e, f):
        draw_point(ax, point)

    EqAngle.draw(ax, (a, b, a, c, d, e, d, c), dep_graph, rng, True)
    Cong.draw(ax, (a, b, c, d), dep_graph, rng, draw_annotations=True)
    Para.draw(ax, (a, b, c, d), dep_graph, rng, True)
    Perp.draw(ax, (a, d, b, c), dep_graph, rng, True)


def _render_reference_scene(png_path: Path, direct_png: bool) -> None:
    fig = init_figure()
    _draw_reference_scene(fig)
    save_figure_as_png(
        fig,
        png_path=str(png_path),
        img_pixels=512,
        direct_png=direct_png,
        svg_path=str(png_path.with_suffix(".svg")),
    )


def test_save_figure_as_png_direct_png_only(tmp_path: Path):
    fig = init_figure()
    png_path = tmp_path / "direct.png"
    svg_path = tmp_path / "direct.svg"

    save_figure_as_png(
        fig,
        png_path=str(png_path),
        img_pixels=512,
        direct_png=True,
        svg_path=str(svg_path),
    )

    assert png_path.exists()
    assert not svg_path.exists()
    with Image.open(png_path) as image:
        assert image.size == (512, 512)
        assert image.convert("RGB").getpixel((256, 256)) == (255, 255, 255)


def test_save_figure_as_png_legacy_svg_conversion(tmp_path: Path):
    fig = init_figure()
    png_path = tmp_path / "legacy.png"
    svg_path = tmp_path / "legacy.svg"

    save_figure_as_png(
        fig,
        png_path=str(png_path),
        img_pixels=512,
        direct_png=False,
        svg_path=str(svg_path),
    )

    assert png_path.exists()
    assert svg_path.exists()
    with Image.open(png_path) as image:
        assert image.size == (512, 512)


def test_default_light_theme_render_has_white_background(tmp_path: Path):
    png_path = tmp_path / "light.png"

    _render_reference_scene(png_path, direct_png=True)

    with Image.open(png_path) as image:
        rgb = image.convert("RGB")
        assert rgb.getpixel((0, 0)) == (255, 255, 255)
        assert rgb.getpixel((256, 256)) == (255, 255, 255)


def test_light_theme_constants():
    assert LIGHT_THEME["background"] == "#ffffff"
    assert LIGHT_THEME["line"] == "#000000"
    assert LIGHT_THEME["circle"] == "#ff0000"
    assert LIGHT_THEME["point_name"] == "#ff00ff"
    assert LIGHT_THEME["perpendicular"] == "#0000ff"
    assert LIGHT_THEME["palette"][0] == "#19e6b4"
    assert LIGHT_THEME["palette"][-1] == "#000000"


def test_build_point_coords_grid_uses_top_left_256_grid():
    point_coords_grid = build_point_coords_grid(
        {
            "raw_a": (0.0, 512.0),
            "raw_b": (512.0, 0.0),
            "raw_c": (256.0, 256.0),
        },
        {"raw_a": "a", "raw_b": "b", "raw_c": "c"},
        canvas_width=512,
        canvas_height=512,
    )

    assert point_coords_grid == {
        "a": [0, 0],
        "b": [255, 255],
        "c": [128, 128],
    }


def test_build_point_coords_grid_clamps_and_sorts():
    point_coords_grid = build_point_coords_grid(
        {
            "raw_b": (999.0, -100.0),
            "raw_a": (-20.0, 800.0),
        },
        {"raw_b": "b", "raw_a": "a"},
        canvas_width=512,
        canvas_height=512,
    )

    assert list(point_coords_grid.keys()) == ["a", "b"]
    assert point_coords_grid["a"] == [0, 0]
    assert point_coords_grid["b"] == [255, 255]


def test_build_point_coords_grid_can_exclude_aux_points():
    point_coords_grid = build_point_coords_grid(
        {
            "raw_a": (0.0, 512.0),
            "raw_b": (512.0, 0.0),
            "raw_aux": (256.0, 256.0),
        },
        {"raw_a": "a", "raw_b": "b"},
        canvas_width=512,
        canvas_height=512,
    )

    assert point_coords_grid == {
        "a": [0, 0],
        "b": [255, 255],
    }
