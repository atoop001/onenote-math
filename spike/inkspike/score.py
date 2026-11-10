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
         r"\operatorname", r"\limits", r"\nolimits", r"\quad", r"\qquad", r"\displaystyle"}
_ALIAS = {r"\dfrac": r"\frac", r"\tfrac": r"\frac", r"\le": r"\leq", r"\ge": r"\geq",
          r"\rightarrow": r"\to", r"\prime": "'"}
_PRIME = re.compile(r"\^\s*\{\s*('+)\s*\}|\^\s*(')")  # f^{'} and f^' are f'
_FUNC_NAMES = ["arcsin", "arccos", "arctan", "sinh", "cosh", "tanh", "sin", "cos", "tan",
               "sec", "csc", "cot", "log", "lim", "exp", "ln"]  # longest first
_FUNCS = {"\\" + n for n in _FUNC_NAMES if n != "lim"}
# A brace group right after one of these is an argument and must be kept.
_ARG_TAKERS = {"^", "_", "}", "]", r"\frac", r"\sqrt", r"\binom", r"\text",
               r"\overline", r"\underline", r"\bar", r"\vec", r"\hat", r"\tilde", r"\dot",
               r"\ddot", r"\mathbf", r"\boldsymbol", r"\mathbb", r"\mathcal"}
# Parens after a function can only be dropped if what follows can't attach to the argument:
# \log(x)^2 is (log x)^2, not log(x^2); \sin(x)y is sin(x)*y, not sin(xy).
_SAFE_AFTER_PAREN = {"+", "-", "=", "<", ">", ",", ")", "]", "}", "\\\\", r"\endrows", r"\cdot",
                     r"\times", r"\leq", r"\geq", r"\neq", r"\to", r"\pm", r"\mp", "/"}
# Every multi-row layout (a system written as two stacked lines) reads the same in the confirm box.
_ENV_BEGIN = re.compile(r"\\begin\{(?:matrix|cases|array|aligned|gathered|split|align\*?)\}(?:\{[lcr|]*\})?")
_ENV_END = re.compile(r"(?:\\\\\s*)?\\end\{(?:matrix|cases|array|aligned|gathered|split|align\*?)\}")
STRUCTURAL = {"^", "_", "{", "}", r"\frac"}


def _merge_function_letters(tokens: list[str]) -> list[str]:
    """Readers often spell functions as plain letters (lnx, log1000): treat them as \\ln, \\log."""
    out, i = [], 0
    while i < len(tokens):
        for name in _FUNC_NAMES:
            if "".join(tokens[i:i + len(name)]) == name and all(len(t) == 1 for t in tokens[i:i + len(name)]):
                out.append("\\" + name)
                i += len(name)
                break
        else:
            out.append(tokens[i])
            i += 1
    return out


def _match(tokens: list[str], i: int, open_: str, close: str) -> int:
    """Index of the token closing the group opened at i, or -1."""
    depth = 0
    for j in range(i, len(tokens)):
        depth += (tokens[j] == open_) - (tokens[j] == close)
        if depth == 0:
            return j
    return -1


def _operand_end(tokens: list[str], i: int) -> int:
    """Index just past one operand starting at i: a token, a {group}, \\frac A B or \\sqrt A. -1 if none."""
    if i >= len(tokens) or tokens[i] in ("}", ")"):
        return -1
    if tokens[i] == "{":
        j = _match(tokens, i, "{", "}")
        return j + 1 if j > 0 else -1
    n_args = {r"\frac": 2, r"\sqrt": 1}.get(tokens[i], 0)
    j = i + 1
    for _ in range(n_args):
        j = _operand_end(tokens, j)
        if j < 0:
            return -1
    return j


def _is_atom(content: list[str]) -> bool:
    return bool(content) and _operand_end(content, 0) == len(content)


def _safe_after(tokens: list[str], k: int) -> bool:
    if k >= len(tokens):
        return True
    nxt = tokens[k]
    if nxt in _SAFE_AFTER_PAREN or nxt in _FUNCS:
        return True
    # a differential: \sin(x)dx, \cos(\theta)d\theta
    return nxt == "d" and k + 1 < len(tokens) and (tokens[k + 1].isalpha() or tokens[k + 1].startswith("\\"))


def _strip_groups(tokens: list[str]) -> tuple[list[str], bool]:
    """Drop braces that only group (not arguments) and parens around one atom after a function."""
    for i, t in enumerate(tokens):
        prev = tokens[i - 1] if i else None
        if t == "{" and prev not in _ARG_TAKERS:
            j = _match(tokens, i, "{", "}")
            if j > 0:
                return tokens[:i] + tokens[i + 1:j] + tokens[j + 1:], True
        if t == "(" and prev in _FUNCS:
            j = _match(tokens, i, "(", ")")
            if j > 0 and _is_atom(tokens[i + 1:j]) and _safe_after(tokens, j + 1):
                return tokens[:i] + tokens[i + 1:j] + tokens[j + 1:], True
    return tokens, False


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
    latex = _ENV_END.sub(r" \\endrows ", _ENV_BEGIN.sub(r" \\rows ", latex))
    latex = _PRIME.sub(lambda m: m.group(1) or m.group(2), latex.replace(r"\prime", "'"))
    tokens = [_ALIAS.get(t, t) for t in _TOKEN.findall(latex) if t not in _DROP]
    tokens = _merge_function_letters(tokens)
    changed = True
    while changed:
        tokens, c1 = _strip_single(tokens, "{", "}")
        tokens, c2 = _strip_groups(tokens)
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
