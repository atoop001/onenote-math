# M3 dev check (this PC, 32-bit OneNote): about 3 minutes

The add-in is already registered on this PC. If OneNote was open before registering, close it and open it again.

1. **Tab.** Open OneNote and click the **Math** tab.
   - Expected: **Solve**, **Show steps** (pressed), **Keep going** and **Stop** (both greyed out), and **Offline** under Status.
2. **Typed problem.** Type `3x-7=11` on a page, lasso it (or select it), and tap **Solve**.
   - Expected: under it appear "Add 7 to both sides…", then **x = 6** in larger bold text, then `Solved offline · verified` in small grey text.
   - The status label shows `Solved offline · verified`.
3. **Nothing selected.** Click on an empty spot and tap **Solve**.
   - Expected: `Lasso a problem first.` Nothing is written.
4. **Handwriting.** Lasso some handwriting and tap **Solve**.
   - Expected: `Ink saved. Handwriting reading isn't installed yet. Lasso typed text to test.` Your ink is unchanged and nothing is written.
5. **Slow problem.** Type `\int e^{x^2}\sin(x^3)\cos(\sqrt{x})dx`, select it and tap **Solve**.
   - Expected: after about 20 s the status reads `This one's taking a while. Keep going or stop?` and **Keep going** lights up.
   - Tap **Stop**. Expected: `Stopped.`
6. **Steps off.** Turn off **Show steps** and solve `3x-7=11` again.
   - Expected: only **x = 6** and the source line.

If anything differs, send a photo of the ribbon and the page. The log is at `%LOCALAPPDATA%\InkMath\inkmath.log`.

To remove the add-in: run `install\unregister.ps1` in PowerShell, then restart OneNote.
