from dataclasses import dataclass

import sympy

KINDS = ("expr", "equation", "inequality", "system", "integral", "derivative", "limit", "sum", "ode",
         "function_def")


@dataclass
class Problem:
    latex: str
    kind: str
    expr: sympy.Basic              # Expr | Eq | Relational | Integral | Derivative | Limit | Sum | Tuple (system)
    equations: list                # rows of a system; [] otherwise
    symbols: list                  # preferred order: x, y, t, theta, n, then alphabetical
    func_name: str | None = None   # function_def only: "f", "f'", "g", ...
    has_complex: bool = False
    raw: sympy.Basic | None = None # same fixes, but unevaluated: keeps x^3y^2/(xy^4) as written (domain notes)
