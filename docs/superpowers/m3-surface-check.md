# M3 Surface check (64-bit OneNote): about 10 minutes, optional now

This proves the add-in loads in 64-bit OneNote. The solver isn't on the Surface until M6, so Solve can only report that.
If you'd rather keep Surface trips few, skip this now: M6's setup check covers it.

1. **Copy two folders to the Surface** (OneDrive works), for example into `C:\InkMath\`:
   - `addin\InkMath.AddIn\bin\Release\net48\` → `C:\InkMath\addin\`
   - `install\` → `C:\InkMath\install\`
2. **Register.** Close OneNote. Open PowerShell (no admin needed) and run:
   ```
   powershell -ExecutionPolicy Bypass -File C:\InkMath\install\register.ps1 -DllPath C:\InkMath\addin\InkMath.AddIn.dll
   ```
3. **Tab.** Open OneNote. Expected: a **Math** tab with **Solve**, **Show steps**, **Keep going**, **Stop** and **Offline**.
4. **Typed text.** Type `3x-7=11`, select it and tap **Solve**.
   - Expected: `The solver isn't running. Check the setup.` That is correct for now; it proves 64-bit loading, the ribbon and reading the selection all work.
5. **Ink.** Lasso handwriting and tap **Solve**. Expected: the "Ink saved…" message.
6. **Report.** Send a photo of the ribbon, plus the first 5 lines of `%LOCALAPPDATA%\InkMath\inkmath.log`. Expected: the first line ends in `64-bit`.
7. **Optional cleanup:**
   ```
   powershell -ExecutionPolicy Bypass -File C:\InkMath\install\unregister.ps1
   ```
