"""Gate the tuned model against the base on the test set, check latency, calibrate the low-confidence threshold.

  cd reader
  .venv\\Scripts\\python -m train.evaluate        (CPU venv, so the timings are real)

Writes models/texteller-tuned/accepted.json, models/reader_calibration.json and an aggregate-only report.
"""
import argparse
import difflib
import json
import statistics
import sys
import time
from pathlib import Path

from inkmath_reader import paths
from inkmath_reader.calibration import FILE_NAME as CALIBRATION_FILE
from inkmath_reader.render import render
from inkmath_reader.symbols import build_symbols, split_symbols

from .dataset import load_tune

LATENCY_FACTOR = 1.15
TARGET_RECALL = 0.90
MAX_FLAGGED = 0.20
GRID = [round(0.50 + i * 0.01, 2) for i in range(50)]          # 0.50 .. 0.99


def gate(base: dict, tuned: dict) -> bool:
    """Tuned is accepted only if it is at least as accurate and at most 15% slower."""
    return (tuned["zero_rate"] >= base["zero_rate"] and tuned["le2_rate"] >= base["le2_rate"]
            and tuned["median_ms"] <= LATENCY_FACTOR * base["median_ms"])


def choose_threshold(confs_wrong: list[float], confs_all: list[float]) -> tuple[float, float, float]:
    """Smallest grid threshold catching ≥90% of wrong symbols; if that flags >20% of all symbols,
    the largest threshold flagging ≤20% instead. Returns (threshold, recall, flagged share)."""
    def stats(t):
        recall = sum(c < t for c in confs_wrong) / len(confs_wrong) if confs_wrong else 1.0
        flagged = sum(c < t for c in confs_all) / len(confs_all) if confs_all else 0.0
        return recall, flagged

    for t in GRID:
        recall, flagged = stats(t)
        if recall >= TARGET_RECALL:
            if flagged <= MAX_FLAGGED:
                return t, recall, flagged
            break
    ok = [t for t in GRID if stats(t)[1] <= MAX_FLAGGED]
    t = max(ok) if ok else GRID[0]
    return (t, *stats(t))


def wrong_flags(pred: list[str], truth: list[str]) -> list[bool]:
    """For each predicted symbol: True when it falls outside an `equal` block against the truth."""
    flags = [True] * len(pred)
    for op, i1, i2, _, _ in difflib.SequenceMatcher(None, pred, truth, autojunk=False).get_opcodes():
        if op == "equal":
            for i in range(i1, i2):
                flags[i] = False
    return flags


_SYNTAX = {"{", "}", "^", "_", "\\left", "\\right"}


def misread_flags(pred: list[str], truth_latex: str, fixes: int) -> list[bool]:
    """Which predicted symbols are misreads. A problem the scorer counts as zero fixes has none (equivalent
    forms are not misreads), and LaTeX syntax pieces never count; the rest are aligned with the truth."""
    if fixes == 0:
        return [False] * len(pred)
    keep = [i for i, t in enumerate(pred) if t not in _SYNTAX]
    truth = [t for t, _, _ in split_symbols(truth_latex) if t not in _SYNTAX]
    flags = [False] * len(pred)
    for i, wrong in zip(keep, wrong_flags([pred[i] for i in keep], truth)):
        flags[i] = wrong
    return flags


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def render_report(base: dict, tuned: dict | None, accepted: bool, threshold: tuple, train_log: str, n_tune: int,
                  n_misread: int) -> str:
    t, recall, flagged = threshold
    rows = [("Base (untuned)", base)] + ([("Tuned", tuned)] if tuned else [])
    lines = [
        "# M4 personal tuning results",
        "",
        f"**Tuned model: {'Accepted' if accepted else 'Rejected'}.** Gate: tuned zero-fix and ≤2-fix rates at least the "
        f"base's, and warm median latency at most {LATENCY_FACTOR:.2f}× the base's.",
        "",
        f"- Test set: {base['n']} problems (the user's handwriting, local only). Tune set: {n_tune} problems.",
        "- Timing: warm read on the dev CPU (GPU not used), model only, median over the test set.",
        "",
        "| Model | Zero fixes | ≤2 fixes | Median ms |",
        "|---|---|---|---|",
    ]
    lines += [f"| {name} | {_pct(s['zero_rate'])} | {_pct(s['le2_rate'])} | {s['median_ms']:.0f} |" for name, s in rows]
    lines += ["", "By area (zero fixes / ≤2 fixes):", ""]
    for name, s in rows:
        areas = ", ".join(f"{a} {_pct(r['zero_rate'])} / {_pct(r['le2_rate'])}" for a, r in s.get("by_area", {}).items())
        lines.append(f"- {name}: {areas}")
    lines += [
        "",
        "## Low-confidence threshold",
        "",
        f"Threshold **{t}**: flags {_pct(recall)} of misread symbols and {_pct(flagged)} of all symbols "
        f"(target: ≥{_pct(TARGET_RECALL)} of misreads, at most {_pct(MAX_FLAGGED)} of symbols). A misread is a "
        "symbol that differs from the expected answer in a problem the scorer says needs fixes; LaTeX syntax "
        "pieces (braces, ^, _) never count.",
        "",
        f"Measured on {n_misread} misread symbols in the whole test set, so the recall figure is a rough guide. "
        "Real corrections collected from M5 on will refine it.",
        "",
        "## Training log",
        "",
        "```",
        train_log.strip(),
        "```",
        "",
    ]
    return "\n".join(lines)


def _evaluate(rec, samples, score_mod):
    """Results for the scorer, plus (confidence, wrong) for every recognized symbol."""
    rec.read(render(samples[0].strokes))                         # warm-up
    results, confs_all, confs_wrong = [], [], []
    for s in samples:
        img = render(s.strokes)
        t0 = time.perf_counter()
        reading = rec.read(img)
        ms = (time.perf_counter() - t0) * 1000
        fixes = score_mod.fixes(reading.latex, s.latex)
        results.append(score_mod.Result(s.id, s.area, reading.latex, s.latex, fixes, ms))
        syms = build_symbols(reading, 0.0)
        flags = misread_flags([x.text for x in syms], s.latex, fixes)
        for sym, wrong in zip(syms, flags):
            confs_all.append(sym.confidence)
            if wrong:
                confs_wrong.append(sym.confidence)
    return results, confs_all, confs_wrong


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="train.evaluate")
    ap.add_argument("--models", default=None)
    ap.add_argument("--ink-dir", default=str(paths.REPO / "data" / "ink"))
    ap.add_argument("--prompts", default=str(paths.REPO / "samples" / "prompts_test.json"))
    ap.add_argument("--tune-prompts", default=str(paths.REPO / "samples" / "prompts_tune.json"))
    ap.add_argument("--report", default=str(paths.REPO / "docs" / "superpowers" / "spike" / "2026-11-m4-tuning-results.md"))
    a = ap.parse_args(argv)

    sys.path.insert(0, str(paths.REPO / "spike"))
    from inkspike import score as score_mod
    from inkmath_reader.recognize import Recognizer
    from inkmath_reader.server import TUNED_DIR

    models = paths.models_dir(a.models)
    tuned_dir = models / TUNED_DIR
    areas = {p["id"]: p["area"] for p in json.loads(Path(a.prompts).read_text(encoding="utf-8"))}
    samples = load_tune(Path(a.ink_dir), Path(a.prompts), manifest="test_manifest.json")
    for s in samples:
        s.area = areas[s.id]

    base_rec = Recognizer(models)
    base_res, b_all, b_wrong = _evaluate(base_rec, samples, score_mod)
    base = score_mod.summarize(base_res)
    del base_rec
    print(f"base: zero {base['zero_rate']:.3f} le2 {base['le2_rate']:.3f} median {base['median_ms']:.0f} ms", flush=True)

    tuned, accepted, confs = None, False, (b_all, b_wrong)
    if (tuned_dir / "config.json").exists():
        tuned_res, t_all, t_wrong = _evaluate(Recognizer(models, tuned_dir), samples, score_mod)
        tuned = score_mod.summarize(tuned_res)
        accepted = gate(base, tuned)
        print(f"tuned: zero {tuned['zero_rate']:.3f} le2 {tuned['le2_rate']:.3f} median {tuned['median_ms']:.0f} ms "
              f"-> {'accepted' if accepted else 'rejected'}", flush=True)
        keep = ("n", "zero_rate", "le2_rate", "median_ms")
        (tuned_dir / "accepted.json").write_text(json.dumps(
            {"accepted": accepted, "base": {k: base[k] for k in keep}, "tuned": {k: tuned[k] for k in keep}}, indent=2),
            encoding="utf-8")
        if accepted:
            confs = (t_all, t_wrong)

    threshold = choose_threshold(confs[1], confs[0])
    (models / CALIBRATION_FILE).write_text(json.dumps(
        {"low_threshold": threshold[0], "recall": threshold[1], "flagged": threshold[2]}, indent=2), encoding="utf-8")
    log_path = tuned_dir / "train_log.txt"
    n_tune = len(load_tune(Path(a.ink_dir), Path(a.tune_prompts)))
    Path(a.report).write_text(render_report(base, tuned, accepted, threshold,
                                            log_path.read_text(encoding="utf-8") if log_path.exists() else "(not trained)",
                                            n_tune, len(confs[1])), encoding="utf-8")
    print(f"threshold {threshold[0]} recall {threshold[1]:.2f} flagged {threshold[2]:.2f}; report {a.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
