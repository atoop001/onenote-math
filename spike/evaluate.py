"""Score one recognizer on a prompt set.

Usage: python evaluate.py --model <name> --set test [--weights <dir>]
Writes data/reports/<name>[-tuned].md (git-ignored: it quotes handwriting results).
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

os.environ["CUDA_VISIBLE_DEVICES"] = ""  # time on CPU, like the Surface

from inkspike.prompts import load_prompts  # noqa: E402
from inkspike.score import Result, error_kind, fixes, summarize  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def run_eval(rec, prompts, ink_dir: Path, set_name: str, out_path: Path) -> dict:
    manifest = json.loads((ink_dir / f"{set_name}_manifest.json").read_text(encoding="utf-8"))
    ok = set(manifest["ok"])
    results = []
    for p in prompts:
        if p.id not in ok:
            continue
        t0 = time.perf_counter()
        pred = rec.recognize(str(ink_dir / f"{p.id}.png"))
        ms = (time.perf_counter() - t0) * 1000
        results.append(Result(p.id, p.area, pred, p.latex, fixes(pred, p.latex), ms))
    s = summarize(results)
    _write_report(rec.name, set_name, s, results, manifest["missing"], out_path)
    return s


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def _write_report(name, set_name, s, results, missing, out_path: Path) -> None:
    kinds = [error_kind(r.pred, r.truth) for r in results]
    lines = [
        f"# {name} on {set_name} set",
        "",
        f"- Items scored: {s['n']} (missing, not scored: {', '.join(missing) or 'none'})",
        f"- Zero fixes: {_pct(s['zero_rate'])} (gate 70%)",
        f"- Two fixes or fewer: {_pct(s['le2_rate'])} (gate 95%)",
        f"- Gate passed: {'yes' if s['passed'] else 'no'}",
        f"- Median time per problem (CPU): {s['median_ms']:.0f} ms",
        f"- Error types: structural: {kinds.count('structural')}, symbol: {kinds.count('symbol')}",
        "",
        "| Area | n | Zero fixes | ≤2 fixes |",
        "|---|---|---|---|",
    ]
    for area, a in s["by_area"].items():
        lines.append(f"| {area} | {a['n']} | {_pct(a['zero_rate'])} | {_pct(a['le2_rate'])} |")
    lines += ["", "## 10 worst", "", "| id | fixes | truth | predicted |", "|---|---|---|---|"]
    for r in sorted(results, key=lambda r: -r.fixes)[:10]:
        lines.append(f"| {r.id} | {r.fixes} | `{r.truth}` | `{r.pred}` |")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--set", default="test", choices=["test", "tune"])
    ap.add_argument("--weights", default=None)
    args = ap.parse_args()

    import models
    rec = models.get(args.model, weights=args.weights)
    prompts = load_prompts(ROOT / "samples" / f"prompts_{args.set}.json")
    suffix = "-tuned" if args.weights else ""
    out = ROOT / "data" / "reports" / f"{args.model}{suffix}.md"
    s = run_eval(rec, prompts, ROOT / "data" / "ink", args.set, out)
    print(f"{args.model}{suffix}: zero {_pct(s['zero_rate'])}, ≤2 {_pct(s['le2_rate'])}, "
          f"passed={s['passed']}, median {s['median_ms']:.0f} ms. Report: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
