# OneNote Ink Math

A OneNote desktop add-in for a math tutor. Lasso handwritten math on a Surface, tap **Math → Solve**, and get the answer with the key steps written under the ink. Everything runs offline on the device.

## How it works

1. **Select.** You lasso your handwriting in OneNote and tap **Solve** on the **Math** tab.
2. **Read.** The add-in (C#) pulls the selected ink off the page and sends it to the **reader**, a local Python service. The reader turns the ink into an image and reads it as LaTeX with TexTeller, a handwriting-math model fine-tuned on the tutor's own writing. Each symbol gets a confidence score and 2–3 alternatives.
3. **Confirm.** *(M5, not built yet.)* A panel shows what was read and highlights unsure symbols so you can fix them with one tap.
4. **Solve.** The **solver**, a second local Python service built on SymPy, works out the problem type, solves it, writes tutor-style key steps, and checks the answer a second, independent way.
5. **Write.** The add-in adds the answer and steps to the page as a new box under your selection.

Typed math works too: select typed LaTeX and **Solve** skips the reading step.

## Status

| Milestone | What | Status |
|---|---|---|
| M0 | Design spec and roadmap | Done |
| M1 | Handwriting accuracy spike and go/no-go gate | Done |
| M2 | Solver engine | Done |
| M3 | OneNote bridge (COM add-in, Math tab) | Done |
| M4 | Recognizer service (reader) and personal tuning | Built; dev check pending |
| M5 | Confirm panel | Not started |
| M6 | Integration and Surface install | Not started |
| M7 | Online reader (only if needed) | Not started |

Live progress is in [`.claude/progress.json`](.claude/progress.json). The full plan is the [roadmap](docs/superpowers/plans/2026-11-09-roadmap.md).

**Reading accuracy** on 60 test problems in the tutor's handwriting: 97% needed no fixes and 100% needed at most 2 fixes, with a median of about 1 s per read on the CPU ([M4 results](docs/superpowers/spike/2026-11-m4-tuning-results.md)).

## File tree

```
onenote-math/
├── addin/                    C# OneNote COM add-in (.NET Framework 4.8)
│   ├── InkMath.slnx            Solution file
│   ├── InkMath.AddIn/          The add-in OneNote loads
│   │   ├── Com/
│   │   │   ├── Connect.cs        Add-in entry point: Math tab ribbon, starts/stops the reader and solver
│   │   │   ├── OneNotePage.cs    Reads the current page and writes to it via OneNote's COM API
│   │   │   └── ComInterfaces.cs  COM interface declarations (IDTExtensibility2, ribbon)
│   │   ├── Ribbon.xml            The Math tab and its Solve button
│   │   ├── SolveController.cs    The Solve flow: selection → read ink → solve → write answer
│   │   ├── SelectionReader.cs    Finds the lassoed ink or typed text in the page XML
│   │   ├── ReaderClient.cs       Talks to the Python reader service
│   │   ├── SolverClient.cs       Talks to the Python solver service
│   │   ├── JsonLinesProcess.cs   Shared code for one warm Python process speaking JSON lines
│   │   ├── Protocol.cs           Request/response types matching the solver's schema
│   │   ├── AnswerWriter.cs       Builds the XML for the answer box under the selection
│   │   ├── Settings.cs           Reads inkmath.settings.json (written by the setup script)
│   │   └── Log.cs                Append-only log at %LOCALAPPDATA%\InkMath\inkmath.log
│   └── InkMath.Tests/          xUnit tests, sample page XML, and stub reader/solver scripts
│
├── reader/                   Python handwriting reader (M4)
│   ├── inkmath_reader/
│   │   ├── server.py             JSON-lines service: "read" ink, save "correction"s
│   │   ├── ink.py                Decodes OneNote ink (ISF) into strokes
│   │   ├── render.py             Draws strokes as a fixed-height image
│   │   ├── recognize.py          Runs TexTeller offline; keeps per-token probabilities
│   │   ├── symbols.py            Splits LaTeX into symbols with confidence and alternatives
│   │   ├── calibration.py        Loads the "unsure symbol" threshold
│   │   ├── corrections.py        Stores the tutor's fixes locally for later retraining
│   │   └── paths.py              Model and user-data folder locations
│   ├── train/                  Personal fine-tuning (run on the GPU)
│   │   ├── dataset.py            Loads tune samples and corrections; augments them
│   │   ├── finetune.py           Fine-tunes TexTeller on the tutor's handwriting
│   │   └── evaluate.py           Accept/reject gate vs the base model; sets the threshold; writes the report
│   └── tests/
│
├── solver/                   Python offline solver (M2), built on SymPy
│   ├── inkmath_solver/
│   │   ├── server.py             JSON-lines service the add-in calls
│   │   ├── engine.py             Request → response: parse, choose operation, solve, verify
│   │   ├── canonical.py          Fixes known reader quirks (e.g. lnx → \ln x) before parsing
│   │   ├── parse.py              LaTeX → problem
│   │   ├── infer.py              Picks the operation, or offers choices when the ink is ambiguous
│   │   ├── problem.py            The parsed-problem type
│   │   ├── schema.py             Request/response types shared with the add-in
│   │   ├── verify.py             Independent answer checks
│   │   ├── textfmt.py            One-line readable answer text
│   │   ├── bench.py              Latency benchmark
│   │   └── ops/
│   │       ├── algebra.py          Equations, systems, simplify/factor, identities (with key steps)
│   │       ├── calculus.py         Derivatives, limits, integrals, ODEs
│   │       ├── series.py           Series convergence tests
│   │       └── base.py             Shared operation types
│   └── tests/
│
├── spike/                    M1 accuracy experiment (kept for re-scoring)
│   ├── make_pages.py           Creates the handwriting prompt pages in OneNote
│   ├── extract_all.py          Pulls the handwritten samples off those pages
│   ├── evaluate.py             Scores a recognizer on a prompt set
│   ├── inkspike/               OneNote access, ISF decoding, rendering, scoring
│   ├── models/                 Candidate recognizers (TexTeller, Pix2Text)
│   └── tests/
│
├── samples/                  Prompt sets (problem text + expected LaTeX), no handwriting
│   ├── prompts_test.json       60 test problems
│   └── prompts_tune.json       60 tuning problems
│
├── install/
│   ├── register.ps1            Registers the add-in, writes its settings, repairs OneNote's type library
│   └── unregister.ps1          Undoes register.ps1
│
├── docs/superpowers/
│   ├── specs/                  Design spec
│   ├── plans/                  Roadmap and one plan per milestone
│   ├── spike/                  Accuracy and tuning results (aggregate numbers only)
│   └── m3-*.md, m4-*.md        Hands-on check lists for each milestone
│
└── .claude/progress.json     Milestone progress
```

**Git-ignored, local only:** `data/` (handwriting samples), `models/` (model weights, tuned model, calibration), and the Python virtual environments.

## Privacy

Handwriting never leaves the machine and never goes in this repo. Samples live in `data/`, and snippets and corrections live in `%LOCALAPPDATA%\InkMath`. Committed reports contain only aggregate numbers.

## Running the tests

| Part | Command (from the folder) | Tests |
|---|---|---|
| Reader | `reader\.venv\Scripts\python -m pytest` | 51 |
| Solver | `solver\.venv\Scripts\python -m pytest` | 276 |
| Add-in | `dotnet test addin\InkMath.slnx` | 82 |

Setup and hands-on checks: [M3 dev check](docs/superpowers/m3-dev-check.md), [M4 dev check](docs/superpowers/m4-dev-check.md).
