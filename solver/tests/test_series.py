import pytest

from helpers import load_all_prompts, run
from inkmath_solver.ops.base import CannotSolve
from inkmath_solver.ops.series import run_series
from inkmath_solver.parse import parse_problem
from inkmath_solver.verify import verify


@pytest.mark.parametrize("latex,test,conv", [
    (r"\sum_{n=1}^{\infty}\frac{1}{n^2}", "p-series", True),
    (r"\sum_{n=0}^{\infty}\left(\frac{1}{2}\right)^n", "Geometric series", True),
    (r"\sum_{n=1}^{\infty}\frac{(-1)^n}{n}", "Alternating series test", True),
    (r"\sum_{n=1}^{\infty}\frac{n}{n+1}", "Divergence test", False),
    (r"\sum_{n=1}^{\infty}\frac{n!}{n^n}", "Ratio test", True),
    (r"\sum_{n=1}^{\infty}\frac{1}{\sqrt{n}}", "p-series", False),
    (r"\sum_{n=2}^{\infty}\frac{1}{n\ln n}", "Integral test", False),
    (r"\sum_{n=1}^{\infty}\frac{1}{n^2+1}", "Limit comparison", True)])
def test_classify(latex, test, conv):
    r = run(latex, run_series)
    assert r.steps[0].startswith(test) and r.value[0] is conv


@pytest.mark.parametrize("latex,text", [
    (r"\sum_{n=1}^{\infty}\frac{1}{n^2}", "Converges; sum = π²/6"),
    (r"\sum_{n=1}^{\infty}\frac{3}{4^n}", "Converges; sum = 1"),
    (r"\sum_{n=1}^{\infty}\frac{n}{n+1}", "Diverges")])
def test_answers(latex, text):
    assert run(latex, run_series).answer.text == text


def test_geometric_sum_step():
    r = run(r"\sum_{n=0}^{\infty}\left(\frac{1}{2}\right)^n", run_series)
    assert r.steps[0] == "Geometric series: r = 1/2, |r| < 1" and r.answer.text == "Converges; sum = 2"


def test_steps_count():
    for p in load_all_prompts():
        if p["latex"].startswith(r"\sum"):
            try:
                r = run(p["latex"], run_series)
            except CannotSolve:
                continue
            assert 1 <= len(r.steps) <= 4, p["id"]


@pytest.mark.corpus
def test_all_corpus_series_verify():
    for p in load_all_prompts():
        if p["latex"].startswith(r"\sum"):
            q = parse_problem(p["latex"])
            r = run(p["latex"], run_series)
            assert verify("series", q, r, q.symbols[0]), p["id"]
