"""Tuning data pipeline and fine-tuning smoke test (synthetic strokes and temp dirs only)."""
import json
import random

import pytest

from conftest import REPO


def _strokes(x0=0.0):
    return [[(x0 + i * 4.0, 10.0 + (i % 3)) for i in range(25)], [(x0 + 20.0, 0.0), (x0 + 20.0, 30.0)]]


def _tune_dir(tmp_path, ok, files, prompts):
    ink = tmp_path / "ink"
    ink.mkdir()
    (ink / "tune_manifest.json").write_text(json.dumps({"ok": ok, "missing": []}), encoding="utf-8")
    for i in files:
        (ink / f"{i}.json").write_text(json.dumps(_strokes()), encoding="utf-8")
    p = tmp_path / "prompts.json"
    p.write_text(json.dumps([{"id": i, "area": "algebra", "display": i, "latex": lx} for i, lx in prompts]),
                 encoding="utf-8")
    return ink, p


def test_load_tune_pairs_manifest_ok_ids_with_prompt_latex(tmp_path):
    from train.dataset import load_tune
    ink, p = _tune_dir(tmp_path, ["U01", "U02"], ["U01", "U02", "U03"],
                       [("U01", "x+1"), ("U02", "2x"), ("U03", "y")])
    samples = load_tune(ink, p)
    assert [(s.id, s.latex) for s in samples] == [("U01", "x+1"), ("U02", "2x")]
    assert len(samples[0].strokes) == 2 and samples[0].strokes[0][0] == (0.0, 10.0)


def test_missing_ids_are_skipped(tmp_path):
    from train.dataset import load_tune
    ink, p = _tune_dir(tmp_path, ["U01", "U02", "U09"], ["U01"], [("U01", "x"), ("U02", "y")])
    assert [s.id for s in load_tune(ink, p)] == ["U01"]


def test_corrections_become_samples(tmp_path):
    from inkmath_reader import corrections
    from train.dataset import load_corrections
    corrections.save(tmp_path, _strokes(), "3x-1=11", "3x-7=11")
    [s] = load_corrections(tmp_path)
    assert s.latex == "3x-7=11" and len(s.strokes) == 2 and s.id.startswith("c")


def test_augment_is_deterministic_per_seed_and_keeps_stroke_count():
    from train.dataset import augment
    a = augment(_strokes(), random.Random(7))
    b = augment(_strokes(), random.Random(7))
    c = augment(_strokes(), random.Random(8))
    assert a == b and a != c
    assert [len(s) for s in a] == [len(s) for s in _strokes()]


def test_augment_stays_within_bounds():
    from train.dataset import augment
    src = [[(i * 10.0, 0.0) for i in range(51)]]          # 500 DIP wide, flat
    for seed in range(50):
        out = augment(src, random.Random(seed))
        xs = [p[0] for s in out for p in s]
        assert 0.85 <= (max(xs) - min(xs)) / 500 <= 1.15


def test_render_view_varies_height_and_stays_grayscale():
    from train.dataset import render_view
    heights = {render_view(_strokes(), random.Random(s)).size[1] for s in range(20)}
    assert min(heights) >= int(0.75 * 256) and max(heights) <= int(1.15 * 256) + 1 and len(heights) > 1


@pytest.mark.model
@pytest.mark.skipif(not (REPO / "models" / "huggingface").exists(), reason="no TexTeller weights")
def test_labels_match_generation_start():
    """generate() starts the decoder with bos, so labels drop the tokenizer's own bos; padding is -100."""
    from inkmath_reader.recognize import _offline_env
    _offline_env(REPO / "models")
    from texteller import load_tokenizer
    from train.finetune import make_labels
    tok = load_tokenizer()
    labels = make_labels(tok, ["x+1", "x"])
    one = tok("x+1").input_ids
    assert labels[0].tolist() == one[1:]
    assert labels[1].tolist()[: len(tok("x").input_ids) - 1] == tok("x").input_ids[1:]
    assert labels[1].tolist()[-1] == -100 and tok.bos_token_id not in labels[:, 0].tolist()


@pytest.mark.slow
@pytest.mark.model
@pytest.mark.skipif(not (REPO / "models" / "huggingface").exists(), reason="no TexTeller weights")
def test_finetune_smoke(tmp_path):
    from train import finetune
    ink, p = _tune_dir(tmp_path, ["U01", "U02", "U03"], ["U01", "U02", "U03"],
                       [("U01", "x+1"), ("U02", "2x"), ("U03", "y")])
    out = tmp_path / "out"
    rc = finetune.main(["--ink-dir", str(ink), "--prompts", str(p), "--out", str(out), "--models", str(REPO / "models"),
                        "--limit", "2", "--epochs", "1", "--views", "1", "--batch", "1", "--device", "cpu"])
    assert rc == 0
    assert (out / "config.json").exists() and (out / "model.safetensors").exists()
    assert (out / "tokenizer.json").exists() and (out / "train_log.txt").exists()
