"""Derivatives, implicit derivatives, limits, integrals, ODEs — each names its method (spec §6.4)."""
from sympy import (Abs, AccumBounds, Add, Piecewise, log, sign, Derivative, Eq, Function, Integral, Limit, Mul, Pow, S, Symbol, apart,
                   cancel, classify_ode, diff, dsolve, factor_list, fraction, idiff, integrate, latex, limit,
                   expand, factor_terms, oo, pi, simplify, sin, sqrt, together)
from sympy.functions.elementary.trigonometric import TrigonometricFunction
from sympy.core.function import AppliedUndef
from sympy.functions.elementary.trigonometric import InverseTrigonometricFunction
from sympy.integrals.manualintegrate import (AddRule, AlternativeRule, ConstantTimesRule, CyclicPartsRule,
                                             DontKnowRule, PartsRule, RewriteRule, SqrtQuadraticRule,
                                             TrigSubstitutionRule, URule, integral_steps, manualintegrate)

from ..problem import Problem
from ..schema import Answer
from ..textfmt import decimal_of, to_text as t
from .base import CannotSolve, OpResult, ode_equation

PRIME = "′"


def _paren(e) -> str:
    s = t(e)
    return "(%s)" % s if isinstance(e, (Add, Mul)) or (isinstance(e, Pow) and e.exp != S.Half) else s


def _prime_name(name: str) -> str:
    return name.replace("'", PRIME) + PRIME


# ---------- derivatives ----------

def _rule_step(f, x) -> str:
    coeff, rest = f.as_independent(x, as_Add=False)
    factors = [g for g in Mul.make_args(rest) if g.has(x)]
    if len(factors) >= 2:
        dens = [g for g in factors if isinstance(g, Pow) and g.exp.is_negative]
        if dens:
            v = Mul(*[Pow(g.base, -g.exp) for g in dens])
            u = Mul(*[g for g in factors if g not in dens])
            return f"Quotient rule: (u′v − uv′)/v² with u = {t(u)}, v = {t(v)}"
        u, v = factors[0], Mul(*factors[1:])
        return f"Product rule: {_paren(u)}′·{_paren(v)} + {_paren(u)}·{_paren(v)}′"
    if not factors:
        return "Derivative of a constant is 0"
    g = factors[0]
    if isinstance(g, Add):
        return "Power rule, term by term" if g.is_polynomial(x) else "Differentiate term by term"
    if isinstance(g, Pow):
        if g.base == x:
            return "Power rule"
        if g.exp.is_negative and g.base.has(x) and not g.exp.has(x):
            return f"Chain rule: u = {t(g.base)}"
        if g.base.has(x):
            return f"Chain rule: u = {t(g.base)}"
        return f"Chain rule: u = {t(g.exp)}" if g.exp != x else "Exponential rule"
    if g.is_Function and g.args and g.args[0] != x:
        return f"Chain rule: u = {t(g.args[0])}"
    return "Basic derivative rules"


def _real(x):
    """The same letter, but real: d/dx|x| and ln|x| then come out as sign(x) and 1/x, not re/im pieces."""
    return Symbol(x.name, real=True)


def run_derivative(p: Problem, var, point=None) -> OpResult:
    if isinstance(p.expr, Derivative):
        f, x = p.expr.expr, p.expr.variables[0]
    else:
        f, x = p.expr, var
    xr = _real(x)
    raw = diff(f.subs(x, xr), xr)
    alt = raw.replace(sign, lambda a: a / Abs(a))          # sign(x)/|x| → x/x² → 1/x
    d = _nicest(simplify(raw), factor_terms(expand(raw)), raw, simplify(alt), alt).subs(xr, x)
    steps = [_rule_step(f, x), "Simplify"]
    if p.kind == "function_def":
        text = f"{_prime_name(p.func_name)}({t(x)}) = {t(d)}"
    else:
        text = t(d)
    return OpResult(d, Answer(latex(d), text, None), steps, [])


def run_implicit_derivative(p: Problem, var, point=None) -> OpResult:
    others = [s for s in p.symbols if s != var]
    if not others:
        raise CannotSolve("Implicit differentiation needs two variables")
    y = others[0]
    F = p.expr.lhs - p.expr.rhs
    d = simplify(idiff(F, y, var))
    text = f"d{t(y)}/d{t(var)} = {t(d)}"
    steps = [f"Implicit differentiation: differentiate both sides, treating {t(y)} as {t(y)}({t(var)})",
             f"Solve for d{t(y)}/d{t(var)}"]
    return OpResult(d, Answer(f"\\frac{{d{latex(y)}}}{{d{latex(var)}}} = {latex(d)}", text, None), steps, [])


# ---------- limits ----------

def _limit_text(v) -> str:
    if v is S.NaN:
        return "Does not exist"
    return t(v)


def _limit_steps(f, z, z0, v, sides):
    num, den = fraction(together(f))
    if sides is not None:
        lm, lp = sides
        return [f"One-sided limits differ: left → {t(lm)}, right → {t(lp)}"]
    if z0.is_infinite:
        if f.is_rational_function(z) and den.has(z):
            return ["Direct substitution gives ∞/∞", f"Divide by the highest power of {t(z)}"]
        return [f"Let {t(z)} → {t(z0)}"]
    try:
        n0, d0 = simplify(num.subs(z, z0)), simplify(den.subs(z, z0))
    except Exception:
        n0 = d0 = None
    if n0 == 0 and d0 == 0:
        c = cancel(f)
        if f.is_rational_function(z) and c.subs(z, z0).is_finite:
            return ["Direct substitution gives 0/0", f"Factor and cancel: {t(c)}"]
        return ["Direct substitution gives 0/0", f"L'Hôpital's rule: {_paren(diff(num, z))}/{_paren(diff(den, z))}"]
    if d0 == 0 and n0 not in (None, 0):
        return [f"The denominator → 0 while the numerator → {t(n0)}"]
    direct = f.subs(z, z0)
    if direct.is_finite and not direct.has(S.NaN):
        return ["Direct substitution"]
    return ["Rewrite as a quotient, then L'Hôpital's rule"]


def run_limit(p: Problem, var, point=None) -> OpResult:
    L = p.expr
    if not isinstance(L, Limit):
        raise CannotSolve("There's no limit here")
    f, z, z0 = L.args[0], L.args[1], L.args[2]
    zr = _real(z)
    f, z = f.subs(z, zr), zr
    d = str(L.args[3])
    sides = None
    if d == "+-" and not z0.is_infinite:
        lp, lm = limit(f, z, z0, "+"), limit(f, z, z0, "-")
        if lp != lm:
            v, sides = S.NaN, (lm, lp)
        else:
            v = lp
    else:
        v = limit(f, z, z0, d if not z0.is_infinite else ("-" if z0 == oo else "+"))
    if isinstance(v, AccumBounds) or v.has(Limit):
        v = S.NaN
    steps = [s.replace("sign(", "sgn(") for s in _limit_steps(f, z, z0, v, sides)]
    tex = r"\text{Does not exist}" if v is S.NaN else latex(v)
    return OpResult(v, Answer(tex, _limit_text(v), decimal_of(v) if v is not S.NaN else None), steps[:4], [])


# ---------- integrals ----------

_BASIC = ("PowerRule", "ConstantRule", "ExpRule", "SinRule", "CosRule", "ReciprocalRule", "Sec2Rule",
          "Csc2Rule", "SecTanRule", "CscCotRule")


def _pick(rule, f):
    while True:
        if isinstance(rule, ConstantTimesRule):
            rule = rule.substep
        elif isinstance(rule, AlternativeRule):
            alts = rule.alternatives
            prefer_parts = f.has(InverseTrigonometricFunction) or any(
                a.func.__name__ == "log" for a in f.atoms(Function))
            parts = [a for a in alts if isinstance(a, (PartsRule, CyclicPartsRule))]
            subs = [a for a in alts if isinstance(a, URule)]
            if prefer_parts and parts:
                rule = parts[0]
            elif subs:   # textbook choice: the simplest inner u (x², not e^(x²))
                rule = min(subs, key=lambda a: (_has_negative_power(a.u_func), a.u_func.count_ops(),
                                                len(str(a.u_func))))
            else:
                rule = alts[0]
        elif isinstance(rule, AddRule):
            rich = [s for s in rule.substeps if type(s).__name__ not in _BASIC]
            if not rich:
                return None
            rule = rich[0]
        else:
            return rule


def _has_negative_power(e) -> bool:
    return any(p.exp.is_negative for p in ([e] if isinstance(e, Pow) else []) + list(e.atoms(Pow)))


def _nicest(*candidates):
    """Shortest form, but never the phase-shift form √2·sin(x + π/4) a student wouldn't recognise."""
    def phase(e):
        return any(a.has(pi) and a.has(*e.free_symbols) for f in e.atoms(TrigonometricFunction) for a in f.args)
    ok = [c for c in candidates if c is not None and not phase(c) and not c.has(Piecewise)] or         [c for c in candidates if c is not None]
    return min(ok, key=lambda c: (c.count_ops(), len(str(c))))


def _has_dontknow(rule) -> bool:
    if isinstance(rule, DontKnowRule):
        return True
    for v in getattr(rule, "__dict__", {}).values():
        items = v if isinstance(v, list) else [v]
        for it in items:
            if hasattr(it, "integrand") and _has_dontknow(it):
                return True
    return False


def _technique(f, x) -> tuple[str, bool]:
    """(step text, manualintegrate is usable)."""
    if f.is_rational_function(x):
        num, den = fraction(together(f))
        if den.has(x) and den.as_poly(x).degree() >= 2:
            facs = [g for g, _ in factor_list(den)[1] if g.has(x)]
            if len(facs) >= 2:      # two different factors; 1/x² is just the power rule
                return f"Partial fractions: {t(apart(f, x))}", True
    rule = integral_steps(f, x)
    usable = not _has_dontknow(rule)
    r = _pick(rule, f)
    if r is None:
        return "Basic antiderivative rules", usable
    if isinstance(r, URule):
        return f"Substitution: u = {t(r.u_func)}", usable
    if isinstance(r, PartsRule):
        return f"Integration by parts: u = {t(r.u)}, dv = {t(r.dv)} d{t(x)}", usable
    if isinstance(r, CyclicPartsRule):
        first = r.parts_rules[0]
        return f"Integration by parts (twice, then solve for the integral): u = {t(first.u)}, " \
               f"dv = {t(first.dv)} d{t(x)}", usable
    if isinstance(r, TrigSubstitutionRule):
        return f"Trig substitution: {t(x)} = {t(r.func)}", usable
    if isinstance(r, SqrtQuadraticRule):
        a, b, c = r.a, r.b, r.c
        if b == 0 and a.is_positive and c.is_negative:
            th = Symbol("theta")
            return f"Trig substitution: {t(x)} = {t(sqrt(a / -c) * sin(th))}", usable
        return "Trig substitution", usable
    if isinstance(r, RewriteRule):
        return f"Rewrite: {t(r.rewritten)}", usable
    if isinstance(r, DontKnowRule):
        return "Computed directly", False
    if type(r).__name__ in _BASIC:
        return "Basic antiderivative rules", usable
    return "Standard antiderivative", usable


def _abs_logs(F, f, x):
    """Textbook ln|u|: wrap a log's argument in |…| unless it is always positive or the integrand
    itself needs it positive (∫x²ln x keeps ln x)."""
    needed = {a.args[0] for a in f.atoms(log)}

    def wrap(e):
        if not isinstance(e, log):
            return False
        u = e.args[0]
        return u.has(x) and u not in needed and u.is_positive is not True and not isinstance(u, Abs)
    return F.replace(wrap, lambda e: log(Abs(e.args[0])))


def _antiderivative(f, x):
    step, usable = _technique(f, x)
    if step.startswith("Partial fractions"):
        F = manualintegrate(apart(f, x), x)       # term by term: 2ln(x − 3) − ln(x + 2)
    else:
        F = manualintegrate(f, x) if usable else None
    if F is None or F.has(Integral):
        F = integrate(f, x)
        if not usable:
            step = "Computed directly"
    if F.has(Integral):
        raise CannotSolve("Couldn't find an antiderivative")
    if F.is_polynomial(x):
        F = F.expand()          # 2x³ − 2x, not 2x(x² − 1)
    elif F.count_ops() < 60:
        F = _nicest(F, simplify(F), factor_terms(F))
    return F, step


def run_integrate(p: Problem, var, point=None) -> OpResult:
    if p.kind == "function_def":
        f, x, bounds = p.expr, var, None
    else:
        I = p.expr if isinstance(p.expr, Integral) else next(iter(p.expr.atoms(Integral)), None)
        if I is None:
            raise CannotSolve("There's no integral here")
        f, lim = I.function, I.limits[0]
        x = lim[0]
        bounds = (lim[1], lim[2]) if len(lim) == 3 else None
    xr = _real(x)
    f, x = f.subs(x, xr), xr
    F, step = _antiderivative(f, x)
    if bounds is None:
        F = _abs_logs(F, f, x)
        if p.kind == "function_def":
            name = p.func_name[:-1].replace("'", PRIME)
            text = f"{name}({t(x)}) = {t(F)} + C"
        else:
            text = f"{t(F)} + C"
        return OpResult(F, Answer(latex(F) + " + C", text, None), [step], [])
    a, b = bounds
    v = integrate(f, (x, a, b))
    if isinstance(v, AccumBounds) or v.has(AccumBounds):    # ∫₀^∞ sin x: oscillates, no limit
        steps = [step, f"Antiderivative: {t(F)}", "The value keeps oscillating → diverges"]
        return OpResult(S.NaN, Answer(r"	ext{Diverges}", "Diverges", None), steps, [], checkable=False)
    if v.has(Integral) or v is S.NaN:
        raise CannotSolve("Couldn't evaluate this integral exactly")
    steps = [step, f"Antiderivative: {t(F)}"]
    if a.is_infinite or b.is_infinite or v.is_infinite:
        steps.append(f"Take the limit as {t(x)} approaches the bound")
    else:
        steps.append(f"Evaluate from {t(a)} to {t(b)}")
    if v in (oo, -oo):
        steps.append("The area grows without bound → diverges")
        return OpResult(v, Answer(r"\text{Diverges}", "Diverges", None), steps[:4], [])
    v = simplify(v)
    return OpResult(v, Answer(latex(v), t(v), decimal_of(v)), steps[:4], [])


# ---------- differential equations ----------

def run_ode(p: Problem, var, point=None) -> OpResult:
    eq, Y = ode_equation(p.expr, var)
    sol = dsolve(eq, Y)
    sols = sol if isinstance(sol, list) else [sol]
    hints = classify_ode(eq, Y)
    steps = (["Separate variables", "Integrate both sides"] if "separable" in hints
             else ["Solve the differential equation"])
    name = t(Symbol(Y.func.__name__))
    text = " or ".join(f"{name} = {t(s.rhs)}" for s in sols)
    tex = r" \text{ or } ".join(latex(s) for s in sols)
    return OpResult(sol, Answer(tex, text, None), steps, [])
