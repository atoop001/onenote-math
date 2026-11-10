"""Final-review findings (Critical C1–C3, Important I4–I11), each pinned before its fix."""
import re

import pytest
from sympy import LambertW, Rational, Symbol, Sum, oo

from inkmath_solver.engine import handle
from inkmath_solver.ops.base import OpResult
from inkmath_solver.parse import parse_problem
from inkmath_solver.schema import Answer, Request
from inkmath_solver.verify import verify

x, n = Symbol("x"), Symbol("n")
RAW = ("re(", "im(", "Piecewise", "AccumBounds", "Derivative", "zoo", "nan", "LambertW(")


def h(latex, **kw):
    return handle(Request(id="t", latex=latex, **kw))


def res(v):
    return OpResult(value=v, answer=Answer("", "", None), steps=[], notes=[])


# C1: an extraneous log root must never be answered, let alone verified
def test_extraneous_log_root_rejected():
    r = h(r"\ln(x-1)=\ln(2x)")
    assert r.answer.text == "No real solutions" and r.verified
    assert verify("solve", parse_problem(r"\ln(x-1)=\ln(2x)"), res([-1]), x) is False


def test_log_equation_keeps_only_real_root():
    r = h(r"\ln x+\ln(x+1)=\ln 6")
    assert r.answer.text == "x = 2" and r.verified


# C2: a missing root must not pass verification
def test_missing_root_not_verified():
    p = parse_problem("e^x=3x")
    assert verify("solve", p, res([-LambertW(Rational(-1, 3))]), x) is False
    r = h("e^x=x+2")
    assert r.verified is False or r.answer.text.count("x ") == 2


# C3: real-only answers (spec §7)
@pytest.mark.parametrize("latex", [r"\arcsin 2", r"\sqrt{-4}"])
def test_non_real_value(latex):
    r = h(latex, operation="evaluate")
    assert r.answer.text == "Not a real number"


# I4: wide-range integrals
def test_convergent_infinite_integral_verified():
    r = h(r"\int_{-\infty}^{\infty}\frac{1}{1+x^2}dx")
    assert r.answer.text == "π" and r.verified
    p = parse_problem(r"\int_{-\infty}^{\infty}\frac{1}{1+x^2}dx")
    assert verify("integrate", p, res(oo), x) is False


# I5: never raw SymPy on the page
@pytest.mark.parametrize("latex", [r"\int_{0}^{\infty}\sin x\,dx", r"\frac{d}{dx}\ln|x|",
                                   r"\lim_{x\to0^{+}}\frac{|x|}{x}", "x^3-3x+1=0"])
def test_no_raw_sympy_output(latex):
    r = h(latex)
    shown = (r.answer.text if r.answer else "") + " ".join(r.steps) + r.message
    assert not any(tok in shown for tok in RAW), shown


def test_oscillating_integral_diverges():
    assert h(r"\int_{0}^{\infty}\sin x\,dx").answer.text == "Diverges"


def test_derivative_of_ln_abs():
    assert h(r"\frac{d}{dx}\ln|x|").answer.text == "1/x"


def test_cubic_three_real_roots_shown_real():
    r = h("x^3-3x+1=0")
    assert not re.search(r"\bi\b", r.answer.text) and r.answer.text.count("x ") == 3 and r.verified


# I6: crashes
def test_single_row_environment():
    assert h(r"\begin{aligned} x+1=2 \end{aligned}").answer.text == "x = 1"


def test_dependent_system():
    r = h(r"\begin{cases}x+y=2\\2x+2y=4\end{cases}")
    assert r.status == "cannot_solve" and "infinitely many" in r.message


def test_symbolic_p_series_does_not_crash():
    assert h(r"\sum_{n=1}^{\infty}\frac{1}{n^{1+\frac{1}{n}}}").status in ("ok", "cannot_solve")


# I8: recognizer variants
def test_left_right_bars():
    assert h(r"\left|x-3\right|=2x").answer.text == "x = 1"


def test_prime_notation_ode():
    r = h("y'=y")
    assert r.status == "ok" and r.operation == "ode" and "C₁" in r.answer.text


# I9: ln|u| in antiderivatives (textbook form), but not where the integrand already needs u > 0
@pytest.mark.parametrize("latex,text", [
    (r"\int\frac{1}{x}dx", "ln|x| + C"), (r"\int\tan x\,dx", "−ln|cos(x)| + C"),
    (r"\int\frac{2x}{x^2+1}dx", "ln(x² + 1) + C"), (r"\int x^2\ln x\,dx", "x³(3ln(x) − 1)/9 + C")])
def test_log_absolute_values(latex, text):
    r = h(latex)
    assert r.answer.text == text and r.verified


# I10: divergence test when the terms oscillate
def test_alternating_terms_not_to_zero():
    r = h(r"\sum_{n=1}^{\infty}\frac{(-1)^n n}{n+1}")
    assert r.answer.text == "Diverges" and r.steps[0].startswith("Divergence test")


# I11: the series check must not just repeat SymPy's verdict
def test_series_verifier_independent(monkeypatch):
    monkeypatch.setattr(Sum, "is_convergent", lambda self: True)
    p = parse_problem(r"\sum_{n=1}^{\infty}\frac{1}{n}")
    assert verify("series", p, res((True, None)), n) is False
