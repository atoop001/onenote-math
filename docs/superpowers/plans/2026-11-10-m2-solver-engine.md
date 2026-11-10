# M2 Solver Engine: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An offline Python solver that takes confirmed LaTeX, either asks which operation to run or solves it, gives key steps, an exact answer and a decimal, and checks the answer a second way. It runs behind a JSON-lines process with a hard 20 s timeout.

**Architecture:** The package `solver/inkmath_solver` is a pipeline: `parse` (LaTeX to a `Problem`), then `infer` (pick the operation or ask), then `ops/*` (SymPy work plus key steps, giving an `OpResult`), then `verify` (an independent check), then `engine` (assembles the `Response`). `server` reads requests on stdin and writes responses on stdout. Each request runs in a warm child process that is killed and respawned on timeout or crash, so a slow solve never blocks the caller. M3's C# add-in launches the server; M5's confirm panel uses `needs_operation` and `choices`.

**Tech Stack:** Python 3.10 (`C:\Python310`), SymPy 1.14.0, mpmath (comes with SymPy), antlr4-python3-runtime 4.11.1 (SymPy's LaTeX parser backend), pytest.

**Spec:** `docs/superpowers/specs/2026-11-09-onenote-ink-math-design.md` (§3, §4, §5, §6.4, §6.5, §7 answer conventions). Roadmap: `docs/superpowers/plans/2026-11-09-roadmap.md`. M1 results (canonicalization caveat): `docs/superpowers/spike/2026-11-m1-accuracy-results.md`.

## Global Constraints

- **Offline.** No network calls, ever.
- **Pure-Python dependencies only** (`sympy==1.14.0`, `antlr4-python3-runtime==4.11.1`, `mpmath`), so M6 can ship an embedded Python on the Surface ("no system Python required").
- **Hard timeout 20 s per request.** On timeout the response message is exactly `This one's taking too long`. Never hang the caller.
- **Key steps:** 3–5 lines in total, made of method, main intermediate result, and answer. The `steps` list holds 1–4 lines and the answer is separate.
- **Answers:** exact form plus a decimal where meaningful. The decimal has 6 significant digits and is shown when the value is a number that is not an integer.
- **Conventions (spec §7):** `\log` means base 10 and `\ln` means natural log. Real solutions only, unless `i` appears in the problem. Trig equations give the general solution plus the solutions on [0, 2π). Domain restrictions go in words in `notes` (e.g. `x ≠ 2`). Indefinite integrals end in `+ C`. `e` is Euler's number. `i` is the imaginary unit unless it is a summation index.
- **Never confidently wrong:** every `ok` answer runs its verifier. A failed check, an exception, or no applicable check gives `verified: false` and the source line `Solved offline · ⚠ unverified`. A pass gives `Solved offline · verified`.
- **No silent guessing of the operation (spec §6.2):** with no explicit operation (no `=`, `∫`, `d/dx`, `lim`, `Σ`, or inequality), return `needs_operation` and do not solve.
- **Series may answer "couldn't determine"** (`status: cannot_solve`) rather than guess.
- **Canonicalization is meaning-preserving only** (M1 caveat 2): every rewrite in `clean_latex` has its own test that shows it does not change the math.

## Review Focus

1. **Harmless recognizer variants** (`\dfrac`, `\left( \right)`, `\mathrm{d}x`, `\operatorname{sec}`, `\lim\limits`, `\rightarrow`, `f^{\prime}`) must parse to the same problem as the plain form. Test in Task 2.
2. **No real solution** (`x^2+1=0`) must answer "No real solutions" with status `ok`. It must not answer with complex roots or an error. Test in Task 5.
3. **Undefined values** (`\frac{1}{0}`, `\ln 0`, `\lim_{x\to0}\frac{1}{x}`) must answer "undefined" or "does not exist" in words. It must never print `zoo` or `nan`, and it must not crash. Tests in Tasks 5 and 6.
4. **Divergent improper integral** (`\int_{0}^{1}\frac{1}{x}dx`) must answer "Diverges". It must not show `∞` as if it were a value or claim a finite answer. Test in Task 6.
5. **Worker crash or garbage input** (a malformed JSON line, or a child process that dies) must get an `error` response, and the server keeps serving the next request. Test in Task 9.

---

## Interfaces (shared by all tasks)

`inkmath_solver/schema.py` (Task 1):

```python
OPERATIONS = ("simplify", "factor", "expand", "solve", "solve_system", "evaluate", "evaluate_at",
              "derivative", "implicit_derivative", "integrate", "limit", "series", "identity", "ode")
STATUSES = ("ok", "needs_operation", "cannot_parse", "cannot_solve", "timeout", "error")

@dataclass
class Request:
    id: str
    latex: str
    operation: str | None = None   # one of OPERATIONS, or None = infer
    variable: str | None = None    # e.g. "x"; None = pick
    point: str | None = None       # LaTeX value for evaluate_at, e.g. "2"
    show_steps: bool = True

@dataclass
class Answer:
    latex: str
    text: str            # one-line Unicode, readable on a shared screen
    decimal: str | None

@dataclass
class Response:
    id: str
    status: str
    operation: str | None = None
    variable: str | None = None
    choices: list[str] = field(default_factory=list)   # needs_operation: best fit first
    steps: list[str] = field(default_factory=list)
    answer: Answer | None = None
    notes: list[str] = field(default_factory=list)
    verified: bool = False
    source: str = ""     # "Solved offline · verified" | "Solved offline · ⚠ unverified"
    message: str = ""    # plain words for non-ok statuses
    ms: int = 0

def request_from_json(line: str) -> Request
def response_to_json(r: Response) -> str     # one line, ensure_ascii=False
```

`inkmath_solver/problem.py` (Task 2):

```python
KINDS = ("expr", "equation", "inequality", "system", "integral", "derivative", "limit", "sum", "ode", "function_def")

@dataclass
class Problem:
    latex: str
    kind: str
    expr: sympy.Basic            # Expr | Eq | Relational | Integral | Derivative | Limit | Sum
    equations: list[sympy.Basic] # rows of a system; [] otherwise
    symbols: list[sympy.Symbol]  # free symbols, preferred order: x, y, t, theta, n, then alphabetical
    func_name: str | None        # function_def only: "f", "f'", "g", ...
    has_complex: bool            # the problem contains the imaginary unit
```

`inkmath_solver/ops/base.py` (Task 4):

```python
@dataclass
class OpResult:
    value: Any            # SymPy object the verifier checks (see each op)
    answer: Answer
    steps: list[str]
    notes: list[str]
    checkable: bool = True   # False → verifier not run, verified=False
```

---

### Task 1: Scaffold, schema, text formatting

**Files:**
- Create: `solver/requirements.txt`, `solver/pytest.ini`, `solver/inkmath_solver/__init__.py`, `solver/inkmath_solver/schema.py`, `solver/inkmath_solver/textfmt.py`, `solver/tests/conftest.py`
- Modify: `.gitignore` (add `solver/.venv/`), `.claude/progress.json` (M2 steps = this plan's 9 tasks)
- Test: `solver/tests/test_schema.py`, `solver/tests/test_textfmt.py`

**Interfaces:**
- Produces: the schema above. `to_text(obj) -> str`, `to_latex(obj) -> str`, `decimal_of(expr) -> str | None` in `textfmt.py`.

- [ ] **Step 1: Scaffold.** Work on branch `m2-solver`. `requirements.txt`: `sympy==1.14.0`, `antlr4-python3-runtime==4.11.1`, `pytest`. `pytest.ini`: `testpaths = tests`, `pythonpath = .`, and a marker `corpus` for the 120-prompt tests. Create a venv: `python -m venv solver\.venv; solver\.venv\Scripts\pip install -r solver\requirements.txt`. Expected: install succeeds.
- [ ] **Step 2: Write the failing tests.**

```python
# test_schema.py
def test_request_roundtrip_defaults():
    r = request_from_json('{"id":"1","latex":"x+1=2"}')
    assert r.operation is None and r.show_steps is True
def test_response_json_is_one_line_unicode():
    s = response_to_json(Response(id="1", status="ok", answer=Answer("\\pi", "π", "3.14159")))
    assert "\n" not in s and "π" in s and json.loads(s)["answer"]["decimal"] == "3.14159"
def test_unknown_operation_rejected():
    with pytest.raises(ValueError): request_from_json('{"id":"1","latex":"x","operation":"graph"}')

# test_textfmt.py
x = Symbol("x"); th = Symbol("theta")
@pytest.mark.parametrize("obj,text", [
    (x**2 + 5*x + 6, "x² + 5x + 6"), (sqrt(2)/2, "√2/2"), (pi/6, "π/6"), (oo, "∞"),
    (log(x), "ln(x)"), (exp(2*x), "e^(2x)"), (th, "θ"), (x*sin(x), "x·sin(x)"),
    (Rational(-3, 4), "−3/4"), (log(9)/2, "ln(9)/2")])
def test_to_text(obj, text): assert to_text(obj) == text
@pytest.mark.parametrize("v,d", [(Integer(6), None), (Rational(5, 2), "2.5"), (pi, "3.14159"),
                                 (sqrt(2)/2, "0.707107"), (x + 1, None), (oo, None)])
def test_decimal_of(v, d): assert decimal_of(v) == d
```

- [ ] **Step 3: Run and verify they fail.** Run `solver\.venv\Scripts\pytest solver -q`. Expected: ImportError.
- [ ] **Step 4: Implement** `schema.py` (dataclasses, plus JSON helpers that validate `operation` against `OPERATIONS`) and `textfmt.py`. `to_text` is a custom `StrPrinter` subclass, so `pretty()` is not used because it prints on several lines. It uses a Unicode minus `−`, superscripts for a single-digit or single-letter exponent and otherwise `^(…)`, `√` with parentheses only when the argument is not an atom, Greek letters by name, `log` printed as `ln`, implicit multiplication for number-times-symbol, and `·` between other factors. `decimal_of` uses `evalf(6)` with trailing zeros stripped, and returns None for integers, infinities, and non-numbers.
- [ ] **Step 5: Run the tests.** Expected: all pass.
- [ ] **Step 6: Commit.** Message: `solver: scaffold, schema, text formatting`. Update `.claude/progress.json` M2 steps to the 9 task titles of this plan.

### Task 2: LaTeX parser

**Files:**
- Create: `solver/inkmath_solver/problem.py`, `solver/inkmath_solver/parse.py`, `solver/tests/helpers.py`
- Test: `solver/tests/test_parse.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `clean_latex(s: str) -> str`, and `parse_problem(latex: str) -> Problem`, which raises `ParseError(message: str)`.
- Produces the test helpers in `tests/helpers.py`, which later test files import:
  - `ROOT` (the repo root `Path`);
  - `load_all_prompts() -> list[dict]` (both sample sets);
  - `run(latex, fn, point=None) -> OpResult`, which parses, then calls `fn(p, var, point)`, where `var` is the function's argument for `function_def` and `p.symbols[0]` otherwise.

Backend: `sympy.parsing.latex.parse_latex(s, backend="antlr")`. On the 120 M1 prompts it parsed 116, and its output was correct. The `lark` backend parsed 100 and gave ambiguous trees on trig powers, so do not use it. The fixes below are the gaps found in that probe.

- [ ] **Step 1: Write the failing tests.**

```python
def same(a, b): return parse_problem(a).expr == parse_problem(b).expr

@pytest.mark.parametrize("variant,plain", [
    (r"\dfrac{1}{x}", r"\frac{1}{x}"), (r"\left(x+1\right)^2", "(x+1)^2"),
    (r"\int x\,\mathrm{d}x", r"\int x dx"), (r"\operatorname{sec} x", r"\sec x"),
    (r"\lim\limits_{x\to0}x", r"\lim_{x\to0}x"), (r"\lim_{x\rightarrow0}x", r"\lim_{x\to0}x"),
    (r"\displaystyle\frac{1}{2}", r"\frac{1}{2}"), (r"x\le3", r"x\leq3")])
def test_harmless_variants_parse_same(variant, plain): assert same(variant, plain)

def test_log_is_base_10_and_ln_is_natural():
    assert parse_problem(r"\log1000").expr == log(1000, 10)
    assert parse_problem(r"\log_{2}8").expr == log(8, 2)
    assert parse_problem(r"\ln x").expr == log(Symbol("x"))
def test_e_is_euler(): assert parse_problem("e^{2x}=9").expr == Eq(exp(2*Symbol("x")), 9)
def test_i_is_imaginary_except_sum_index():
    assert parse_problem("x^2=-1+i").has_complex
    p = parse_problem(r"\sum_{i=1}^{\infty}\frac{1}{i^2}"); assert not p.has_complex
def test_letter_before_paren_is_multiplication():
    x = Symbol("x"); assert parse_problem(r"\frac{1}{x(x+1)}").expr == 1/(x*(x+1))
def test_system_rows():
    p = parse_problem(r"\begin{cases}x+y=7\\2x-y=2\end{cases}")
    assert p.kind == "system" and len(p.equations) == 2
    assert parse_problem(r"\begin{matrix}x+y=7\\2x-y=2\end{matrix}").kind == "system"
def test_function_definition():
    p = parse_problem("f(x)=x^3-3x+2"); assert p.kind == "function_def" and p.func_name == "f"
    assert parse_problem("f'(x)=6x^2-2").func_name == "f'"
@pytest.mark.parametrize("latex,kind", [("3x-7=11","equation"), ("|2x-1|<5","inequality"),
    (r"\int_{0}^{\pi}x\sin x\,dx","integral"), (r"\frac{d}{dx}\tan(2x)","derivative"),
    (r"\lim_{x\to0^{+}}x\ln x","limit"), (r"\sum_{n=1}^{\infty}\frac{1}{n^2}","sum"),
    (r"\frac{dy}{dx}=3y","ode"), ("x^2+5x+6","expr")])
def test_kinds(latex, kind): assert parse_problem(latex).kind == kind
def test_symbol_order(): assert [s.name for s in parse_problem("y+x+t").symbols] == ["x", "y", "t"]
def test_garbage_raises(): pytest.raises(ParseError, parse_problem, r"\frac{x+")

@pytest.mark.corpus
def test_all_120_prompts_parse():
    for f in ("samples/prompts_test.json", "samples/prompts_tune.json"):
        for p in json.load(open(ROOT / f, encoding="utf-8")):
            parse_problem(p["latex"])   # must not raise
```

- [ ] **Step 2: Run and verify they fail.** Run `solver\.venv\Scripts\pytest solver/tests/test_parse.py -q`. Expected: ImportError.
- [ ] **Step 3: Implement `clean_latex`.** It applies string rewrites only: `\dfrac`/`\tfrac` to `\frac`; drop `\displaystyle` and `\limits`; `\mathrm{d}` to `d`; `\operatorname{NAME}` to `\NAME` for the trig, log and ln names; `\rightarrow` to `\to`; `\le`/`\ge` (not followed by a letter) to `\leq`/`\geq`; `^{\prime}` and `^{'}` to `'`; `\log` not followed by `_` to `\log_{10}`. No bare-letter merging such as `lnx`: that belongs to M4's confirm chips.
- [ ] **Step 4: Implement `parse_problem`.** Clean the LaTeX. Split `cases`/`matrix`/`array`/`aligned` environments into rows and parse each row. Parse with antlr. Then post-process the tree:
  - `Symbol('e')` becomes `E`.
  - `Symbol('i')` becomes `I`, except when it is a Sum index.
  - `log(a, E)` becomes `log(a)`.
  - An `AppliedUndef` with a one-letter name other than f, g, h becomes `Symbol(name) * arg`.
  - A top-level `Eq` whose left side is an `AppliedUndef` named f/g/h (with optional primes) applied to symbols is a `function_def`, and its `expr` is the right side.
  - An `Eq` that contains `Derivative(y, x)` is an `ode`.

  Wrap any parser exception in `ParseError("Couldn't read this expression")`.
- [ ] **Step 5: Run the tests,** including `-m corpus`. Expected: all pass.
- [ ] **Step 6: Commit.** Message: `solver: LaTeX parser with meaning-preserving cleanup`.

### Task 3: Operation inference

**Files:**
- Create: `solver/inkmath_solver/infer.py`
- Test: `solver/tests/test_infer.py`

**Interfaces:**
- Consumes: `Problem`.
- Produces: `infer_operation(p: Problem) -> tuple[str | None, list[str]]`. The first item is the preselected operation, or None when the user must choose. The second is the menu choices, best fit first.

Rules, in order:
1. `integral` → integrate.
2. `derivative` → derivative.
3. `limit` → limit.
4. `sum` → series.
5. `system` → solve_system.
6. `ode` → ode.
7. `inequality` → solve.
8. `equation`: identity if `lhs - rhs` is zero at 5 random real points (numeric check, tolerance 1e-9). Otherwise solve with one free symbol. With two or more free symbols, return None and the choices `[implicit_derivative, solve]`.
9. `function_def` → None, with choices `[derivative, evaluate_at, solve, simplify, factor]`. For a name ending in `'`, the choices start with integrate.
10. `expr` with no free symbols → None, `[evaluate]`.
11. `expr` that is a polynomial → None, `[factor, simplify, expand, solve, derivative, evaluate_at]`.
12. `expr` that is a rational function or contains a trig function → None, `[simplify, factor, expand, solve, derivative, evaluate_at]`.

When the preselected operation is not None, the choices list is all operations that fit, with it first.

- [ ] **Step 1: Write the failing tests.**

```python
@pytest.mark.parametrize("latex,op,first", [
    ("3x-7=11","solve","solve"), (r"\int2xe^{x^2}dx","integrate","integrate"),
    (r"\cos(2x)=\cos^2x-\sin^2x","identity","identity"), (r"\sin(2x)=\sin x","solve","solve"),
    ("x^2+5x+6",None,"factor"), (r"\frac{x^2-1}{x^2+2x+1}",None,"simplify"),
    (r"\sin^2x+\cos^2x",None,"simplify"), (r"\log1000",None,"evaluate"),
    ("x^2+y^2=25",None,"implicit_derivative"), ("f(x)=x^3-3x+2",None,"derivative"),
    ("f'(x)=6x^2-2",None,"integrate"), (r"\begin{cases}x+y=7\\2x-y=2\end{cases}","solve_system","solve_system")])
def test_infer(latex, op, first):
    got, choices = infer_operation(parse_problem(latex))
    assert got == op and choices[0] == first and set(choices) <= set(OPERATIONS)
```

- [ ] **Step 2: Run and verify they fail.** Expected: ImportError.
- [ ] **Step 3: Implement** `infer.py` per the rules above. Seed random points with `random.Random(0)`, and skip points where either side is not finite.
- [ ] **Step 4: Run the tests.** Expected: pass.
- [ ] **Step 5: Commit.** Message: `solver: operation inference (ask, don't guess)`.

### Task 4: Independent verification

**Files:**
- Create: `solver/inkmath_solver/ops/__init__.py`, `solver/inkmath_solver/ops/base.py`, `solver/inkmath_solver/verify.py`
- Test: `solver/tests/test_verify.py`

**Interfaces:**
- Consumes: `Problem`, `OpResult`.
- Produces: `verify(op: str, p: Problem, r: OpResult, variable: Symbol) -> bool`, and the `VERIFIERS` mapping from op to function. Every verifier catches its own exceptions and returns False. Each one checks a different way from how the answer was computed (spec §6.5). The tests feed each verifier a right answer and a wrong answer.

The `value` each op hands its verifier:

| op | value |
|---|---|
| solve | `list[Expr]` of finite solutions, or a `Set` (inequality or trig) |
| solve_system | `list[dict[Symbol, Expr]]` |
| integrate | the antiderivative `Expr`, or the definite value (`oo`/`-oo` = diverges) |
| derivative, implicit_derivative | the derivative `Expr` |
| limit | the limit value (`oo`, `-oo`, or `nan` = does not exist) |
| simplify, factor, expand, evaluate, evaluate_at | the result `Expr` |
| identity | `bool` |
| series | `(converges: bool, sum: Expr | None)` |
| ode | the solution `Eq` |

Checks:
- **solve:** substitute each solution numerically, |lhs − rhs| < 1e-9. For a `Set` from an inequality, test 20 sample points: inside points must satisfy the relation and outside points must not. For a trig `ImageSet`, check k = −1, 0, 1.
- **solve_system:** substitute into every row.
- **integrate (indefinite):** the derivative of the answer minus the integrand is ≈ 0 at 5 random points.
- **integrate (definite):** `mpmath.quad` within 1e-8 relative. If the answer is a divergence, `quad` must fail or grow when the cut-off is pushed further out.
- **derivative:** central difference with h = 1e-6 at 3 points, within 1e-5 relative.
- **implicit_derivative:** compare with −F_x/F_y at 3 points on the curve.
- **limit:** evaluate at x₀ ± 10⁻ᵏ for k = 3..7 (or x = 10ᵏ for ∞) on the problem's side or sides. The values must approach the answer. For ±∞, |values| must grow. For "does not exist", the two sides must disagree or the values must not settle.
- **simplify, factor, expand, evaluate, evaluate_at, identity:** compare the original and the result numerically at 5 random points with 50-digit precision. A false identity must show a point where they differ.
- **series:** the convergence verdict must agree with `Sum.is_convergent()`. When a sum is given, it must agree with `mpmath.nsum` to 1e-8.
- **ode:** `checkodesol(...)[0] is True`.

- [ ] **Step 1: Write the failing tests.** One right/wrong pair per op, for example:

```python
x = Symbol("x")
def res(v): return OpResult(value=v, answer=Answer("", "", None), steps=[], notes=[])
def test_solve(): p = parse_problem("3x-7=11"); assert verify("solve", p, res([6]), x); assert not verify("solve", p, res([5]), x)
def test_integrate_indefinite():
    p = parse_problem(r"\int x\sin x\,dx")
    assert verify("integrate", p, res(sin(x) - x*cos(x)), x)
    assert not verify("integrate", p, res(sin(x) + x*cos(x)), x)
def test_integrate_divergent():
    p = parse_problem(r"\int_{0}^{1}\frac{1}{x}dx"); assert verify("integrate", p, res(oo), x)
    assert not verify("integrate", p, res(Integer(2)), x)
def test_limit_dne(): p = parse_problem(r"\lim_{x\to0}\frac{1}{x}"); assert verify("limit", p, res(nan), x)
def test_false_identity(): p = parse_problem(r"\sin(2x)=2\sin x"); assert verify("identity", p, res(False), x)
def test_verifier_exception_is_false(): assert verify("solve", parse_problem("x=1"), res(["junk"]), x) is False
```

  Write similar pairs for solve_system, inequality, trig ImageSet, derivative, implicit_derivative, simplify, evaluate, series, and ode.
- [ ] **Step 2: Run and verify they fail.**
- [ ] **Step 3: Implement** `ops/base.py` (`OpResult`) and `verify.py`.
- [ ] **Step 4: Run the tests.** Expected: pass.
- [ ] **Step 5: Commit.** Message: `solver: independent answer verification`.

### Task 5: Algebra and precalc operations

**Files:**
- Create: `solver/inkmath_solver/ops/algebra.py`
- Test: `solver/tests/test_algebra.py`

**Interfaces:**
- Consumes: `Problem`, `OpResult`, `textfmt`.
- Produces: `run_solve`, `run_solve_system`, `run_simplify`, `run_factor`, `run_expand`, `run_evaluate`, `run_evaluate_at`, and `run_identity`. Each has the signature `(p: Problem, var: Symbol, point: Expr | None) -> OpResult` and raises `CannotSolve(message)` when SymPy gives up.

Solving uses `solveset(..., domain=S.Reals)`, or `S.Complexes` if `p.has_complex`. Trig equations: the general solution comes from solveset on Reals, and the second list comes from solveset on `Interval.Ropen(0, 2*pi)`. Answer text uses this form: `θ = π/6 + 2πk, θ = 5π/6 + 2πk (k any integer); on [0, 2π): π/6, 5π/6`. Excluded values go into `notes` as `x ≠ a`, from the denominators of the original problem, for simplify and for solve. Rejected extraneous roots go into `notes` as `x = −1 rejected (doesn't check)`. A result of `zoo` or `nan` becomes the answer `Undefined`.

Step templates, 1–4 lines each, chosen by equation shape (the first match wins):

| Shape | Steps |
|---|---|
| linear | `Collect x terms: 3x = 18`, `Divide by 3` |
| quadratic that factors over ℚ | `Factor: (x + 1)(2x − 5) = 0`, `Set each factor to 0` |
| quadratic that doesn't factor | `Quadratic formula: a = …, b = …, c = …` |
| rational | `Multiply both sides by (x − 2)` plus the exclusion note |
| radical | `Square both sides: x + 5 = (x − 1)²`, `Solve, then check each root` |
| absolute value | `Split: −5 < 2x − 1 < 5` (or the two-case form for > and ≥) |
| exponential | `Take ln of both sides` (or `Rewrite with the same base: 3^(x+1) = 3³`) |
| log | `Combine logs: log₂(x(x − 2)) = 3`, `Rewrite in exponential form: x(x − 2) = 2³` |
| trig | `Factor as a quadratic in cos(x)` when applicable, then `Solve for cos(x) = …` |
| system | `Substitute y = …` (when a row is already solved for a variable) or `Eliminate y` |
| anything else | `Solve for x` |

simplify, factor and expand use the single step `Factor numerator and denominator` / `Cancel common factors` as they apply. identity uses `Simplify both sides` plus `Both sides are equal → identity holds`, or `Not an identity: at x = 1, left = …, right = …`.

- [ ] **Step 1: Write the failing tests.** These use `run` from `tests/helpers.py`.

```python
@pytest.mark.parametrize("latex,text", [
    ("3x-7=11", "x = 6"), ("2x^2-3x-5=0", "x = −1, x = 5/2"), (r"\frac{x+3}{x-2}=4", "x = 11/3"),
    (r"\sqrt{x+5}=x-1", "x = 4"), ("|2x-1|<5", "−2 < x < 3"), (r"\log_{2}x+\log_{2}(x-2)=3", "x = 4"),
    ("5-2x\\geq3x+20", "x ≤ −3"), ("x^3-8=0", "x = 2"), (r"\ln x=2", "x = e²"), ("3^{x+1}=27", "x = 2"),
    ("x^2+1=0", "No real solutions")])
def test_solve_answers(latex, text): assert run(latex, run_solve).answer.text == text

def test_extraneous_root_noted(): assert any("−1 rejected" in n for n in run(r"\sqrt{x+5}=x-1", run_solve).notes)
def test_trig_general_and_interval():
    t = run(r"2\sin\theta-1=0", run_solve).answer.text
    assert "π/6 + 2πk" in t and "5π/6 + 2πk" in t and "on [0, 2π): π/6, 5π/6" in t
def test_system(): assert run(r"\begin{cases}x+y=7\\2x-y=2\end{cases}", run_solve_system).answer.text == "x = 3, y = 4"
def test_nonlinear_system_two_solutions():
    assert run(r"\begin{cases}y=x^2-1\\y=x+1\end{cases}", run_solve_system).answer.text == "(x, y) = (−1, 0), (2, 3)"
def test_simplify_with_domain():
    r = run(r"\frac{x^2-1}{x^2+2x+1}", run_simplify); assert r.answer.text == "(x − 1)/(x + 1)" and "x ≠ −1" in r.notes
def test_factor(): assert run("x^2+5x+6", run_factor).answer.text == "(x + 2)(x + 3)"
def test_evaluate(): r = run(r"\sin\frac{\pi}{6}+\cos\frac{\pi}{3}", run_evaluate); assert r.answer.text == "1"
def test_evaluate_log_base10(): assert run(r"\log1000", run_evaluate).answer.text == "3"
def test_undefined(): assert run(r"\frac{1}{0}", run_evaluate).answer.text == "Undefined"
def test_identity_true(): assert run(r"\cos(2x)=\cos^2x-\sin^2x", run_identity).value is True
def test_identity_false(): r = run(r"\sin(2x)=2\sin x", run_identity); assert r.value is False and "Not an identity" in r.steps[-1]
def test_steps_linear(): assert run("3x-7=11", run_solve).steps[0] == "Collect x terms: 3x = 18"
def test_steps_count():
    for l in ("3x-7=11", r"\sqrt{x+5}=x-1", "|2x-1|<5", r"2\cos^2x-\cos x-1=0"):
        assert 1 <= len(run(l, run_solve).steps) <= 4
```

- [ ] **Step 2: Run and verify they fail.**
- [ ] **Step 3: Implement** `ops/algebra.py`.
- [ ] **Step 4: Run the tests.** Expected: pass.
- [ ] **Step 5: Commit.** Message: `solver: algebra and precalc operations with key steps`.

### Task 6: Calculus operations

**Files:**
- Create: `solver/inkmath_solver/ops/calculus.py`
- Test: `solver/tests/test_calculus.py`

**Interfaces:**
- Consumes: `Problem`, `OpResult`, `textfmt`.
- Produces: `run_derivative`, `run_implicit_derivative`, `run_limit`, `run_integrate`, and `run_ode`, with the same signature as Task 5.

- **Derivative steps.** Name the outermost rule: `Product rule`, `Quotient rule` (a Mul with a non-constant negative power), `Chain rule` (a function of a non-symbol argument, or a power of a non-symbol base), or `Power rule`/`Basic rules`. The step text is the rule name plus its pieces, e.g. `Product rule: (x³)′·sin(x) + x³·(sin(x))′`. Then `Simplify`. The answer is `simplify(diff(...))`. When the request is for `function_def`, differentiate the right side.
- **Implicit derivative.** Use `idiff(F, y, x)`. Steps: `Implicit differentiation: differentiate both sides, treating y as y(x)`, then `Solve for dy/dx`. The answer reads `dy/dx = −x/y`.
- **Limit.** Use `limit()` on the problem's direction. For a two-sided limit, compute both sides. If they differ, or the result is `nan`/`AccumBounds`, the answer is `Does not exist`. A step is `Direct substitution gives 0/0` (or `∞/∞`) when that is true, followed by `Factor and cancel`, `Divide by the highest power`, or `L'Hôpital's rule`: factor and cancel when `cancel()` removes the 0/0, highest power for a rational function at ∞, otherwise L'Hôpital. Infinite answers read `∞` and `−∞`.
- **Integrate.** For a rational integrand whose denominator has degree ≥ 2 and factors, the first step is `Partial fractions: <apart(...)>`. Otherwise walk `integral_steps(f, x)`. Unwrap `ConstantTimesRule`, `AlternativeRule` (take the first alternative) and `AddRule` (take the first non-basic child). Name the first technique found:

  | Rule | Step text |
  |---|---|
  | `URule` | `Substitution: u = <u_func>` |
  | `PartsRule`/`CyclicPartsRule` | `Integration by parts: u = <u>, dv = <dv>` |
  | `TrigSubstitutionRule`/`SqrtQuadraticRule` | `Trig substitution` (plus `x = 3 sin θ` when the form is √(a² − x²)) |
  | `RewriteRule` | `Rewrite: <rewritten>` |
  | otherwise | `Basic antiderivative rules` |

  The answer comes from `manualintegrate`, falling back to `integrate` if a `DontKnowRule` appears. When it falls back, the technique step reads `Computed directly`. An indefinite answer gets `+ C`. A definite integral adds the step `Evaluate from a to b`. An improper integral that diverges answers `Diverges`, and its value is `oo`. For a `function_def` (e.g. `f'(x)=6x^2-2`), integrate the right side and answer `f(x) = … + C`.
- **ODE.** Use `dsolve`. Step: `Separate variables` when `classify_ode` lists `separable`, otherwise `Solve the differential equation`.

- [ ] **Step 1: Write the failing tests.**

```python
@pytest.mark.parametrize("latex,text", [
    (r"\lim_{x\to0}\frac{\sin x}{x}", "1"), (r"\lim_{x\to\infty}\frac{3x^2+1}{x^2-4}", "3"),
    (r"\lim_{x\to2}\frac{x^2-4}{x-2}", "4"), (r"\lim_{x\to0^{+}}x\ln x", "0"),
    (r"\lim_{x\to0}\frac{1}{x}", "Does not exist"), (r"\lim_{x\to0^{+}}\frac{1}{x}", "∞")])
def test_limits(latex, text): assert run(latex, run_limit).answer.text == text
@pytest.mark.parametrize("latex,step", [
    (r"\frac{d}{dx}(x^3\sin x)", "Product rule"), (r"\frac{d}{dx}\frac{x+1}{x-1}", "Quotient rule"),
    (r"\frac{d}{dx}\ln(x^2+1)", "Chain rule")])
def test_derivative_rule_named(latex, step): assert run(latex, run_derivative).steps[0].startswith(step)
def test_derivative_answer(): assert run(r"\frac{d}{dx}\ln(x^2+1)", run_derivative).answer.text == "2x/(x² + 1)"
def test_implicit(): assert run("x^2+y^2=25", run_implicit_derivative).answer.text == "dy/dx = −x/y"
@pytest.mark.parametrize("latex,step", [
    (r"\int x\sin x\,dx", "Integration by parts"), (r"\int2xe^{x^2}dx", "Substitution: u = x²"),
    (r"\int\frac{3x+5}{(x+1)(x+2)}dx", "Partial fractions"), (r"\int\sqrt{9-x^2}dx", "Trig substitution")])
def test_integral_technique(latex, step): assert run(latex, run_integrate).steps[0].startswith(step)
@pytest.mark.parametrize("latex,text", [
    (r"\int_{0}^{\pi}x\sin x\,dx", "π"), (r"\int_{1}^{\infty}\frac{1}{x^2}dx", "1"),
    (r"\int_{0}^{\frac{\pi}{2}}\cos^2\theta\,d\theta", "π/4"), (r"\int_{0}^{1}\frac{1}{x}dx", "Diverges")])
def test_definite(latex, text): assert run(latex, run_integrate).answer.text == text
def test_indefinite_has_C(): assert run(r"\int2xe^{x^2}dx", run_integrate).answer.text.endswith("+ C")
def test_ode(): assert "C₁" in run(r"\frac{dy}{dx}=3y", run_ode).answer.text
```

- [ ] **Step 2: Run and verify they fail.**
- [ ] **Step 3: Implement** `ops/calculus.py`.
- [ ] **Step 4: Run the tests.** Expected: pass.
- [ ] **Step 5: Commit.** Message: `solver: derivatives, limits, integrals, ODEs with technique names`.

### Task 7: Series

**Files:**
- Create: `solver/inkmath_solver/ops/series.py`
- Test: `solver/tests/test_series.py`

**Interfaces:**
- Consumes: `Problem`, `OpResult`.
- Produces: `run_series(p, var, point) -> OpResult`, whose value is `(converges, sum_or_None)`, and `classify(term: Expr, n: Symbol) -> tuple[str, bool] | None` (the test name and whether the series converges).

The tests are tried in this order, and the first one that decides wins:
1. **Divergence test:** lim aₙ ≠ 0, so the series diverges.
2. **Geometric:** aₙ₊₁/aₙ simplifies to a constant r, and the series converges iff |r| < 1.
3. **p-series:** aₙ = c/nᵖ, and the series converges iff p > 1.
4. **Alternating series test:** aₙ = (−1)ⁿbₙ with bₙ decreasing to 0, so the series converges.
5. **Ratio test:** L = lim |aₙ₊₁/aₙ|. If L < 1 it converges, if L > 1 it diverges, and L = 1 does not decide.
6. **Root test:** the same rule for lim |aₙ|^(1/n).
7. **Limit comparison:** compare with 1/n^d, where d = (degree of the denominator) − (degree of the numerator), for an algebraic aₙ.
8. **Integral test:** aₙ is positive and decreasing, and ∫ from N to ∞ converges or diverges.

If none decides, the status is `cannot_solve` with the message `Couldn't determine whether this series converges`. When the series converges, try `summation()`. If the result has a closed form, give it as the sum. Otherwise the answer is `Converges` with no sum.

The steps are `<Test name>: <one-line reason>` followed by the conclusion, e.g. `Geometric series: r = 1/2, |r| < 1`, then `Sum = a/(1 − r) = 2`.

- [ ] **Step 1: Write the failing tests.**

```python
@pytest.mark.parametrize("latex,test,conv", [
    (r"\sum_{n=1}^{\infty}\frac{1}{n^2}", "p-series", True), (r"\sum_{n=0}^{\infty}\left(\frac{1}{2}\right)^n", "Geometric series", True),
    (r"\sum_{n=1}^{\infty}\frac{(-1)^n}{n}", "Alternating series test", True), (r"\sum_{n=1}^{\infty}\frac{n}{n+1}", "Divergence test", False),
    (r"\sum_{n=1}^{\infty}\frac{n!}{n^n}", "Ratio test", True), (r"\sum_{n=1}^{\infty}\frac{1}{\sqrt{n}}", "p-series", False),
    (r"\sum_{n=2}^{\infty}\frac{1}{n\ln n}", "Integral test", False), (r"\sum_{n=1}^{\infty}\frac{1}{n^2+1}", "Limit comparison", True)])
def test_classify(latex, test, conv):
    r = run(latex, run_series); assert r.steps[0].startswith(test) and r.value[0] is conv
@pytest.mark.parametrize("latex,text", [
    (r"\sum_{n=1}^{\infty}\frac{1}{n^2}", "Converges; sum = π²/6"), (r"\sum_{n=1}^{\infty}\frac{3}{4^n}", "Converges; sum = 1"),
    (r"\sum_{n=1}^{\infty}\frac{n}{n+1}", "Diverges")])
def test_answers(latex, text): assert run(latex, run_series).answer.text == text
```

- [ ] **Step 2: Run and verify they fail.**
- [ ] **Step 3: Implement** `ops/series.py`.
- [ ] **Step 4: Run the tests.** Expected: pass.
- [ ] **Step 5: Commit.** Message: `solver: series convergence tests and sums`.

### Task 8: Engine

**Files:**
- Create: `solver/inkmath_solver/engine.py`
- Test: `solver/tests/test_engine.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `handle(req: Request) -> Response`. It never raises: any unexpected exception gives `status: error` with the message `Something went wrong solving this`. It does not time itself out (Task 9 does that).

Flow:
1. Parse. A `ParseError` gives `cannot_parse` with its message.
2. If `req.operation` is None, call `infer_operation`. If that returns None, respond `needs_operation` with the choices and no solving.
3. Pick the variable: `req.variable`, else the first entry of `p.symbols` (for `function_def`, its argument).
4. Run the op. `CannotSolve` gives `cannot_solve` with its message.
5. Verify, unless `checkable` is False.
6. Set `source`. Drop `steps` if `show_steps` is False. Set `ms`.

For `evaluate_at`, parse `req.point` with `parse_problem`; a missing point gives `cannot_solve` with `Which value should I use?`.

- [ ] **Step 1: Write the failing tests.**

```python
def h(latex, **kw): return handle(Request(id="t", latex=latex, **kw))
def test_ok_verified(): r = h("3x-7=11"); assert (r.status, r.verified, r.source) == ("ok", True, "Solved offline · verified")
def test_needs_operation(): r = h("x^2+5x+6"); assert r.status == "needs_operation" and r.choices[0] == "factor" and r.answer is None
def test_chosen_operation(): assert h("x^2+5x+6", operation="factor").answer.text == "(x + 2)(x + 3)"
def test_evaluate_at(): assert h("f(x)=x^3-3x+2", operation="evaluate_at", point="2").answer.text == "4"
def test_cannot_parse(): assert h(r"\frac{x+").status == "cannot_parse"
def test_hide_steps(): assert h("3x-7=11", show_steps=False).steps == []
def test_unverified_marked(monkeypatch):
    monkeypatch.setitem(VERIFIERS, "solve", lambda *a: False)
    r = h("3x-7=11"); assert r.verified is False and r.source == "Solved offline · ⚠ unverified"

@pytest.mark.corpus
def test_corpus_all_120():
    """Every prompt: ask (needs_operation) or solve; with choices[0] if asked. No errors."""
    bad = []
    for p in load_all_prompts():
        r = h(p["latex"])
        if r.status == "needs_operation": r = h(p["latex"], operation=r.choices[0])
        if r.status not in ("ok", "cannot_solve") or (r.status == "ok" and not r.verified):
            bad.append((p["id"], r.status, r.verified, r.message))
    assert bad == []
```

- [ ] **Step 2: Run and verify they fail.**
- [ ] **Step 3: Implement** `engine.py`.
- [ ] **Step 4: Run the tests,** including `-m corpus`. Expected: pass. Any corpus item that only reaches `cannot_solve` must be a series item; list them in the commit message.
- [ ] **Step 5: Commit.** Message: `solver: engine (parse, infer, run, verify)`.

### Task 9: Server with warm worker and 20 s timeout

**Files:**
- Create: `solver/inkmath_solver/server.py`, `solver/inkmath_solver/__main__.py`, `solver/inkmath_solver/bench.py`
- Test: `solver/tests/test_server.py`

**Interfaces:**
- Consumes: `handle`, `request_from_json`, `response_to_json`.
- Produces the process protocol M3 uses: `python -m inkmath_solver [--timeout 20]`. It reads one JSON request per line on stdin and writes one JSON response per line on stdout, in the same order and with the same `id`. It writes nothing else to stdout (logs go to stderr). It prints the line `{"ready": true}` once the worker is warm. EOF on stdin exits cleanly.

**Design.**
- The server process stays light: it does not import SymPy.
- It keeps one `multiprocessing` child (spawn context) that has already imported SymPy and `engine` and warmed the parser on `x+1`. Requests go to the child over a `Pipe`.
- **Timeout:** `conn.poll(timeout)` returns False. Terminate the child and respond `timeout` with the message `This one's taking too long`. Start a new child at once, so the next request finds it warming or warm.
- **Child crash:** an `EOFError` or a dead process gives `error` with `Something went wrong solving this`, and the child respawns.
- **Bad JSON or unknown operation:** respond `error` with `id` `""` (or the id if it can be read) and keep going.

- [ ] **Step 1: Write the failing tests.** These are subprocess tests against `python -m inkmath_solver`.

```python
def start(*args): p = Popen([sys.executable, "-m", "inkmath_solver", *args], stdin=PIPE, stdout=PIPE, text=True, encoding="utf-8", cwd=SOLVER); assert json.loads(p.stdout.readline()) == {"ready": True}; return p
def ask(p, obj): p.stdin.write(json.dumps(obj) + "\n"); p.stdin.flush(); return json.loads(p.stdout.readline())

def test_roundtrip():
    p = start(); r = ask(p, {"id": "a", "latex": "3x-7=11"}); assert r["id"] == "a" and r["answer"]["text"] == "x = 6"; p.stdin.close(); assert p.wait(10) == 0
def test_timeout_then_recovers():
    p = start("--timeout", "1")
    t = time.monotonic(); r = ask(p, {"id": "slow", "latex": r"\int e^{x^2}\sin(x^3)\cos(\sqrt{x})dx", "operation": "integrate"})
    assert r["status"] == "timeout" and r["message"] == "This one's taking too long" and time.monotonic() - t < 3
    assert ask(p, {"id": "b", "latex": "3x-7=11"})["status"] == "ok"
def test_bad_json_keeps_serving():
    p = start(); p.stdin.write("not json\n"); p.stdin.flush(); assert json.loads(p.stdout.readline())["status"] == "error"
    assert ask(p, {"id": "c", "latex": "x+1=2"})["status"] == "ok"
def test_worker_crash_recovers():
    p = start(); kill_worker_child(p)
    assert ask(p, {"id": "d", "latex": "x+1=2"})["status"] in ("ok", "error")
    assert ask(p, {"id": "e", "latex": "x+1=2"})["status"] == "ok"
```

  For `kill_worker_child(p)`, the server logs `worker pid <n>` to stderr each time it spawns, so start the process with `stderr=PIPE`. The test reads that line and runs `taskkill /F /PID <n>`. For the slow-integral test: if that integral finishes in under 1 s on the dev machine, swap in any request that takes over 2 s, and note the swap in the commit message.
- [ ] **Step 2: Run and verify they fail.**
- [ ] **Step 3: Implement** `server.py` and `__main__.py`.
- [ ] **Step 4: Run the tests.** Expected: pass.
- [ ] **Step 5: Implement `bench.py`.** `python -m inkmath_solver.bench --set ../samples/prompts_test.json` runs every prompt through one warm server (answering `needs_operation` with `choices[0]`). It prints one line per prompt with id, status, verified and ms, then the median ms, the maximum ms, and the count over 5 s. Run it on both sets. Expected: no `error` or `timeout`. Record the median and maximum in the commit message. The Surface estimate is the dev time × 1.75, and the target is under 5 s.
- [ ] **Step 6: Commit.** Message: `solver: JSON-lines server with warm worker and 20 s timeout`. Mark M2's steps done in `.claude/progress.json`.

---

## Notes for later milestones (not tasks here)

- **M3:** launch `python -m inkmath_solver` once per OneNote session, wait for `{"ready": true}`, and keep the process. Also apply your own 25 s read timeout as a backstop.
- **M4:** `clean_latex` is the vetted, meaning-preserving cleanup. Reuse it, and don't fork `spike/inkspike/score.normalize`.
- **M6:** bundle an embedded Python 3.10 with this package's pinned dependencies. Re-run `bench.py` on the Surface.
