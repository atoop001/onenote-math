"""One-line Unicode text for answers (readable on a shared screen), LaTeX, and decimals."""
import re

from sympy import E, Integer, Pow, Rational, S, Symbol, latex
from sympy.printing.str import StrPrinter

GREEK = {"alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "theta": "θ",
         "lambda": "λ", "mu": "μ", "pi": "π", "sigma": "σ", "phi": "φ", "omega": "ω", "tau": "τ"}
_SUP = dict(zip("0123456789+-()nixyk", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁽⁾ⁿⁱˣʸᵏ"))
MINUS = "−"


class _TextPrinter(StrPrinter):
    def _print_Symbol(self, expr):
        name = expr.name
        m = re.fullmatch(r"([A-Za-z]+)(\d+)", name)     # C1 -> C₁
        if m and name not in GREEK:
            name = m.group(1) + "_" + m.group(2)
        base, sub = (name.split("_", 1) + [""])[:2] if "_" in name else (name, "")
        base = GREEK.get(base, base)
        sub = "".join("₀₁₂₃₄₅₆₇₈₉"[int(c)] if c.isdigit() else c for c in sub)
        return base + sub

    def _print_Dummy(self, expr):
        return self._print_Symbol(expr)

    def _arc(self, name, expr):
        return "%s(%s)" % (name, self._print(expr.args[0]))

    def _print_asin(self, expr):
        return self._arc("arcsin", expr)

    def _print_acos(self, expr):
        return self._arc("arccos", expr)

    def _print_atan(self, expr):
        return self._arc("arctan", expr)

    def _print_acot(self, expr):
        return self._arc("arccot", expr)

    def _print_zeta(self, expr):
        return "ζ(%s)" % self._print(expr.args[0])

    def _print_Pi(self, expr):
        return "π"

    def _print_Infinity(self, expr):
        return "∞"

    def _print_NegativeInfinity(self, expr):
        return "-∞"

    def _print_Exp1(self, expr):
        return "e"

    def _print_ImaginaryUnit(self, expr):
        return "i"

    def _print_log(self, expr):
        a = expr.args[0]
        return "ln" + self._print(a) if a.func.__name__ == "Abs" else "ln(%s)" % self._print(a)

    def _print_sign(self, expr):
        return "sgn(%s)" % self._print(expr.args[0])

    def _print_exp(self, expr):
        return "e" + self._sup(expr.args[0])

    def _print_Abs(self, expr):
        return "|%s|" % self._print(expr.args[0])

    def _wrap(self, expr):
        s = self._print(expr)
        return s if expr.is_Atom or expr.is_Function or (expr.is_Pow and expr.exp == S.Half) else "(%s)" % s

    def _sup(self, e):
        s = self._print(e)
        if (e.is_Integer or (e.is_Symbol and len(s) == 1)) and all(c in _SUP for c in s):
            return "".join(_SUP[c] for c in s)
        return "^(%s)" % s

    def _print_Pow(self, expr, rational=False):
        b, e = expr.base, expr.exp
        if e == S.Half:
            return "√" + self._wrap(b)
        if e.is_number and e.is_negative:
            return "1/" + self._wrap(Pow(b, -e)) if not (b.is_Atom and -e == 1) else "1/" + self._print(b)
        if b == E:
            return "e" + self._sup(e)
        return self._wrap(b) + self._sup(e)


_PRINTER = _TextPrinter()


def to_text(obj) -> str:
    s = _PRINTER.doprint(obj)
    s = re.sub(r"(\d)\*(?=[^\d\s])", r"\1", s)   # 5*x -> 5x, 2*√2 -> 2√2
    s = re.sub(r"\*(?=\()", "", s)                # (x + 2)*(x + 3) -> (x + 2)(x + 3)
    s = re.sub(r"\*(?=[A-Za-zα-ωπ][^A-Za-z(]|[A-Za-zα-ωπ]$)", "", s)   # π*k -> πk, x*y -> xy
    s = s.replace("*", "·")
    return s.replace("-", MINUS)


def to_latex(obj) -> str:
    return latex(obj)


def decimal_of(v) -> str | None:
    try:
        v = S(v)
    except Exception:
        return None
    if not getattr(v, "is_number", False) or v.free_symbols:
        return None
    if v.has(S.Infinity, S.NegativeInfinity, S.ComplexInfinity, S.NaN) or v.is_integer:
        return None
    if v.is_real is False:
        return None
    try:
        f = float(v.evalf(15))
    except (TypeError, ValueError):
        return None
    if abs(f - round(f)) < 1e-12:   # an integer that SymPy didn't simplify, e.g. sin(π/6) + cos(π/3)
        return None
    return "{:.6g}".format(f).replace("-", MINUS)
