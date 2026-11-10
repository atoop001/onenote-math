import pytest
from sympy import Integer, Rational, Symbol, exp, log, oo, pi, sin, sqrt

from inkmath_solver.textfmt import decimal_of, to_text

x = Symbol("x")
th = Symbol("theta")


@pytest.mark.parametrize("obj,text", [
    (x**2 + 5*x + 6, "x² + 5x + 6"), (sqrt(2)/2, "√2/2"), (pi/6, "π/6"), (oo, "∞"),
    (log(x), "ln(x)"), (exp(2*x), "e^(2x)"), (th, "θ"), (x*sin(x), "x·sin(x)"),
    (Rational(-3, 4), "−3/4"), (log(9)/2, "ln(9)/2"),
    ((x + 2)*(x + 3), "(x + 2)(x + 3)"), (2*pi*Symbol("k"), "2πk"), (6*x*Symbol("y"), "6xy"),
    (x*(x - 2), "x(x − 2)")])
def test_to_text(obj, text):
    assert to_text(obj) == text


@pytest.mark.parametrize("v,d", [(Integer(6), None), (Rational(5, 2), "2.5"), (pi, "3.14159"),
                                 (sqrt(2)/2, "0.707107"), (x + 1, None), (oo, None)])
def test_decimal_of(v, d):
    assert decimal_of(v) == d
