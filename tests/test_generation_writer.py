from pathlib import Path

from PIL import Image

from newclid.generation.writer import build_point_coords_grid, save_figure_as_png
from newclid.numerical.draw_figure import init_figure


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
