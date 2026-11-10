from pathlib import Path

from inkspike.prompts import load_prompts

ROOT = Path(__file__).resolve().parents[2]
TEST_SET = ROOT / "samples" / "prompts_test.json"
TUNE_SET = ROOT / "samples" / "prompts_tune.json"


def _check(path, prefix):
    ps = load_prompts(path)
    assert len(ps) == 60
    assert len({p.id for p in ps}) == 60
    assert all(p.id.startswith(prefix) for p in ps)
    counts = {a: sum(p.area == a for p in ps) for a in ("algebra", "precalc", "calc1", "calc2")}
    assert counts == {"algebra": 15, "precalc": 10, "calc1": 15, "calc2": 20}
    assert all(p.display and p.latex for p in ps)
    return ps


def test_test_set():
    _check(TEST_SET, "T")


def test_tune_set():
    _check(TUNE_SET, "U")


def test_sets_do_not_overlap():
    a = {p.latex for p in load_prompts(TEST_SET)}
    b = {p.latex for p in load_prompts(TUNE_SET)}
    assert not a & b


def test_coverage_of_hard_layouts():
    ps = load_prompts(TEST_SET)
    joined = " ".join(p.latex for p in ps)
    for needle in (r"\int_", r"\frac", "^", r"\sqrt", r"\lim_", r"\sum_", r"\sin", r"\theta", r"\ln", r"\infty"):
        assert needle in joined, needle
