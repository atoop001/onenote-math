# OneNote Ink Math: Design

**Date:** 2026-11-09
**Status:** Draft. Awaiting user approval.

## 1. Intent and the why

The user is a math tutor (basic algebra through Calculus 2). They teach in the **Microsoft 365 desktop OneNote app on a Surface Pro 8**, handwriting problems with a pen while a student watches. They want to lasso a handwritten problem, have it recognized and solved, and see the answer (with key steps) on the page **so tutor and student can check their work**.

Microsoft's "Ink to Math" / "Math Assistant" does this but only in Education editions of OneNote. The user has used it and reports:

- **Liked:** convenient (one selection, one action), usually correct math, graphing, answer pasted onto the page.
- **Disliked:** it misread their handwriting most of the time; the correction tool could not fix complex problems, so complex problems often could not be solved at all.

This add-in exists to fix exactly those two failures. Handwriting accuracy on *this user's* writing and a correction flow that can fix *structure* (not just characters) are the product. The solver is the comparatively easy part.

## 2. Goals

1. One lasso + one ribbon tap starts the flow inside OneNote desktop.
2. Recognize handwritten math from basic algebra through Calc 2 accurately for this user's handwriting.
3. Always show a **confirm step** before solving; allow fixes by tapping and by typing.
4. Solve with **key steps** (3–5 lines: method used, main intermediate result, answer).
5. Write the result onto the page under the ink as ordinary, editable page content.
6. Work **fully offline**. Nothing leaves the Surface unless the user explicitly turns on an online option.
7. Never present an unchecked answer as certain.

## 3. Anti-goals (failure even if it technically works)

The user would abandon the add-in mid-session for these, **in this priority order**:

1. **Too many corrections.** Target: most problems need zero taps in the confirm box; a messy problem needs at most 1–2 fixes.
2. **Too slow.** Target: under 3 s from tapping Solve to the confirm box appearing; under 5 s more from confirming to the answer on the page. When solver work passes 20 s, the user is asked "This one's taking a while. Keep going or stop?" (user's decision, revised 2026-11-10; it replaced a hard stop at 20 s). **Keep going** allows another 20 s and then asks again. **Stop** ends it with a plain message. A Cancel/Stop control works at any time during a solve. Never hang OneNote.
3. **Confidently wrong.** Every answer is independently verified (see §6.5). If verification fails or is impossible, the answer carries a visible "⚠ unverified" mark.

Also: never cover the page with a modal pop-up, never move or alter the user's ink, never leave clutter beyond the inserted answer.

## 4. Non-goals (v1)

- Word problems. The tutor sets up the math by hand; the add-in solves what is written.
- Graphing. The user liked this in Ink to Math; it is the first candidate for a later version.
- Installing on other machines (other tutors/students). v1 targets one Surface. Code should be structured so a real installer can be added later (separate install/registration logic, no hard-coded user paths).
- Full textbook-style step-by-step solutions. Key steps only.
- Checking a student's answer ("is this work correct?"). The add-in solves what is lassoed; tutor and student compare. (User's decision.)
- Multiple problems in one lasso. One lasso = one problem (a system of equations written on several lines counts as one problem).
- Editing with the pen inside the confirm box. Fixes are taps or typing.
- The confirm box remembering fixes between problems. Each problem starts fresh. (Fixes *are* saved as training data for the recognizer, §6.3; that is separate.)

## 5. Scope of math

| Area | Must handle |
|---|---|
| Algebra | Solve equations and inequalities (linear, quadratic, rational, radical, absolute value), systems of equations, factoring, simplifying, exponents and logs |
| Precalc / trig | Trig equations, verifying identities (are both sides equal?), simplifying rational expressions |
| Calc 1 | Limits (including one-sided and at ∞), derivatives (including implicit), evaluating at a point |
| Calc 2 | Integrals by any technique (substitution, parts, partial fractions, trig substitution), improper integrals, series convergence and sums |

**Answers:** exact form (π, √2/2), plus a decimal value next to it where meaningful.

**Series:** the offline engine is weakest here. It may answer "couldn't determine" rather than guess. When it answers, the key steps name the test used (divergence, geometric, p-series, ratio, root, comparison, integral, alternating series).

## 6. How it works

### 6.1 Target environment (fixed)

- **Surface (production):** OneNote for Microsoft 365, Version 2611, Build 16.0.20625.20034, **64-bit**. Windows 11 26H2. Intel Core i7-1185G7, 16 GB RAM, no discrete GPU. Everything must run CPU-only here.
- **Dev machine (where code is written and tested):** OneNote for Microsoft 365, Build 16.0.20527.20150, **32-bit** (x86 Click-to-Run). Python 3.10, .NET SDK, Git installed.
- The add-in must register and work under **both** bitnesses. Final acceptance happens on the Surface.
- Install on the Surface is a setup script the user runs once (an "unknown publisher" warning is acceptable). No code-signing certificate in v1.

### 6.2 User flow

1. **Select.** The user lassos handwritten ink on a OneNote page.
2. **Solve.** On a **Math** ribbon tab the user taps **Solve**. The tab also has a **Show steps** toggle (on by default) and a status badge showing **Offline** / **Online**.
3. **Confirm.** A panel opens **beside the page** (not covering it, so the student can still see the work). It shows:
   - a snippet of the selected ink,
   - the recognized expression as **tappable symbol chips** (Option B, the primary view),
   - low-confidence symbols highlighted, each offering 2–3 likely alternatives on tap,
   - **structural fixes** on tap: "make this an exponent," "make this a subscript/limit," "group these as a fraction" (and equivalents needed for roots, limits of integration, etc.),
   - a **Type it instead** button that switches to a text box with a live rendered preview (Option A) for anything chips cannot fix,
   - a small **action menu** (user's decision: ask, don't guess). When the ink has no explicit operation (no `=`, `∫`, `d/dx`, `lim`, `Σ`, inequality), e.g. `x² + 5x + 6`, the menu must be answered before solving. Choices fit the expression: Simplify, Factor, Expand, Solve for _x_ (when set equal to 0), Derivative, Evaluate at a point. When the operation is explicit, the menu shows that operation preselected and can still be changed,
   - **Solve** and **Cancel**.
   Nothing is solved until the user taps Solve in this panel.
4. **Answer.** The result is written onto the page directly under the selected ink as normal editable content: key steps (if Show steps is on), the answer in exact form + decimal, and a small source line (e.g., "Solved offline · verified"). An unverified result shows "⚠ unverified" in that line.

Reference mockups (user reviewed and chose B as primary, A as fallback): https://claude.ai/artifact/QqDDXD8vVzJBjPHUvPEk5a

### 6.3 Handwriting recognition (the core risk)

- **Offline, local model** specialized in handwritten math, running on the Surface CPU. Expected ~1–2 s per problem on this hardware.
- Must produce, per recognized symbol, a confidence and ranked alternatives (to drive highlighting and tap-to-fix), and enough structure (superscript, subscript, fraction, limits) for the structural fixes to act on.
- **Personal tuning session (required, one-time, 5–10 min):** the user writes a prepared set of sample problems covering the symbols and layouts in §5 (∫ with limits, dx, exponents, fractions, roots, lim, Σ, trig names, Greek letters). The recognizer is adapted to this user's handwriting from those samples.
- **Learning from corrections:** every confirmed fix is saved locally (ink + corrected expression) as additional training data, so accuracy improves with use. Re-adaptation may run in the background or on demand; it must never slow a live Solve.
- **Accuracy gate and fallback order (user's decision):** an early spike measures the offline recognizer on a fixed test set of the user's real handwriting (written on the Surface; see §6.7). Pass threshold (Claude's call): ≥70% of test problems need zero fixes and ≥95% need ≤2 fixes. If the offline recognizer misses that:
  1. **First fallback:** accept more taps. Ship offline-only, and invest in the tap-to-fix flow and in learning from corrections.
  2. **Second fallback:** if real use still produces too many corrections, build the **online reader** (below) and make it easy to turn on.
- **Online reader (off by default):** for a hard problem when Wi-Fi is available, the user may send the ink image to an online AI vision model. It requires an explicit toggle and an API key, and the badge shows **Online** whenever it is on. It is built only if the second fallback is triggered, or after everything else ships.

### 6.4 Solver

- **SymPy** (offline, bundled with the add-in, no system Python required on the Surface).
- **Key steps:**
  - Integrals: use SymPy's rule-based integration step information to name the technique and the main intermediate result.
  - Derivatives: rule names (chain, product, quotient, implicit).
  - Algebra: custom step generation ("factor," "subtract 3 from both sides"). Expected to be the roughest area at first; acceptable.
  - Series: name of the convergence test applied and its conclusion.
- Check-in every 20 s ("Keep going or stop?"), as in §3. The user can stop at any time.

### 6.5 Verification ("never confidently wrong")

Before showing an answer, check it a second, independent way:

- Indefinite integrals: differentiate the answer and compare to the integrand.
- Definite / improper integrals: compare the exact result to a numerical estimate.
- Equations / systems: substitute solutions back in.
- Derivatives: compare against a numerical derivative at sample points.
- Limits: numerical approach from the relevant side(s).
- Identities / simplification: compare both sides numerically at random points.

Fail or not checkable → "⚠ unverified" in the source line.

### 6.6 Privacy

Offline by default. Ink, training samples, and correction history stay on the user's own devices: the Surface, plus the dev machine for training (via the user's own OneNote sync, §6.7). Nothing goes to a third party unless the online reader is turned on. This matters because the notes involve students.

### 6.7 Remote sessions and development logistics

- **Sessions are remote (user's answer):** the student watches through a Teams/Zoom screen share. If the tutor shares only the OneNote window, a separate confirm panel may not appear for the student. Claude's call: this is acceptable, because the confirm step is the tutor's private check and the **answer is written onto the page**, which the student does see. Requirement: the inserted answer must look clear on a shared screen (readable size, good contrast). The setup notes should mention that sharing the full screen shows the panel too.
- **Handwriting samples:** OneNote on the Surface and on the dev machine use the **same Microsoft account** (user's answer). The user writes the tuning and test samples in a dedicated notebook section on the Surface; it syncs to the dev machine, where the builder extracts the ink for the accuracy spike and for training. No manual file copying.
- **Surface testing:** the builder cannot reach the Surface. Anything that must be checked there (64-bit registration, latency targets, final acceptance) is packaged as a short script or checklist the user runs, and the plan should batch these to keep Surface round-trips few.

## 7. Decisions made by Claude, not the user

These were stated to the user as defaults. The user did not object, but they are Claude's calls and can be revisited:

- **Add-in technology:** a C# COM add-in for OneNote desktop (ribbon + OneNote's COM API to read the page/selection and write content). Modern Office web add-ins do not run in OneNote desktop.
- **Solver:** SymPy, bundled.
- **Recognizer:** an open-source handwritten-math model run locally (specific model left to the builder, §8).
- **Verification step** (§6.5) and **personal tuning session** (§6.3) were proposed by Claude. The user saw both and said "that all looks correct."
- **Structural tap-to-fix** and **learning from corrections** were proposed by Claude. The user confirmed both.
- **Answer format on the page:** ordinary editable text under the ink. Whether it uses OneNote's native equation objects or plain Unicode text is left to the builder; readability on the page is what matters.
- **Show steps** defaults to on.
- **Answer conventions** (settable later in a small settings file): `log` = base 10, `ln` = natural log; real solutions only unless complex numbers appear in the problem; trig equations show the general solution plus the solutions on [0, 2π); domain restrictions are stated in words under the answer (e.g., "x ≠ 2").
- **Where training runs:** the dev machine has an NVIDIA RTX 3080 (10 GB) and 32 GB RAM, so the initial personal tuning and any heavy re-training run there. The tuned model is then copied to the Surface. On the Surface, any learning from corrections uses only lightweight adaptation, runs only while OneNote is idle (ideally while plugged in), and never competes with a live Solve. If lightweight on-device adaptation is not practical, corrections are collected on the Surface and folded in during the next re-training on the dev machine.

## 8. Left to the builder

- Which recognition model to use and how adaptation works (fine-tuning, few-shot, etc.), provided §3's targets are met on the user's real handwriting. **Prove this first:** an early spike should measure recognition accuracy on real samples of the user's handwriting before the rest is built around it.
- How ink is obtained from the OneNote selection (page XML, ink serialization, rendering to an image) and how the model consumes it.
- How the C# add-in and the Python/SymPy side communicate (separate process is expected, so a slow solve can never freeze OneNote).
- How the "beside the page" panel is implemented (e.g., a tool window docked next to the OneNote window), provided it does not cover the page.
- How the tuning session is presented (e.g., a generated OneNote page of prompts the user writes under).
- Repo layout, test strategy, and setup-script details.
