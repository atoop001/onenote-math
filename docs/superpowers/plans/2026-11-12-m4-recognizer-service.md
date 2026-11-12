# M4 Recognizer Service: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A resident, offline handwriting reader. It turns the lassoed ink into LaTeX, with a confidence and up to 3 alternatives per symbol. It is tuned to the user's handwriting, and it saves corrections for later training. The add-in calls it when ink is lassoed.

**Architecture:**
- **The reader process.** A new Python package `reader/inkmath_reader` runs as one warm process (`python -m inkmath_reader`) and speaks JSON lines over stdin/stdout, like the M2 solver.
  - It loads TexTeller once at startup; a cold load takes about 36 s.
  - Each `read` does ISF → strokes → PNG → `model.generate` with per-token scores → symbols with confidences and alternatives.
- **Training tools** live in `reader/train/` (dev machine, GPU). They fine-tune TexTeller on the user's tune samples (and later on saved corrections), then gate the tuned model on the test set.
- **Solver side.** The solver gets a small set of vetted LaTeX rewrites for reader quirks.
- **Add-in side.** It gets a `ReaderClient` sharing one process class with `SolverClient`. Until M5's confirm panel, a lassoed-ink Solve shows the reading in the status label and does **not** solve (spec §6.2: nothing is solved before confirming).

**Tech Stack:**
- Python 3.10.
- Reader runtime: torch 2.14.1 CPU build, transformers 4.47.0, texteller 1.0.2, Pillow, numpy, and the WinRT ink packages. These are the same pins as `spike/requirements.txt`, minus pix2text and rapidocr.
- Training: the CUDA build of torch 2.14.1 on the RTX 3080, in a separate venv.
- C# net48 and xUnit for the add-in, as in M3.

**Spec:** `docs/superpowers/specs/2026-11-09-onenote-ink-math-design.md` (§2, §3, §6.3, §6.6, §7 "Where training runs", §8). M1 results and carry-forward list: `docs/superpowers/spike/2026-11-m1-accuracy-results.md`. M3 bridge: `docs/superpowers/plans/2026-11-10-m3-onenote-bridge.md`.

## Global Constraints

- **Handwriting stays local (spec §6.6).**
  - No real ink, rendered sample images, or per-sample model outputs go into the repo. Committed reports hold aggregate numbers only.
  - `data/` and `models/` stay git-ignored.
  - Snippets and corrections are written under `%LOCALAPPDATA%\InkMath\` only.
  - Test fixtures use synthetic strokes generated in code.
- **Offline at runtime.** The reader sets `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` before importing texteller, and never downloads. Model files come from the models directory (default `<repo>/models`, `HF_HOME=<models>/huggingface`, as in M1).
- **CPU only at runtime** (spec §6.1). `reader/.venv` gets the CPU torch build. CUDA is used only by `reader/train`, on the dev machine (spec §7).
- **Import order (M1 carry-forward 3).** In any process, `torch` is imported before any `winrt` module. `inkmath_reader/__init__.py` imports torch first, with a comment naming WinError 1114.
- **Never hang OneNote (spec §3).**
  - The reader starts on its own background thread, never on the add-in's worker queue, so a 36 s cold load can't delay a typed-text Solve.
  - A `read` with no reply for 30 s kills the reader, restarts it in the background, and returns an error.
- **Latency (spec §3: <3 s to the confirm box).**
  - The model stays loaded.
  - Generation is capped at `max_new_tokens=256`.
  - The warm `read` median on the dev CPU over the test set is at most **1.5 s**; the M1 baseline was 1.22 s.
- **Alternatives (spec §6.3).** At most **3** per symbol, model-ranked first, then from the confusion table.
  - A symbol is `low` when its confidence is below the calibrated threshold.
  - The threshold defaults to **0.85** until Task 7 calibrates it.
- **Canonicalization (M1 carry-forward 2).** Only the rewrites listed in Task 5. Each has a does-not-change-meaning test. Spike `normalize()` is never used outside scoring.
- **Python packages:**
  - `reader/` gets its own venv, `reader/.venv`.
  - Training gets `reader/.venv-train`.
  - Both are git-ignored.

**Reader protocol (exact):**
- **Startup line:** `{"status":"ready","model":"texteller" | "texteller-tuned","load_ms":<int>}`.
- **Read request:** `{"id":"r1","op":"read","ink":["<base64 ISF>", ...]}`.
- **Read reply, `ok`:** `{"id":"r1","status":"ok","latex":"3x-7=11","symbols":[{"text":"3","start":0,"end":1,"confidence":0.98,"low":false,"alternatives":["8","5"]}, ...],"snippet":"<path to last.png>","model":"texteller","ms":{"ink":<int>,"model":<int>,"total":<int>}}`.
  - `start` and `end` are character offsets into `latex`.
- **Read reply, other statuses:**
  - `no_ink`: `"Lasso some handwriting first."`
  - `empty`: `"Couldn't read any math in this ink."`
  - `error`: `"Couldn't read this handwriting."`
- **Correction request:** `{"id":"c1","op":"correction","ink":[...],"recognized":"...","corrected":"..."}` → `{"id":"c1","status":"saved"}`.
- **Bad JSON or an unknown op:** `{"id":<id or null>,"status":"error","message":"Bad request"}`.
- **Exit:** the reader exits when stdin closes.

**Status copy for lassoed ink, until M5 (exact):**

| When | Status label |
|---|---|
| Read ok | `Read: {latex} · {s:0.0} s`, plus ` · {n} to check` when n > 0 symbols are `low`. `latex` is cut to 60 characters, adding `…`. |
| Reader still loading | `The handwriting reader is still starting. Try again in a moment.` |
| Reader not set up (no settings) | `Handwriting reading isn't set up. Check the setup.` |
| `no_ink`, `empty` or `error` | the reply's `message` |

## Review Focus

1. **Solve while the reader is still loading,** e.g. right after OneNote opens. Expected: the "still starting" message at once, and a typed-text Solve still works. Test: Task 9 `Ink_solve_while_reader_starting_returns_at_once`.
2. **Reader hangs or dies mid-read.** Expected: an error within 30 s, the reader restarts by itself, and the next read works. Test: Task 8 `Silent_reader_times_out_and_restarts`, `Crashed_reader_errors_then_recovers`.
3. **A two-line system, a single dot, or a very wide line.** Expected: both lines in one image, no crash on a one-point stroke, width capped at 2048 px. Test: Task 1 `Two_rows_stay_in_one_image`, `Single_point_stroke_renders`, `Wide_ink_is_capped`.
4. **The model returns nothing.** Expected: status `empty` with its message, and nothing written. Test: Task 4 `Empty_reading_is_reported`.
5. **A rewrite that would change meaning.** Expected: `\ln(x)^2`, `\sin^{2}x`, `\log_{2}x` and `\sinh x` are untouched. Test: Task 5 `Rewrites_never_touch_valid_forms`.

---

### Task 1: Reader package, ink to image

**Files:**
- Create: `reader/requirements.txt`, `reader/pytest.ini` (markers `model`, `samples`, `gpu`, `slow`), `reader/inkmath_reader/__init__.py`, `reader/inkmath_reader/paths.py`, `reader/inkmath_reader/ink.py`, `reader/inkmath_reader/render.py`, `reader/tests/conftest.py`, `reader/tests/test_ink.py`
- Modify: `.gitignore` (add `reader/.venv/`, `reader/.venv-train/`)

**Interfaces:**
- Produces:
  - `paths.models_dir(override: str | None = None) -> Path`: precedence is `override`, then env `INKMATH_MODELS`, then `<repo>/models`.
  - `paths.user_dir() -> Path`: `%LOCALAPPDATA%\InkMath`.
  - `ink.Stroke = list[tuple[float, float]]`.
  - `ink.decode_items(items: list[bytes]) -> list[Stroke]`: all items merged in page DIPs.
  - `ink.encode_strokes(strokes) -> bytes`: used by tests and training.
  - `ink.NoInk(Exception)`.
  - `render.render(strokes, height_px=256, pad_px=16, line_px=3) -> PIL.Image.Image`: mode `L`, black on white, width capped at `MAX_WIDTH_PX = 2048`. It raises `NoInk` for zero points.

- [ ] **Step 1: Create the venv.** `py -3.10 -m venv reader\.venv`, then install `requirements.txt` with torch from `https://download.pytorch.org/whl/cpu`.
- [ ] **Step 2: Write the failing tests** in `test_ink.py`. Build strokes in code (no fixtures):
  - `Isf_round_trip`: encode two strokes, decode them, and get the same points within 0.5 DIP.
  - `Items_merge_in_page_coordinates`: two items at different positions decode to one list holding both strokes' points unchanged.
  - `Two_rows_stay_in_one_image`: strokes at y≈0 and y≈60 give an image 256 px high with ink in both its top and bottom thirds.
  - `Single_point_stroke_renders`: a one-point stroke gives an image without raising.
  - `Wide_ink_is_capped`: a 5000-DIP-wide stroke gives width ≤ 2048.
  - `No_points_raises_NoInk`.
  - `Torch_loads_before_winrt`: in a subprocess, `import inkmath_reader.ink`; assert `torch` was in `sys.modules` before `winrt.windows.ui.input.inking`.
  - `Models_dir_precedence`: override, then env, then default.
- [ ] **Step 3: Run** `reader\.venv\Scripts\python -m pytest reader/tests/test_ink.py -q`. Expected: FAIL (modules missing).
- [ ] **Step 4: Implement.** Port `spike/inkspike/isf.py` and `render.py`. `render` returns the image instead of saving it. Pad the image to ≥30 px wide (texteller `MIN_WIDTH`).
- [ ] **Step 5: Run the tests.** Expected: PASS.
- [ ] **Step 6: Commit:** `reader: package scaffold, ISF decoding and rendering`.

### Task 2: Recognizer with per-token scores

**Files:**
- Create: `reader/inkmath_reader/recognize.py`, `reader/tests/test_recognize.py`

**Interfaces:**
- Consumes: `paths.models_dir`.
- Produces:
  - `TokenStep(text: str, prob: float, alts: list[tuple[str, float]])`.
  - `RawReading(latex: str, raw: str, steps: list[TokenStep])`. `raw` is the concatenation of the step texts; `latex` is `raw` after TexTeller's own post-processing.
  - `Recognizer(models_dir: Path, weights_dir: Path | None = None, max_tokens: int = 256, top_k: int = 5)`, with `.name` (`texteller` or `texteller-tuned`) and `.read(img: PIL.Image.Image) -> RawReading`.

- [ ] **Step 1: Write the failing tests.** All are marked `model`, and are skipped when `models/huggingface` is missing.
  - `Read_matches_img2latex`: draw `x^2+1` with PIL's default font on a white 400×120 image. `Recognizer.read(img).latex` equals `strip_delims(img2latex(model, tok, [np.array(img.convert("RGB"))])[0])`.
  - `Steps_carry_probabilities`: every `0 < prob ≤ 1`; every `len(alts) ≤ top_k - 1`; `"".join(s.text for s in steps) == raw`.
  - `Max_tokens_caps_generation`: `Recognizer(..., max_tokens=8)` gives `len(steps) ≤ 8`.
- [ ] **Step 2: Run** `reader\.venv\Scripts\python -m pytest reader/tests/test_recognize.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - Set the offline env vars and `HF_HOME` before importing texteller.
  - Mirror `texteller.api.inference.img2latex`: use `transform` on the RGB array and the same `GenerationConfig`, plus `output_scores=True, return_dict_in_generate=True`.
  - Softmax each step's scores. `prob` is the chosen token's probability. `alts` are the next `top_k-1` tokens, as `tokenizer.convert_tokens_to_string([t])`.
  - Stop at EOS.
  - Post-process `raw` exactly as `img2latex` does (`remove_style`, `format_latex`, `add_newlines`), then `strip_delims` (port it from `spike/models/texteller.py`).
  - Load tuned weights when `weights_dir` is given.
- [ ] **Step 4: Run the tests.** Expected: PASS.
- [ ] **Step 5: Commit:** `reader: TexTeller recognizer with per-token probabilities and alternatives`.

### Task 3: Symbols, confidences and alternatives

**Files:**
- Create: `reader/inkmath_reader/symbols.py`, `reader/tests/test_symbols.py`

**Interfaces:**
- Consumes: `RawReading`, `TokenStep`.
- Produces:
  - `Symbol(text, start, end, confidence: float, low: bool, alternatives: list[str])`.
  - `split_symbols(latex: str) -> list[tuple[str, int, int]]`.
  - `build_symbols(reading: RawReading, low_threshold: float) -> list[Symbol]`.
  - `CONFUSIONS: dict[str, list[str]]`.

**Symbol units:** a command `\\[A-Za-z]+`; an escaped character `\\.`; or any single non-whitespace character. Whitespace is skipped. `start` and `end` are offsets into the string.

**Confidence mapping (algorithm):**
1. Split `raw` into symbols. Each raw symbol's confidence is the minimum `prob` over the steps whose text overlaps its span.
2. Split `latex` into symbols. Align the two symbol-text lists with `difflib.SequenceMatcher(autojunk=False)`.
   - `equal` blocks copy the confidence.
   - `replace` blocks give every `latex` symbol the minimum confidence over the raw symbols in that block.
   - `insert` blocks get 1.0, because they are formatting only.
3. **Alternatives:**
   - Take the step where the symbol's first token was generated. For each alt token, rebuild the symbol with that token's text in place of the chosen token's text.
   - Keep the result if it is exactly one symbol unit, differs from `text`, and isn't a duplicate.
   - Then fill from `CONFUSIONS[text]` up to 3.
   - Symbols from `insert` blocks get only confusion alternatives.

**`CONFUSIONS`:** `x↔\times`, `1↔l↔|`, `2↔z`, `5↔s`, `0↔o↔\theta`, `9↔g↔q`, `6↔b`, `7↔\tau`, `t↔+`, `u↔v`, `\pi↔n`, `-↔=`, `\leq↔<`, `\geq↔>`, `\alpha↔a`, `e↔c`, `y↔4`, `(`↔`|`. Each relation applies both ways.

- [ ] **Step 1: Write the failing tests** with hand-built `RawReading`s; no model is needed.
  - `Split_handles_commands_escapes_and_spaces`: `split_symbols(r"\frac{3}{x} \leq 2")` gives texts `["\\frac","{","3","}","{","x","}","\\leq","2"]` with correct offsets.
  - `Confidence_is_min_over_overlapping_tokens`: steps `"\\fr"(0.9)`, `"ac"(0.6)` give `\frac` confidence 0.6.
  - `Formatting_changes_keep_confidences`: raw `"x^{2}"`, latex `"x^{2}"` with a space inserted still map 1:1.
  - `Replaced_block_takes_block_minimum`.
  - `Alternatives_come_from_model_then_confusions`: chosen `"5"` with alts `[("6",.1),("S",.05)]` gives `["6","S","s"]` (3 maximum).
  - `Multi_unit_alternatives_are_dropped`: an alt `"5x"` is skipped.
  - `Low_flag_uses_threshold`: confidence 0.84 with threshold 0.85 is `low`.
- [ ] **Step 2: Run** `pytest reader/tests/test_symbols.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `symbols.py`.
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit:** `reader: symbol units with confidences and up to 3 alternatives`.

### Task 4: Reader service, corrections store, CLI

**Files:**
- Create: `reader/inkmath_reader/server.py`, `reader/inkmath_reader/__main__.py`, `reader/inkmath_reader/corrections.py`, `reader/inkmath_reader/calibration.py`, `reader/tests/test_server.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces:
  - `Server(recognizer, user_dir: Path, low_threshold: float)`, with `.handle(msg: dict) -> dict` (the exact protocol above).
  - `main(argv) -> int`, with options `--models DIR` and `--file last.json`. `--file` runs one read of an M3 `last.json` (`ink[].isf`), prints the reply, and exits.
  - Weights choice: `models/texteller-tuned/` when `models/texteller-tuned/accepted.json` has `"accepted": true`; otherwise the base model.
  - `corrections.save(dir, strokes, recognized, corrected) -> Path`: writes `<dir>/YYYYMMDD-HHMMSS-<6 hex>.json` with `{"strokes","recognized","corrected"}`.
  - `corrections.load(dir) -> list[tuple[list[Stroke], str]]` returns (strokes, corrected).
  - `calibration.low_threshold(models_dir) -> float`: reads `models/reader_calibration.json` `{"low_threshold": x}`, defaulting to 0.85.
  - Snippet: each ok read saves the rendered image to `user_dir/selections/last.png`.

- [ ] **Step 1: Write the failing tests.** In-process tests use a `FakeRecognizer` defined in the test file that returns a fixed `RawReading`, and `user_dir=tmp_path`.
  - `Read_ok_returns_latex_symbols_snippet_and_timings`.
  - `No_ink_items_is_no_ink`.
  - `Empty_reading_is_reported`.
  - `Recognizer_exception_is_error_and_server_survives`.
  - `Bad_json_and_unknown_op_are_bad_request`.
  - `Correction_is_saved_under_user_dir_and_loads_back`.
  - `Tuned_weights_used_only_when_accepted`: tested on the chooser function with a temp models dir.
  - `Calibration_default_and_file`.
  - `Process_round_trip`, marked `model`: start `python -m inkmath_reader` as a subprocess, wait for `ready`, send one read built from synthetic strokes, get `status` `ok` or `empty`, close stdin, and the process exits within 5 s.
- [ ] **Step 2: Run** `pytest reader/tests/test_server.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - Mirror `solver/inkmath_solver/server.py`'s line loop: UTF-8 stdio, flush per line, `ms` timings, and exit on stdin EOF.
  - Load the model before printing `ready`.
  - Log to stderr only.
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Manual check.** Run `reader\.venv\Scripts\python -m inkmath_reader --file %LOCALAPPDATA%\InkMath\selections\last.json`. Expected: an `ok` reply whose `latex` matches the user's 3x−7=11 ink from the M3 dev check.
- [ ] **Step 6: Commit:** `reader: JSON-lines service, corrections store, one-shot CLI`.

### Task 5: Solver canonicalization of reader quirks

**Files:**
- Create: `solver/inkmath_solver/canonical.py`, `solver/tests/test_canonical.py`
- Modify: `solver/inkmath_solver/parse.py` (`clean_latex` calls `canonicalize` first)

**Interfaces:** Produces `canonicalize(latex: str) -> str`.

**The vetted rewrites (all others are out of scope):**
1. A bare function name with no backslash, not preceded by a letter or `\`: `ln log sin cos tan sec csc cot arcsin arccos arctan`. It gets `\` and a space, e.g. `lnx` → `\ln x`.
2. A command glued to its argument: `\lnx` → `\ln x`, `\sinx` → `\sin x`. Only when the glued name isn't itself a known command (`\sinh` stays).
3. `\left\{\begin{array}{...}A\\B\end{array}\right.` → `\begin{cases}A\\B\end{cases}`.

(Measured today: the M2 parser already handles `\rightarrow`, `f^{'}`, `f^{\prime}`, `matrix` systems and `\mathrm{d}x`. No rewrite is added for those.)

- [ ] **Step 1: Write the failing tests:**
  - `Rewrites`, parametrized input → output: `lnx`→`\ln x`, `sinx+1`→`\sin x+1`, `\lnx`→`\ln x`, `\cosx`→`\cos x`, and the array system → cases.
  - `Rewrites_keep_meaning`: `parse_problem(canonicalize(a))` equals `parse_problem(b)` for each pair. The b's are the intended forms: `\ln x`, `\sin x+1`, `\begin{cases}x+y=3\\x-y=1\end{cases}`.
  - `Rewrites_never_touch_valid_forms`: `\ln(x)^2`, `\sin^{2}x`, `\log_{2}x`, `\sinh x`, `\arcsin x`, `\cos x`, `x\ln x`, `3x-7=11` are returned unchanged.
  - `Solve_reads_bare_lnx`: an engine request for `lnx=1` returns `ok` with answer `x = e`.
- [ ] **Step 2: Run** `solver\.venv\Scripts\python -m pytest solver/tests/test_canonical.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** with regexes anchored as described, then hook it into `clean_latex`.
- [ ] **Step 4: Run the whole solver suite.** Expected: all pass (239 + new).
- [ ] **Step 5: Commit:** `solver: vetted rewrites for reader quirks (bare ln/sin, glued commands, array systems)`.

### Task 6: Personal tuning: data and fine-tuning

**Tune data:** all 60 tune samples (U01–U60) are extracted in `data/ink` (re-extracted 2026-11-12). In M1, Tune 2–5 hadn't finished syncing when extraction ran. If `tune_manifest.json` shows any missing, re-run `spike\.venv\Scripts\python spike\extract_all.py --set tune` first.

**Files:**
- Create: `reader/train/requirements-train.txt`, `reader/train/dataset.py`, `reader/train/finetune.py`, `reader/tests/test_train_dataset.py`

**Interfaces:**
- Consumes: `ink.Stroke`, `render.render`, `corrections.load`, `samples/prompts_tune.json`, and `data/ink/U*.json` (the stroke lists M1 wrote) with `tune_manifest.json`.
- Produces:
  - `Sample(id: str, strokes: list[Stroke], latex: str)`.
  - `load_tune(ink_dir: Path, prompts: Path) -> list[Sample]`: only ids in the manifest's `ok` list.
  - `load_corrections(dir: Path) -> list[Sample]`.
  - `augment(strokes, rng: random.Random) -> list[Stroke]`.
  - `finetune.main(argv) -> int`, with options `--out models/texteller-tuned`, `--epochs 15`, `--lr 1e-5`, `--batch 4`, `--views 8`, `--seed 7`, `--corrections DIR` (optional, repeatable) and `--limit N` (for the smoke test).

**Augmentation (decided):**
- per-axis scale in U(0.9, 1.1);
- rotation in U(−3°, 3°);
- x-shear in U(−0.1, 0.1);
- point jitter N(0, 0.3 DIP);
- render `height_px` in U(0.75, 1.15) × 256;
- `line_px` from {2, 3, 4}.

**Training (decided):**
- Each epoch sees `views` augmented renders per sample.
- Labels are `tokenizer(latex).input_ids`, truncated to 256, with pad positions set to −100.
- Optimizer: AdamW, weight decay 0.01, 50 warmup steps with linear decay, gradient clipping at 1.0, fp16 autocast on CUDA.
- Save with `save_pretrained` (model and tokenizer) into `--out`.
- One run with these settings. If Task 7 rejects it, exactly one retry with `--lr 5e-6 --epochs 8`, ledgered.

- [ ] **Step 1: Create the training venv.** `reader\.venv-train` with `requirements-train.txt`: the reader pins, plus the CUDA build of torch 2.14.1 from the PyTorch index (the newest `cu12x` tag offered for 2.14.1). Check that `torch.cuda.is_available()` is True.
- [ ] **Step 2: Write the failing tests** with synthetic strokes and temp dirs:
  - `Load_tune_pairs_manifest_ok_ids_with_prompt_latex`;
  - `Missing_ids_are_skipped`;
  - `Corrections_become_samples`;
  - `Augment_is_deterministic_per_seed_and_keeps_stroke_count`;
  - `Augment_stays_within_bounds`: bounding-box scale within [0.85, 1.15];
  - `Finetune_smoke`, marked `slow` and `model`: `--limit 2 --epochs 1 --views 1 --batch 1` on CPU writes `config.json` and `model.safetensors` to a temp `--out`.
- [ ] **Step 3: Run** `reader\.venv\Scripts\python -m pytest reader/tests/test_train_dataset.py -q`. Expected: FAIL.
- [ ] **Step 4: Implement** `dataset.py` and `finetune.py`.
- [ ] **Step 5: Run.** Expected: PASS.
- [ ] **Step 6: Train for real:** `reader\.venv-train\Scripts\python reader\train\finetune.py --out models\texteller-tuned`. Expected: it finishes on the GPU, and the training loss falls below half its first-epoch value. Log the loss per epoch to `models/texteller-tuned/train_log.txt`.
- [ ] **Step 7: Commit** the code only: `reader: personal tuning data pipeline and fine-tuning`.

### Task 7: Tuning gate, latency and confidence calibration

**Files:**
- Create: `reader/train/evaluate.py`, `reader/tests/test_train_evaluate.py`, `docs/superpowers/spike/2026-11-m4-tuning-results.md` (generated, aggregate numbers only)

**Interfaces:**
- Consumes:
  - `Recognizer`, `build_symbols`, `split_symbols`;
  - spike scoring via `sys.path` insert of `<repo>/spike`: `inkspike.score.fixes`, `summarize`, `Result`, and `inkspike.prompts.load_prompts`;
  - `samples/prompts_test.json` and `data/ink/T*.json`.
- Produces:
  - `evaluate.main(argv) -> int`. It runs in `reader\.venv` (CPU, so latency is real).
  - It writes `models/texteller-tuned/accepted.json` (`{"accepted": bool, "base": {...}, "tuned": {...}}`), `models/reader_calibration.json` and the report.
  - `gate(base: dict, tuned: dict) -> bool`.
  - `choose_threshold(confs_wrong: list[float], confs_all: list[float]) -> tuple[float, float, float]`, returning (threshold, recall, flagged share).

**Gate (decided):** the tuned model is accepted only if all three hold:
- zero-fix rate ≥ base;
- ≤2-fix rate ≥ base;
- warm median latency ≤ 1.15 × base.

Ties count as accepted.

**Calibration (decided):**
- Run on the test set with the accepted model.
- Align each reading's symbols to the truth's `split_symbols` with `SequenceMatcher`. Symbols outside `equal` blocks are *wrong*.
- Over the grid 0.50–0.99 (step 0.01), pick the smallest threshold whose recall of wrong symbols is ≥ 0.90.
- If that flags more than 20% of all symbols, pick the largest threshold flagging ≤ 20% instead.
- Report recall and flagged share.

- [ ] **Step 1: Write the failing tests** (pure, no model):
  - `Gate_accepts_equal_or_better`;
  - `Gate_rejects_worse_accuracy`;
  - `Gate_rejects_slower_than_115_percent`;
  - `Threshold_reaches_90_percent_recall`;
  - `Threshold_capped_at_20_percent_flagged`;
  - `Report_contains_no_latex_or_ids`: the rendered report text has no `T\d\d` and no `\\`.
- [ ] **Step 2: Run** `pytest reader/tests/test_train_evaluate.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Run the evaluation for real.**
  - Run `reader\.venv\Scripts\python reader\train\evaluate.py`.
  - Expected: the report shows base and tuned zero-fix, ≤2-fix and median ms; the accepted flag; and the threshold with its recall and flagged share.
  - Check that base reproduces M1 (93% / 98%, ±1 problem).
  - Check that the warm median is ≤ 1.5 s (Global Constraints).
- [ ] **Step 6: Commit** the code and report: `reader: tuning gate, latency check and low-confidence calibration`.

### Task 8: Add-in: shared process class and ReaderClient

**Files:**
- Create: `addin/InkMath.AddIn/JsonLinesProcess.cs`, `addin/InkMath.AddIn/ReaderClient.cs`, `addin/InkMath.Tests/ReaderClientTests.cs`, `addin/InkMath.Tests/fixtures/stub_reader.py` (modes `ok`, `slowready`, `silent`, `crash`, `low`)
- Modify: `addin/InkMath.AddIn/SolverClient.cs` (uses `JsonLinesProcess`; behavior unchanged)

**Interfaces:**
- Produces:
  - `JsonLinesProcess(string exe, string args, string workDir, IDictionary<string,string> env, int readyTimeoutSeconds, Func<string,bool> isReady, string logName)`.
    - Members: `bool Start()`, `bool Write(string line)`, `string ReadLine(TimeSpan timeout)` (null on timeout or exit), `void Kill()`, `bool Alive`, `int? ProcessId`, `Dispose()`.
    - It keeps M3's C1 rules: Write and Dispose never block, and Dispose kills after 3 s on the thread pool.
  - `ReaderSymbol { Text, Start, End, Confidence, Low, Alternatives (List<string>) }`.
  - `ReaderResult { Status, Message, Latex, Symbols, Snippet, Model, TotalMs }`.
  - `IReader : IDisposable`, with members `bool Ready`, `void StartInBackground()` and `ReaderResult Read(string id, IList<byte[]> isf)`.
  - `ReaderClient(ReaderSettings s) : IReader`, where `ReaderSettings { PythonExe, ReaderDir, ModelsDir, ReadyTimeoutSeconds = 120, ReadTimeoutSeconds = 30, ExtraArgs }`.
    - It launches `-m inkmath_reader --models "<ModelsDir>"` with `PYTHONUTF8=1`.
    - Not ready: returns status `starting` at once.
    - Timeout or exit mid-read: kills, restarts in the background, and returns `error` / `Couldn't read this handwriting.`
- Constants: `ReaderClient.Starting = "The handwriting reader is still starting. Try again in a moment."`, `ReaderClient.Failed = "Couldn't read this handwriting."`

- [ ] **Step 1: Write the failing tests:**
  - `Reads_ok_reply_with_symbols`;
  - `Not_ready_returns_starting_immediately`: `slowready` mode; `Read` returns in < 200 ms;
  - `Silent_reader_times_out_and_restarts`: `ReadTimeoutSeconds=2`; the next read after the restart is ok;
  - `Crashed_reader_errors_then_recovers`;
  - `Dispose_never_blocks`.

  The existing `SolverClientTests` (11) must keep passing unchanged.
- [ ] **Step 2: Run** `dotnet test addin/InkMath.slnx --filter ReaderClientTests`. Expected: FAIL.
- [ ] **Step 3: Implement.** Extract `JsonLinesProcess` from `SolverClient` (launch, ready wait, stdout/stderr threads, write gate, kill), then build `ReaderClient` on it.
- [ ] **Step 4: Run the full suite.** Expected: all pass.
- [ ] **Step 5: Commit:** `addin: shared JSON-lines process class; reader client with start-up, timeout and restart`.

### Task 9: Add-in: read lassoed ink, setup and dev check

**Files:**
- Modify:
  - `addin/InkMath.AddIn/Settings.cs` (`readerPythonExe`, `readerDir`, `modelsDir`);
  - `addin/InkMath.AddIn/SolveController.cs` (the ink branch calls `IReader`; `StatusText.InkSaved` is replaced by the M4 copy above);
  - `addin/InkMath.AddIn/Com/Connect.cs` (creates the `ReaderClient` and calls `StartInBackground()` from `OnStartupComplete`, never via `Enqueue`; disposes on shutdown);
  - `install/register.ps1` and `install/unregister.ps1` (`-ReaderPythonExe`, `-ReaderDir`, `-ModelsDir` written to the settings JSON);
  - `addin/InkMath.Tests/SolveControllerTests.cs`, `ConnectTests.cs`, `RegistrationTests.cs`.
- Create: `docs/superpowers/m4-dev-check.md`
- Modify: `docs/superpowers/plans/2026-11-09-roadmap.md` (M4 row links this plan)

**Interfaces:**
- Consumes: `IReader`, `ReaderResult`.
- `SolveController(IOneNotePage page, ISolver solver, IReader reader, ISelectionStore store, Action changed)`. `reader` may be null when not configured.
- Ink flow: save the selection (as in M3), then `reader.Read("k1"…)`, set the status per the table, and log `read: <latex> · <n> low · <ms> ms · <model>`. Nothing is solved and nothing is written to the page.

- [ ] **Step 1: Write the failing tests:**
  - `Ink_read_ok_shows_latex_and_time`: `Read: 3x-7=11 · 1.4 s`;
  - `Ink_read_counts_low_symbols`: `… · 2 to check`;
  - `Long_latex_is_cut_at_60`;
  - `Ink_solve_while_reader_starting_returns_at_once`;
  - `Reader_not_configured_message`;
  - `Ink_never_writes_to_the_page`;
  - `Reader_start_does_not_block_the_worker`: Connect with a reader whose start blocks for 5 s; a queued typed-text solve still runs within 1 s;
  - `Register_writes_reader_settings`.
- [ ] **Step 2: Run** `dotnet test addin/InkMath.slnx`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run.** Expected: all pass.
- [ ] **Step 5: Re-register the add-in on the dev PC** with the reader settings. Restart OneNote cleanly: close it, force-stop any windowless `ONENOTE`, restart. Check that the log shows `reader ready`.
- [ ] **Step 6: Write `m4-dev-check.md`** (5 steps, about 5 min):
  1. Open OneNote and wait about 40 s.
  2. Lasso the 3x−7=11 ink and tap Solve. Expected: `Read: 3x-7=11 · ~1.5 s`.
  3. Lasso a messy problem. Expected: `· n to check`.
  4. Restart OneNote and tap Solve within 10 s. Expected: the "still starting" message, and typed text still solves.
  5. Expected: a log line with timings.
- [ ] **Step 7: Commit:** `addin: read lassoed ink with the reader service; M4 setup and dev check`.

### Task 10 (deferred to M6 by the user, 2026-11-12): Surface latency check

Not run in M4. M6 runs this check as part of the Surface install.

**Files:** Create `install/surface-reader-bench.ps1` and `docs/superpowers/m4-surface-check.md`.

The script:
1. Installs Python 3.10 with `winget` if it is missing.
2. Creates a temporary venv and installs `reader/requirements.txt`.
3. Copies `models/` from a folder the user brings over.
4. Times 10 warm reads of synthetic strokes.
5. Prints the median.

Pass: median ≤ 2.5 s, leaving 0.5 s for the confirm panel.

---

## Notes for later milestones

- **M5 (confirm panel):** chips come from `symbols[]` (`start`/`end` index `latex`); structural fixes edit `latex` by span; the snippet is `snippet`; every confirmed fix calls the reader's `correction` op.
- **M6:** bundle `reader/.venv` and `models/` for the Surface; decide how Surface corrections reach the dev machine for re-training (`finetune.py --corrections DIR`).
