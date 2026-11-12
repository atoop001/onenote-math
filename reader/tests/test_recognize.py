"""Recognizer with per-token scores. Uses a typed (PIL font) image, not handwriting."""
import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from conftest import REPO

MODELS = REPO / "models"
pytestmark = [pytest.mark.model, pytest.mark.skipif(not (MODELS / "huggingface").exists(), reason="no TexTeller weights")]


def _typed_image() -> Image.Image:
    img = Image.new("L", (400, 120), 255)
    ImageDraw.Draw(img).text((20, 30), "x^2+1", fill=0, font=ImageFont.load_default(size=48))
    return img


@pytest.fixture(scope="module")
def rec():
    from inkmath_reader.recognize import Recognizer
    return Recognizer(MODELS)


def test_read_matches_img2latex(rec):
    from texteller import img2latex
    from inkmath_reader.recognize import strip_delims
    img = _typed_image()
    expected = strip_delims(img2latex(rec.model, rec.tokenizer, [np.array(img.convert("RGB"))],
                                      device=rec.device, max_tokens=256)[0])
    assert rec.read(img).latex == expected


def test_steps_carry_probabilities(rec):
    r = rec.read(_typed_image())
    assert r.steps
    assert all(0 < s.prob <= 1 for s in r.steps)
    assert all(len(s.alts) <= rec.top_k - 1 for s in r.steps)
    assert "".join(s.text for s in r.steps) == r.raw
    assert rec.name == "texteller"


def test_max_tokens_caps_generation():
    from inkmath_reader.recognize import Recognizer
    short = Recognizer(MODELS, max_tokens=8)
    assert len(short.read(_typed_image()).steps) <= 8


def test_strip_delims():
    from inkmath_reader.recognize import strip_delims
    assert strip_delims(r"\[x^2+1\]") == "x^2+1"
    assert strip_delims("$$x$$") == "x"
    assert strip_delims("x^2") == "x^2"
