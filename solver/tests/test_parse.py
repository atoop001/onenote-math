import pytest
from sympy import Eq, Symbol, exp, log

from helpers import load_all_prompts
from inkmath_solver.parse import ParseError, parse_problem


def same(a, b):
    return parse_problem(a).expr == parse_problem(b).expr


@pytest.mark.parametrize("variant,plain", [
    (r"\dfrac{1}{x}", r"\frac{1}{x}"), (r"\left(x+1\right)^2", "(x+1)^2"),
    (r"\int x\,\mathrm{d}x", r"\int x dx"), (r"\operatorname{sec} x", r"\sec x"),
    (r"\lim\limits_{x\to0}x", r"\lim_{x\to0}x"), (r"\lim_{x\rightarrow0}x", r"\lim_{x\to0}x"),
    (r"\displaystyle\frac{1}{2}", r"\frac{1}{2}"), (r"x\le3", r"x\leq3"),
    (r"f^{\prime}(x)=2x", "f'(x)=2x"), (r"f^{'}(x)=2x", "f'(x)=2x")])
def test_harmless_variants_parse_same(variant, plain):
    assert same(variant, plain)


def test_log_is_base_10_and_ln_is_natural():
    assert parse_problem(r"\log1000").expr == log(1000, 10)
    assert parse_problem(r"\log_{2}8").expr == log(8, 2)
    assert parse_problem(r"\ln x").expr == log(Symbol("x"))


def test_e_is_euler():
    assert parse_problem("e^{2x}=9").expr == Eq(exp(2*Symbol("x")), 9)


def test_i_is_imaginary_except_sum_index():
    assert parse_problem("x^2=-1+i").has_complex
    p = parse_problem(r"\sum_{i=1}^{\infty}\frac{1}{i^2}")
    assert not p.has_complex


def test_letter_before_paren_is_multiplication():
    x = Symbol("x")
    assert parse_problem(r"\frac{1}{x(x+1)}").expr == 1/(x*(x+1))


def test_system_rows():
    p = parse_problem(r"\begin{cases}x+y=7\\2x-y=2\end{cases}")
    assert p.kind == "system" and len(p.equations) == 2
    assert parse_problem(r"\begin{matrix}x+y=7\\2x-y=2\end{matrix}").kind == "system"


def test_function_definition():
    p = parse_problem("f(x)=x^3-3x+2")
    assert p.kind == "function_def" and p.func_name == "f"
    assert parse_problem("f'(x)=6x^2-2").func_name == "f'"


@pytest.mark.parametrize("latex,kind", [
    ("3x-7=11", "equation"), ("|2x-1|<5", "inequality"),
    (r"\int_{0}^{\pi}x\sin x\,dx", "integral"), (r"\frac{d}{dx}\tan(2x)", "derivative"),
    (r"\lim_{x\to0^{+}}x\ln x", "limit"), (r"\sum_{n=1}^{\infty}\frac{1}{n^2}", "sum"),
    (r"\frac{dy}{dx}=3y", "ode"), ("x^2+5x+6", "expr")])
def test_kinds(latex, kind):
    assert parse_problem(latex).kind == kind


def test_pi_is_the_constant():
    from sympy import Rational, pi
    assert parse_problem(r"\sin\frac{\pi}{6}").expr == Rational(1, 2)
    assert parse_problem(r"\int_{0}^{\pi}x\,dx").expr.limits[0][2] == pi
    assert parse_problem(r"\int_{0}^{\pi}x\,dx").symbols == [Symbol("x")]


def test_limit_direction_is_not_a_variable():
    assert parse_problem(r"\lim_{x\to0^{+}}\frac{1}{x}").symbols == [Symbol("x")]


def test_raw_keeps_expression_as_written():
    from sympy import fraction
    p = parse_problem(r"\frac{x^3y^2}{xy^4}")
    assert p.expr == Symbol("x")**2 / Symbol("y")**2          # evaluated form cancels
    assert Symbol("x") in fraction(p.raw)[1].free_symbols      # raw still divides by x (x ≠ 0)


def test_symbol_order():
    assert [s.name for s in parse_problem("y+x+t").symbols] == ["x", "y", "t"]


def test_garbage_raises():
    pytest.raises(ParseError, parse_problem, r"\frac{x+")


@pytest.mark.corpus
def test_all_120_prompts_parse():
    for p in load_all_prompts():
        parse_problem(p["latex"])  # must not raise
