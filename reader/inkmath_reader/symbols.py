"""Turn a RawReading into tappable symbols: text span, confidence, low flag, up to 3 alternatives."""
import difflib
import re
from dataclasses import dataclass, field

from .recognize import RawReading

MAX_ALTERNATIVES = 3

_UNIT = re.compile(r"\\[A-Za-z]+|\\.|\S")

# Handwriting look-alikes. Each group is symmetric: every member offers the others.
_GROUPS = [
    ["x", "\\times"], ["1", "l", "|"], ["2", "z"], ["5", "s"], ["0", "o", "\\theta"], ["9", "g", "q"],
    ["6", "b"], ["7", "\\tau"], ["t", "+"], ["u", "v"], ["\\pi", "n"], ["-", "="], ["\\leq", "<"],
    ["\\geq", ">"], ["\\alpha", "a"], ["e", "c"], ["y", "4"], ["(", "|"],
]
CONFUSIONS: dict[str, list[str]] = {}
for _g in _GROUPS:
    for _a in _g:
        CONFUSIONS.setdefault(_a, []).extend(b for b in _g if b != _a and b not in CONFUSIONS.get(_a, []))


@dataclass
class Symbol:
    text: str
    start: int
    end: int
    confidence: float
    low: bool
    alternatives: list[str] = field(default_factory=list)


def split_symbols(latex: str) -> list[tuple[str, int, int]]:
    """Symbol units: a command, an escaped character, or any single non-space character."""
    return [(m.group(), m.start(), m.end()) for m in _UNIT.finditer(latex)]


# LaTeX syntax, not math a tutor would pick: offered only in place of another syntax piece.
_SYNTAX = {"\\", "{", "}", "^", "_", "&"}


def _is_unit(s: str) -> bool:
    units = split_symbols(s)
    return len(units) == 1 and units[0][0] == s


def _fits(alt: str, text: str) -> bool:
    return alt != text and _is_unit(alt) and (alt in _SYNTAX) == (text in _SYNTAX)


def _raw_symbols(reading: RawReading):
    """(text, start, end, confidence, model alternatives) for each unit of reading.raw."""
    spans, pos = [], 0
    for step in reading.steps:
        spans.append((pos, pos + len(step.text), step))
        pos += len(step.text)
    out = []
    for text, s, e in split_symbols(reading.raw):
        over = [(ts, te, st) for ts, te, st in spans if ts < e and te > s]
        conf = min((st.prob for _, _, st in over), default=1.0)
        alts = []
        if over:
            ts, te, st = over[0]
            for alt, _ in st.alts:
                cand = reading.raw[s:max(s, ts)] + alt.strip() + reading.raw[min(te, e):e]
                if _fits(cand, text) and cand not in alts:
                    alts.append(cand)
        out.append((text, s, e, conf, alts))
    return out


def _with_confusions(text: str, alts: list[str]) -> list[str]:
    out = list(alts)
    for c in CONFUSIONS.get(text, []):
        if c != text and c not in out:
            out.append(c)
    return out[:MAX_ALTERNATIVES]


def build_symbols(reading: RawReading, low_threshold: float) -> list[Symbol]:
    raw = _raw_symbols(reading)
    final = split_symbols(reading.latex)
    sm = difflib.SequenceMatcher(None, [r[0] for r in raw], [f[0] for f in final], autojunk=False)
    out: list[Symbol] = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "delete":
            continue
        for k, (text, s, e) in enumerate(final[j1:j2]):
            if op == "equal":
                conf, alts = raw[i1 + k][3], raw[i1 + k][4]
            elif op == "replace":
                conf, alts = min(r[3] for r in raw[i1:i2]), []
            else:  # insert: formatting added by post-processing
                conf, alts = 1.0, []
            out.append(Symbol(text, s, e, conf, conf < low_threshold, _with_confusions(text, alts)))
    return out
