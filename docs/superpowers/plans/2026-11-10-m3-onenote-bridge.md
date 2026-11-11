# M3 OneNote Bridge: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A C# COM add-in that gives OneNote desktop a **Math** ribbon tab:
- **Solve** reads the lassoed selection, sends it to the M2 solver and writes the answer under the selection as ordinary page content.
- **Show steps**, **Keep going** and **Stop** work, and a status badge shows **Offline**.
- It registers for 32-bit and 64-bit OneNote.

**Architecture:** One .NET Framework 4.8 class library, `InkMath.AddIn`, holds everything. There are two layers:
- **Pure logic, unit-tested:**
  - `Protocol`: the M2 JSON lines;
  - `SelectionReader`: page XML → selection;
  - `AnswerWriter`: response → page XML;
  - `SolverClient`: the Python process;
  - `SolveController`: the flow and status text.
- **A thin COM shell:**
  - `Connect`: IDTExtensibility2 plus the ribbon;
  - `OneNotePage`: late-bound OneNote calls.

OneNote loads COM add-ins out of process in a `dllhost` surrogate. Ribbon callbacks therefore only queue work. All OneNote reads and writes and all solver I/O run on one background STA thread, and status changes are marshaled back to the ribbon thread.

Until M4, ink can't be recognized. Lassoed ink is saved locally for M4, and lassoed **typed text** goes straight to the solver as LaTeX. That keeps the bridge testable end to end now.

**Tech Stack:**
- C# on .NET Framework 4.8. It is built into Windows 11, so nothing needs installing on the Surface.
- Built with the .NET SDK (`dotnet build`). The SDK pulls the net48 reference assemblies automatically.
- xUnit 2 for tests.
- The PowerShell 5.1 built into Windows runs the registration scripts.
- Python 3.10 runs the M2 solver from `solver/.venv` on the dev machine. M6 bundles Python for the Surface.

**Spec:** `docs/superpowers/specs/2026-11-09-onenote-ink-math-design.md` (§2, §3, §6.1, §6.2 steps 1, 2 and 4, §6.7, §7, §8). Roadmap: `docs/superpowers/plans/2026-11-09-roadmap.md`. M2 protocol: `solver/inkmath_solver/server.py` and `schema.py`; M2 plan "Notes for later milestones → M3".

## Global Constraints

- **Never hang OneNote (spec §3).**
  - Every ribbon callback returns at once. It only reads state or queues work.
  - No OneNote COM call and no solver I/O runs on the ribbon thread.
- **Never modal (spec §3).** No `MessageBox` and no dialogs. All messages go to the ribbon status label.
- **Never move or alter the user's ink (spec §3).**
  - Writing adds exactly one new `one:Outline`.
  - The update XML contains only `one:Page ID` and that new Outline.
- **Write only on `ok`.** Every other status shows its message in the status label and writes nothing. That keeps the page free of clutter (spec §3).
- **Offline.** No network calls.
- **Both bitnesses (spec §6.1).**
  - The library is one AnyCPU `net48` assembly.
  - Registration writes the COM keys in both the 32-bit and the 64-bit registry views.
  - It uses no runtime dependencies outside the .NET Framework GAC: no NuGet packages at runtime, and JSON is handled with `System.Web.Script.Serialization.JavaScriptSerializer`.
- **No hard-coded user paths (spec §4).**
  - The solver location comes from `inkmath.settings.json` beside the DLL, written by `install/register.ps1`.
  - Logs and saved selections go under `%LOCALAPPDATA%\InkMath\`.
- **Handwriting stays local (spec §6.6).** No real ink goes into the repo. Fixtures replace every `one:Data` payload with `AAAA`.
- **Readable on a shared screen (spec §6.7):**
  - steps: 14 pt in `#1A1A1A`;
  - answer line: 16 pt bold in `#1A1A1A`;
  - decimal line and notes: 14 pt in `#1A1A1A`;
  - source line: 11 pt in `#555555`.
- **Show steps** is on by default on every start (spec §7).
- **Check-in (spec §3, M2):**
  - On `still_working`, the status label shows the server's message, and **Keep going** and **Stop** are enabled.
  - Without an answer, solving continues.
  - **Stop** is enabled for the whole solve.
- **Dead-solver rule (M2 note):** if no line arrives for 25 s during a solve, kill and restart the solver process. The solve ends with status `error` and message `Something went wrong solving this`.

**Status copy (exact strings):**

| When | Status label |
|---|---|
| Nothing selected | `Lasso a problem first.` |
| Ink selected (until M4) | `Ink saved. Handwriting reading isn't installed yet. Lasso typed text to test.` |
| Solve sent | `Solving…` |
| `still_working` | the response's `message` |
| `ok` | the response's `source` |
| `needs_operation` | `What should I do with this? ` + the choices' labels joined with ` · ` |
| `cannot_parse`, `cannot_solve`, `error`, `stopped` | the response's `message` |
| Solver failed to start | `The solver isn't running. Check the setup.` |
| Writing to the page failed | `Couldn't write the answer onto the page.` |
| Any other exception | `Something went wrong. Details are in the log.` |

**Operation labels**, used for `needs_operation` and reused by M5:

| Operation | Label |
|---|---|
| simplify | Simplify |
| factor | Factor |
| expand | Expand |
| solve | Solve |
| solve_system | Solve system |
| evaluate | Evaluate |
| evaluate_at | Evaluate at a point |
| derivative | Derivative |
| implicit_derivative | Implicit derivative |
| integrate | Integrate |
| limit | Limit |
| series | Series |
| identity | Check identity |
| ode | Solve ODE |

**Fixed IDs:**

| Item | Value |
|---|---|
| CLSID and AppID | `{7E3C1B52-4A9D-4F0E-9C61-2B8D5A4F3E17}` |
| ProgID | `InkMath.Connect` |
| Class | `InkMath.AddIn.Connect` |
| Add-in key | `Software\Microsoft\Office\OneNote\AddIns\InkMath.Connect` |
| LoadBehavior | `3` |
| FriendlyName | `Ink Math` |
| Description | `Solve handwritten math` |

## Review Focus

1. **A callback that throws.** If any COM entry point (OnConnection, a ribbon callback) throws, OneNote silently disables the add-in by setting LoadBehavior to 2. Expected: every entry point catches, logs and sets the status. Test: Task 6 `Callbacks_never_throw_when_controller_throws`.
2. **The solver's stderr is never read.** If stderr is not drained, the pipe fills and the solver blocks forever. Expected: stderr is drained continuously into the log. Test: Task 4 `Survives_chatty_stderr`, which uses a stub that writes 1 MB to stderr before answering.
3. **Unicode through the pipes.** Characters like `−`, `√`, `≈`, `⚠`, `π` and `x³` can be garbled by the console code page or a BOM. Expected: the answer text arrives byte-exact. Test: Task 4 `Real_solver_roundtrip_keeps_unicode` with `x^2=2` gives `x = −√2, x = √2`.
4. **Solve with no real selection.** This covers nothing lassoed, only the caret in a typed outline, or only the page title selected. Expected: `Lasso a problem first.` and nothing written. Tests: Task 2 `Caret_only_is_empty` and `Title_selection_is_ignored`; Task 5 `Empty_selection_writes_nothing`.
5. **The solver is missing, killed or silent.** Expected:
   - Solve never blocks;
   - a missing Python gives `The solver isn't running. Check the setup.`;
   - a killed or silent solver gives the error message and a restart, and the next solve works.

   Tests: Task 4 `Missing_python_fails_fast`, `Killed_process_gives_error_and_restarts` and `Silent_process_is_declared_dead`.

---

## File structure

```
addin/
  InkMath.sln
  InkMath.AddIn/InkMath.AddIn.csproj      net48, AnyCPU, ComVisible(false) by default
    Protocol.cs          SolverRequest, SolverResponse, SolverAnswer, Protocol (JSON), OperationLabels
    SelectionReader.cs   InkSelection, InkItem, PageRect, SelectionReader
    AnswerWriter.cs      AnswerWriter
    SolverClient.cs      ISolver, SolverSettings, SolverClient
    SolveController.cs   IOneNotePage, ISelectionStore, SolveController, StatusText
    Settings.cs          AddInSettings (inkmath.settings.json), Log, SelectionStore
    Com/ComInterfaces.cs IDTExtensibility2, IRibbonExtensibility, ext_ConnectMode, ext_DisconnectMode
    Com/Connect.cs       the COM class: lifecycle, ribbon callbacks, worker thread, UI marshaling
    Com/OneNotePage.cs   IOneNotePage over late-bound OneNote.Application
    Ribbon.xml           embedded resource
  InkMath.Tests/InkMath.Tests.csproj      net48, xunit
    ProtocolTests.cs, SelectionReaderTests.cs, AnswerWriterTests.cs, SolverClientTests.cs,
    SolveControllerTests.cs, ConnectTests.cs, RegistrationTests.cs
    fixtures/selection_typed.xml, selection_ink.xml, selection_caret.xml, selection_title.xml
    fixtures/stub_solver.py
install/
  register.ps1, unregister.ps1
docs/superpowers/m3-dev-check.md, docs/superpowers/m3-surface-check.md
```

**Test command (whole suite):** `rtk dotnet test addin/InkMath.sln`. Tests that need the real solver find it at `solver/.venv/Scripts/python.exe`, relative to the repo root. The repo root is found by walking up from the test assembly until a `.git` folder is found.

---

### Task 1: Scaffold and protocol

**Files:**
- Create: `addin/InkMath.sln`, both `.csproj` files, `Protocol.cs`, `ProtocolTests.cs`
- Modify: `.gitignore` (add `addin/**/bin/`, `addin/**/obj/`)

**Interfaces:**
- Produces:
  - `class SolverRequest { string Id; string Latex; string Operation; string Variable; string Point; bool ShowSteps = true; }`
  - `class SolverAnswer { string Latex; string Text; string Decimal; }`
  - `class SolverResponse { string Id; string Status; string Operation; string Variable; List<string> Choices; List<string> Steps; SolverAnswer Answer; List<string> Notes; bool Verified; string Source; string Message; int Ms; }`
    - The lists are never null.
  - `static class Protocol`:
    - `string ToJson(SolverRequest r)`: snake_case keys. Null optional fields are omitted.
    - `string Control(string id, string control)` gives `{"id":…,"control":…}`.
    - `SolverResponse Parse(string line)`.
    - `bool IsReady(string line)`.
  - `static class OperationLabels { string Label(string op); }`: the table in Global Constraints. An unknown op returns the op itself.

- [ ] **Step 1: Check the SDK.** Run `dotnet --list-sdks`. Expected: at least one SDK listed. If none is listed, stop and ask the user to run `winget install Microsoft.DotNet.SDK.10`.
- [ ] **Step 2: Scaffold.** Create the solution and both projects.
  - The library: `<TargetFramework>net48</TargetFramework>`, `<Reference Include="Microsoft.CSharp" />`, `System.Web.Extensions` and `System.Windows.Forms`, with `Ribbon.xml` as an `EmbeddedResource` (an empty placeholder until Task 6).
  - The tests: net48, `xunit` 2.9.x, `xunit.runner.visualstudio` 2.8.x and `Microsoft.NET.Test.Sdk` 17.x, referencing the library.
  - Run `rtk dotnet build addin/InkMath.sln`. Expected: build succeeded.
- [ ] **Step 3: Write the failing tests** in `ProtocolTests.cs`:

```csharp
[Fact] public void Request_json_uses_snake_case_and_omits_nulls() {
    var j = Protocol.ToJson(new SolverRequest { Id = "a", Latex = "3x-7=11", ShowSteps = false });
    Assert.Equal("{\"id\":\"a\",\"latex\":\"3x-7=11\",\"show_steps\":false}", j);
}
[Fact] public void Control_line() =>
    Assert.Equal("{\"id\":\"a\",\"control\":\"stop\"}", Protocol.Control("a", "stop"));
[Fact] public void Parses_ok_response_with_unicode() {
    var r = Protocol.Parse("{\"id\": \"a\", \"status\": \"ok\", \"operation\": \"solve\", \"variable\": \"x\", \"choices\": [\"solve\"], \"steps\": [\"Quadratic formula: a = 1, b = 0, c = −2\"], \"answer\": {\"latex\": \"x\", \"text\": \"x = −√2, x = √2\", \"decimal\": \"−1.41421, 1.41421\"}, \"notes\": [], \"verified\": true, \"source\": \"Solved offline · verified\", \"message\": \"\", \"ms\": 339}");
    Assert.Equal("x = −√2, x = √2", r.Answer.Text);
    Assert.True(r.Verified);
    Assert.Equal(339, r.Ms);
}
[Fact] public void Parses_response_without_answer() {
    var r = Protocol.Parse("{\"id\":\"b\",\"status\":\"needs_operation\",\"choices\":[\"factor\",\"evaluate_at\"],\"answer\":null,\"message\":\"What should I do with this?\"}");
    Assert.Null(r.Answer);
    Assert.Empty(r.Steps);
    Assert.Equal(new[] { "factor", "evaluate_at" }, r.Choices);
}
[Fact] public void Ready_line() {
    Assert.True(Protocol.IsReady("{\"ready\": true}"));
    Assert.False(Protocol.IsReady("{\"id\":\"a\"}"));
}
[Fact] public void Labels() {
    Assert.Equal("Evaluate at a point", OperationLabels.Label("evaluate_at"));
    Assert.Equal("graph", OperationLabels.Label("graph"));
}
```

- [ ] **Step 4: Run them.** `rtk dotnet test addin/InkMath.sln`. Expected: they fail to compile because the types are missing.
- [ ] **Step 5: Implement `Protocol.cs`** using `JavaScriptSerializer`. Write the request JSON by building a `Dictionary<string, object>` in key order: `id`, `latex`, `operation`, `variable`, `point`, `show_steps`.
- [ ] **Step 6: Run the tests.** Expected: 6 pass.
- [ ] **Step 7: Commit.** Message: `addin: scaffold net48 add-in and M2 protocol`. In `.claude/progress.json`, replace M3's steps with this plan's 7 task titles.

### Task 2: Selection reader

**Files:**
- Create: `SelectionReader.cs`, `SelectionReaderTests.cs`, four fixtures

**Interfaces:**
- Produces:
  - `struct PageRect { double X, Y, Width, Height; double Bottom => Y + Height; }`
  - `class InkItem { byte[] Isf; PageRect Bounds; }`
  - `class InkSelection { string PageId; List<InkItem> Ink; string TypedText; PageRect Bounds; bool IsEmpty => Ink.Count == 0 && string.IsNullOrWhiteSpace(TypedText); }`
  - `static InkSelection SelectionReader.Read(string pageXml)`.
    - The input is XML from `GetPageContent(pageId, out xml, piBinaryDataSelection = 3)`.
    - The namespace is `http://schemas.microsoft.com/office/onenote/2013/onenote`.

**Rules:**
- An element counts as selected when it has `selected="all"` or `selected="partial"`.
- **Ink:**
  - every selected `one:InkDrawing` gives its `one:Data` base64 (decoded) and its `Position`/`Size`;
  - every selected `one:InkWord` inside an `one:Outline` gives its data and the bounds of the containing Outline (M1 found that InkWords carry no position of their own).
- **Typed text:** the text of selected `one:T` elements in Outlines.
  - Remove HTML tags and decode entities.
  - Join with `\n` and trim.
  - A `one:T` whose text is empty after trimming is ignored. That is how a caret selection shows up.
- **Bounds** is the union of the selected items' bounds. For typed text, it uses the containing Outline's Position/Size.
- Anything under `one:Title` is ignored.

- [ ] **Step 1: Write the fixtures.** They are hand-written page XML in the 2013 schema, modeled on `spike/tests/fixtures/page_inkdrawing.xml`, and every `one:Data` is `AAAA`.
  - `selection_typed.xml`: an Outline at (36, 120) with size 200×30, holding `<one:T selected="all"><![CDATA[3x-7=11]]></one:T>`, plus an unselected InkDrawing elsewhere.
  - `selection_ink.xml`: two selected InkDrawings at (40, 100) 50×20 and (100, 110) 60×30, plus one unselected InkDrawing.
  - `selection_caret.xml`: an Outline whose only selected T is `<one:T selected="all"><![CDATA[]]></one:T>`.
  - `selection_title.xml`: a selected T inside `one:Title` only.
- [ ] **Step 2: Write the failing tests:**

```csharp
[Fact] public void Typed_text_selection() {
    var s = SelectionReader.Read(Fixture("selection_typed.xml"));
    Assert.Equal("3x-7=11", s.TypedText);
    Assert.Empty(s.Ink);
    Assert.Equal(new PageRect(36, 120, 200, 30), s.Bounds);
}
[Fact] public void Ink_selection_unions_bounds_and_skips_unselected() {
    var s = SelectionReader.Read(Fixture("selection_ink.xml"));
    Assert.Equal(2, s.Ink.Count);
    Assert.Equal(new PageRect(40, 100, 120, 40), s.Bounds);
    Assert.Equal(new byte[] { 0, 0, 0 }, s.Ink[0].Isf);   // "AAAA"
}
[Fact] public void Caret_only_is_empty() => Assert.True(SelectionReader.Read(Fixture("selection_caret.xml")).IsEmpty);
[Fact] public void Title_selection_is_ignored() => Assert.True(SelectionReader.Read(Fixture("selection_title.xml")).IsEmpty);
[Fact] public void Html_in_typed_text_is_stripped() =>
    Assert.Equal("x < 2", SelectionReader.Read(TypedPage("<span style='font-weight:bold'>x &lt; 2</span>")).TypedText);
[Fact] public void Page_id_is_read() => Assert.False(string.IsNullOrEmpty(SelectionReader.Read(Fixture("selection_ink.xml")).PageId));
```

`Fixture(name)` reads `fixtures/<name>`. Mark the fixtures `CopyToOutputDirectory`. `TypedPage(cdata)` returns `selection_typed.xml` with the CDATA replaced.

- [ ] **Step 3: Run them.** Expected: compile failure.
- [ ] **Step 4: Implement `SelectionReader.Read`** with `System.Xml.Linq`.
- [ ] **Step 5: Run them.** Expected: 6 pass.
- [ ] **Step 6: Commit.** Message: `addin: read lassoed ink and typed text from page XML`.

### Task 3: Answer writer

**Files:**
- Create: `AnswerWriter.cs`, `AnswerWriterTests.cs`

**Interfaces:**
- Consumes: `SolverResponse` (Task 1) and `PageRect` (Task 2).
- Produces: `static string AnswerWriter.BuildXml(string pageId, PageRect below, SolverResponse r)`.
  - It gives a `one:Page` element with the `ID` set, containing exactly one `one:Outline`.
  - The Outline has `<one:Position x="{below.X}" y="{below.Bottom + 14}" z="0"/>` and `one:OEChildren`, with one `one:OE` per line in this order:
    1. each step;
    2. the answer line: `Answer.Text`, bold;
    3. the decimal line `≈ {Decimal}`, only when `Decimal` is non-empty and `Answer.Text` does not contain `≈`;
    4. each note;
    5. the source line.
  - Each line's text is `<one:T><![CDATA[<span style='…'>escaped text</span>]]></one:T>`, using the styles from Global Constraints.
  - Escaping is HTML (`&` `<` `>`), so `]]>` can never appear.
  - Numbers are written with `CultureInfo.InvariantCulture`.

- [ ] **Step 1: Write the failing tests:**

```csharp
static SolverResponse Ok(params string[] steps) => new SolverResponse { Id = "a", Status = "ok", Steps = steps.ToList(),
    Answer = new SolverAnswer { Text = "x = −√2, x = √2", Decimal = "−1.41421, 1.41421" },
    Notes = new List<string> { "x ≠ 2" }, Source = "Solved offline · verified" };

[Fact] public void Lines_in_order() {
    var lines = Texts(AnswerWriter.BuildXml("P1", new PageRect(36, 120, 200, 30), Ok("Quadratic formula")));
    Assert.Equal(new[] { "Quadratic formula", "x = −√2, x = √2", "≈ −1.41421, 1.41421", "x ≠ 2", "Solved offline · verified" }, lines);
}
[Fact] public void Placed_under_selection() {
    var pos = Xml(AnswerWriter.BuildXml("P1", new PageRect(36.5, 120, 200, 30), Ok())).Descendants(One + "Position").Single();
    Assert.Equal("36.5", (string)pos.Attribute("x"));
    Assert.Equal("164", (string)pos.Attribute("y"));
}
[Fact] public void Only_one_outline_and_nothing_else() {
    var page = Xml(AnswerWriter.BuildXml("P1", new PageRect(0, 0, 1, 1), Ok()));
    Assert.Equal("P1", (string)page.Attribute("ID"));
    Assert.Equal(new[] { "Outline" }, page.Elements().Select(e => e.Name.LocalName));
}
[Fact] public void No_decimal_line_when_text_has_approx() { /* Text "x ≈ 0.347296", Decimal "0.347296" → no "≈ …" line */ }
[Fact] public void Hidden_steps_mean_no_step_lines() { /* Steps empty → first line is the answer */ }
[Fact] public void Escapes_html() { /* Text "x < 2 & y > 3" → Texts() returns it unchanged; raw XML contains "&lt;" */ }
[Fact] public void Answer_is_bold_and_16pt_source_is_11pt_grey() { /* CDATA of answer contains "font-weight:bold" and "16pt"; source contains "11pt" and "#555555" */ }
```

`Texts(xml)` gives each OE's span text, HTML-decoded. `One` is the namespace. Write the three commented bodies as real assertions.

- [ ] **Step 2: Run them.** Expected: compile failure.
- [ ] **Step 3: Implement `AnswerWriter.BuildXml`.**
- [ ] **Step 4: Run them.** Expected: 7 pass.
- [ ] **Step 5: Commit.** Message: `addin: build the answer outline (steps, answer, decimal, notes, source)`.

### Task 4: Solver client

**Files:**
- Create: `SolverClient.cs`, `SolverClientTests.cs`, `fixtures/stub_solver.py`

**Interfaces:**
- Consumes: `Protocol` (Task 1).
- Produces:
  - `class SolverSettings { string PythonExe; string SolverDir; double CheckinSeconds = 20; double DeadAfterSeconds = 25; double ReadyTimeoutSeconds = 60; string ExtraArgs = null; }`
    - `ExtraArgs` replaces `-m inkmath_solver --checkin N` when set. The tests use it to run the stub.
  - `interface ISolver : IDisposable`:
    - `bool Start()`: launch and wait for ready. False on failure. Safe to call again.
    - `SolverResponse Solve(SolverRequest req, Action<SolverResponse> onCheckIn)`: blocks the calling worker thread until the final response.
    - `void Continue(string id)`.
    - `void Stop(string id)`.
  - `class SolverClient : ISolver`.

**Rules:**
- **Launching the process:**
  - Run `PythonExe -m inkmath_solver --checkin {CheckinSeconds}` in `SolverDir`.
  - Set `CreateNoWindow`.
  - Redirect stdin, stdout and stderr.
  - stdout is read as UTF-8.
  - stdin is a `StreamWriter(BaseStream, new UTF8Encoding(false))` with AutoFlush.
  - Set the environment variable `PYTHONUTF8=1`.
- **stderr** is drained on its own thread into `Log`.
- **stdout** is read on its own thread into a `BlockingCollection<string>`.
- **`Solve`:**
  - Calls `Start()` if the process isn't running, and returns a `SolverResponse { Status = "error", Message = "The solver isn't running. Check the setup." }` if that fails.
  - Writes the request.
  - Takes lines:
    - a line whose id matches and whose status is `still_working` → `onCheckIn`;
    - a matching final line → return it;
    - other ids → log and skip.
  - No line for `DeadAfterSeconds` → kill, restart, and return the error `Something went wrong solving this`.
  - Process exit or end of stdout → the same, as a crash.
- **`Continue`/`Stop`** write a control line. They are thread-safe, because they are called from the ribbon thread while `Solve` blocks on the worker thread.
- **`Dispose`** closes stdin, waits 3 s, then kills.

**Stub solver:** `stub_solver.py <mode>`.
- It always prints `{"ready": true}` first, then reads one request.
- Mode `answer` replies ok with `answer.text` `"x = 6"`.
- Mode `stderr` writes 1 MB to stderr first, then replies.
- Mode `silent` never replies.
- Mode `crash` exits with code 3.

- [ ] **Step 1: Write the failing tests.** `Real()` builds settings for the repo's venv with `CheckinSeconds = 1`. `Stub(mode)` uses the venv's Python with `ExtraArgs = "<fixtures>/stub_solver.py <mode>"` and `DeadAfterSeconds = 3`.

```csharp
[Fact] public void Real_solver_roundtrip_keeps_unicode() {
    using var s = new SolverClient(Real());
    Assert.True(s.Start());
    var r = s.Solve(new SolverRequest { Id = "a", Latex = "x^2=2" }, _ => { });
    Assert.Equal("ok", r.Status);
    Assert.Equal("x = −√2, x = √2", r.Answer.Text);
}
[Fact] public void Checkin_then_stop() {
    using var s = new SolverClient(Real());
    s.Start();
    var checkins = 0;
    var r = s.Solve(new SolverRequest { Id = "slow", Latex = @"\int e^{x^2}\sin(x^3)\cos(\sqrt{x})dx", Operation = "integrate" },
                    c => { checkins++; s.Stop("slow"); });
    Assert.Equal(1, checkins);
    Assert.Equal("stopped", r.Status);
    Assert.Equal("ok", s.Solve(new SolverRequest { Id = "b", Latex = "x+1=2" }, _ => { }).Status);
}
[Fact] public void Stop_before_checkin_from_another_thread() { /* Task.Delay(300) then Stop("slow") on a thread-pool thread; Solve returns "stopped" in < 3 s */ }
[Fact] public void Survives_chatty_stderr() { /* Stub("stderr") → ok, within 10 s */ }
[Fact] public void Silent_process_is_declared_dead() { /* Stub("silent") → status "error", message "Something went wrong solving this", in 3–6 s */ }
[Fact] public void Killed_process_gives_error_and_restarts() { /* Stub("crash") → error; a second Solve (the stub restarted) → still answers "error" or "ok" without hanging */ }
[Fact] public void Missing_python_fails_fast() { /* PythonExe = @"C:\nope\python.exe" → Start() false in < 2 s; Solve → "The solver isn't running. Check the setup." */ }
[Fact] public void Dispose_ends_the_process() { /* Real(): Start, remember the pid, Dispose → the process exits within 5 s */ }
```

Write the commented bodies as real assertions.

- [ ] **Step 2: Run them.** Expected: compile failure.
- [ ] **Step 3: Implement `SolverClient` and the stub.**
- [ ] **Step 4: Run them.** Expected: 8 pass. Also run the whole suite: everything passes.
- [ ] **Step 5: Commit.** Message: `addin: solver client (warm process, check-in, stop, dead-process restart)`.

### Task 5: Solve controller

**Files:**
- Create: `SolveController.cs`, `Settings.cs` (`Log`, `SelectionStore`, `AddInSettings`), `SolveControllerTests.cs`

**Interfaces:**
- Consumes: `ISolver` (Task 4), `SelectionReader` (Task 2), `AnswerWriter` (Task 3) and `OperationLabels` (Task 1).
- Produces:
  - `interface IOneNotePage`:
    - `string ReadCurrentPageSelection()`: page XML with `piBinaryDataSelection`.
    - `void Update(string xml)`.
  - `interface ISelectionStore { void SaveLast(InkSelection s); }`. The real one writes `%LOCALAPPDATA%\InkMath\selections\last.json` with the page id, the bounds and base64 ISF per item.
  - `class SolveController`:
    - Constructor: `(IOneNotePage page, ISolver solver, ISelectionStore store, Action changed)`.
    - Properties: `bool ShowSteps = true`, `string Status = ""`, `bool Busy`, `bool AwaitingCheckIn`.
    - `void Solve()`: runs on the worker thread. It sets `Busy`, updates `Status`, and calls `changed()` after every change.
    - `void KeepGoing()`: calls `solver.Continue` and clears `AwaitingCheckIn`.
    - `void Stop()`: calls `solver.Stop` on the current id.
    - Request ids are `"r1"`, `"r2"` and so on.
  - `static class Log { void Info(string m); void Error(string m, Exception e); }`. It writes to `%LOCALAPPDATA%\InkMath\inkmath.log` and never throws.
  - `class AddInSettings { string PythonExe; string SolverDir; static AddInSettings Load(string dllDir); }`. It reads `inkmath.settings.json` and returns null when the file is missing.

**Flow of `Solve()`:**
1. Read the selection.
2. If it is empty → `Lasso a problem first.`
3. If it has ink → `store.SaveLast` and the ink status message.
4. If it has only typed text →
   1. `Solving…`;
   2. `solver.Solve` with `ShowSteps`;
   3. on `ok` → `page.Update(AnswerWriter.BuildXml(...))`, and the status is the source;
   4. otherwise → the status table.
5. Any exception → logged, and the status from the table.
6. `Busy` is cleared in a `finally` block.
7. Log the read, solve and write times in ms.

- [ ] **Step 1: Write the failing tests** with fakes:
  - `FakePage` returns a fixture's XML and records `Update` calls.
  - `FakeSolver` returns a scripted response and can raise check-ins.
  - `FakeStore` records saves.

```csharp
[Fact] public void Typed_problem_is_solved_and_written() { /* selection_typed + ok → 1 Update containing "x = 6"; Status == "Solved offline · verified"; Busy false */ }
[Fact] public void Empty_selection_writes_nothing() { /* selection_caret → Status "Lasso a problem first."; 0 Updates; solver not called */ }
[Fact] public void Ink_is_saved_not_solved() { /* selection_ink → store saved once; solver not called; ink status copy */ }
[Fact] public void Needs_operation_lists_labels() { /* choices factor, evaluate_at → "What should I do with this? Factor · Evaluate at a point"; 0 Updates */ }
[Fact] public void Non_ok_writes_nothing() { /* cannot_solve message "Couldn't determine whether this series converges" → that status; 0 Updates */ }
[Fact] public void Checkin_sets_awaiting_and_keep_going_continues() { /* FakeSolver raises still_working → AwaitingCheckIn true, Status is its message; KeepGoing() → solver.Continue("r1") called, AwaitingCheckIn false */ }
[Fact] public void Show_steps_off_is_sent() { /* ShowSteps = false → request.ShowSteps false */ }
[Fact] public void Write_failure_has_its_own_message() { /* FakePage.Update throws → "Couldn't write the answer onto the page."; Busy false */ }
[Fact] public void Read_failure_is_caught() { /* ReadCurrentPageSelection throws → "Something went wrong. Details are in the log." */ }
```

Write the commented bodies as real assertions.

- [ ] **Step 2: Run them.** Expected: compile failure.
- [ ] **Step 3: Implement** `SolveController`, `Log`, `SelectionStore` and `AddInSettings`.
- [ ] **Step 4: Run the whole suite.** Expected: all pass.
- [ ] **Step 5: Commit.** Message: `addin: solve controller (selection → solver → page, status text)`.

### Task 6: COM shell and ribbon

**Files:**
- Create: `Com/ComInterfaces.cs`, `Com/Connect.cs`, `Com/OneNotePage.cs`, `Ribbon.xml`, `ConnectTests.cs`

**Interfaces:**
- Consumes: `SolveController`, `SolverClient`, `AddInSettings`, `Log` and `SelectionStore` (Task 5).
- **COM interface declarations** (`[ComImport, InterfaceType(ComInterfaceType.InterfaceIsDual)]`; DispIds in order):
  - `IDTExtensibility2`, `[Guid("B65AD801-ABAF-11D0-BB8B-00A0C90F2744")]`:
    - `OnConnection(object Application, ext_ConnectMode ConnectMode, object AddInInst, ref Array custom)`, DispId 1;
    - `OnDisconnection(ext_DisconnectMode RemoveMode, ref Array custom)`, DispId 2;
    - `OnAddInsUpdate(ref Array custom)`, DispId 3;
    - `OnStartupComplete(ref Array custom)`, DispId 4;
    - `OnBeginShutdown(ref Array custom)`, DispId 5.
  - `IRibbonExtensibility`, `[Guid("000C0396-0000-0000-C000-000000000046")]`: `string GetCustomUI(string RibbonID)`, DispId 1.
- **`Connect`:**
  - Attributes: `[ComVisible(true)]`, `[Guid("7E3C1B52-4A9D-4F0E-9C61-2B8D5A4F3E17")]`, `[ProgId("InkMath.Connect")]`, `[ClassInterface(ClassInterfaceType.AutoDispatch)]`.
  - Implements both interfaces.
  - Ribbon callbacks are public methods taking `object control`, with the control id read through `dynamic`:
    - `OnRibbonLoad(object ribbonUI)`;
    - `OnSolve(object control)`;
    - `OnKeepGoing(object control)`;
    - `OnStop(object control)`;
    - `OnToggleSteps(object control, bool pressed)`;
    - `bool GetPressed(object control)`;
    - `bool GetEnabled(object control)`;
    - `string GetLabel(object control)`.
  - `GetEnabled` rules:
    - `solveButton` = !Busy;
    - `keepGoingButton` = AwaitingCheckIn;
    - `stopButton` = Busy.
  - `GetLabel` rules:
    - `badgeLabel` = `Offline`;
    - `statusLabel` = Status, or a single space when Status is empty, because an empty label collapses.
- **Threads:**
  - `OnConnection` captures a `WindowsFormsSynchronizationContext` on the ribbon thread, creating a hidden `Control` so it has a window handle.
  - It starts one background STA worker thread with a `BlockingCollection<Action>` queue.
  - `OnStartupComplete` queues `solver.Start()`.
  - `OnSolve` queues `controller.Solve()`.
  - `changed` posts `ribbon.Invalidate()` to the captured context.
  - `OnBeginShutdown` and `OnDisconnection` dispose the solver and end the worker.
  - Every public method body is wrapped in try/catch, which logs and returns a safe default.
- **`OneNotePage`:**
  - Creates its own `OneNote.Application` on the worker thread with `Activator.CreateInstance(Type.GetTypeFromProgID("OneNote.Application"))` and uses `dynamic`.
  - `ReadCurrentPageSelection()`: `app.Windows.CurrentWindow.CurrentPageId`, then `GetPageContent(id, out xml, 3)`.
  - `Update(xml)`: `UpdatePageContent(xml)`.
- **`Ribbon.xml`:**
  - Namespace `http://schemas.microsoft.com/office/2009/07/customui`, with `onLoad="OnRibbonLoad"`.
  - One tab, `inkMathTab`, labeled `Math`.
  - Group `solveGroup`, labeled `Solve`:
    - `solveButton` (large, label `Solve`);
    - `showStepsToggle` (`Show steps`, `getPressed`/`onAction="OnToggleSteps"`);
    - `keepGoingButton` (`Keep going`);
    - `stopButton` (`Stop`).
  - Group `statusGroup`, labeled `Status`: `badgeLabel` and `statusLabel` (both `getLabel="GetLabel"`).
  - No `imageMso` in v1.

- [ ] **Step 1: Write the failing tests:**

```csharp
[Fact] public void Ribbon_xml_is_valid_and_every_callback_exists() {
    var xml = new Connect().GetCustomUI("Microsoft.OneNote.Page");
    var doc = XDocument.Parse(xml);
    var callbacks = doc.Descendants().SelectMany(e => e.Attributes())
        .Where(a => a.Name.LocalName.StartsWith("on") || a.Name.LocalName.StartsWith("get")).Select(a => a.Value).Distinct();
    foreach (var name in callbacks) Assert.NotNull(typeof(Connect).GetMethod(name));
    Assert.Equal("Math", (string)doc.Descendants().Single(e => (string)e.Attribute("id") == "inkMathTab").Attribute("label"));
}
[Fact] public void Com_identity() { /* the Guid and ProgId attributes on Connect equal the Fixed IDs; ComVisible true */ }
[Fact] public void Labels_and_enabled_when_idle() { /* without OnConnection (controller null): GetLabel badge == "Offline", status == " ", GetEnabled(solve) true, stop false; GetPressed(steps) true */ }
[Fact] public void Callbacks_never_throw_when_controller_throws() { /* inject a controller whose members throw (internal test ctor); every public callback returns without throwing */ }
```

`FakeControl` is a class with a public `Id` property. `dynamic` reads it the same way it reads the real IRibbonControl. Write the commented bodies as real assertions.

- [ ] **Step 2: Run them.** Expected: compile failure.
- [ ] **Step 3: Implement** the COM interfaces, `Connect`, `OneNotePage` and `Ribbon.xml`.
- [ ] **Step 4: Run the whole suite.** Expected: all pass.
- [ ] **Step 5: Commit.** Message: `addin: COM shell, Math ribbon tab, OneNote page access`.

### Task 7: Registration, dev check and Surface check

**Files:**
- Create: `install/register.ps1`, `install/unregister.ps1`, `RegistrationTests.cs`, `docs/superpowers/m3-dev-check.md`, `docs/superpowers/m3-surface-check.md`
- Modify: `docs/superpowers/plans/2026-11-09-roadmap.md` (the M3 row status), `.claude/progress.json`

**Interfaces:**
- `register.ps1 -DllPath <path> [-PythonExe <path>] [-SolverDir <path>] [-KeyPrefix 'Software']`
  - It runs without admin, using HKCU only.
  - Under `<KeyPrefix>\Classes`, it writes in **both** `RegistryView.Registry32` and `RegistryView.Registry64`, using `[Microsoft.Win32.RegistryKey]::OpenBaseKey('CurrentUser', view)`:
    - `CLSID\{guid}`:
      - default value = `InkMath.Connect`;
      - `AppID` = `{guid}`.
    - `CLSID\{guid}\InprocServer32`:
      - default value = `mscoree.dll`;
      - `ThreadingModel` = `Both`;
      - `Class` = `InkMath.AddIn.Connect`;
      - `Assembly` = `InkMath.AddIn, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null`;
      - `RuntimeVersion` = `v4.0.30319`;
      - `CodeBase` = the `file:///` URI of the DLL.
    - `CLSID\{guid}\ProgId`: default value = `InkMath.Connect`.
    - `AppID\{guid}`: `DllSurrogate` = `""`.
    - `InkMath.Connect\CLSID`: default value = `{guid}`.
  - It writes the add-in key under `<KeyPrefix>\Microsoft\Office\OneNote\AddIns\InkMath.Connect`, with `LoadBehavior` (DWORD) 3, `FriendlyName` and `Description`.
  - When `-PythonExe` is given, it writes `inkmath.settings.json`, holding `pythonExe` and `solverDir`, beside the DLL.
- `unregister.ps1 [-KeyPrefix 'Software']` deletes all of the above in both views.

- [ ] **Step 1: Write the failing tests.** They run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File install/register.ps1 …` with `-KeyPrefix "Software\InkMathTest-<new guid>"` against a temporary copy of the built DLL.

```csharp
[Fact] public void Register_writes_both_views_and_settings() { /* for each view: CLSID…\InprocServer32 Class == "InkMath.AddIn.Connect", CodeBase ends with "InkMath.AddIn.dll", AppID\{guid} has DllSurrogate == ""; AddIns key LoadBehavior == 3; settings json has pythonExe */ }
[Fact] public void Unregister_removes_everything() { /* after unregister, the test prefix key has no CLSID/AppID/AddIns subkeys in either view; then delete the prefix key */ }
```

- [ ] **Step 2: Run them.** Expected: fail, because the scripts are missing.
- [ ] **Step 3: Write the scripts.** Run the tests. Expected: pass. Run the whole suite. Expected: all pass.
- [ ] **Step 4: Dev load check.** This is automated evidence that 32-bit OneNote loads the add-in.
  1. Close OneNote.
  2. Run `rtk dotnet build addin/InkMath.sln -c Release`.
  3. Run `install/register.ps1` with the Release DLL, the venv's `python.exe` and `solver/`.
  4. Start OneNote and wait 20 s.
  5. Expected:
     - `%LOCALAPPDATA%\InkMath\inkmath.log` has the lines written by `OnConnection`, `GetCustomUI` and a successful `solver.Start()`;
     - the AddIns key `LoadBehavior` is still 3.
  - **If OneNote doesn't load it** (no log line, or LoadBehavior changes to 2):
    1. Use systematic debugging: check the `AppID`/`DllSurrogate` keys and the Event Viewer → Application log for `dllhost` errors.
    2. If the per-user (HKCU) registration is the cause, rule to register under HKLM and make the setup elevated, and ledger it.
- [ ] **Step 5: Write `m3-dev-check.md`.** It is a 3-minute check for the user on the dev machine:
  1. Open OneNote. The **Math** tab is there, with **Solve**, **Show steps** (on), **Keep going** and **Stop** (greyed out), and **Offline**.
  2. Type `3x-7=11` on a page, lasso it and tap **Solve**.
     - Expected: `x = 6` with steps appears under it in large dark text, ending in `Solved offline · verified`. The status shows the same source line.
  3. Tap **Solve** with nothing selected. Expected: `Lasso a problem first.` and nothing written.
  4. Lasso some handwriting and tap **Solve**. Expected: the ink status message; the ink is unchanged and nothing is written.
  5. Type `\int e^{x^2}\sin(x^3)\cos(\sqrt{x})dx`, lasso it and tap **Solve**.
     - Expected: after 20 s the status reads `This one's taking a while. Keep going or stop?` and **Keep going** is enabled.
     - Tap **Stop**. Expected: `Stopped.`
  6. Turn off **Show steps** and solve `3x-7=11` again. Expected: only the answer and the source line.
- [ ] **Step 6: Write `m3-surface-check.md`.** It is a 64-bit load check, about 10 minutes.
  - Copy `addin/InkMath.AddIn/bin/Release/net48/` and `install/` to the Surface, for example via OneDrive.
  - Run `register.ps1 -DllPath …` without Python, because the solver arrives in M6.
  - Open OneNote. The Math tab appears.
  - Lasso typed text and tap **Solve**. Expected: `The solver isn't running. Check the setup.`. That proves that 64-bit loading, the ribbon, reading the selection and the status label all work.
  - Lasso ink and tap Solve. Expected: the ink message.
  - Run `unregister.ps1` afterwards if wanted.
  - **Ruling for the executor:** the Surface run is optional now and is otherwise batched into M6, per spec §6.7 (few Surface round-trips). Tell the user it exists.
- [ ] **Step 7: Commit.** Message: `install: per-user registration for 32- and 64-bit OneNote; M3 check sheets`. Then mark M3's steps done in `progress.json`, except the dev check, which stays open until the user confirms it.

---

## Notes for later milestones (not tasks here)

- **M4:**
  - Replace the ink branch of `SolveController.Solve()`: send `InkSelection` to the recognizer service, which reads `Ink[i].Isf` plus the bounds. `last.json` is a ready-made sample input.
  - Recognition must stay off the ribbon thread, the same as solving.
- **M5:**
  - The confirm panel sits between the selection read and `solver.Solve`.
  - It uses `OperationLabels` for the action menu.
  - It replaces the ribbon-only Keep going/Stop with panel buttons that call `SolveController.KeepGoing`/`Stop`.
  - The typed-text path becomes "Type it instead".
- **M6:**
  - `register.ps1` becomes part of the Surface setup script, with `-PythonExe` pointing at the bundled Python.
  - Measure on the Surface the time from Solve to the answer on the page; the log already records read, solve and write times.
