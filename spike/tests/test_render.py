from PIL import Image

from inkspike.render import render_png


def test_render_normalizes_scale(tmp_path):
    a = [[(0, 0), (100, 50)]]
    b = [[(5000, 7000), (15000, 12000)]]
    render_png(a, tmp_path / "a.png")
    render_png(b, tmp_path / "b.png")
    ia, ib = Image.open(tmp_path / "a.png"), Image.open(tmp_path / "b.png")
    assert ia.size == ib.size and ia.getbbox() == ib.getbbox()


def test_render_height_and_ink_color(tmp_path):
    render_png([[(0, 0), (300, 100)]], tmp_path / "c.png")
    im = Image.open(tmp_path / "c.png").convert("L")
    assert im.size[1] == 256
    assert im.getpixel((0, 0)) == 255 and im.getextrema()[0] == 0
