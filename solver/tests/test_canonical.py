"""Vetted rewrites for handwriting-reader quirks. Each must keep the meaning (M1 carry-forward 2)."""
import pytest

from inkmath_solver.canonical import canonicalize
from inkmath_solver.engine import handle
from inkmath_solver.parse import parse_problem
from inkmath_solver.schema import Request

ARRAY = r"\left\{\begin{array}{l}x+y=3\\x-y=1\end{array}\right."
CASES = r"\begin{cases}x+y=3\\x-y=1\end{cases}"

PAIRS = [
    ("lnx", r"\ln x"),
    ("sinx+1", r"\sin x+1"),
    (r"\lnx", r"\ln x"),
    (r"\cosx", r"\cos x"),
    ("2tanx", r"2\tan x"),
    ("log100", r"\log 100"),
    (ARRAY, CASES),
    (r"\left\{\begin{array}{ll}x+y=3\\x-y=1\end{array}\right.", CASES),
]


@pytest.mark.parametrize("raw, fixed", PAIRS)
def test_rewrites(raw, fixed):
    assert canonicalize(raw) == fixed


@pytest.mark.parametrize("raw, fixed", PAIRS)
def test_rewrites_keep_meaning(raw, fixed):
    a, b = parse_problem(canonicalize(raw)), parse_problem(fixed)
    assert (a.kind, a.expr, a.equations) == (b.kind, b.expr, b.equations)


@pytest.mark.parametrize("valid", [
    r"\ln(x)^2", r"\sin^{2}x", r"\log_{2}x", r"\sinh x", r"\arcsin x", r"\cos x", r"x\ln x", "3x-7=11",
    r"\cosh(2x)", r"\tan\theta", r"\lim_{x\to0}\frac{\sin x}{x}", r"\begin{cases}x=1\\y=2\end{cases}",
    r"\ln x", r"\log 100", "x+y", r"\operatorname{sinc}x",
])
def test_rewrites_never_touch_valid_forms(valid):
    assert canonicalize(valid) == valid


def test_solve_reads_bare_lnx():
    r = handle(Request(id="a", latex="lnx=1"))
    assert r.status == "ok" and r.answer.text == "x = e"
