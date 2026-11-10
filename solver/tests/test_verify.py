"""Each verifier must accept a right answer and reject a wrong one (spec §6.5)."""
from sympy import (Eq, Function, ImageSet, Integer, Interval, Lambda, Rational, S, Symbol, Union, cos, exp,
                   log, nan, oo, pi, sin, sqrt)

from inkmath_solver.ops.base import OpResult
from inkmath_solver.parse import parse_problem
from inkmath_solver.schema import Answer
from inkmath_solver.verify import verify

x, y, n, k, th = (Symbol(s) for s in ("x", "y", "n", "k", "theta"))


def res(v):
    return OpResult(value=v, answer=Answer("", "", None), steps=[], notes=[])


def ok(op, latex, right, wrong, var=x):
    p = parse_problem(latex)
    assert verify(op, p, res(right), var) is True, "right answer rejected"
    assert verify(op, p, res(wrong), var) is False, "wrong answer accepted"


def test_solve():
    ok("solve", "3x-7=11", [Integer(6)], [Integer(5)])


def test_solve_no_real_solutions():
    ok("solve", "x^2+1=0", [], [Integer(1)])
    assert verify("solve", parse_problem("x^2-1=0"), res([]), x) is False


def test_solve_inequality():
    ok("solve", "|2x-1|<5", Interval.open(-2, 3), Interval.open(-2, 4))


def test_solve_trig_imageset():
    right = Union(ImageSet(Lambda(k, 2*pi*k + pi/6), S.Integers), ImageSet(Lambda(k, 2*pi*k + 5*pi/6), S.Integers))
    wrong = ImageSet(Lambda(k, 2*pi*k + pi/3), S.Integers)
    ok("solve", r"2\sin\theta-1=0", right, wrong, th)


def test_solve_system():
    ok("solve_system", r"\begin{cases}x+y=7\\2x-y=2\end{cases}", [{x: 3, y: 4}], [{x: 4, y: 3}])


def test_integrate_indefinite():
    ok("integrate", r"\int x\sin x\,dx", sin(x) - x*cos(x), sin(x) + x*cos(x))


def test_integrate_definite():
    ok("integrate", r"\int_{0}^{\pi}x\sin x\,dx", pi, Integer(3))
    ok("integrate", r"\int_{1}^{\infty}\frac{1}{x^2}dx", Integer(1), oo)


def test_integrate_divergent():
    ok("integrate", r"\int_{0}^{1}\frac{1}{x}dx", oo, Integer(2))
    ok("integrate", r"\int_{1}^{\infty}\frac{1}{x}dx", oo, Integer(5))


def test_integrate_function_def():
    ok("integrate", "f'(x)=6x^2-2", 2*x**3 - 2*x, 6*x**3 - 2*x)


def test_derivative():
    ok("derivative", r"\frac{d}{dx}\ln(x^2+1)", 2*x/(x**2 + 1), x/(x**2 + 1))


def test_implicit_derivative():
    ok("implicit_derivative", "x^2+y^2=25", -x/y, x/y)


def test_limit():
    ok("limit", r"\lim_{x\to0}\frac{\sin x}{x}", Integer(1), Integer(2))
    ok("limit", r"\lim_{x\to\infty}\left(1+\frac{1}{x}\right)^x", exp(1), Integer(1))
    ok("limit", r"\lim_{x\to0^{+}}x\ln x", Integer(0), Integer(-1))


def test_limit_dne_and_infinite():
    ok("limit", r"\lim_{x\to0}\frac{1}{x}", nan, Integer(0))
    ok("limit", r"\lim_{x\to0^{+}}\frac{1}{x}", oo, nan)


def test_simplify_factor_expand():
    ok("simplify", r"\frac{x^2-1}{x^2+2x+1}", (x - 1)/(x + 1), (x + 1)/(x - 1))
    ok("factor", "x^2+5x+6", (x + 2)*(x + 3), (x + 1)*(x + 6))


def test_evaluate():
    ok("evaluate", r"\sin\frac{\pi}{6}+\cos\frac{\pi}{3}", Integer(1), Rational(1, 2))
    ok("evaluate", r"\frac{1}{0}", S.ComplexInfinity, Integer(0))


def test_evaluate_at():
    ok("evaluate_at", "f(x)=x^3-3x+2", (Integer(2), Integer(4)), (Integer(2), Integer(5)))


def test_identity():
    ok("identity", r"\cos(2x)=\cos^2x-\sin^2x", True, False)
    ok("identity", r"\sin(2x)=2\sin x", False, True)


def test_series():
    ok("series", r"\sum_{n=1}^{\infty}\frac{1}{n^2}", (True, pi**2/6), (True, Integer(2)), n)
    ok("series", r"\sum_{n=1}^{\infty}\frac{1}{n}", (False, None), (True, None), n)
    ok("series", r"\sum_{n=1}^{\infty}\frac{(-1)^n}{n}", (True, -log(2)), (False, None), n)


def test_ode():
    Y = Function("y")
    C1 = Symbol("C1")
    ok("ode", r"\frac{dy}{dx}=3y", Eq(Y(x), C1*exp(3*x)), Eq(Y(x), C1*exp(2*x)))


def test_verifier_exception_is_false():
    assert verify("solve", parse_problem("x=1"), res(["junk"]), x) is False
    assert verify("nonsense-op", parse_problem("x=1"), res([1]), x) is False
