"""Pick the operation when the ink makes it explicit; otherwise offer choices (spec §6.2: ask, don't guess)."""
import random

from sympy import Abs, N
from sympy.functions.elementary.trigonometric import TrigonometricFunction

from .problem import Problem

_EXPLICIT = {"integral": "integrate", "derivative": "derivative", "limit": "limit", "sum": "series",
             "system": "solve_system", "ode": "ode", "inequality": "solve"}
_POLY_MENU = ["factor", "simplify", "expand", "solve", "derivative", "evaluate_at"]
_RATIONAL_MENU = ["simplify", "factor", "expand", "solve", "derivative", "evaluate_at"]
_OTHER_MENU = ["simplify", "expand", "factor", "solve", "derivative", "evaluate_at"]


def is_identity(lhs, rhs, symbols, n_points: int = 5) -> bool:
    """Numeric check: lhs - rhs is 0 at random real points where both sides are defined."""
    rng = random.Random(0)
    diff = lhs - rhs
    good = tries = 0
    while good < n_points and tries < 40:
        tries += 1
        subs = {s: rng.uniform(0.1, 3.0) for s in symbols}
        try:
            v = complex(N(diff.subs(subs), 30))
        except (TypeError, ValueError):
            continue
        if v != v or abs(v) == float("inf"):
            continue
        if abs(v) > 1e-9:
            return False
        good += 1
    return good >= 3


def infer_operation(p: Problem) -> tuple[str | None, list[str]]:
    if p.kind in _EXPLICIT:
        op = _EXPLICIT[p.kind]
        return op, [op]
    if p.kind == "equation":
        e = p.expr
        if is_identity(e.lhs, e.rhs, p.symbols):
            return "identity", ["identity", "solve"]
        if len(p.symbols) <= 1:
            return "solve", ["solve"]
        return None, ["implicit_derivative", "solve"]
    if p.kind == "function_def":
        menu = ["derivative", "evaluate_at", "solve", "simplify", "factor"]
        if p.func_name and p.func_name.endswith("'"):
            menu = ["integrate"] + menu
        return None, menu
    # plain expression: no explicit operation
    e = p.expr
    if not e.free_symbols:
        return None, ["evaluate"]
    syms = list(e.free_symbols)
    if e.is_polynomial(*syms):
        return None, list(_POLY_MENU)
    if e.is_rational_function(*syms) or e.has(TrigonometricFunction) or e.has(Abs):
        return None, list(_RATIONAL_MENU)
    return None, list(_OTHER_MENU)
