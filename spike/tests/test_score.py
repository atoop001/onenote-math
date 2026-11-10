from inkspike.score import Result, error_kind, fixes, normalize, summarize


def test_equivalent_forms_normalize_equal():
    pairs = [(r"\sin(x)", r"\sin x"), (r"x\,dx", "x dx"), (r"\mathrm{d}x", "dx"),
             (r"\left(x+1\right)", "(x+1)"), (r"\dfrac{1}{2}", r"\frac{1}{2}"), ("{x}^{2}", "x^2")]
    for a, b in pairs:
        assert normalize(a) == normalize(b), (a, b)


def test_different_math_stays_different():
    assert normalize(r"\sin(x+1)") != normalize(r"\sin x+1")
    assert normalize("x^{12}") != normalize("x^1 2")
    assert normalize(r"\frac{1}{2}") != normalize("12")


def test_fixes_counts_tokens():
    assert fixes(r"\int_{0}^{\pi} x \sin x dx", r"\int_{0}^{\pi} x \sin x dx") == 0
    assert fixes("x^3", "x^2") == 1
    assert fixes(r"\frac{1}{x}", "1/x") >= 1


def test_summarize_gate():
    rs = [Result(str(i), "algebra", "a", "a", 0, 100) for i in range(70)] + \
         [Result(str(i), "calc2", "a", "a", 2, 100) for i in range(25)] + \
         [Result(str(i), "calc2", "a", "a", 3, 100) for i in range(5)]
    s = summarize(rs)
    assert s["zero_rate"] == 0.70 and s["le2_rate"] == 0.95 and s["passed"] is True
    assert s["by_area"]["algebra"]["zero_rate"] == 1.0
    assert s["median_ms"] == 100


def test_summarize_fails_below_gate():
    rs = [Result(str(i), "algebra", "a", "a", 0, 50) for i in range(69)] + \
         [Result(str(i), "algebra", "a", "a", 1, 50) for i in range(31)]
    assert summarize(rs)["passed"] is False


def test_error_kind():
    assert error_kind("x^3", "x^2") == "symbol"
    assert error_kind("x2", "x^2") == "structural"
    assert error_kind("x", "x") is None
