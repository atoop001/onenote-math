# M1 handwriting accuracy results (2026-11-10)

**Gate: PASS.** TexTeller, untuned, CPU only. Recommendation: proceed to M4 with **TexTeller**.

## Setup

- 60 test problems (T01–T60: 15 algebra, 10 precalc, 15 calc 1, 20 calc 2), handwritten by the user on the Surface Pro 8 in OneNote, synced, and extracted on the dev machine (60/60 extracted).
- "Fixes" = token edit distance after normalizing forms that show the same math (see `spike/inkspike/score.py`).
- Gate (spec §6.3): ≥70% of problems need zero fixes **and** ≥95% need ≤2 fixes.
- Timing: warm call on the dev CPU (Ryzen 7 3700X, GPU hidden), not counting model load.

## Results (test set)

| Model | Tuned | Zero fixes | ≤2 fixes | Gate | Dev median | Est. Surface (×1.75) |
|---|---|---|---|---|---|---|
| TexTeller 1.0.2 | no | **93%** | **98%** | **PASS** | 1220 ms | ~2.1 s |
| Pix2Text MFR 1.1.7 | no | 67% | 82% | fail | 280 ms | ~0.5 s |

TexTeller by area (zero fixes / ≤2 fixes): algebra 93% / 100%, precalc 90% / 90%, calc 1 87% / 100%, calc 2 100% / 100%.

Error split for TexTeller: 4 problems need any fix, all **symbol** errors and none structural (a misread letter or digit in a trig name, a constant, a differential, and one dropped pair of parentheses). The confirm panel's per-symbol tap-to-fix chips cover these, so no structural-fix priority is needed.

The scorer first counted equivalent forms as errors (a two-line system written as `matrix` instead of `cases` = 10 fixes; `\rightarrow` vs `\to`; bare `lnx`). Before that fix, the scores were TexTeller 72% / 90% and Pix2Text 58% / 77%. All 18 TexTeller items that became zero-fix were checked by eye and are the same math.

## Tuning experiment: not run

The plan asked for the gate to be measured after tuning. The untuned baseline already passes, so skipping tuning only makes the result more conservative. The tune set is also incomplete on the dev machine (20/60: pages Tune 2–5 have no ink here). `finetune.py` was not written.

**Open risk:** spec §6.3 makes a one-time **personal tuning session required**. This spike did not prove that TexTeller can be fine-tuned on a few dozen samples and still run on CPU. That must be shown in the milestone that builds the tuning session, before it is built around TexTeller.

## Caveats and what M4 must carry forward

1. **Latency is the tight spot.** About 2.1 s estimated on the Surface for recognition alone, against the spec's <3 s to the confirm box. The model must stay loaded (a resident service; cold load is ~36 s), and M4 should measure on the Surface itself early.
2. **Canonicalize reader output before SymPy, using a vetted subset only.** Bare `lnx`/`log1000` → `\ln x`/`\log 1000`, `\rightarrow` → `\to`, `f^{'}` → `f'`, and matrix/array systems treated as a system. Do **not** reuse `normalize()` as-is: it is a scoring tool, and dropping parentheses or braces must never change meaning before solving (e.g. `\ln(x)^2` is (ln x)², not ln(x²)). Every rewrite M4 uses needs its own does-not-change-meaning test.
3. **Import order.** In one process, PyTorch must be imported before the WinRT ink APIs (WinError 1114 otherwise), or the two must run in separate processes.
4. **One sitting, careful writing.** All 60 samples were written in one session. Rushed live-tutoring handwriting may score lower. Collect real corrections from M5 on, to feed the personal tuning planned in the spec.
5. Pix2Text is 4× faster but fails the gate. Keep it only as a candidate for a fast first guess, if latency on the Surface proves too slow.
