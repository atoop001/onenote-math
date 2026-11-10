"""Algebra and precalc: solve, systems, simplify/factor/expand, evaluate, identities. Key steps per spec §6.4."""
from sympy import (Abs, Add, ConditionSet, Dummy, EmptySet, Eq, FiniteSet, ImageSet, Interval, Mul, N, Poly, Pow,
                   Rational, S, Symbol, Union, cancel, sqrt, expand, factor, factor_list, floor, fraction, latex, log, nsimplify,
                   pi, simplify, solve, solveset, together, trigsimp, expand_trig)
from sympy.core.relational import Relational
from sympy.functions.elementary.trigonometric import TrigonometricFunction

from ..problem import Problem
from ..schema import Answer
from ..textfmt import MINUS, decimal_of, to_text as t
from .base import CannotSolve, OpResult

_REL = {"<": "<", "<=": "≤", ">": ">", ">=": "≥"}
_LATEX_REL = {"<": "<", "<=": r"\leq", ">": ">", ">=": r"\geq"}
_SUB = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


# ---------- shared helpers ----------

def _paren(e) -> str:
    s = t(e)
    return "(%s)" % s if isinstance(e, Add) else s


def _den(e) -> str:
    s = t(e)
    return "(%s)" % s if isinstance(e, (Add, Mul)) else s


def _num(e):
    try:
        v = complex(N(e, 30))
    except (TypeError, ValueError):
        return None
    return None if v != v or abs(v) == float("inf") else v


def _fmt(v: complex) -> str:
    return ("%.4g" % v.real).replace("-", MINUS)


def _undefined(v) -> bool:
    return v.has(S.ComplexInfinity, S.NaN) or v in (S.Infinity, S.NegativeInfinity)


def excluded_values(expr) -> list[str]:
    """'x ≠ 2' for every real zero of a denominator in the expression as written."""
    out = []
    for p in expr.atoms(Pow):
        if not (p.exp.is_number and p.exp.is_negative) or not p.base.free_symbols:
            continue
        try:
            facs = factor_list(p.base)[1]
        except Exception:
            facs = [(p.base, 1)]
        for fac, _ in facs:
            syms = fac.free_symbols
            if len(syms) != 1:
                continue
            s = next(iter(syms))
            roots = solveset(fac, s, S.Reals)
            if isinstance(roots, FiniteSet):
                for r in sorted(roots, key=lambda z: N(z)):
                    note = f"{t(s)} ≠ {t(r)}"
                    if note not in out:
                        out.append(note)
    return out


def _sort_key(z):
    if z.free_symbols:                      # symbolic answer, e.g. y = 3 − x
        return (1, 0.0, 0.0, str(z))
    re_, im_ = N(z).as_real_imag()
    return (0, float(re_), float(im_), "")


def _sorted(sols):
    return sorted(sols, key=_sort_key)


def _solutions_answer(var, sols) -> Answer:
    if not sols:
        return Answer(r"\text{No real solutions}", "No real solutions", None)
    text = ", ".join(f"{t(var)} = {t(s)}" for s in sols)
    tex = ", ".join(f"{latex(var)} = {latex(s)}" for s in sols)
    decs = [decimal_of(s) for s in sols]
    dec = ", ".join(d or t(s) for d, s in zip(decs, sols)) if any(decs) else None
    return Answer(tex, text, dec)


def _set_text(s, v) -> tuple[str, str]:
    vt, vl = t(v), latex(v)
    if s is S.EmptySet:
        return "No real solutions", r"\text{No real solutions}"
    if s == S.Reals:
        return "All real numbers", r"\text{All real numbers}"
    if isinstance(s, Interval):
        a, b = s.start, s.end
        lo, hi = ("<" if s.left_open else "≤"), ("<" if s.right_open else "≤")
        llo, lhi = ("<" if s.left_open else r"\leq"), ("<" if s.right_open else r"\leq")
        if a == -S.Infinity:
            return f"{vt} {hi} {t(b)}", f"{vl} {lhi} {latex(b)}"
        if b == S.Infinity:
            ge = ">" if s.left_open else "≥"
            return f"{vt} {ge} {t(a)}", f"{vl} {'>' if s.left_open else chr(92) + 'geq'} {latex(a)}"
        return f"{t(a)} {lo} {vt} {hi} {t(b)}", f"{latex(a)} {llo} {vl} {lhi} {latex(b)}"
    if isinstance(s, Union):
        parts = [_set_text(a, v) for a in s.args]
        return " or ".join(p[0] for p in parts), r" \text{ or } ".join(p[1] for p in parts)
    if isinstance(s, FiniteSet):
        a = _solutions_answer(v, _sorted(s))
        return a.text, a.latex
    return t(s), latex(s)


# ---------- solve: step templates ----------

def _log_parts(lhs, var):
    """lhs = Σ log_b(u_i) with one base b → (b, Π u_i); else None."""
    base, args = None, []
    for term in Add.make_args(lhs):
        b, u = S.Exp1, None
        for fac in Mul.make_args(term):
            if isinstance(fac, log) and fac.has(var):
                u = fac.args[0]
            elif isinstance(fac, Pow) and fac.exp == -1 and isinstance(fac.base, log) and not fac.base.has(var):
                b = fac.base.args[0]
            else:
                return None
        if u is None or (base is not None and b != base):
            return None
        base = b
        args.append(u)
    return (base, Mul(*args)) if args else None


def _log_name(b) -> str:
    return "ln" if b == S.Exp1 else "log" + t(b).translate(_SUB)


def _equation_steps(eq, f, var):
    """(steps, candidate roots before checking)."""
    v = t(var)
    lhs, rhs = eq.lhs, eq.rhs
    if f.is_polynomial(var):
        poly = Poly(f, var)
        deg = poly.degree()
        if deg == 1:
            a, b = poly.all_coeffs()
            steps = [f"Collect {v} terms: {t(a * var)} = {t(-b)}"]
            return steps + ([f"Divide by {t(a)}"] if a != 1 else []), []
        facs = [g for g, _ in factor_list(f)[1]]
        if len(facs) > 1 or (facs and Poly(facs[0], var).degree() < deg) or \
                (len(facs) == 1 and factor_list(f)[1][0][1] > 1):
            return [f"Factor: {t(factor(f))} = 0", "Set each factor to 0"], []
        if deg == 2:
            a, b, c = poly.all_coeffs()
            steps = [f"Quadratic formula: a = {t(a)}, b = {t(b)}, c = {t(c)}"]
            disc = b**2 - 4*a*c
            if disc.is_negative:
                steps.append(f"b² − 4ac = {t(disc)} < 0")
            return steps, []
        return [f"Solve for {v}"], []
    num, den = fraction(together(f))
    if den.has(var):
        return [f"Multiply both sides by {_paren(den)}", f"Solve: {t(expand(num))} = 0"], \
            list(solveset(num, var, S.Reals)) if isinstance(solveset(num, var, S.Reals), FiniteSet) else []
    roots = [p for p in f.atoms(Pow) if p.exp == S.Half and p.base.has(var)]
    if roots:
        for side, other in ((lhs, rhs), (rhs, lhs)):
            if isinstance(side, Pow) and side.exp == S.Half:
                A, B = side.base, other
                cands = solveset(A - B**2, var, S.Reals)
                return [f"Square both sides: {t(A)} = {t(Pow(B, 2, evaluate=False))}",
                        "Solve, then check each root"], list(cands) if isinstance(cands, FiniteSet) else []
        return ["Isolate the root and square both sides", "Solve, then check each root"], []
    if f.has(Abs):
        return ["Split into two cases: the inside is positive or negative", f"Solve each case for {v}"], []
    exp_pows = [p for p in f.atoms(Pow) if p.exp.has(var) and not p.base.has(var)]
    if exp_pows or f.has(S.Exp1):
        if isinstance(lhs, Pow) and lhs.base.is_number and lhs.base != S.Exp1 and rhs.is_number:
            m = nsimplify(log(rhs) / log(lhs.base))
            if m.is_Rational:
                return [f"Rewrite with the same base: {t(lhs)} = {t(Pow(lhs.base, m, evaluate=False))}",
                        f"Set exponents equal: {t(lhs.exp)} = {t(m)}"], []
        return ["Take ln of both sides", f"Solve for {v}"], []
    if f.has(log):
        parts = _log_parts(lhs, var)
        if parts and not rhs.has(var):
            b, u = parts
            power = Pow(b, rhs, evaluate=False)
            steps = []
            if len(Add.make_args(lhs)) > 1:
                steps.append(f"Combine logs: {_log_name(b)}({t(u)}) = {t(rhs)}")
            steps.append(f"Rewrite in exponential form: {t(u)} = {t(power)}")
            cands = solveset(u - b**rhs, var, S.Reals)
            return steps, list(cands) if isinstance(cands, FiniteSet) else []
        return [f"Solve for {v}"], []
    return [f"Solve for {v}"], []


def _trig_steps(f, var):
    fns = list(f.atoms(TrigonometricFunction))
    if len(fns) == 1:
        T = fns[0]
        u = Dummy("u")
        g = f.subs(T, u)
        if not g.has(var) and g.is_polynomial(u):
            deg = Poly(g, u).degree()
            vals = sorted(solveset(g, u, S.Reals), key=lambda z: N(z)) if deg else []
            if deg == 2:
                return [f"Factor as a quadratic in {t(T)}: {t(factor(g).subs(u, T))} = 0",
                        f"Solve: {t(T)} = " + ", ".join(t(z) for z in vals)]
            if deg == 1:
                return [f"Isolate {t(T)}: {t(T)} = {t(vals[0])}"]
    return [f"Solve for {t(var)}"]


def _imageset_text(img, var, k):
    lam = img.lamda
    kd = lam.variables[0]
    e = lam.expr
    c = e.subs(kd, 0)
    m = abs(simplify((e - c) / kd))
    c = simplify(c - floor(c / m) * m)
    term = t(m * k)
    return c, (f"{t(var)} = {term}" if c == 0 else f"{t(var)} = {t(c)} + {term}")


def _solve_trig(f, var, notes):
    gen = solveset(f, var, S.Reals)
    if gen is S.EmptySet:
        return OpResult([], Answer(r"\text{No real solutions}", "No real solutions", None), _trig_steps(f, var), notes)
    imgs = list(gen.args) if isinstance(gen, Union) else [gen]
    if not all(isinstance(i, ImageSet) for i in imgs):
        raise CannotSolve("Couldn't solve this exactly")
    k = Symbol("k")
    parts = sorted((_imageset_text(i, var, k) for i in imgs), key=lambda cp: N(cp[0]))
    inside = set()
    for img in imgs:   # list [0, 2π) members from the general solution (solveset on an interval drops roots)
        for kv in range(-12, 13):
            z = simplify(img.lamda(kv))
            if 0 <= N(z) < N(2 * pi):
                inside.add(z)
    in_list = ", ".join(t(z) for z in sorted(inside, key=lambda z: N(z))) or "none"
    text = ", ".join(p for _, p in parts) + f" (k any integer); on [0, 2π): {in_list}"
    tex = latex(gen) + r",\ k \in \mathbb{Z}"
    return OpResult(gen, Answer(tex, text, None), _trig_steps(f, var), notes)


def _solve_inequality(p, var):
    rel = p.expr
    sol = solveset(rel, var, S.Reals)
    if isinstance(sol, ConditionSet):
        raise CannotSolve("Couldn't solve this inequality exactly")
    op = _REL.get(rel.rel_op, rel.rel_op)
    f = rel.lhs - rel.rhs
    if isinstance(rel.lhs, Abs) and not rel.rhs.has(var):
        A, c = rel.lhs.args[0], rel.rhs
        if rel.rel_op in ("<", "<="):
            steps = [f"Split: {t(-c)} {op} {t(A)} {op} {t(c)}", f"Solve for {t(var)}"]
        else:
            steps = [f"Split: {t(A)} {'<' if op == '>' else '≤'} {t(-c)} or {t(A)} {op} {t(c)}",
                     "Solve each part"]
    elif f.is_polynomial(var) and Poly(f, var).degree() == 1:
        a, b = Poly(f, var).all_coeffs()
        steps = [f"Collect {t(var)} terms: {t(a * var)} {op} {t(-b)}"]
        if a.is_negative:
            steps.append(f"Divide by {t(a)} (flip the sign)")
        elif a != 1:
            steps.append(f"Divide by {t(a)}")
    else:
        steps = [f"Find where {t(f)} changes sign", f"Solve for {t(var)}"]
    text, tex = _set_text(sol, var)
    return OpResult(sol, Answer(tex, text, None), steps, excluded_values(p.raw if p.raw is not None else p.expr))


# ---------- public operations ----------

def _try_solve(f, var):
    try:
        return list(solve(f, var))
    except Exception:
        return []


def _satisfies(f, var, c, allow_complex: bool) -> bool:
    if not allow_complex and c.is_real is False:
        return False
    v = _num(f.subs(var, c))
    return v is not None and abs(v) < 1e-9


def run_solve(p: Problem, var, point=None) -> OpResult:
    if p.kind == "inequality":
        return _solve_inequality(p, var)
    if p.kind == "equation":
        eq = p.expr
    elif p.kind in ("expr", "function_def"):
        eq = Eq(p.expr, 0)
    else:
        raise CannotSolve("There's no equation to solve here")
    f = eq.lhs - eq.rhs
    notes = excluded_values(p.raw if p.raw is not None else p.expr)
    if any(fn.has(var) for fn in f.atoms(TrigonometricFunction)):
        return _solve_trig(f, var, notes)
    domain = S.Complexes if p.has_complex else S.Reals
    sols = solveset(f, var, domain)
    if sols == domain:
        return OpResult(sols, Answer(r"\text{All real numbers}", "All real numbers", None), ["Both sides are equal"],
                        notes, checkable=False)
    steps, cands = _equation_steps(eq, f, var)
    if not isinstance(sols, FiniteSet) and sols is not S.EmptySet:
        # solveset gave up (e.g. sums of logs): keep the candidates that really satisfy the equation
        pool = cands or _try_solve(f, var)
        if not pool:
            raise CannotSolve("Couldn't solve this exactly")
        sols = [c for c in pool if _satisfies(f, var, c, p.has_complex)]
    sols = _sorted(sols)
    for c in cands:
        if c.is_real and c not in sols:
            notes.append(f"{t(var)} = {t(c)} rejected (doesn't check)")
    return OpResult(sols, _solutions_answer(var, sols), steps[:4], notes)


def run_solve_system(p: Problem, var=None, point=None) -> OpResult:
    syms = p.symbols
    sols = solve(p.equations, syms, dict=True)
    if not p.has_complex:
        sols = [s for s in sols if all(v.is_real is not False for v in s.values())]
    sols = sorted(sols, key=lambda d: [float(N(d.get(s, 0)).as_real_imag()[0]) for s in syms])
    steps = []
    for row in p.equations:
        if isinstance(row.lhs, Symbol) and not row.rhs.has(row.lhs):
            s = row.lhs
            steps.append(f"Substitute {t(s)} = {t(row.rhs)}")
            other = next((r for r in p.equations if r is not row), None)
            if other is not None:
                sub = other.subs(s, row.rhs)
                if isinstance(sub, Eq):
                    steps.append(f"Solve: {t(sub.lhs)} = {t(sub.rhs)}")
            steps.append(f"Back-substitute to find {t(s)}")
            break
    else:
        steps = [f"Eliminate {t(syms[-1])}", f"Back-substitute to find {t(syms[-1])}"]
    if not sols:
        return OpResult([], Answer(r"\text{No real solutions}", "No real solutions", None), steps, [])
    if any(v.free_symbols for s in sols for v in s.values()):
        raise CannotSolve("This system has infinitely many solutions")
    if len(sols) == 1:
        s = sols[0]
        text = ", ".join(f"{t(v)} = {t(s[v])}" for v in syms if v in s)
        tex = ", ".join(f"{latex(v)} = {latex(s[v])}" for v in syms if v in s)
    else:
        names = "(" + ", ".join(t(v) for v in syms) + ")"
        text = f"{names} = " + ", ".join("(" + ", ".join(t(s[v]) for v in syms) + ")" for s in sols)
        tex = text
    return OpResult(sols, Answer(tex, text, None), steps, [])


def _original(p: Problem):
    return p.raw if p.raw is not None else p.expr


def run_simplify(p: Problem, var=None, point=None) -> OpResult:
    orig = _original(p)
    result = simplify(p.expr)
    if result.is_rational_function():
        result = factor(cancel(result))
        if result.is_Mul and len(fraction(result)[1].free_symbols) == 0:
            result = cancel(result)
    num, den = fraction(orig)
    if den.free_symbols:
        steps = [f"Factor numerator and denominator: {_paren(factor(num))}/{_den(factor(den))}",
                 "Cancel common factors"]
    elif orig.has(TrigonometricFunction):
        steps = ["Apply trig identities"]
    else:
        steps = ["Simplify"]
    return OpResult(result, Answer(latex(result), t(result), decimal_of(result)), steps, excluded_values(orig))


def run_factor(p: Problem, var=None, point=None) -> OpResult:
    e = p.expr
    result = factor(e)
    steps = ["Factor"]
    syms = list(e.free_symbols)
    if len(syms) == 1 and e.is_polynomial(syms[0]) and Poly(e, syms[0]).degree() == 2:
        a, b, c = Poly(e, syms[0]).all_coeffs()
        roots = [r for r in solveset(e, syms[0], S.Reals)] if a == 1 else []
        if a == 1 and len(roots) == 2 and all(r.is_integer for r in roots):
            r1, r2 = sorted(-r for r in roots)
            steps = [f"Find two numbers that multiply to {t(c)} and add to {t(b)}: {t(r1)}, {t(r2)}"]
        elif b == 0 and c.is_negative:
            steps = [f"Difference of squares: {t(Pow(sqrt(a) * syms[0], 2, evaluate=False))} − "
                     f"{t(Pow(sqrt(-c), 2, evaluate=False))}"]
    elif len(Add.make_args(e)) == 2 and any(c.could_extract_minus_sign() for c in Add.make_args(e)):
        steps = ["Difference of squares"]
    return OpResult(result, Answer(latex(result), t(result), None), steps, [])


def run_expand(p: Problem, var=None, point=None) -> OpResult:
    result = expand(p.expr)
    return OpResult(result, Answer(latex(result), t(result), None), ["Multiply out"], [])


def run_evaluate(p: Problem, var=None, point=None) -> OpResult:
    orig = _original(p)
    v = simplify(p.expr)
    if _undefined(v):
        return OpResult(S.ComplexInfinity, Answer(r"\text{Undefined}", "Undefined", None),
                        ["Division by zero or a value outside the domain"], [])
    exact = []
    for a in sorted(orig.atoms(TrigonometricFunction, log), key=str):
        if not a.free_symbols:
            av = simplify(a.func(*a.args))
            if av != a:
                exact.append(f"{t(a)} = {t(av)}")
    steps = ["Exact values: " + ", ".join(exact[:3])] if exact else ["Evaluate"]
    return OpResult(v, Answer(latex(v), t(v), decimal_of(v)), steps, [])


def run_evaluate_at(p: Problem, var, point=None) -> OpResult:
    if point is None:
        raise CannotSolve("Which value should I use?")
    f = p.expr.rhs if isinstance(p.expr, Eq) else p.expr
    result = simplify(f.subs(var, point))
    if _undefined(result):
        return OpResult((point, result), Answer(r"\text{Undefined}", "Undefined", None),
                        [f"Substitute {t(var)} = {t(point)}"], [], checkable=False)
    return OpResult((point, result), Answer(latex(result), t(result), decimal_of(result)),
                    [f"Substitute {t(var)} = {t(point)}"], [])


def run_identity(p: Problem, var, point=None) -> OpResult:
    e = p.expr
    lhs, rhs = e.lhs, e.rhs
    d = simplify(lhs - rhs)
    if d != 0:
        d = trigsimp(expand_trig(expand(d)))
    if d == 0:
        return OpResult(True, Answer(r"\text{Identity holds}", "Identity holds", None),
                        ["Simplify both sides", "Both sides are equal → identity holds"], [])
    for tv in (1, S.Half, 2, Rational(3, 10)):
        lv, rv = _num(lhs.subs(var, tv)), _num(rhs.subs(var, tv))
        if lv is not None and rv is not None and abs(lv - rv) > 1e-6:
            return OpResult(False, Answer(r"\text{Not an identity}", "Not an identity", None),
                            ["Simplify both sides",
                             f"Not an identity: at {t(var)} = {t(tv)}, left = {_fmt(lv)}, right = {_fmt(rv)}"], [])
    return OpResult(True, Answer(r"\text{Identity holds}", "Identity holds", None),
                    ["Compare both sides", "Both sides are equal → identity holds"], [])
