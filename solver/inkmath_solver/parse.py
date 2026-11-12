"""LaTeX → Problem. Only meaning-preserving rewrites (M1 caveat 2); each one has a test."""
import re
import warnings

from sympy import E, Derivative, Eq, I, Integral, Limit, Sum, Symbol, Tuple, nsimplify, pi
from sympy.core.function import AppliedUndef
from sympy.core.relational import Relational

from .canonical import canonicalize
from .problem import Problem

_FUNCS = "arcsin|arccos|arctan|sinh|cosh|tanh|sin|cos|tan|sec|csc|cot|log|ln|exp"
_REWRITES = [
    (re.compile(r"\\[dt]frac(?![a-zA-Z])"), r"\\frac"),
    (re.compile(r"\\(?:displaystyle|limits|nolimits)(?![a-zA-Z])"), ""),
    (re.compile(r"\\mathrm\{\s*d\s*\}"), "d"),
    (re.compile(r"\\operatorname\{\s*(" + _FUNCS + r")\s*\}"), r"\\\1"),
    (re.compile(r"\\rightarrow(?![a-zA-Z])"), r"\\to"),
    (re.compile(r"\\(?:left|right|big|Big)\s*(?:\||\\vert(?![a-zA-Z]))"), "|"),
    (re.compile(r"\\le(?![a-zA-Z])"), r"\\leq"),
    (re.compile(r"\\ge(?![a-zA-Z])"), r"\\geq"),
    (re.compile(r"\^\s*\{\s*((?:\\prime\s*|'\s*)+)\}|\^\s*\\prime(?![a-zA-Z])"),
     lambda m: "'" * max(1, (m.group(1) or "").count("\\prime") + (m.group(1) or "").count("'"))),
    (re.compile(r"\\log(?![a-zA-Z])(?!\s*_)"), r"\\log_{10}"),
]
_ENV = re.compile(r"^\s*\\begin\{(cases|matrix|pmatrix|bmatrix|array|aligned|gathered|align\*?)\}"
                  r"(?:\{[lcr|]*\})?(.*?)\\end\{\1\}\s*$", re.S)
_PREFERRED = ["x", "y", "t", "theta", "n"]
_FUNC_DEF = re.compile(r"^[fgh]'*$")
_PRIMED = re.compile(r"([A-Za-z])('+)")


class ParseError(Exception):
    def __init__(self, message: str = "Couldn't read this expression"):
        super().__init__(message)
        self.message = message


def clean_latex(s: str) -> str:
    s = canonicalize(s)                 # reader quirks first (lnx, \sinx, array systems)
    for pat, rep in _REWRITES:
        s = pat.sub(rep, s)
    return s.strip()


def _parse_one(s: str):
    from sympy.parsing.latex import parse_latex
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return parse_latex(s, backend="antlr")
    except Exception as e:  # LaTeXParsingError and antlr internals
        raise ParseError() from e


def _rebuild(e, sum_vars: set, evaluate: bool = True):
    """Re-create the tree (evaluated or not), fixing the parser's known misreadings."""
    if isinstance(e, Symbol):
        if e.name == "e":
            return E
        if e.name == "pi":
            return pi
        m = _PRIMED.fullmatch(e.name)
        if m:                                       # y' = y  ->  dy/dx = y
            return Derivative(Symbol(m.group(1)), Symbol("x"), len(m.group(2)))
        if e.name == "i" and "i" not in sum_vars:
            return I
        return e
    if e.is_Float:
        return nsimplify(e, rational=True)       # 0.01 -> 1/100, so log(0.01) = -2 exactly
    if e.is_Atom:
        return e
    args = [_rebuild(a, sum_vars, evaluate) for a in e.args]
    if isinstance(e, AppliedUndef):
        name = e.func.__name__
        if len(name) == 1 and name not in "fgh" and len(args) == 1:
            from sympy import Mul
            return Mul(Symbol(name), args[0], evaluate=evaluate)   # x(x+1) is multiplication
        return e.func(*args)
    if isinstance(e, Relational) or not evaluate:
        try:
            return e.func(*args, evaluate=False)
        except TypeError:
            return e.func(*args)
    try:
        return e.func(*args)
    except Exception:
        return e.func(*args, evaluate=False)


def _sum_vars(e) -> set:
    return {str(lim[0]) for s in e.atoms(Sum) for lim in s.limits}


def _clean(e, evaluate: bool = True):
    return _rebuild(e, _sum_vars(e), evaluate)


def _order(symbols) -> list:
    symbols = [s for s in symbols if s.name.replace("'", "").isidentifier()]   # drops Limit's '+'/'-' dir

    def key(s):
        return (_PREFERRED.index(s.name), "") if s.name in _PREFERRED else (len(_PREFERRED), s.name)
    return sorted(symbols, key=key)


def _kind(e) -> str:
    if isinstance(e, Relational):
        if not isinstance(e, Eq):
            return "inequality"
        if e.has(Derivative) and any(isinstance(d.expr, Symbol) for d in e.atoms(Derivative)):
            return "ode"
        return "equation"
    for cls, name in ((Integral, "integral"), (Derivative, "derivative"), (Limit, "limit"), (Sum, "sum")):
        if isinstance(e, cls):
            return name
    for cls, name in ((Integral, "integral"), (Derivative, "derivative"), (Limit, "limit"), (Sum, "sum")):
        if e.has(cls):
            return name
    return "expr"


def parse_problem(latex: str) -> Problem:
    s = clean_latex(latex)
    if not s:
        raise ParseError()
    m = _ENV.match(s)
    if m:
        rows = [r.replace("&", "").strip() for r in re.split(r"\\\\", m.group(2))]
        eqs = [_clean(_parse_one(r)) for r in rows if r]
        if not eqs:
            raise ParseError()
        if len(eqs) == 1:
            e = eqs[0]
            raw = _clean(_parse_one(next(r for r in rows if r)), evaluate=False)
        else:
            expr = Tuple(*eqs)
            syms = set().union(*(q.atoms(Symbol) for q in eqs))
            return Problem(latex, "system", expr, eqs, _order(syms), None, expr.has(I))
    else:
        parsed = _parse_one(s)
        e, raw = _clean(parsed), _clean(parsed, evaluate=False)

    if isinstance(e, Eq) and isinstance(e.lhs, AppliedUndef) and _FUNC_DEF.match(e.lhs.func.__name__) \
            and all(isinstance(a, Symbol) for a in e.lhs.args):
        args = list(e.lhs.args)
        rest = [s for s in _order(e.rhs.atoms(Symbol)) if s not in args]
        return Problem(latex, "function_def", e.rhs, [], args + rest, e.lhs.func.__name__, e.rhs.has(I),
                       raw.rhs if isinstance(raw, Eq) else e.rhs)

    syms = e.atoms(Symbol) if hasattr(e, "atoms") else set()
    written = raw if raw is not None else e          # sqrt(-4) evaluates to 2i; the ink had no i
    return Problem(latex, _kind(e), e, [], _order(syms), None, written.has(I), raw)
