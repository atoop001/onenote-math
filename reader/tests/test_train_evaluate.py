"""Tuning gate, threshold calibration and the committed report (pure, no model)."""
import re

from train.evaluate import choose_threshold, gate, render_report, wrong_flags

BASE = {"zero_rate": 0.93, "le2_rate": 0.98, "median_ms": 1000.0, "n": 60}


def test_gate_accepts_equal_or_better():
    assert gate(BASE, dict(BASE))
    assert gate(BASE, dict(BASE, zero_rate=0.97, median_ms=1150.0))


def test_gate_rejects_worse_accuracy():
    assert not gate(BASE, dict(BASE, zero_rate=0.92))
    assert not gate(BASE, dict(BASE, le2_rate=0.97))


def test_gate_rejects_slower_than_115_percent():
    assert not gate(BASE, dict(BASE, median_ms=1151.0))


def test_threshold_reaches_90_percent_recall():
    wrong = [0.3, 0.4, 0.5, 0.6, 0.62, 0.64, 0.66, 0.68, 0.7, 0.95]   # 9 of 10 below 0.71
    all_ = wrong + [0.99] * 90
    t, recall, flagged = choose_threshold(wrong, all_)
    assert t == 0.71 and recall >= 0.9 and abs(flagged - 0.09) < 1e-9


def test_threshold_capped_at_20_percent_flagged():
    wrong = [0.9] * 10
    all_ = wrong + [0.8] * 30 + [0.99] * 60          # reaching 90% recall would flag 40%
    t, recall, flagged = choose_threshold(wrong, all_)
    assert flagged <= 0.20 and t == 0.8 and recall == 0.0


def test_wrong_flags_mark_symbols_outside_equal_blocks():
    assert wrong_flags(["3", "x", "-", "1", "=", "1", "1"], ["3", "x", "-", "7", "=", "1", "1"]) == \
        [False, False, False, True, False, False, False]


def test_zero_fix_problems_have_no_misreads():
    from train.evaluate import misread_flags
    assert misread_flags(["x", "^", "{", "2", "}"], "x^2", fixes=0) == [False] * 5


def test_syntax_pieces_are_never_misreads():
    from train.evaluate import misread_flags
    assert misread_flags(["x", "^", "{", "3", "}", "+", "1"], "x^2+1", fixes=1) == \
        [False, False, False, True, False, False, False]


def test_report_contains_no_latex_or_ids():
    s = dict(BASE, by_area={"algebra": {"n": 15, "zero_rate": 0.93, "le2_rate": 1.0}})
    text = render_report(base=s, tuned=dict(s, zero_rate=0.95), accepted=True, threshold=(0.8, 0.91, 0.12),
                         train_log="samples=60 epochs=15\nepoch 1: loss 0.5", n_tune=60, n_misread=2)
    assert "Accepted" in text and "0.8" in text
    assert "2 misread symbols" in text
    assert not re.search(r"\b[TU]\d\d\b", text) and "\\" not in text
