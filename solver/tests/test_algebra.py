import pytest

from helpers import run
from inkmath_solver.ops.algebra import (run_evaluate, run_evaluate_at, run_expand, run_factor, run_identity,
                                        run_simplify, run_solve, run_solve_system)
from inkmath_solver.parse import parse_problem
from inkmath_solver.verify import verify


@pytest.mark.parametrize("latex,text", [
    ("3x-7=11", "x = 6"), ("2x^2-3x-5=0", "x = −1, x = 5/2"), (r"\frac{x+3}{x-2}=4", "x = 11/3"),
    (r"\sqrt{x+5}=x-1", "x = 4"), ("|2x-1|<5", "−2 < x < 3"), (r"\log_{2}x+\log_{2}(x-2)=3", "x = 4"),
    ("5-2x\\geq3x+20", "x ≤ −3"), ("x^3-8=0", "x = 2"), (r"\ln x=2", "x = e²"), ("3^{x+1}=27", "x = 2"),
    ("x^2+1=0", "No real solutions")])
def test_solve_answers(latex, text):
    assert run(latex, run_solve).answer.text == text


def test_extraneous_root_noted():
    assert any("−1 rejected" in n for n in run(r"\sqrt{x+5}=x-1", run_solve).notes)
    assert any("−2 rejected" in n for n in run(r"\log_{2}x+\log_{2}(x-2)=3", run_solve).notes)


def test_rational_equation_domain_note():
    assert "x ≠ 2" in run(r"\frac{x+3}{x-2}=4", run_solve).notes


def test_trig_general_and_interval():
    t = run(r"2\sin\theta-1=0", run_solve).answer.text
    assert "π/6 + 2πk" in t and "5π/6 + 2πk" in t and "on [0, 2π): π/6, 5π/6" in t


def test_trig_quadratic():
    r = run(r"2\cos^2x-\cos x-1=0", run_solve)
    assert "on [0, 2π): 0, 2π/3, 4π/3" in r.answer.text
    assert r.steps[0].startswith("Factor as a quadratic in cos(x)")


def test_system():
    assert run(r"\begin{cases}x+y=7\\2x-y=2\end{cases}", run_solve_system).answer.text == "x = 3, y = 4"


def test_nonlinear_system_two_solutions():
    r = run(r"\begin{cases}y=x^2-1\\y=x+1\end{cases}", run_solve_system)
    assert r.answer.text == "(x, y) = (−1, 0), (2, 3)"


def test_simplify_with_domain():
    r = run(r"\frac{x^2-1}{x^2+2x+1}", run_simplify)
    assert r.answer.text == "(x − 1)/(x + 1)" and "x ≠ −1" in r.notes


def test_simplify_keeps_cancelled_domain():
    r = run(r"\frac{x^3y^2}{xy^4}", run_simplify)
    assert r.answer.text == "x²/y²" and "x ≠ 0" in r.notes and "y ≠ 0" in r.notes


def test_factor():
    assert run("x^2+5x+6", run_factor).answer.text == "(x + 2)(x + 3)"


def test_expand():
    assert run("(x+1)^2", run_expand).answer.text == "x² + 2x + 1"


def test_evaluate():
    assert run(r"\sin\frac{\pi}{6}+\cos\frac{\pi}{3}", run_evaluate).answer.text == "1"


def test_evaluate_log_base10():
    assert run(r"\log1000", run_evaluate).answer.text == "3"


def test_undefined():
    assert run(r"\frac{1}{0}", run_evaluate).answer.text == "Undefined"
    assert run(r"\ln 0", run_evaluate).answer.text == "Undefined"


def test_evaluate_at():
    r = run("f(x)=x^3-3x+2", run_evaluate_at, point=parse_problem("2").expr)
    assert r.answer.text == "4" and r.value[1] == 4


def test_identity_true():
    assert run(r"\cos(2x)=\cos^2x-\sin^2x", run_identity).value is True


def test_identity_false():
    r = run(r"\sin(2x)=2\sin x", run_identity)
    assert r.value is False and "Not an identity" in r.steps[-1]


def test_steps_linear():
    assert run("3x-7=11", run_solve).steps[0] == "Collect x terms: 3x = 18"


def test_steps_count():
    for latex in ("3x-7=11", r"\sqrt{x+5}=x-1", "|2x-1|<5", r"2\cos^2x-\cos x-1=0", "2x^2-3x-5=0",
                  r"\log_{2}x+\log_{2}(x-2)=3", "3^{x+1}=27"):
        assert 1 <= len(run(latex, run_solve).steps) <= 4, latex


@pytest.mark.parametrize("latex", ["3x-7=11", "2x^2-3x-5=0", r"\sqrt{x+5}=x-1", "|2x-1|<5",
                                   r"2\sin\theta-1=0", "x^2+1=0", r"\frac{x+3}{x-2}=4"])
def test_answers_pass_verification(latex):
    p = parse_problem(latex)
    r = run_solve(p, p.symbols[0], None)
    assert verify("solve", p, r, p.symbols[0])


def test_fraction_steps_are_unambiguous():
    assert run(r"\frac{x^3y^2}{xy^4}", run_simplify).steps[0] == "Factor numerator and denominator: x³y²/(xy⁴)"


def test_difference_of_squares_step():
    assert run("4x^2-9", run_factor).steps[0] == "Difference of squares: (2x)² − 3²"
