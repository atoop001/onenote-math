"""Independent checks (spec §6.5). Each one checks a different way from how the answer was found.

Every verifier returns True only when its check passes; any exception means False ("⚠ unverified").
"""
import random

import mpmath
from sympy import (Derivative, Eq, FiniteSet, ImageSet, Integral, Interval, Limit, N, S, Set, Sum, Symbol,
                   Union, checkodesol, lambdify, oo)

from .ops.base import OpResult, ode_equation
from .problem import Problem

TOL = 1e-9
mpmath.mp.dps = 30


def _num(expr, subs=None):
    """Complex value of expr at subs, or None if undefined/non-finite."""
    try:
        v = complex(N(expr.subs(subs) if subs else expr, 30))
    except (TypeError, ValueError, ZeroDivisionError, AttributeError):
        return None
    if v != v or abs(v) == float("inf"):
        return None
    return v


def _close(a, b, rel=TOL):
    return a is not None and b is not None and abs(a - b) <= rel * max(1.0, abs(a), abs(b))


def _rand_points(n, lo=0.2, hi=2.8, seed=1):
    rng = random.Random(seed)
    return [rng.uniform(lo, hi) for _ in range(n)]


def _residual(p: Problem):
    e = p.expr
    return e.lhs - e.rhs


# ---------- solve ----------

def _members(s, var):
    """Finite sample of points from a solution set (k = -1, 0, 1 for ImageSets)."""
    if isinstance(s, (list, tuple)):
        return list(s)
    if isinstance(s, FiniteSet):
        return list(s)
    if isinstance(s, ImageSet):
        lam = s.lamda
        return [lam(kv) for kv in (-1, 0, 1)]
    if isinstance(s, Union):
        out = []
        for a in s.args:
            out += _members(a, var)
        return out
    raise TypeError(f"can't sample {type(s).__name__}")


def _verify_relation_set(p: Problem, value: Set, var) -> bool:
    rel = p.expr
    pts = [x / 2 for x in range(-40, 41)] + [b + d for b in value.boundary if b.is_finite
                                              for d in (-1e-3, 1e-3)]
    checked = 0
    for t in pts:
        try:
            holds = bool(rel.subs(var, t))
        except TypeError:
            continue  # undefined here
        if value.contains(t) not in (S.true, S.false):
            continue
        if holds != bool(value.contains(t)):
            return False
        checked += 1
    return checked >= 20


def _no_real_root(f, var) -> bool:
    prev = None
    for i in range(-400, 401):
        v = _num(f, {var: i / 8})
        if v is None or abs(v.imag) > TOL:
            prev = None
            continue
        if abs(v.real) < 1e-6:
            return False
        if prev is not None and (prev > 0) != (v.real > 0):
            return False
        prev = v.real
    return True


def verify_solve(p, r, var):
    v = r.value
    if p.kind == "inequality":
        return _verify_relation_set(p, v, var)
    f = _residual(p)
    if isinstance(v, Set) and not isinstance(v, (FiniteSet, ImageSet, Union)):
        return False
    pts = _members(v, var)
    if not pts:
        return not p.has_complex and _no_real_root(f, var)
    for s in pts:
        if not _close(_num(f, {var: s}), 0):
            return False
    return True


def verify_solve_system(p, r, var):
    sols = r.value
    if not sols:
        return False
    for sol in sols:
        for eq in p.equations:
            if not _close(_num(eq.lhs - eq.rhs, sol), 0):
                return False
    return True


# ---------- calculus ----------

def _integral_parts(p: Problem, var):
    if p.kind == "function_def":
        return p.expr, var, None
    I = p.expr if isinstance(p.expr, Integral) else next(iter(p.expr.atoms(Integral)))
    f = I.function
    lim = I.limits[0]
    x = lim[0]
    return f, x, (lim[1], lim[2]) if len(lim) == 3 else None


def _truncated(fl, a, b, a_cut, b_cut):
    return mpmath.quad(fl, [a_cut, b_cut])


def _diverges(f, x, a, b) -> bool:
    """Push finite singular endpoints/infinite bounds outward; a divergent integral keeps growing."""
    fl = lambdify(x, f, "mpmath")
    a_sing = a.is_infinite or _num(f, {x: a}) is None
    b_sing = b.is_infinite or _num(f, {x: b}) is None
    if not (a_sing or b_sing):
        return False
    vals = []
    for kexp in (1, 2, 3, 4, 5):
        eps, big = mpmath.mpf(10) ** -kexp, mpmath.mpf(10) ** kexp
        lo = (-big if a.is_infinite else mpmath.mpf(N(a, 30)) + (eps if a_sing else 0))
        hi = (big if b.is_infinite else mpmath.mpf(N(b, 30)) - (eps if b_sing else 0))
        vals.append(abs(complex(mpmath.quad(fl, [lo, hi]))))
    steps = [vals[i + 1] - vals[i] for i in range(len(vals) - 1)]
    return steps[-1] > 0.3 * abs(steps[0]) and vals[-1] > 2


def verify_integrate(p, r, var):
    f, x, bounds = _integral_parts(p, var)
    v = r.value
    if bounds is None:
        for t in _rand_points(5):
            d = _num(Derivative(v, x).doit(), {x: t})
            g = _num(f, {x: t})
            if g is None:
                continue
            if not _close(d, g, 1e-8):
                return False
        return True
    a, b = bounds
    if v in (oo, -oo):
        return _diverges(f, x, a, b)
    if _diverges(f, x, a, b):
        return False
    fl = lambdify(x, f, "mpmath")
    lo = -mpmath.inf if a == -oo else (mpmath.inf if a == oo else mpmath.mpf(N(a, 30)))
    hi = mpmath.inf if b == oo else (-mpmath.inf if b == -oo else mpmath.mpf(N(b, 30)))
    q = complex(mpmath.quad(fl, [lo, hi]))
    return _close(q, _num(v), 1e-8)


def verify_derivative(p, r, var):
    f = p.expr.expr if isinstance(p.expr, Derivative) else p.expr
    if isinstance(p.expr, Derivative):
        var = p.expr.variables[0]
    h = mpmath.mpf("1e-8")
    fl = lambdify(var, f, "mpmath")
    checked = 0
    for t in _rand_points(3, 0.3, 2.5, seed=2):
        try:
            num = (fl(t + h) - fl(t - h)) / (2 * h)
        except (ZeroDivisionError, ValueError):
            continue
        if not _close(complex(num), _num(r.value, {var: t}), 1e-5):
            return False
        checked += 1
    return checked >= 2


def verify_implicit_derivative(p, r, var):
    F = _residual(p)
    others = [s for s in p.symbols if s != var]
    yv = others[0]
    Fx, Fy = F.diff(var), F.diff(yv)
    Fl = lambdify((var, yv), F, "mpmath")
    checked = 0
    for x0 in (0.5, 1.3, 2.1):
        for y0 in (1, -1, 3, 0.5):
            try:
                ys = mpmath.findroot(lambda t: Fl(x0, t), y0)
            except (ValueError, ZeroDivisionError):
                continue
            pt = {var: x0, yv: complex(ys).real}
            fy = _num(Fy, pt)
            if fy is None or abs(fy) < 1e-6:
                continue
            want = -_num(Fx, pt) / fy
            if not _close(_num(r.value, pt), want, 1e-7):
                return False
            checked += 1
            break
    return checked >= 2


def verify_limit(p, r, var):
    L = p.expr
    f, z, z0 = L.args[0], L.args[1], L.args[2]
    d = str(L.args[3])
    fl = lambdify(z, f, "mpmath")
    mpmath.mp.dps = 50

    def seq(sign):
        out = []
        for kexp in range(3, 8):
            t = (mpmath.mpf(10) ** kexp) * (1 if z0 == oo else -1) if z0.is_infinite \
                else mpmath.mpf(N(z0, 50)) + sign * mpmath.mpf(10) ** -kexp
            try:
                out.append(complex(fl(t)))
            except (ZeroDivisionError, ValueError):
                return None
        return out

    try:
        sides = [seq(1)] if z0.is_infinite else [seq(s) for s in ((1,) if d == "+" else (-1,) if d == "-" else (1, -1))]
    finally:
        mpmath.mp.dps = 30
    if any(s is None for s in sides):
        return False
    v = r.value

    def goes_to(s, target):
        if target == oo:
            return s[-1].real > 1e5 and abs(s[-1]) > abs(s[-2]) > abs(s[0])
        if target == -oo:
            return s[-1].real < -1e5 and abs(s[-1]) > abs(s[-2]) > abs(s[0])
        tv = _num(target)
        return tv is not None and abs(s[-1] - tv) <= 1e-3 * max(1, abs(tv))

    if v is S.NaN:
        for inf in (oo, -oo):
            if all(goes_to(s, inf) for s in sides):
                return False          # it has a limit: ±∞
        if len(sides) == 2:
            l, rr = sides
            return not (abs(l[-1] - rr[-1]) <= 1e-3 * max(1, abs(l[-1]))) or not all(
                abs(s[-1] - s[-2]) < 1e-3 * max(1, abs(s[-1])) for s in sides)
        s = sides[0]
        return abs(s[-1] - s[-2]) > 1e-3 * max(1, abs(s[-1]))
    return all(goes_to(s, v) for s in sides)


# ---------- algebra ----------

def _original(p: Problem):
    return p.raw if p.raw is not None and not isinstance(p.raw, Eq) else p.expr


def _same_function(a, b, symbols) -> bool:
    if not symbols:
        va, vb = _num(a), _num(b)
        if va is None and vb is None:
            return True
        return _close(va, vb)
    checked = 0
    for i, t in enumerate(_rand_points(5, seed=3)):
        subs = {s: t + 0.37 * j for j, s in enumerate(symbols)}
        va, vb = _num(a, subs), _num(b, subs)
        if va is None:
            continue
        if not _close(va, vb):
            return False
        checked += 1
    return checked >= 3


def verify_same(p, r, var):
    return _same_function(_original(p), r.value, sorted(_original(p).free_symbols, key=str))


def verify_evaluate_at(p, r, var):
    point, result = r.value
    return _close(_num(p.expr, {var: point}), _num(result))


def verify_identity(p, r, var):
    f = _residual(p)
    syms = sorted(f.free_symbols, key=str)
    rng = random.Random(7)
    zero = good = 0
    for _ in range(30):
        subs = {s: rng.uniform(-3, 3) for s in syms}
        v = _num(f, subs)
        if v is None:
            continue
        good += 1
        zero += abs(v) <= TOL
        if good >= 6:
            break
    if good < 3:
        return False
    holds = zero == good          # every sampled point agrees
    return holds if r.value else not holds


# ---------- series, ode ----------

def verify_series(p, r, var):
    conv, total = r.value
    s = p.expr if isinstance(p.expr, Sum) else next(iter(p.expr.atoms(Sum)))
    truth = s.is_convergent()
    if truth not in (S.true, S.false, True, False):
        return False
    if bool(truth) is not bool(conv):
        return False
    if total is None:
        return True
    n, a, b = s.limits[0]
    fl = lambdify(n, s.function, "mpmath")
    approx = complex(mpmath.nsum(fl, [int(a), mpmath.inf if b == oo else int(b)]))
    return _close(approx, _num(total), 1e-8)


def verify_ode(p, r, var):
    eq, Y = ode_equation(p.expr, var)
    sols = r.value if isinstance(r.value, (list, tuple)) else [r.value]
    return bool(sols) and all(checkodesol(eq, s, Y)[0] is True for s in sols)


VERIFIERS = {
    "solve": verify_solve, "solve_system": verify_solve_system, "integrate": verify_integrate,
    "derivative": verify_derivative, "implicit_derivative": verify_implicit_derivative,
    "limit": verify_limit, "simplify": verify_same, "factor": verify_same, "expand": verify_same,
    "evaluate": verify_same, "evaluate_at": verify_evaluate_at, "identity": verify_identity,
    "series": verify_series, "ode": verify_ode,
}


def verify(op: str, p: Problem, r: OpResult, variable: Symbol) -> bool:
    fn = VERIFIERS.get(op)
    if fn is None:
        return False
    try:
        return bool(fn(p, r, variable))
    except Exception:
        return False
