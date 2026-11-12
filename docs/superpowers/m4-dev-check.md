# M4 dev check (about 5 minutes, on the dev PC)

The add-in now reads lassoed handwriting and shows what it read in the status label. It does **not** solve ink yet: solving waits for M5's confirm panel (spec §6.2, nothing is solved before you confirm). Typed text still solves as in M3.

1. **Open OneNote and wait about 40 seconds.** The handwriting reader loads in the background (about 36 s on this PC).
2. **Lasso your 3x − 7 = 11 ink and tap Math → Solve.**
   - Expected: the status label shows `Read: 3x-7=11 · 1.5 s` (the time may differ; under 3 s is the target).
   - Nothing is written to the page.
3. **Lasso a messier problem and tap Solve.**
   - Expected: `Read: … · n to check` when some symbols are uncertain. (M5 will highlight those symbols.)
4. **Restart OneNote and tap Solve on ink within 10 seconds.**
   - Expected: `The handwriting reader is still starting. Try again in a moment.`
   - Then select typed text (e.g. `3x-7=11`) and tap Solve: it still solves right away.
5. **Check the log:** `%LOCALAPPDATA%\InkMath\inkmath.log` has a line like `read k1: 3x-7=11 · 0 low · 1500 ms (reader 950 ms) · texteller-tuned`.

If any step doesn't match, tell Claude what the status label said; details are in the log.
