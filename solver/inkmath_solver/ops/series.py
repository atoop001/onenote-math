"""Series convergence: try the standard tests in textbook order and name the one that decides (spec §5)."""
from sympy import (AccumBounds, Abs, N, Pow, S, Sum, Symbol, combsimp, integrate, latex, limit, log, oo,
                   simplify, summation)

from ..problem import Problem
from ..schema import Answer
from ..textfmt import to_text as t
from .base import CannotSolve, OpResult


def _lim(e, n):
    try:
        v = limit(e, n, oo)
    except Exception:
        return None
    return None if v.has(S.NaN) or v.has(limit) else v


def _positive_decreasing(b, n, start) -> bool:
    try:
        vals = [float(N(b.subs(n, k))) for k in range(int(start) + 5, int(start) + 40)]
    except (TypeError, ValueError):
        return False
    return all(v > 0 for v in vals) and all(a > c for a, c in zip(vals, vals[1:]))


def _alternating_part(term, n):
    """term = ±(−1)^(n+c)·b with b > 0 → b, else None."""
    if not any(isinstance(f, Pow) and f.base == -1 and f.exp.has(n) for f in term.atoms(Pow)):
        return None
    k = Symbol("k", integer=True, positive=True)   # (−1)^(2k) = 1 only for integer k
    tk = term.subs(n, k)
    for sign in ((-1) ** k, (-1) ** (k + 1)):
        b = simplify(tk * sign)
        if not any(isinstance(f, Pow) and f.base == -1 for f in b.atoms(Pow)) and \
                _positive_decreasing(b, k, 1):
            return b.subs(k, n)
    return None


def classify(term, n, start=1) -> tuple[str, bool] | None:
    """(step text that starts with the test name, converges?) or None if no test decides."""
    L = _lim(term, n)
    if L is not None and L != 0:
        shown = "does not exist" if isinstance(L, AccumBounds) else t(L)
        return f"Divergence test: lim aₙ = {shown} ≠ 0", False

    r = simplify(term.subs(n, n + 1) / term)
    if not r.has(n) and r.is_number:
        conv = bool(Abs(r) < 1)
        return f"Geometric series: r = {t(r)}, |r| {'<' if conv else '≥'} 1", conv

    c, e = term.as_coeff_exponent(n)
    if e != 0 and not c.has(n) and simplify(term - c * n**e) == 0:
        p = -e
        conv = bool(p > 1)
        return f"p-series: p = {t(p)} {'>' if conv else '≤'} 1", conv

    b = _alternating_part(term, n)
    if b is not None and _lim(b, n) == 0 and _positive_decreasing(b, n, start):
        return f"Alternating series test: bₙ = {t(b)} decreases to 0", True

    ratio = _lim(simplify(combsimp(Abs(term.subs(n, n + 1) / term))), n)
    if ratio is not None and ratio.is_number and ratio != 1 and not isinstance(ratio, AccumBounds):
        conv = bool(ratio < 1)
        return f"Ratio test: L = {t(ratio)} {'<' if conv else '>'} 1", conv

    root = _lim(Abs(term) ** (S.One / n), n)
    if root is not None and root.is_number and root != 1 and not isinstance(root, AccumBounds):
        conv = bool(root < 1)
        return f"Root test: L = {t(root)} {'<' if conv else '>'} 1", conv

    if b is None:
        p = _lim(-log(Abs(term)) / log(n), n)
        if p is not None and p.is_Rational and p > 0:
            Lc = _lim(simplify(term * n**p), n)
            if Lc is not None and Lc.is_finite and Lc.is_positive:
                conv = bool(p > 1)
                cmp = t(1 / Pow(n, p, evaluate=False))
                return (f"Limit comparison with {cmp}: L = {t(Lc)}, p = {t(p)} {'>' if conv else '≤'} 1",
                        conv)

        x = Symbol("x", positive=True)
        f = term.subs(n, x)
        lo = max(int(start), 3)
        if _positive_decreasing(term, n, lo):
            try:
                I = integrate(f, (x, lo, oo))
            except Exception:
                I = None
            if I is not None and not I.has(S.NaN) and not I.has(integrate):
                if I in (oo, -oo):
                    return f"Integral test: ∫ {t(f)} dx diverges", False
                if I.is_finite:
                    return f"Integral test: ∫ {t(f)} dx converges", True
    return None


def run_series(p: Problem, var, point=None) -> OpResult:
    s = p.expr if isinstance(p.expr, Sum) else next(iter(p.expr.atoms(Sum)), None)
    if s is None:
        raise CannotSolve("There's no series here")
    n, a, b = s.limits[0]
    if b != oo:
        total = simplify(s.doit())
        return OpResult((True, total), Answer(latex(total), f"Sum = {t(total)}", None), ["Add the terms"], [])
    term = s.function
    found = classify(term, n, a)
    if found is None:
        raise CannotSolve("Couldn't determine whether this series converges")
    step, conv = found
    steps = [step, "So the series converges" if conv else "So the series diverges"]
    total = None
    if conv:
        try:
            total = simplify(summation(term, (n, a, oo)))
        except Exception:
            total = None
        if total is not None and (total.has(Sum) or not total.is_finite):
            total = None
    if total is not None:
        if step.startswith("Geometric"):
            first = simplify(term.subs(n, a))
            steps.append(f"Sum = a/(1 − r) with a = {t(first)}")
        text, tex = f"Converges; sum = {t(total)}", rf"\text{{Converges; sum}} = {latex(total)}"
    elif conv:
        text, tex = "Converges", r"\text{Converges}"
    else:
        text, tex = "Diverges", r"\text{Diverges}"
    return OpResult((conv, total), Answer(tex, text, None), steps, [])
