# M1 Handwriting Accuracy Spike: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure how accurately offline handwritten-math recognizers read *this user's* handwriting, before and after tuning on their samples, and produce a go/no-go report against the spec's accuracy gate.

**Architecture:** A throwaway-quality but tested Python toolkit (`spike/inkspike`) talks to OneNote through its COM API (pywin32). It (1) generates prompt pages the user hand-copies on the Surface, (2) after OneDrive sync, pulls the ink back on the dev machine, decodes it to strokes, and renders PNGs, (3) runs candidate recognizers through one adapter interface, and (4) scores them with a LaTeX token edit distance. A fine-tuning experiment on the dev GPU measures the tuned score that the gate is judged on.

**Tech Stack:** Python 3.10 (dev machine, `C:\Python310`), pywin32 (OneNote COM), `winrt-Windows.UI.Input.Inking` + `winrt-Windows.Storage.Streams` (ISF decoding), Pillow, pytest, candidate recognizers (pix2text MFR, TexTeller, optional third), PyTorch with CUDA for fine-tuning (RTX 3080).

**Spec:** `docs/superpowers/specs/2026-11-09-onenote-ink-math-design.md` (§3, §5, §6.3, §6.7). Roadmap: `docs/superpowers/plans/2026-11-09-roadmap.md`.

## Global Constraints

- Gate: on the test set, **≥70% of problems need zero fixes and ≥95% need ≤2 fixes**, measured after tuning.
- Math scope of prompts: basic algebra through Calc 2 (spec §5 table), including ∫ with limits, dx, exponents, fractions, roots, lim, Σ, trig names, Greek letters.
- Recognition must be able to run **CPU-only** on an i7-1185G7 / 16 GB (record CPU latency per model; target ≈1–2 s per problem on the Surface, which is about 1.5–2× slower than the dev machine's Ryzen 7 3700X).
- Handwriting data is the user's and involves teaching material: `data/` and `models/` are **git-ignored** and never uploaded anywhere.
- OneNote on the dev machine is **32-bit**. Nothing in M1 may assume 64-bit.
- Samples are written **on the Surface** in a dedicated section and reach the dev machine through the user's OneNote/OneDrive sync (same Microsoft account).
- Ground-truth LaTeX must be in the forms recognizers emit (`\frac{}{}`, `\int_{0}^{\pi}`, `\sin x`, `\lim_{x \to 0}`, `\sum_{n=1}^{\infty}`).

## Review Focus

1. **Notebook not syncing / wrong notebook:** if the chosen notebook isn't on OneDrive, or sync hasn't finished, extraction finds no ink. Expected: the extractor prints per-page ink counts and fails loudly ("page 'Ink Math Test 3' has 0 strokes; has it synced?") instead of scoring 0%. Test in Task 3.
2. **Ink outside a prompt's band, or a skipped prompt:** the user writes slightly into the next prompt's area or skips one. Expected: strokes go to the nearest prompt *above* them; prompts with no strokes are reported as `missing` and excluded from the denominator, listed by id. Test in Task 3.
3. **Ink stored as `InkWord` inside outlines instead of `InkDrawing`:** OneNote can store pen ink either way. Expected: both are extracted. Test in Task 3.
4. **Equivalent LaTeX scored as an error:** `\sin(x)` vs `\sin x`, `\,dx` vs `dx`, `\mathrm{d}x`, `\left(` vs `(`, `\dfrac` vs `\frac`. Expected: they normalize equal. Test in Task 4.
5. **Coordinate units differ between pages/devices:** Surface ink may arrive in HIMETRIC with a different scale or offset. Expected: rendering normalizes each problem by its own bounding box, so the PNG looks the same regardless of absolute units. Test in Task 3.

---

### Task 1: Repo scaffold and prompt sets

**Files:**
- Create: `.gitignore`, `spike/requirements.txt`, `spike/pytest.ini`, `spike/inkspike/__init__.py`, `spike/inkspike/prompts.py`
- Create: `samples/prompts_test.json`, `samples/prompts_tune.json`
- Create: `.claude/progress.json`
- Test: `spike/tests/test_prompts.py`

**Interfaces:**
- Produces: `Prompt` dataclass `(id: str, area: str, display: str, latex: str)`; `load_prompts(path: str) -> list[Prompt]`. `area` ∈ `{"algebra","precalc","calc1","calc2"}`. Ids are `T01..T60` (test) and `U01..U60` (tune).

- [ ] **Step 1: Create the scaffold.** `.gitignore` covers `spike/.venv/`, `data/`, `models/`, `__pycache__/`, `.pytest_cache/`. `requirements.txt`: `pywin32`, `pillow`, `pytest`, `winrt-runtime`, `winrt-Windows.UI.Input.Inking`, `winrt-Windows.Storage.Streams`, `winrt-Windows.Foundation`, `winrt-Windows.Foundation.Collections`. `pytest.ini` defines markers `onenote` (needs the OneNote desktop app) and `samples` (needs synced user samples). Create the venv: `python -m venv spike\.venv; spike\.venv\Scripts\pip install -r spike\requirements.txt`. Expected: install succeeds.
- [ ] **Step 2: Write the failing test** `spike/tests/test_prompts.py`:

```python
from inkspike.prompts import load_prompts

def _check(path, prefix):
    ps = load_prompts(path)
    assert len(ps) == 60
    assert len({p.id for p in ps}) == 60
    assert all(p.id.startswith(prefix) for p in ps)
    counts = {a: sum(p.area == a for p in ps) for a in ("algebra", "precalc", "calc1", "calc2")}
    assert counts == {"algebra": 15, "precalc": 10, "calc1": 15, "calc2": 20}
    assert all(p.display and p.latex for p in ps)
    return ps

def test_test_set(): _check("samples/prompts_test.json", "T")
def test_tune_set(): _check("samples/prompts_tune.json", "U")

def test_sets_do_not_overlap():
    a = {p.latex for p in load_prompts("samples/prompts_test.json")}
    b = {p.latex for p in load_prompts("samples/prompts_tune.json")}
    assert not a & b

def test_coverage_of_hard_layouts():
    ps = load_prompts("samples/prompts_test.json")
    joined = " ".join(p.latex for p in ps)
    for needle in (r"\int_", r"\frac", "^", r"\sqrt", r"\lim_", r"\sum_", r"\sin", r"\theta", r"\ln", r"\infty"):
        assert needle in joined, needle
```

- [ ] **Step 3: Run it.** `cd spike; .venv\Scripts\pytest tests/test_prompts.py -v`. Expected: FAIL (module/files missing).
- [ ] **Step 4: Implement `load_prompts` and write both JSON files** (a list of objects with the four fields). Calc2 has 12 integrals (by parts, substitution, partial fractions, trig substitution, improper) and 8 series. Each set has at least 2 multi-line systems (`\begin{cases}`) and 3 problems with no explicit operation (e.g. `x^2+5x+6`). `display` is plain Unicode the user copies (e.g. `∫₀^π x sin x dx`). Each set should take about 10 minutes to hand-copy: keep problems at most about 25 symbols.
- [ ] **Step 5: Run the tests.** Same command. Expected: 4 passed.
- [ ] **Step 6: Update `.claude/progress.json`** (it already exists): mark M1 "Scaffold and prompt sets" done and bump `updated`. In every later task, mark that task's matching M1 step done.
- [ ] **Step 7: Commit.** `rtk git add .gitignore spike samples .claude/progress.json; rtk git commit -m "spike: scaffold and prompt sets"`

### Task 2: Generate prompt pages in OneNote

**Files:**
- Create: `spike/inkspike/onenote_io.py`, `spike/make_pages.py`
- Test: `spike/tests/test_onenote_io.py`

**Interfaces:**
- Consumes: `load_prompts`, `Prompt`.
- Produces:
  - `NS = "http://schemas.microsoft.com/office/onenote/2013/onenote"`
  - `build_prompt_page_xml(page_id: str, title: str, prompts: list[Prompt], top: float = 80.0, gap: float = 140.0) -> str`: prompt *i* is a typed outline at `x=36, y=top + i*gap` with text `"{id}. {display}"`.
  - `band_tops(n: int, top: float = 80.0, gap: float = 140.0) -> list[float]`
  - `class OneNote` with `list_notebooks() -> list[tuple[str, str]]` (name, id), `ensure_section(notebook_id: str, name: str) -> str`, `create_page(section_id: str, xml_builder) -> str`, `get_page_xml(page_id: str, binary: bool) -> str`, `pages_in_section(section_id: str) -> list[tuple[str, str]]` (title, id), `delete_page(page_id: str) -> None`.
  - Section names: `"Ink Math Test"` and `"Ink Math Tune"`. Page titles: `"Ink Math Test 1".."Ink Math Test 6"` (10 prompts each), same pattern for Tune.

- [ ] **Step 1: Write the failing tests.**

```python
import xml.etree.ElementTree as ET
from inkspike.onenote_io import build_prompt_page_xml, band_tops, NS
from inkspike.prompts import Prompt

P = [Prompt("T01", "calc2", "∫₀^π x sin x dx", r"\int_{0}^{\pi} x \sin x \, dx"),
     Prompt("T02", "algebra", "x² + 5x + 6", "x^2+5x+6")]

def test_page_xml_has_title_and_positioned_prompts():
    root = ET.fromstring(build_prompt_page_xml("{PAGE}", "Ink Math Test 1", P))
    assert root.find(f".//{{{NS}}}Title//{{{NS}}}T").text == "Ink Math Test 1"
    outlines = root.findall(f"{{{NS}}}Outline")
    ys = [float(o.find(f"{{{NS}}}Position").get("y")) for o in outlines]
    assert ys == band_tops(2)
    assert "T01. ∫₀^π x sin x dx" in ET.tostring(root, encoding="unicode")

def test_band_tops():
    assert band_tops(3) == [80.0, 220.0, 360.0]

import pytest
@pytest.mark.onenote
def test_roundtrip_in_scratch_section():
    from inkspike.onenote_io import OneNote
    on = OneNote()
    nb = on.list_notebooks()[0][1]
    sec = on.ensure_section(nb, "Ink Math Spike Scratch")
    pid = on.create_page(sec, lambda page_id: build_prompt_page_xml(page_id, "scratch", P))
    try:
        assert "T02. x² + 5x + 6" in on.get_page_xml(pid, binary=False)
    finally:
        on.delete_page(pid)
```

- [ ] **Step 2: Run them.** `.venv\Scripts\pytest tests/test_onenote_io.py -v`. Expected: FAIL (import error).
- [ ] **Step 3: Implement `onenote_io.py`** with `win32com.client.Dispatch("OneNote.Application")`. Use `GetHierarchy("", hsSections=2)` and `GetHierarchy(section_id, hsPages=4)`, `OpenHierarchy(path, notebook_id, out, cftSection=3)` for `ensure_section` (path = `"<name>.one"` relative to the notebook), `CreateNewPage`, `UpdatePageContent`, and `GetPageContent(page_id, pageInfo)` (`piBasic=0`, `piBinaryData=1`). `ensure_section` returns the existing section if one with that name exists.
- [ ] **Step 4: Run the tests.** Expected: 3 passed. OneNote must be running; delete the scratch section by hand afterward.
- [ ] **Step 5: Implement `make_pages.py`** (CLI): `python make_pages.py --notebook "<name>"` lists notebooks when the name is missing or wrong. It creates both sections and 6 pages in each. It refuses to run if the section already has pages (so it never duplicates). After creating, it prints: "Created 12 pages. On the Surface, open each page and write each problem in the space under it."
- [ ] **Step 6: Commit.** `rtk git commit -am "spike: OneNote prompt page generator"` (add new files first).
- [ ] **Step 7: USER STEP (pause execution here).** Ask the user which notebook to use. It must be one synced to OneDrive and open on both machines. Run `make_pages.py`, then ask the user to write all 120 problems on the Surface with their normal pen and normal handwriting (about 20 minutes total). Each answer goes under its prompt, before the next prompt's line. Continue only after the user confirms they're done and the pages have synced.

### Task 3: Extract ink, decode, group, render

**Files:**
- Create: `spike/inkspike/isf.py`, `spike/inkspike/extract.py`, `spike/inkspike/render.py`, `spike/extract_all.py`
- Test: `spike/tests/test_isf.py`, `spike/tests/test_extract.py`, `spike/tests/test_render.py`, `spike/tests/fixtures/page_inkword.xml`, `spike/tests/fixtures/page_inkdrawing.xml`

**Interfaces:**
- Consumes: `OneNote`, `band_tops`, `load_prompts`.
- Produces:
  - `Stroke = list[tuple[float, float]]`
  - `decode_isf(data: bytes) -> list[Stroke]` (via WinRT `InkStrokeContainer.load_async`; points from `get_ink_points()`)
  - `encode_isf(strokes: list[Stroke]) -> bytes` (test helper using `InkStrokeBuilder` + `save_async`)
  - `ink_items(page_xml: str) -> list[tuple[float, float, bytes]]`: (page x, page y, ISF bytes) for every `InkDrawing` and every `InkWord`, with the element's `Position` (an `InkWord` without its own position inherits its `Outline`'s)
  - `assign_to_bands(items_y: list[float], tops: list[float]) -> list[int]` (index of the nearest band top at or above y; ink above the first band goes to band 0)
  - `render_png(strokes: list[Stroke], path: str, height_px: int = 256, pad_px: int = 16, width_px_line: int = 3) -> None` (scale to the bounding box, black on white)
  - CLI `extract_all.py --set test|tune` writes `data/ink/<id>.json` (strokes) and `data/ink/<id>.png`, plus `data/ink/<set>_manifest.json` = `{"ok": [...ids], "missing": [...ids]}`.

- [ ] **Step 1: Verify the ink format on real data first (no test).** After Task 2's user step, dump one synced page with `get_page_xml(pid, binary=True)` to `data/debug_page.xml`. Confirm the ink appears as `one:InkDrawing` and/or `one:InkWord`, each with a base64 `one:Data` element. Confirm that `decode_isf` on one of them returns points. Copy one trimmed, sanitized element of each kind into the two fixture files. **If the data is not ISF or WinRT decoding fails, stop and report to the user before going on.** The fallback is a small C# helper, which needs the .NET SDK.
- [ ] **Step 2: Write the failing tests.**

```python
# test_isf.py
from inkspike.isf import encode_isf, decode_isf
def test_isf_roundtrip():
    s = [[(0, 0), (10, 5), (20, 0)], [(5, 10), (5, 30)]]
    out = decode_isf(encode_isf(s))
    assert len(out) == 2 and len(out[0]) >= 3

# test_extract.py
from inkspike.extract import ink_items, assign_to_bands
def test_inkword_and_inkdrawing_both_found():
    for f in ("page_inkword.xml", "page_inkdrawing.xml"):
        assert len(ink_items(open(f"tests/fixtures/{f}", encoding="utf-8").read())) >= 1
def test_assign_to_bands_nearest_above():
    assert assign_to_bands([90, 219, 221, 10], [80.0, 220.0, 360.0]) == [0, 0, 1, 0]

# test_render.py  (also Review Focus 5)
from PIL import Image
from inkspike.render import render_png
def test_render_normalizes_scale(tmp_path):
    a = [[(0, 0), (100, 50)]]; b = [[(5000, 7000), (15000, 12000)]]
    render_png(a, tmp_path / "a.png"); render_png(b, tmp_path / "b.png")
    ia, ib = Image.open(tmp_path / "a.png"), Image.open(tmp_path / "b.png")
    assert ia.size == ib.size and ia.getbbox() == ib.getbbox()
```

- [ ] **Step 3: Run them.** `.venv\Scripts\pytest tests/test_isf.py tests/test_extract.py tests/test_render.py -v`. Expected: FAIL (imports).
- [ ] **Step 4: Implement `isf.py`, `extract.py`, and `render.py`** with the signatures above. In `extract_all.py`, the band for each ink item comes from its y position. Group the strokes by band, map band *i* on page *k* to prompt index `10*(k-1)+i`, and write the outputs.
- [ ] **Step 5: Run the tests.** Expected: 4 passed.
- [ ] **Step 6: Add the Review Focus 1–2 tests to `test_extract.py`:**
  - `test_manifest_lists_missing`: given band assignments with one empty band, the manifest builder returns that prompt id under `missing`.
  - `test_zero_ink_page_raises`: a page with no ink raises `NoInkError` whose message contains the page title and "synced". (Factor manifest building into `build_manifest(assignments: dict[str, int]) -> dict` and page checking into `check_page_has_ink(title: str, items: list) -> None` in `extract.py`.)
  Run them to see them fail, implement, and run again to see them pass.
- [ ] **Step 7: Run the real extraction.** `.venv\Scripts\python extract_all.py --set test` and then `--set tune`. Expected: each prints "ok: N, missing: M" with N ≥ 55. Open 5 random PNGs to check that each one looks like its prompt.
- [ ] **Step 8: Commit** (code and fixtures only; `data/` is ignored). `rtk git commit -m "spike: ink extraction and rendering"`

### Task 4: Scoring harness

**Files:**
- Create: `spike/inkspike/score.py`, `spike/evaluate.py`
- Test: `spike/tests/test_score.py`

**Interfaces:**
- Produces:
  - `normalize(latex: str) -> list[str]`: a token list
  - `fixes(pred: str, truth: str) -> int`: Levenshtein distance over `normalize` tokens
  - `Result(id, area, pred, truth, fixes, ms)` dataclass
  - `summarize(results: list[Result]) -> dict` with keys `zero_rate`, `le2_rate`, `passed` (bool: `zero_rate >= 0.70 and le2_rate >= 0.95`), `by_area`, `median_ms`
  - `class Recognizer(Protocol): name: str; def recognize(self, png_path: str) -> str: ...`
  - CLI `evaluate.py --model <name> --set test [--weights <dir>]` writes `reports/<name>[-tuned].md` (git-ignored copy in `data/reports/`, and a committed summary table only, without handwriting images)

- [ ] **Step 1: Write the failing tests** (including Review Focus 4):

```python
from inkspike.score import normalize, fixes, summarize, Result

def test_equivalent_forms_normalize_equal():
    pairs = [(r"\sin(x)", r"\sin x"), (r"x\,dx", "x dx"), (r"\mathrm{d}x", "dx"),
             (r"\left(x+1\right)", "(x+1)"), (r"\dfrac{1}{2}", r"\frac{1}{2}"), ("{x}^{2}", "x^2")]
    for a, b in pairs:
        assert normalize(a) == normalize(b), (a, b)

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
```

- [ ] **Step 2: Run it.** `.venv\Scripts\pytest tests/test_score.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement `score.py`.** The tokenizer splits on `\command`, single characters, `{`, `}`, `^`, and `_`. It drops whitespace, `\,` `\;` `\!` `\left` `\right`, and braces around a single token. It maps `\dfrac`/`\tfrac`→`\frac` and `\mathrm{d}`→`d`, and drops the parentheses directly after a trig/log command when they enclose a single token.
- [ ] **Step 4: Run it.** Expected: 3 passed.
- [ ] **Step 5: Implement `evaluate.py`.** It times each `recognize` call (wall-clock ms, CPU only: set `CUDA_VISIBLE_DEVICES=""`), excludes `missing` ids, and writes a report with: the summary, a by-area table, the 10 worst items as (id, truth, pred, fixes), and a count of errors that are *structural* (a `^`, `_`, `{`, `}`, or `\frac` token is involved) vs *symbol*.
- [ ] **Step 6: Commit.** `rtk git commit -m "spike: scoring harness"`

### Task 5: Candidate recognizers (baseline)

**Files:**
- Create: `spike/models/__init__.py` (registry `get(name: str) -> Recognizer`), `spike/models/pix2text_mfr.py`, `spike/models/texteller.py`, optional `spike/models/<third>.py`
- Modify: `spike/requirements.txt` (add per-model packages)
- Test: `spike/tests/test_models.py`

**Interfaces:**
- Consumes: the `Recognizer` protocol from Task 4.
- Produces: registry names `"pix2text"`, `"texteller"`, and optionally one third name. Each `recognize(png_path) -> str` returns a LaTeX string.

- [ ] **Step 1: Write the failing test** `test_models.py` (marked `samples`): for each registered model, `recognize` on the PNG for the first `ok` id in `data/ink/test_manifest.json` returns a non-empty string in under 10 s.
- [ ] **Step 2: Run it.** `.venv\Scripts\pytest tests/test_models.py -v -m samples`. Expected: FAIL.
- [ ] **Step 3: Implement the adapters.** pix2text: its math-formula recognizer (MFR) on the PNG, ONNX/CPU. TexTeller: its inference API, CPU. Third (optional, only if one of the first two can't be fine-tuned in Task 6): a CROHME-trained handwritten-math model with public weights. Pin exact package versions in `requirements.txt`.
- [ ] **Step 4: Run it.** Expected: passed for every registered model.
- [ ] **Step 5: Run the baselines.** `.venv\Scripts\python evaluate.py --model <each> --set test`. Expected: one report per model. Record zero_rate, le2_rate, and median_ms.
- [ ] **Step 6: Commit.** `rtk git commit -m "spike: baseline recognizers"`

### Task 6: Tuning experiment, gate report, and hand-off

**Files:**
- Create: `spike/finetune.py`, `docs/superpowers/spike/2026-11-m1-accuracy-results.md`
- Modify: `.claude/progress.json`

**Interfaces:**
- Consumes: `Recognizer` adapters (Task 5), the tune set from `data/ink/` (Task 3), `evaluate.py --weights` (Task 4).
- Produces: `finetune.py --model <name> --out models/<name>-tuned` (GPU), loadable by the same adapter via `--weights`.

- [ ] **Step 1: Install PyTorch with CUDA in the venv** (build matching the 617.x driver) and confirm `torch.cuda.is_available()` is `True`.
- [ ] **Step 2: Implement `finetune.py`** for the best-baseline model that can be fine-tuned. Train only on the **tune** set (`U01–U60`), with augmentation (small rotation, scale, stroke-width jitter, elastic distortion). Mixing in public handwritten-math data such as CROHME or MathWriting is allowed to prevent overfitting. Do not use any test-set ink. The adaptation method is the implementer's choice; it must produce weights that run on CPU.
- [ ] **Step 3: Evaluate.** `evaluate.py --model <name> --set test --weights models/<name>-tuned`. Expected: a report with the tuned zero_rate, le2_rate, and CPU median_ms.
- [ ] **Step 4: Write `2026-11-m1-accuracy-results.md`:** the baseline vs tuned table for each model, gate PASS/FAIL, the structural vs symbol error split, and estimated Surface latency (dev ms × 1.75). The recommendation is one of:
  - PASS: proceed to M4 with model X.
  - FAIL: fallback 1, accept more taps. Include the expected average taps per problem and which structural fixes the confirm panel must prioritize, based on the error split.
  - FAIL badly (le2_rate < 0.80): flag fallback 2 (online reader) to the user early.
- [ ] **Step 5: Mark M1 done** in `.claude/progress.json` and bump `updated`.
- [ ] **Step 6: Commit.** `rtk git add docs spike .claude; rtk git commit -m "spike: tuning experiment and gate report"`
- [ ] **Step 7: Report the gate result to the user** in plain words, and ask them to approve the next milestone plan.
