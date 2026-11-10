import pytest

from helpers import load_all_prompts
from inkmath_solver.engine import handle
from inkmath_solver.schema import Request
from inkmath_solver.verify import VERIFIERS


def h(latex, **kw):
    return handle(Request(id="t", latex=latex, **kw))


def test_ok_verified():
    r = h("3x-7=11")
    assert (r.status, r.verified, r.source) == ("ok", True, "Solved offline · verified")
    assert r.operation == "solve" and r.variable == "x" and r.ms >= 0


def test_needs_operation():
    r = h("x^2+5x+6")
    assert r.status == "needs_operation" and r.choices[0] == "factor" and r.answer is None


def test_chosen_operation():
    assert h("x^2+5x+6", operation="factor").answer.text == "(x + 2)(x + 3)"


def test_evaluate_at():
    assert h("f(x)=x^3-3x+2", operation="evaluate_at", point="2").answer.text == "4"


def test_evaluate_at_without_point():
    r = h("f(x)=x^3-3x+2", operation="evaluate_at")
    assert r.status == "cannot_solve" and r.message == "Which value should I use?"


def test_cannot_parse():
    r = h(r"\frac{x+")
    assert r.status == "cannot_parse" and r.message


def test_hide_steps():
    assert h("3x-7=11", show_steps=False).steps == []


def test_unverified_marked(monkeypatch):
    monkeypatch.setitem(VERIFIERS, "solve", lambda *a: False)
    r = h("3x-7=11")
    assert r.verified is False and r.source == "Solved offline · ⚠ unverified"


def test_unexpected_exception_is_error(monkeypatch):
    import inkmath_solver.engine as eng
    monkeypatch.setitem(eng.RUNNERS, "solve", lambda *a: 1 / 0)
    r = h("3x-7=11")
    assert r.status == "error" and r.message == "Something went wrong solving this"


def test_variable_override():
    assert h("x+y=3", operation="solve", variable="y").answer.text == "y = 3 − x"


@pytest.mark.corpus
def test_corpus_all_120():
    """Every prompt: ask (needs_operation) or solve; with choices[0] if asked. No errors."""
    bad = []
    for p in load_all_prompts():
        r = h(p["latex"])
        if r.status == "needs_operation":
            r = h(p["latex"], operation=r.choices[0])
        if r.status not in ("ok", "cannot_solve") or (r.status == "ok" and not r.verified):
            bad.append((p["id"], r.status, r.verified, r.message))
        if r.status == "cannot_solve":
            assert p["latex"].startswith(r"\sum"), (p["id"], r.message)
    assert bad == []


def test_raw_sympy_never_reaches_the_page(monkeypatch):
    import inkmath_solver.engine as eng
    from inkmath_solver.ops.base import OpResult
    from inkmath_solver.schema import Answer
    bad = OpResult(value=1, answer=Answer("", "Piecewise((0, Eq(x, 0)), (1/x, True))", None), steps=[], notes=[])
    monkeypatch.setitem(eng.RUNNERS, "solve", lambda *a: bad)
    r = h("3x-7=11")
    assert r.status == "cannot_solve" and r.answer is None
