import pytest

from inkmath_solver.infer import infer_operation
from inkmath_solver.parse import parse_problem
from inkmath_solver.schema import OPERATIONS


@pytest.mark.parametrize("latex,op,first", [
    ("3x-7=11", "solve", "solve"), (r"\int2xe^{x^2}dx", "integrate", "integrate"),
    (r"\cos(2x)=\cos^2x-\sin^2x", "identity", "identity"), (r"\sin(2x)=\sin x", "solve", "solve"),
    ("x^2+5x+6", None, "factor"), (r"\frac{x^2-1}{x^2+2x+1}", None, "simplify"),
    (r"\sin^2x+\cos^2x", None, "simplify"), (r"\log1000", None, "evaluate"),
    ("x^2+y^2=25", None, "implicit_derivative"), ("f(x)=x^3-3x+2", None, "derivative"),
    ("f'(x)=6x^2-2", None, "integrate"),
    (r"\begin{cases}x+y=7\\2x-y=2\end{cases}", "solve_system", "solve_system"),
    (r"\lim_{x\to0}\frac{\sin x}{x}", "limit", "limit"), (r"\frac{d}{dx}\tan(2x)", "derivative", "derivative"),
    (r"\sum_{n=1}^{\infty}\frac{1}{n^2}", "series", "series"), (r"\frac{dy}{dx}=3y", "ode", "ode"),
    ("|2x-1|<5", "solve", "solve")])
def test_infer(latex, op, first):
    got, choices = infer_operation(parse_problem(latex))
    assert got == op and choices[0] == first and set(choices) <= set(OPERATIONS)
