"""Score recognizer output against ground-truth LaTeX.

A "fix" is one token the tutor would have to tap and change in the confirm box,
so the score is token-level edit distance after both sides are normalized to
remove differences that don't change the math (spacing, \\left, \\dfrac, ...).
"""
import re
import statistics
from collections import Counter
from dataclasses import dataclass
from typing import Protocol

_TOKEN = re.compile(r"\\[a-zA-Z]+|\\.|\S")
_DROP = {r"\,", r"\;", r"\!", r"\:", r"\ ", r"\left", r"\right", r"\mathrm", r"\mathit",
         r"\quad", r"\qquad", r"\displaystyle"}
_ALIAS = {r"\dfrac": r"\frac", r"\tfrac": r"\frac", r"\le": r"\leq", r"\ge": r"\geq"}
_FUNCS = {r"\sin", r"\cos", r"\tan", r"\sec", r"\csc", r"\cot", r"\arcsin", r"\arccos",
          r"\arctan", r"\sinh", r"\cosh", r"\tanh", r"\ln", r"\log", r"\exp"}
STRUCTURAL = {"^", "_", "{", "}", r"\frac"}


def _strip_single(tokens: list[str], open_: str, close: str, only_after=None) -> tuple[list[str], bool]:
    out, changed, i = [], False, 0
    while i < len(tokens):
        if (i + 2 < len(tokens) and tokens[i] == open_ and tokens[i + 2] == close
                and tokens[i + 1] not in (open_, close)
                and (only_after is None or (out and out[-1] in only_after))):
            out.append(tokens[i + 1])
            i += 3
            changed = True
        else:
            out.append(tokens[i])
            i += 1
    return out, changed


def normalize(latex: str) -> list[str]:
    tokens = [_ALIAS.get(t, t) for t in _TOKEN.findall(latex) if t not in _DROP]
    changed = True
    while changed:
        tokens, c1 = _strip_single(tokens, "{", "}")
        tokens, c2 = _strip_single(tokens, "(", ")", only_after=_FUNCS)
        changed = c1 or c2
    return tokens


def _levenshtein(a: list[str], b: list[str]) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def fixes(pred: str, truth: str) -> int:
    return _levenshtein(normalize(pred), normalize(truth))


def error_kind(pred: str, truth: str) -> str | None:
    """None if no fixes; 'structural' if any differing token is ^ _ { } or \\frac; else 'symbol'."""
    a, b = normalize(pred), normalize(truth)
    if a == b:
        return None
    p, t = Counter(a), Counter(b)
    diff = set((p - t) + (t - p))
    # Same tokens in a different order means things moved, which is structural.
    return "structural" if not diff or diff & STRUCTURAL else "symbol"


@dataclass
class Result:
    id: str
    area: str
    pred: str
    truth: str
    fixes: int
    ms: float


class Recognizer(Protocol):
    name: str

    def recognize(self, png_path: str) -> str: ...


def _rates(rs: list[Result]) -> dict:
    n = len(rs)
    return {
        "n": n,
        "zero_rate": sum(r.fixes == 0 for r in rs) / n if n else 0.0,
        "le2_rate": sum(r.fixes <= 2 for r in rs) / n if n else 0.0,
    }


def summarize(results: list[Result]) -> dict:
    s = _rates(results)
    s["passed"] = bool(results) and s["zero_rate"] >= 0.70 and s["le2_rate"] >= 0.95
    areas = sorted({r.area for r in results})
    s["by_area"] = {a: _rates([r for r in results if r.area == a]) for a in areas}
    s["median_ms"] = statistics.median(r.ms for r in results) if results else 0.0
    return s
