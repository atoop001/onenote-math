"""Vetted rewrites for quirks of the handwriting reader (TexTeller), applied before parsing.

Only these three, each covered by a does-not-change-meaning test (tests/test_canonical.py):
1. A bare function name with no backslash:      lnx -> \\ln x,  sinx+1 -> \\sin x+1,  log100 -> \\log 100
2. A function command glued to its argument:    \\lnx -> \\ln x,  \\sintheta -> \\sin\\theta  (\\sinh stays)
3. A brace-and-array system:                    \\left\\{\\begin{array}{l}A\\\\B\\end{array}\\right. -> cases

Text inside \\operatorname{}, \\text{}, \\mathrm{} and \\mathit{} is never touched.
"""
import re

FUNCS = sorted(["arcsin", "arccos", "arctan", "sinh", "cosh", "tanh", "sech", "csch", "coth",
                "sin", "cos", "tan", "sec", "csc", "cot", "ln", "log"], key=len, reverse=True)
_GREEK = {"alpha", "beta", "gamma", "delta", "epsilon", "theta", "vartheta", "lambda", "mu", "pi", "rho",
          "sigma", "tau", "phi", "varphi", "omega"}

_TOKEN = re.compile(
    r"(\\\\|\\(?:operatorname|text|mathrm|mathit)\{[^}]*\})"     # 1: leave alone (a \\ row break, or text)
    r"|\\([A-Za-z]+)"                                             # 2: a command (maybe glued)
    r"|(?<![A-Za-z])(" + "|".join(FUNCS) + r")(?=[A-Za-z0-9(])"   # 3: a bare function name
)
_ARRAY_SYSTEM = re.compile(r"\\left\\\{\s*\\begin\{array\}\{[^}]*\}(.*?)\\end\{array\}\s*\\right\.", re.S)


def _glued(name: str) -> str | None:
    """\\lnx -> \\ln x; None when `name` is not a function glued to one letter or a Greek letter."""
    for f in FUNCS:
        if name.startswith(f):
            rest = name[len(f):]
            if len(rest) == 1:
                return f"\\{f} {rest}"
            if rest in _GREEK:
                return f"\\{f}\\{rest}"
            return None
    return None


def _fix(m: re.Match) -> str:
    if m.group(1):
        return m.group(1)
    if m.group(2):
        return _glued(m.group(2)) or m.group(0)
    name = m.group(3)
    nxt = m.string[m.end():m.end() + 1]
    return f"\\{name}" + (" " if nxt.isalnum() else "")


def canonicalize(latex: str) -> str:
    s = _ARRAY_SYSTEM.sub(lambda m: r"\begin{cases}" + m.group(1) + r"\end{cases}", latex)
    return _TOKEN.sub(_fix, s)
