import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_all_prompts() -> list[dict]:
    out = []
    for f in ("samples/prompts_test.json", "samples/prompts_tune.json"):
        out += json.load(open(ROOT / f, encoding="utf-8"))
    return out


def run(latex, fn, point=None):
    from inkmath_solver.parse import parse_problem
    p = parse_problem(latex)
    if p.kind == "function_def":
        var = p.symbols[0]
    else:
        var = p.symbols[0] if p.symbols else None
    return fn(p, var, point)
