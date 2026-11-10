import pytest

from helpers import run
from inkmath_solver.ops.calculus import (run_derivative, run_implicit_derivative, run_integrate, run_limit,
                                         run_ode)
from inkmath_solver.parse import parse_problem
from inkmath_solver.verify import verify


@pytest.mark.parametrize("latex,text", [
    (r"\lim_{x\to0}\frac{\sin x}{x}", "1"), (r"\lim_{x\to\infty}\frac{3x^2+1}{x^2-4}", "3"),
    (r"\lim_{x\to2}\frac{x^2-4}{x-2}", "4"), (r"\lim_{x\to0^{+}}x\ln x", "0"),
    (r"\lim_{x\to0}\frac{1}{x}", "Does not exist"), (r"\lim_{x\to0^{+}}\frac{1}{x}", "∞")])
def test_limits(latex, text):
    assert run(latex, run_limit).answer.text == text


@pytest.mark.parametrize("latex,step", [
    (r"\lim_{x\to2}\frac{x^2-4}{x-2}", "Factor and cancel"),
    (r"\lim_{x\to\infty}\frac{3x^2+1}{x^2-4}", "Divide by the highest power"),
    (r"\lim_{x\to0}\frac{\sin x}{x}", "L'Hôpital's rule")])
def test_limit_method_named(latex, step):
    assert any(s.startswith(step) for s in run(latex, run_limit).steps)


@pytest.mark.parametrize("latex,step", [
    (r"\frac{d}{dx}(x^3\sin x)", "Product rule"), (r"\frac{d}{dx}\frac{x+1}{x-1}", "Quotient rule"),
    (r"\frac{d}{dx}\ln(x^2+1)", "Chain rule")])
def test_derivative_rule_named(latex, step):
    assert run(latex, run_derivative).steps[0].startswith(step)


def test_derivative_answer():
    assert run(r"\frac{d}{dx}\ln(x^2+1)", run_derivative).answer.text == "2x/(x² + 1)"


def test_derivative_of_function_def():
    assert run("f(x)=x^3-3x+2", run_derivative).answer.text == "f′(x) = 3x² − 3"


def test_implicit():
    assert run("x^2+y^2=25", run_implicit_derivative).answer.text == "dy/dx = −x/y"


@pytest.mark.parametrize("latex,step", [
    (r"\int x\sin x\,dx", "Integration by parts"), (r"\int2xe^{x^2}dx", "Substitution: u = x²"),
    (r"\int\frac{3x+5}{(x+1)(x+2)}dx", "Partial fractions"), (r"\int\sqrt{9-x^2}dx", "Trig substitution")])
def test_integral_technique(latex, step):
    assert run(latex, run_integrate).steps[0].startswith(step)


@pytest.mark.parametrize("latex,text", [
    (r"\int_{0}^{\pi}x\sin x\,dx", "π"), (r"\int_{1}^{\infty}\frac{1}{x^2}dx", "1"),
    (r"\int_{0}^{\frac{\pi}{2}}\cos^2\theta\,d\theta", "π/4"), (r"\int_{0}^{1}\frac{1}{x}dx", "Diverges")])
def test_definite(latex, text):
    assert run(latex, run_integrate).answer.text == text


def test_indefinite_has_C():
    assert run(r"\int2xe^{x^2}dx", run_integrate).answer.text.endswith("+ C")


def test_integrate_function_def():
    assert run("f'(x)=6x^2-2", run_integrate).answer.text == "f(x) = 2x³ − 2x + C"


def test_ode():
    assert "C₁" in run(r"\frac{dy}{dx}=3y", run_ode).answer.text


@pytest.mark.parametrize("op,fn,latex", [
    ("limit", run_limit, r"\lim_{h\to0}\frac{(2+h)^2-4}{h}"),
    ("limit", run_limit, r"\lim_{x\to0}\frac{1}{x}"),
    ("derivative", run_derivative, r"\frac{d}{dx}e^{3x}\cos x"),
    ("integrate", run_integrate, r"\int\frac{1}{x^2-1}dx"),
    ("integrate", run_integrate, r"\int_{0}^{1}\frac{1}{x}dx"),
    ("integrate", run_integrate, r"\int e^x\cos x\,dx"),
    ("implicit_derivative", run_implicit_derivative, "x^3+y^3=6xy"),
    ("ode", run_ode, r"\frac{dy}{dx}=\frac{x}{y}")])
def test_answers_pass_verification(op, fn, latex):
    p = parse_problem(latex)
    r = run(latex, fn)
    assert verify(op, p, r, p.symbols[0])
