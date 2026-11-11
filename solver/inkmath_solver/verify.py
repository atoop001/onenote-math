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


def _no_real_root(f, var, p=None) -> bool:
    prev = None
    for i in range(-400, 401):
        v = _num(f, {var: i / 8})
        if v is None or abs(v.imag) > TOL or (p is not None and not _sides_real(p, {var: i / 8})):
            prev = None
            continue
        if abs(v.real) < 1e-6:
            return False
        if prev is not None and (prev > 0) != (v.real > 0):
            return False
        prev = v.real
    return True


def _real(v) -> bool:
    return v is not None and abs(v.imag) <= 1e-12 * max(1.0, abs(v))


def _sides_real(p: Problem, subs) -> bool:
    """Both sides defined and real here (an 'answer' where ln of a negative appears is no answer)."""
    e = p.expr
    return _real(_num(e.lhs, subs)) and _real(_num(e.rhs, subs))


def _real_roots_of(f, var, lo=-50.0, hi=50.0, step=1 / 16):
    """Roots of a real residual found by sign changes on a grid, refined by bisection; poles are dropped."""
    fl = lambdify(var, f, "mpmath")

    def val(t):
        try:
            c = complex(fl(mpmath.mpf(t)))
        except (ZeroDivisionError, ValueError, TypeError, OverflowError):
            return None
        return c.real if abs(c.imag) <= 1e-12 * max(1.0, abs(c)) and c == c else None

    roots, t, prev = [], lo, None
    while t <= hi:
        cur = val(t)
        if cur is not None and prev is not None and prev[1] != 0 and (prev[1] > 0) != (cur > 0):
            a, b, fa = prev[0], t, prev[1]
            for _ in range(60):
                m = (a + b) / 2
                fm = val(m)
                if fm is None:
                    break
                if (fm > 0) == (fa > 0):
                    a, fa = m, fm
                else:
                    b = m
            fm = val((a + b) / 2)
            if fm is not None and abs(fm) < 1e-6:
                roots.append((a + b) / 2)
        elif cur is not None and cur == 0:
            roots.append(t)
        prev = (t, cur) if cur is not None else None
        t += step
    return roots


def verify_solve(p, r, var):
    v = r.value
    if p.kind == "inequality":
        return _verify_relation_set(p, v, var)
    f = _residual(p)
    if isinstance(v, Set) and not isinstance(v, (FiniteSet, ImageSet, Union)):
        return False
    pts = _members(v, var)
    if not pts:
        return not p.has_complex and _no_real_root(f, var, p)
    for s in pts:
        if not _close(_num(f, {var: s}), 0):
            return False
        if not p.has_complex and not getattr(s, "free_symbols", None) and \
                not (_real(_num(s)) and _sides_real(p, {var: s})):
            return False
    if p.has_complex or any(getattr(s, "free_symbols", None) for s in pts) or f.free_symbols - {var}:
        return True
    # completeness: every real root the residual has must be among the answers
    listed = [complex(_num(s)).real for s in (_wide_members(v, var) if not isinstance(v, list) else pts)]
    for root in _real_roots_of(f, var):
        if not any(abs(root - s) < 1e-5 * max(1.0, abs(s)) for s in listed):
            return False
    return True


def _wide_members(s, var):
    if isinstance(s, ImageSet):
        return [s.lamda(kv) for kv in range(-20, 21)]
    if isinstance(s, Union):
        out = []
        for a in s.args:
            out += _wide_members(a, var)
        return out
    return list(s)


def verify_solve_system(p, r, var):
    sols = r.value
    if not sols:
        return False
    for sol in sols:
        if not p.has_complex and not all(_real(_num(val)) for val in sol.values()):
            return False
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


def _quad(fl, lo, hi):
    """Quadrature split at 0 and at ±10^k, so wide or infinite ranges stay accurate."""
    cuts = [mpmath.mpf(0)] + [s * mpmath.mpf(10) ** k for k in range(0, 7) for s in (1, -1)]
    pts = [lo] + sorted(c for c in cuts if lo < c < hi) + [hi]
    return mpmath.quad(fl, pts)


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
        vals.append(abs(complex(_quad(fl, lo, hi))))
    steps = [vals[i + 1] - vals[i] for i in range(len(vals) - 1)]
    return steps[-1] > 0.3 * abs(steps[0]) and vals[-1] > 2


def verify_integrate(p, r, var):
    f, x, bounds = _integral_parts(p, var)
    v = r.value
    if bounds is None:
        xr = Symbol(x.name, real=True)
        dv, fr = Derivative(v.subs(x, xr), xr).doit(), f.subs(x, xr)
        checked = 0
        for t in _rand_points(10, 0.05, 2.8) + _rand_points(8, -2.8, -0.05, seed=4):
            g = _num(fr, {xr: t})
            if not _real(g):
                continue
            if not _close(_num(dv, {xr: t}), g, 1e-8):
                return False
            checked += 1
        return checked >= 3
    a, b = bounds
    if v in (oo, -oo):
        return _diverges(f, x, a, b)
    if _diverges(f, x, a, b):
        return False
    fl = lambdify(x, f, "mpmath")
    lo = -mpmath.inf if a == -oo else (mpmath.inf if a == oo else mpmath.mpf(N(a, 30)))
    hi = mpmath.inf if b == oo else (-mpmath.inf if b == -oo else mpmath.mpf(N(b, 30)))
    q = complex(_quad(fl, lo, hi))
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
    if not p.has_complex and not _original(p).free_symbols:
        v = _num(r.value)
        if v is not None and not _real(v):
            return False                     # spec §7: real answers only
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
    if _numeric_contradicts(s, bool(conv)):     # an independent second look at the same claim
        return False
    if total is None:
        return True
    n, a, b = s.limits[0]
    fl = lambdify(n, s.function, "mpmath")
    approx = complex(mpmath.nsum(fl, [int(a), mpmath.inf if b == oo else int(b)]))
    return _close(approx, _num(total), 1e-8)


def _numeric_contradicts(s, conv: bool) -> bool:
    """Partial sums S(10^2), S(10^3), S(10^4): a convergent series' increments shrink; a divergent one's don't."""
    n, a, _ = s.limits[0]
    fl = lambdify(n, s.function, "mpmath")
    old = mpmath.mp.dps
    mpmath.mp.dps = 15
    try:
        total, sums, k = mpmath.mpf(0), {}, int(a)
        for stop in (10**2, 10**3, 10**4):
            while k <= stop:
                total += fl(k)
                k += 1
            sums[stop] = complex(total)
        tail = abs(complex(fl(10**4)))
    except (OverflowError, ValueError, ZeroDivisionError, TypeError):
        return False                         # can't sample: no contradiction found
    finally:
        mpmath.mp.dps = old
    if not all(abs(v) < float("inf") and v == v for v in sums.values()):
        return conv
    d1, d2 = abs(sums[10**3] - sums[10**2]), abs(sums[10**4] - sums[10**3])
    if conv:
        return tail > 1e-2 or (d1 > 1e-9 and d2 >= 0.95 * d1)
    return tail < 1e-12 and d2 < 0.5 * d1 and d2 < 1e-3


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
