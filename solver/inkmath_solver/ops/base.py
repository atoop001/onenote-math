from dataclasses import dataclass
from typing import Any

from sympy import Derivative, Eq, Function, Symbol

from ..schema import Answer


@dataclass
class OpResult:
    value: Any            # what the verifier checks (see the plan's value table)
    answer: Answer
    steps: list
    notes: list
    checkable: bool = True


class CannotSolve(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def ode_equation(expr, x: Symbol):
    """dy/dx = 3y with y a plain Symbol → (Eq(y(x)', 3*y(x)), y(x))."""
    ys = {d.expr for d in expr.atoms(Derivative) if isinstance(d.expr, Symbol)}
    if len(ys) != 1:
        raise CannotSolve("Couldn't tell which function to solve for")
    ysym = ys.pop()
    Y = Function(ysym.name)(x)
    e = expr.replace(lambda a: isinstance(a, Derivative) and a.expr == ysym,
                     lambda a: Y.diff(x, sum(c for _, c in a.variable_count)))
    e = e.subs(ysym, Y)
    return (e if isinstance(e, Eq) else Eq(e, 0)), Y
