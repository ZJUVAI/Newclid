from pathlib import Path

from PIL import Image

from newclid.generation.writer import save_figure_as_png
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
