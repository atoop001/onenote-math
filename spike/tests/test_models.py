import json
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
INK = ROOT / "data" / "ink"


@pytest.mark.samples
@pytest.mark.parametrize("name", ["pix2text", "texteller"])
def test_model_recognizes_first_sample(name):
    import models
    manifest = json.loads((INK / "test_manifest.json").read_text(encoding="utf-8"))
    png = INK / f"{manifest['ok'][0]}.png"
    rec = models.get(name)
    rec.recognize(str(png))  # first call loads weights; time a warm call
    t0 = time.perf_counter()
    out = rec.recognize(str(png))
    assert isinstance(out, str) and out.strip()
    assert time.perf_counter() - t0 < 10


def test_model_files_are_stored_in_repo_models_folder():
    import os
    import models
    base = ROOT / "models"
    for var in ("HF_HOME", "PIX2TEXT_HOME", "CNSTD_HOME", "CNOCR_HOME", "TORCH_HOME"):
        assert Path(os.environ[var]).is_relative_to(base), var


def test_display_delimiters_are_stripped():
    from models.texteller import strip_delims
    assert strip_delims(r"\[x^2+1\]") == "x^2+1"
    assert strip_delims("$$x$$") == "x"
    assert strip_delims("x^2") == "x^2"


def test_registry_rejects_unknown_name():
    import models
    with pytest.raises(KeyError, match="pix2text"):
        models.get("nope")
