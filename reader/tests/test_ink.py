"""Ink decoding and rendering. All strokes are synthetic (no real handwriting in the repo)."""
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import READER, REPO


def _line(x0, y0, x1, y1, n=20):
    return [(x0 + (x1 - x0) * i / (n - 1), y0 + (y1 - y0) * i / (n - 1)) for i in range(n)]


def test_isf_round_trip():
    from inkmath_reader.ink import decode_items, encode_strokes
    strokes = [_line(10, 10, 60, 40), _line(70, 40, 90, 10)]
    back = decode_items([encode_strokes(strokes)])
    assert len(back) == 2
    for a, b in zip(strokes, back):
        assert len(a) == len(b)
        assert all(abs(p[0] - q[0]) < 0.5 and abs(p[1] - q[1]) < 0.5 for p, q in zip(a, b))


def test_items_merge_in_page_coordinates():
    from inkmath_reader.ink import decode_items, encode_strokes
    a, b = _line(10, 10, 40, 10), _line(300, 200, 330, 230)
    merged = decode_items([encode_strokes([a]), encode_strokes([b])])
    assert len(merged) == 2
    assert abs(merged[1][0][0] - 300) < 0.5 and abs(merged[1][0][1] - 200) < 0.5


def _ink_rows(img):
    w, h = img.size
    px = img.load()
    return [y for y in range(h) if any(px[x, y] < 128 for x in range(w))]


def test_two_rows_stay_in_one_image():
    from inkmath_reader.render import render
    img = render([_line(0, 0, 100, 0), _line(0, 60, 100, 60)])
    assert img.size[1] == 256 and img.mode == "L"
    rows = _ink_rows(img)
    assert min(rows) < 256 / 3 and max(rows) > 2 * 256 / 3


def test_single_point_stroke_renders():
    from inkmath_reader.render import render
    img = render([[(5.0, 5.0)]])
    assert img.size[0] >= 30 and img.size[1] == 256


def test_wide_ink_is_capped():
    from inkmath_reader.render import render, MAX_WIDTH_PX
    assert MAX_WIDTH_PX == 2048
    assert render([_line(0, 0, 5000, 10)]).size[0] <= 2048


def test_no_points_raises_noink():
    from inkmath_reader.ink import NoInk
    from inkmath_reader.render import render
    with pytest.raises(NoInk):
        render([])
    with pytest.raises(NoInk):
        render([[]])


def test_torch_loads_before_winrt():
    code = (
        "import sys, builtins\n"
        "order = []\n"
        "real = builtins.__import__\n"
        "def spy(name, *a, **k):\n"
        "    if name == 'torch' or name.startswith('winrt.windows.ui.input.inking'):\n"
        "        order.append(name)\n"
        "    return real(name, *a, **k)\n"
        "builtins.__import__ = spy\n"
        "import inkmath_reader.ink\n"
        "builtins.__import__ = real\n"
        "print(order[0] if order else 'none', 'torch' in sys.modules)\n"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=READER, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert out.stdout.split() == ["torch", "True"]


def test_models_dir_precedence(monkeypatch, tmp_path):
    from inkmath_reader import paths
    monkeypatch.delenv("INKMATH_MODELS", raising=False)
    assert paths.models_dir() == REPO / "models"
    monkeypatch.setenv("INKMATH_MODELS", str(tmp_path / "env"))
    assert paths.models_dir() == tmp_path / "env"
    assert paths.models_dir(str(tmp_path / "arg")) == tmp_path / "arg"


def test_user_dir_is_local_appdata(monkeypatch, tmp_path):
    from inkmath_reader import paths
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert paths.user_dir() == tmp_path / "InkMath"
